#!/usr/bin/env python3
"""
MCUBED Multi-Model AI Gateway
=============================

One entry point for OpenAI, Anthropic, Google Vertex AI and DeepSeek models,
built on LiteLLM (direct provider SDK calls) with OpenRouter as a second
transport for every model.

Features
--------
* Automatic fallback routing   - ordered chain of models x routes (direct, then
                                 OpenRouter), retries with backoff for transient
                                 errors, circuit breakers, quarantine.
* Token usage tracking         - every attempt is written to a SQLite ledger
                                 (tokens, cost, latency, status, errors).
* Cost optimization            - per-request cost estimation, per-request and
                                 daily budgets, task-aware tier selection,
                                 response cache, savings-vs-premium reporting.
* Balanced self-learning       - Thompson-sampling router that learns each
                                 model's quality, reliability, latency and cost
                                 per task type, balancing exploitation with a
                                 controlled amount of exploration.
* Automated process improvement- an optimizer that periodically reviews the
                                 ledger and tunes the routing policy (tier per
                                 task, route order, output-token estimates,
                                 retries, quarantines) with guardrails, a change
                                 log, and automatic rollback when quality drops.

Usage
-----
    python gateway.py chat "Explain CAP theorem" [--strategy balanced|cost|quality]
    python gateway.py feedback <request_id> 0.9
    python gateway.py improve [--dry-run]
    python gateway.py report [--days 7]
    python gateway.py models
    python gateway.py simulate --n 300          # offline demo, no API keys needed

Set GATEWAY_MOCK=1 to run without API keys (LiteLLM mock responses).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import os
import random
import re
import sqlite3
import statistics
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("mcubed.gateway")

# --------------------------------------------------------------------------- #
# LiteLLM, or a stdlib-only shim for constrained devices (Android / Termux)
# --------------------------------------------------------------------------- #
# LiteLLM pulls in native wheels (tokenizers, tiktoken, pydantic-core) that can
# be slow or impossible to build on Android. In LITE mode the gateway uses only
# the Python standard library and sends every request through OpenRouter's
# OpenAI-compatible endpoint, which still reaches OpenAI, Anthropic, Google and
# DeepSeek models. Force it with GATEWAY_LITE=1.
LITE = os.getenv("GATEWAY_LITE", "0") == "1"
if not LITE:
    try:
        import litellm  # type: ignore

        litellm.suppress_debug_info = True
    except Exception:  # noqa: BLE001
        LITE = True
if LITE:
    import types
    import urllib.error
    import urllib.request

    class _LLMError(Exception):
        def __init__(self, message: str = "", llm_provider: str = "", model: str = "", **_: Any):
            super().__init__(message)
            self.message, self.llm_provider, self.model = message, llm_provider, model

    _names = ["RateLimitError", "Timeout", "APIConnectionError", "ServiceUnavailableError",
              "InternalServerError", "AuthenticationError", "NotFoundError", "ContextWindowExceededError",
              "ContentPolicyViolationError", "BadRequestError", "PermissionDeniedError"]
    litellm = types.SimpleNamespace(**{n: type(n, (_LLMError,), {}) for n in _names})  # type: ignore
    litellm.model_cost = {}

    class _Obj(dict):
        __getattr__ = dict.get

    def _wrap(d: Any) -> Any:
        if isinstance(d, dict):
            return _Obj({k: _wrap(v) for k, v in d.items()})
        if isinstance(d, list):
            return [_wrap(x) for x in d]
        return d

    def _model_response(model: str = "", choices: Any = None, usage: Any = None, **_: Any) -> Any:
        for c in choices or []:
            c.setdefault("message", {}).setdefault("content", "")
        return _wrap({"model": model, "choices": choices or [], "usage": usage or {}, "_hidden_params": {}})

    def _token_counter(model: str = "", messages: Any = None, **_: Any) -> int:
        chars = sum(len(str(m.get("content", ""))) for m in messages or [])
        return chars // 4 + 4 * len(messages or [])

    def _lite_target(model: str) -> Optional[tuple[str, str, str, str]]:
        """(provider, base_url, env_key, wire_model) for routes LITE mode can call over plain HTTPS."""
        if model.startswith("openrouter/"):
            return "openrouter", "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY", model.split("/", 1)[1]
        if model.startswith("deepseek/"):
            return "deepseek", "https://api.deepseek.com", "DEEPSEEK_API_KEY", model.split("/", 1)[1]
        if model.startswith("openai/") or "/" not in model:
            return "openai", "https://api.openai.com/v1", "OPENAI_API_KEY", model.split("/", 1)[-1]
        return None

    def _completion(model: str, messages: list, timeout: float = 60, **kw: Any) -> Any:
        target = _lite_target(model)
        if target is None:
            raise litellm.AuthenticationError(f"LITE mode cannot call {model} directly; use its OpenRouter route",
                                              "lite", model)
        provider, base, env_key, wire_model = target
        body = {"model": wire_model, "messages": messages,
                **{k: v for k, v in kw.items() if k in ("max_tokens", "temperature", "top_p", "response_format",
                                                        "stop", "seed", "tools", "tool_choice")}}
        if provider == "openai" and "max_tokens" in body:  # current OpenAI models use max_completion_tokens
            body["max_completion_tokens"] = body.pop("max_tokens")
        headers = {"Authorization": f"Bearer {os.getenv(env_key, '')}", "Content-Type": "application/json"}
        if provider == "openrouter":
            headers["X-Title"] = "MCUBED Gateway"
        req = urllib.request.Request(f"{base}/chat/completions", data=json.dumps(body).encode(), headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.loads(r.read())
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")[:500]
            cls = {400: "BadRequestError", 401: "AuthenticationError", 402: "RateLimitError",
                   403: "PermissionDeniedError", 404: "NotFoundError", 408: "Timeout", 413: "ContextWindowExceededError",
                   429: "RateLimitError", 500: "InternalServerError", 502: "ServiceUnavailableError",
                   503: "ServiceUnavailableError"}.get(e.code, "APIConnectionError")
            if e.code == 400 and "context" in msg.lower():
                cls = "ContextWindowExceededError"
            raise getattr(litellm, cls)(msg, provider, model) from None
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise litellm.APIConnectionError(str(e), provider, model) from None
        if "error" in data:
            raise litellm.ServiceUnavailableError(str(data["error"])[:500], provider, model)
        resp = _wrap(data)
        cost = (data.get("usage") or {}).get("cost")
        resp["_hidden_params"] = {"response_cost": cost} if cost else {}
        return resp

    litellm.ModelResponse = _model_response
    litellm.token_counter = _token_counter
    litellm.completion = _completion

TIERS = ["economy", "standard", "premium"]
TIER_RANK = {t: i for i, t in enumerate(TIERS)}
TASK_TYPES = ["simple", "extraction", "summarization", "creative", "code", "reasoning"]

PROVIDER_ENV = {
    "openai": ["OPENAI_API_KEY"],
    "anthropic": ["ANTHROPIC_API_KEY"],
    "vertex_ai": ["VERTEXAI_PROJECT"],  # plus ADC / GOOGLE_APPLICATION_CREDENTIALS
    "deepseek": ["DEEPSEEK_API_KEY"],
    "openrouter": ["OPENROUTER_API_KEY"],
}

TRANSIENT_ERRORS = (
    litellm.RateLimitError,
    litellm.Timeout,
    litellm.APIConnectionError,
    litellm.ServiceUnavailableError,
    litellm.InternalServerError,
)
# Errors where retrying the same route is pointless; move to the next route.
SKIP_ERRORS = (
    litellm.AuthenticationError,
    litellm.NotFoundError,
    litellm.ContextWindowExceededError,
    litellm.ContentPolicyViolationError,
    litellm.BadRequestError,
    litellm.PermissionDeniedError,
)


# --------------------------------------------------------------------------- #
# Exceptions and data classes
# --------------------------------------------------------------------------- #
class GatewayError(Exception):
    pass


class BudgetExceeded(GatewayError):
    pass


class AllRoutesFailed(GatewayError):
    def __init__(self, attempts: list[dict]):
        self.attempts = attempts
        summary = "; ".join(f"{a['model']}: {a['error']}" for a in attempts[-5:])
        super().__init__(f"All routes failed ({len(attempts)} attempts). Last: {summary}")


@dataclass
class Route:
    model: str  # LiteLLM model id
    via: str  # "direct" | "openrouter"
    price_in: float  # USD per token
    price_out: float  # USD per token
    max_input_tokens: int

    @property
    def transport_provider(self) -> str:
        return "openrouter" if self.via == "openrouter" else ""


@dataclass
class ModelSpec:
    alias: str
    provider: str
    tier: str
    quality: int
    routes: list[Route]

    def price(self) -> tuple[float, float]:
        r = self.routes[0]
        return r.price_in, r.price_out


@dataclass
class GatewayResponse:
    request_id: str
    text: str
    model_alias: str
    model: str
    via: str
    task_type: str
    tier_policy: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    baseline_cost_usd: float
    latency_ms: int
    attempts: int
    cached: bool = False
    exploratory: bool = False
    auto_quality: float = 0.0
    finish_reason: str = ""
    compression: Optional[dict] = None
    raw: Any = field(default=None, repr=False)

    @property
    def savings_usd(self) -> float:
        return max(0.0, self.baseline_cost_usd - self.cost_usd)

    def summary(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if k not in ("raw", "text")}
        d["savings_usd"] = round(self.savings_usd, 6)
        return d


# --------------------------------------------------------------------------- #
# Pricing helpers
# --------------------------------------------------------------------------- #
def _lookup_price(model: str) -> Optional[dict]:
    """Find a model in LiteLLM's price map (tries with and without provider prefix)."""
    candidates = [model]
    if "/" in model:
        candidates.append(model.split("/", 1)[1])
    for key in candidates:
        info = litellm.model_cost.get(key)
        if info and info.get("input_cost_per_token") is not None:
            return info
    return None


def build_route(cfg: dict) -> Route:
    info = _lookup_price(cfg["model"]) or {}
    p_in = info.get("input_cost_per_token")
    p_out = info.get("output_cost_per_token")
    if p_in is None:
        p_in = cfg.get("price_in", 0.0) / 1e6
    if p_out is None:
        p_out = cfg.get("price_out", 0.0) / 1e6
    return Route(
        model=cfg["model"],
        via=cfg.get("via", "direct"),
        price_in=float(p_in),
        price_out=float(p_out),
        max_input_tokens=int(cfg.get("max_input_tokens") or info.get("max_input_tokens") or 128_000),
    )


# --------------------------------------------------------------------------- #
# Task classification and automatic quality evaluation
# --------------------------------------------------------------------------- #
_TASK_PATTERNS = {
    "code": r"\b(code|function|bug|debug|python|javascript|typescript|sql|regex|refactor|api|class|compile|stack ?trace|unit test)\b|```",
    "reasoning": r"\b(prove|proof|derive|step[- ]by[- ]step|analy[sz]e|trade-?offs?|strategy|why does|evaluate|plan|architecture|optimi[sz]e|math|calculate)\b",
    "extraction": r"\b(extract|parse|json|fields?|table|classify|label|categori[sz]e|entities)\b",
    "summarization": r"\b(summari[sz]e|summary|tl;?dr|key points|condense|recap)\b",
    "creative": r"\b(story|poem|slogan|creative|brainstorm|tagline|write a (blog|post|song)|marketing copy)\b",
}
_REFUSAL = re.compile(r"^(i'?m sorry|i cannot|i can'?t help|as an ai)", re.I)


def classify_task(messages: list[dict]) -> str:
    text = " ".join(str(m.get("content", "")) for m in messages if m.get("role") != "system").lower()
    scores = {t: len(re.findall(p, text)) for t, p in _TASK_PATTERNS.items()}
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return "reasoning" if len(text) > 4000 else "simple"
    return best


def auto_evaluate(text: str, finish_reason: str, task_type: str, wants_json: bool) -> float:
    """Cheap, model-free quality signal in [0, 1]. Explicit feedback overrides it."""
    if not text or not text.strip():
        return 0.0
    if _REFUSAL.match(text.strip()):
        return 0.3
    score = 0.75
    if finish_reason == "length":
        score = 0.4
    if wants_json or task_type == "extraction" and text.strip().startswith(("{", "[")):
        try:
            json.loads(text.strip().strip("`").removeprefix("json"))
            score = max(score, 0.85)
        except Exception:
            score = min(score, 0.35) if wants_json else score
    if task_type in ("code", "reasoning") and len(text) < 40:
        score = min(score, 0.5)
    return score


# --------------------------------------------------------------------------- #
# Storage: usage ledger, feedback, learned policy, improvement log
# --------------------------------------------------------------------------- #
SCHEMA = """
CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL, day TEXT, request_id TEXT, alias TEXT, provider TEXT, tier TEXT,
    model TEXT, via TEXT, task_type TEXT, status TEXT, error_type TEXT, error TEXT,
    prompt_tokens INTEGER DEFAULT 0, completion_tokens INTEGER DEFAULT 0,
    cost_usd REAL DEFAULT 0, baseline_cost_usd REAL DEFAULT 0, latency_ms INTEGER DEFAULT 0,
    retry_index INTEGER DEFAULT 0, exploratory INTEGER DEFAULT 0, cached INTEGER DEFAULT 0,
    auto_quality REAL, finish_reason TEXT,
    original_tokens INTEGER DEFAULT 0, compressed INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS attempts_daily (
    day TEXT, ts REAL, alias TEXT, provider TEXT, tier TEXT, via TEXT, task_type TEXT, status TEXT,
    n INTEGER, cached_n INTEGER, prompt_tokens INTEGER, completion_tokens INTEGER, cost_usd REAL,
    baseline_cost_usd REAL, latency_sum REAL, quality_sum REAL, quality_n INTEGER,
    original_tokens INTEGER, compressed_n INTEGER,
    PRIMARY KEY (day, alias, via, task_type, status)
);
CREATE INDEX IF NOT EXISTS ix_attempts_alias ON attempts(alias, task_type, ts);
CREATE INDEX IF NOT EXISTS ix_attempts_req ON attempts(request_id);
CREATE INDEX IF NOT EXISTS ix_attempts_day ON attempts(day);
CREATE TABLE IF NOT EXISTS feedback (
    request_id TEXT PRIMARY KEY, score REAL, source TEXT, note TEXT, ts REAL
);
CREATE TABLE IF NOT EXISTS policy (
    key TEXT PRIMARY KEY, value TEXT, updated REAL
);
CREATE TABLE IF NOT EXISTS improvements (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, kind TEXT, target TEXT,
    old_value TEXT, new_value TEXT, reason TEXT, baseline_quality REAL,
    baseline_cost REAL, baseline_n INTEGER, status TEXT DEFAULT 'active'
);
"""


USAGE_VIEW = """
CREATE TEMP VIEW IF NOT EXISTS usage_all AS
  SELECT day, ts, alias, provider, tier, via, task_type, status, 1 AS n, cached AS cached_n,
         prompt_tokens, completion_tokens, cost_usd, baseline_cost_usd, latency_ms AS latency_sum,
         original_tokens, compressed AS compressed_n
  FROM attempts
  UNION ALL
  SELECT day, ts, alias, provider, tier, via, task_type, status, n, cached_n, prompt_tokens,
         completion_tokens, cost_usd, baseline_cost_usd, latency_sum, original_tokens, compressed_n
  FROM attempts_daily;
"""


class Store:
    def __init__(self, path: str, storage_cfg: Optional[dict] = None):
        self.path = path
        self.cfg = storage_cfg or {}
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        # forward-compatible migration for databases created by older versions
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(attempts)")}
        for col, ddl in (("original_tokens", "INTEGER DEFAULT 0"), ("compressed", "INTEGER DEFAULT 0")):
            if col not in cols:
                self.conn.execute(f"ALTER TABLE attempts ADD COLUMN {col} {ddl}")
        self.conn.executescript(USAGE_VIEW)
        self.conn.commit()

    # -- self data compression (storage) ------------------------------------ #
    def size_mb(self) -> float:
        try:
            return os.path.getsize(self.path) / 1e6
        except OSError:
            return 0.0

    def storage_stats(self) -> dict:
        raw = self.query("SELECT COUNT(*) c, MIN(ts) t FROM attempts")[0]
        agg = self.query("SELECT COUNT(*) c, COALESCE(SUM(n),0) s FROM attempts_daily")[0]
        return {"db_mb": round(self.size_mb(), 3), "raw_rows": raw["c"], "aggregated_rows": agg["c"],
                "attempts_in_aggregates": agg["s"], "oldest_raw_ts": raw["t"],
                "max_db_mb": self.cfg.get("max_db_mb", 50), "max_raw_rows": self.cfg.get("max_raw_rows", 200_000),
                "retain_raw_days": self.cfg.get("retain_raw_days", 30)}

    def compaction_needed(self) -> bool:
        st = self.storage_stats()
        return st["db_mb"] > st["max_db_mb"] or st["raw_rows"] > st["max_raw_rows"]

    def compact(self, retain_days: Optional[float] = None, force: bool = False) -> dict:
        """
        Roll raw attempt rows older than `retain_days` into per-day aggregates, delete
        them, and VACUUM. Runs automatically only when the DB exceeds its size/row
        limits; if still over the limit it halves the retention window (floor 1 day).
        Totals, costs and token counts are preserved exactly; only per-request detail
        for old rows is dropped (the learner only needs the recent window anyway).
        """
        if not force and not self.compaction_needed():
            return {"compacted": False, "reason": "within limits", **self.storage_stats()}
        before = self.storage_stats()
        days = float(retain_days if retain_days is not None else self.cfg.get("retain_raw_days", 30))
        moved_total = 0
        while True:
            cutoff = time.time() - days * 86400
            with self._lock:
                self.conn.execute(
                    """INSERT INTO attempts_daily
                       SELECT a.day, MIN(a.ts), a.alias, MAX(a.provider), MAX(a.tier), a.via, a.task_type, a.status,
                              COUNT(*), SUM(a.cached), SUM(a.prompt_tokens), SUM(a.completion_tokens), SUM(a.cost_usd),
                              SUM(a.baseline_cost_usd), SUM(a.latency_ms),
                              SUM(COALESCE(f.score, a.auto_quality)), COUNT(COALESCE(f.score, a.auto_quality)),
                              SUM(a.original_tokens), SUM(a.compressed)
                       FROM attempts a LEFT JOIN feedback f ON f.request_id=a.request_id
                       WHERE a.ts < ? GROUP BY a.day, a.alias, a.via, a.task_type, a.status
                       ON CONFLICT(day, alias, via, task_type, status) DO UPDATE SET
                         n=n+excluded.n, cached_n=cached_n+excluded.cached_n,
                         prompt_tokens=prompt_tokens+excluded.prompt_tokens,
                         completion_tokens=completion_tokens+excluded.completion_tokens,
                         cost_usd=cost_usd+excluded.cost_usd, baseline_cost_usd=baseline_cost_usd+excluded.baseline_cost_usd,
                         latency_sum=latency_sum+excluded.latency_sum, quality_sum=quality_sum+excluded.quality_sum,
                         quality_n=quality_n+excluded.quality_n, original_tokens=original_tokens+excluded.original_tokens,
                         compressed_n=compressed_n+excluded.compressed_n""", (cutoff,))
                moved = self.conn.execute("DELETE FROM attempts WHERE ts < ?", (cutoff,)).rowcount
                self.conn.execute("DELETE FROM feedback WHERE request_id NOT IN (SELECT DISTINCT request_id FROM attempts)")
                self.conn.commit()
                self.conn.execute("VACUUM")
            moved_total += moved
            st = self.storage_stats()
            over = st["db_mb"] > st["max_db_mb"] or st["raw_rows"] > st["max_raw_rows"]
            if not over or days <= 1:
                break
            days = max(1.0, days / 2)
        after = self.storage_stats()
        return {"compacted": True, "rows_aggregated": moved_total, "retain_days_used": days,
                "db_mb_before": before["db_mb"], "db_mb_after": after["db_mb"], **after}

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self.conn.execute(sql, params)
            self.conn.commit()
            return cur

    def query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self.conn.execute(sql, params).fetchall()

    def log_attempt(self, **row) -> None:
        now = time.time()
        row.setdefault("ts", now)
        row.setdefault("day", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
        cols = ",".join(row)
        self.execute(f"INSERT INTO attempts ({cols}) VALUES ({','.join('?' * len(row))})", tuple(row.values()))

    def spent_today(self) -> float:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        r = self.query("SELECT COALESCE(SUM(cost_usd),0) s FROM usage_all WHERE day=?", (day,))
        return float(r[0]["s"])

    def get_policy(self, key: str, default: Any = None) -> Any:
        r = self.query("SELECT value FROM policy WHERE key=?", (key,))
        return json.loads(r[0]["value"]) if r else default

    def set_policy(self, key: str, value: Any) -> None:
        self.execute(
            "INSERT INTO policy(key,value,updated) VALUES(?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated=excluded.updated",
            (key, json.dumps(value), time.time()),
        )

    def request_count(self) -> int:
        raw = int(self.query("SELECT COUNT(DISTINCT request_id) c FROM attempts")[0]["c"])
        agg = int(self.query("SELECT COALESCE(SUM(n),0) c FROM attempts_daily WHERE status='ok'")[0]["c"])
        return raw + agg


# --------------------------------------------------------------------------- #
# Balanced self-learning router
# --------------------------------------------------------------------------- #
@dataclass
class ArmStats:
    n: int = 0  # successful responses observed
    q_sum: float = 0.0  # sum of quality scores
    ok: int = 0  # successful attempts
    fail: int = 0  # failed attempts
    latency_ms: float = 0.0
    out_tokens: float = 0.0


class Learner:
    """
    Learns per (model alias, task type):
      quality     ~ Beta(prior + sum q, prior + sum (1-q))   (feedback > judge > auto-eval)
      reliability ~ Beta(1 + ok, 1 + fail)
      latency, output tokens -> recency-windowed means
    The 'balanced' strategy draws Thompson samples and maximises
      utility = w_q * quality * reliability - w_c * cost_norm - w_l * latency_norm
    which naturally balances exploitation and exploration; an extra
    explore_rate lets the router probe one tier below the current policy so the
    optimizer has evidence for safe downgrades.
    """

    def __init__(self, store: Store, cfg: dict):
        self.store = store
        self.cfg = cfg
        self._cache: dict[tuple[str, str], ArmStats] = {}
        self._cache_ts = 0.0
        self.rng = random.Random()

    def invalidate(self) -> None:
        self._cache_ts = 0.0

    def _refresh(self) -> None:
        if time.time() - self._cache_ts < 5:
            return
        window = int(self.cfg.get("recency_window", 200))
        rows = self.store.query(
            """
            SELECT alias, task_type, status, latency_ms, completion_tokens, quality FROM (
              SELECT a.alias, a.task_type, a.status, a.latency_ms, a.completion_tokens,
                     COALESCE(f.score, a.auto_quality) AS quality,
                     ROW_NUMBER() OVER (PARTITION BY a.alias, a.task_type ORDER BY a.ts DESC) rn
              FROM attempts a LEFT JOIN feedback f ON f.request_id = a.request_id
              WHERE a.cached = 0
            ) WHERE rn <= ?
            """,
            (window,),
        )
        stats: dict[tuple[str, str], ArmStats] = {}
        lat: dict[tuple, list] = {}
        out: dict[tuple, list] = {}
        for r in rows:
            k = (r["alias"], r["task_type"])
            s = stats.setdefault(k, ArmStats())
            if r["status"] == "ok":
                s.ok += 1
                s.n += 1
                s.q_sum += float(r["quality"] if r["quality"] is not None else 0.75)
                lat.setdefault(k, []).append(r["latency_ms"] or 0)
                out.setdefault(k, []).append(r["completion_tokens"] or 0)
            else:
                s.fail += 1
        for k, s in stats.items():
            s.latency_ms = statistics.fmean(lat[k]) if lat.get(k) else 0.0
            s.out_tokens = statistics.fmean(out[k]) if out.get(k) else 0.0
        self._cache = stats
        self._cache_ts = time.time()

    def stats(self, alias: str, task_type: str) -> ArmStats:
        self._refresh()
        return self._cache.get((alias, task_type), ArmStats())

    def all_stats(self) -> dict[tuple[str, str], ArmStats]:
        self._refresh()
        return dict(self._cache)

    def expected_quality(self, spec: ModelSpec, task_type: str) -> float:
        s = self.stats(spec.alias, task_type)
        k = float(self.cfg.get("prior_strength", 4))
        prior = spec.quality / 10.0
        return (prior * k + s.q_sum) / (k + s.n)

    def sample_utility(self, spec: ModelSpec, task_type: str, est_cost: float,
                       max_cost: float, max_latency: float) -> float:
        s = self.stats(spec.alias, task_type)
        k = float(self.cfg.get("prior_strength", 4))
        prior = spec.quality / 10.0
        a = 1 + prior * k + s.q_sum
        b = 1 + (1 - prior) * k + (s.n - s.q_sum)
        q = self.rng.betavariate(a, b)
        rel = self.rng.betavariate(1 + s.ok + 3, 1 + s.fail)  # optimistic prior
        w = self.cfg.get("weights", {})
        cost_norm = math.log1p(est_cost * 1e4) / math.log1p(max_cost * 1e4) if max_cost > 0 else 0
        lat_norm = (s.latency_ms / max_latency) if max_latency > 0 and s.latency_ms else 0.3
        return (w.get("quality", 1.0) * q * rel
                - w.get("cost", 0.35) * cost_norm
                - w.get("latency", 0.15) * lat_norm)


# --------------------------------------------------------------------------- #
# Self data compression (context)
# --------------------------------------------------------------------------- #
class Compressor:
    """
    Shrinks a conversation only when needed: when it would overflow every
    eligible model's context window, exceed the per-request cost cap, or pass
    the learned trigger threshold. Stages run cheapest-first and stop as soon
    as the target is met:

      1. normalize  - collapse whitespace, blank-line runs, duplicate lines
      2. summarize  - fold older turns into one summary note (economy model;
                      skipped in mock mode) or drop them with a marker
      3. truncate   - head/tail trim the largest remaining messages

    System messages and the most recent turns are always preserved.
    """

    def __init__(self, gw: "Gateway"):
        self.gw = gw

    @property
    def cfg(self) -> dict:
        return self.gw.defaults.get("compression", {})

    def tokens(self, messages: list[dict]) -> int:
        return self.gw._count_tokens(messages)

    @staticmethod
    def _normalize(text: str) -> str:
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r" *\n *", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        out, prev = [], None
        for line in text.split("\n"):
            if line and line == prev:
                continue
            out.append(line)
            prev = line
        return "\n".join(out).strip()

    @staticmethod
    def _trim(text: str, max_chars: int) -> str:
        if len(text) <= max_chars:
            return text
        head = int(max_chars * 0.6)
        tail = max_chars - head
        cut = len(text) - head - tail
        return f"{text[:head]}\n[... {cut // 4} tokens trimmed by gateway ...]\n{text[-tail:]}"

    def _summarize(self, older: list[dict]) -> Optional[str]:
        if self.gw.mock or not self.cfg.get("summarize_with_model", True):
            return None
        transcript = "\n".join(f"{m['role']}: {m.get('content', '')}" for m in older)[:400_000]
        try:
            r = self.gw.chat(
                [{"role": "system", "content": "Summarize this conversation history for another AI. Keep facts, "
                                               "decisions, names, numbers, code identifiers and open questions. "
                                               "Be terse."},
                 {"role": "user", "content": transcript}],
                tier="economy", strategy="cost", use_cache=False, task_type="summarization",
                _allow_compress=False, max_tokens=int(self.cfg.get("summary_max_tokens", 800)))
            return r.text
        except Exception as e:  # noqa: BLE001
            log.warning("summary compression failed, falling back to drop: %s", e)
            return None

    def compress(self, messages: list[dict], target_tokens: int) -> tuple[list[dict], dict]:
        original = self.tokens(messages)
        stages: list[str] = []
        msgs = [dict(m) for m in messages]

        # 1. normalize
        for m in msgs:
            if isinstance(m.get("content"), str):
                m["content"] = self._normalize(m["content"])
        stages.append("normalize")

        # 2. summarize / drop older turns
        keep = int(self.gw.compression_keep_turns())
        if self.tokens(msgs) > target_tokens:
            system = [m for m in msgs if m.get("role") == "system"]
            convo = [m for m in msgs if m.get("role") != "system"]
            if len(convo) > keep:
                older, recent = convo[:-keep], convo[-keep:]
                summary = self._summarize(older)
                note = (f"Summary of {len(older)} earlier messages:\n{summary}" if summary
                        else f"[{len(older)} earlier messages omitted by gateway to fit context/budget]")
                msgs = system + [{"role": "system", "content": note}] + recent
                stages.append("summarize" if summary else "drop_older")

        # 3. head/tail truncate the largest messages until under target
        guard = 0
        while self.tokens(msgs) > target_tokens and guard < 20:
            guard += 1
            idx = max(range(len(msgs)), key=lambda i: len(str(msgs[i].get("content", ""))))
            content = str(msgs[idx].get("content", ""))
            excess_chars = (self.tokens(msgs) - target_tokens) * 4 + 200
            new_len = max(400, len(content) - excess_chars)
            if new_len >= len(content):
                break
            msgs[idx]["content"] = self._trim(content, new_len)
            if "truncate" not in stages:
                stages.append("truncate")

        final = self.tokens(msgs)
        return msgs, {"original_tokens": original, "compressed_tokens": final,
                      "ratio": round(final / original, 3) if original else 1.0, "stages": stages}


# --------------------------------------------------------------------------- #
# Circuit breaker
# --------------------------------------------------------------------------- #
class CircuitBreaker:
    def __init__(self, threshold: int, cooldown_s: float):
        self.threshold = threshold
        self.cooldown = cooldown_s
        self.failures: dict[str, int] = {}
        self.opened_at: dict[str, float] = {}

    def available(self, key: str) -> bool:
        t = self.opened_at.get(key)
        if t is None:
            return True
        if time.time() - t > self.cooldown:  # half-open: allow one probe
            self.opened_at.pop(key, None)
            self.failures[key] = self.threshold - 1
            return True
        return False

    def success(self, key: str) -> None:
        self.failures[key] = 0
        self.opened_at.pop(key, None)

    def failure(self, key: str) -> None:
        self.failures[key] = self.failures.get(key, 0) + 1
        if self.failures[key] >= self.threshold:
            self.opened_at[key] = time.time()
            log.warning("circuit opened for %s", key)


# --------------------------------------------------------------------------- #
# Automated process improvement
# --------------------------------------------------------------------------- #
class Optimizer:
    """
    Reviews the ledger and tunes the live routing policy. Every change is
    logged to `improvements` with a baseline; later runs evaluate active changes
    and roll them back automatically if quality dropped.

    Rules (all require min_samples of evidence and move one step at a time):
      1. tier_policy      lower a task's tier when the cheaper tier meets the
                          quality target; raise it when the current tier misses.
      2. route_order      put OpenRouter first for a model when it is clearly
                          more reliable than the direct provider.
      3. output_tokens    calibrate expected output tokens per task (p75) so
                          cost estimates and budget checks are accurate.
      4. retries          cut per-route retries when retries rarely succeed.
      5. quarantine       temporarily pull models whose reliability collapsed.
      6. rollback         revert active changes whose follow-up quality fell.
    """

    def __init__(self, gw: "Gateway"):
        self.gw = gw
        self.store = gw.store
        self.cfg = gw.defaults.get("improvement", {})

    # -- metrics helpers ---------------------------------------------------- #
    def _task_metrics(self, task_type: str, since: float = 0.0, tier: Optional[str] = None) -> tuple[float, float, int]:
        sql = """SELECT COALESCE(f.score, a.auto_quality) q, a.cost_usd c FROM attempts a
                 LEFT JOIN feedback f ON f.request_id=a.request_id
                 WHERE a.status='ok' AND a.cached=0 AND a.task_type=? AND a.ts>=?"""
        params: list = [task_type, since]
        if tier:
            sql += " AND a.tier=?"
            params.append(tier)
        rows = self.store.query(sql, tuple(params))
        if not rows:
            return 0.0, 0.0, 0
        qs = [float(r["q"] if r["q"] is not None else 0.75) for r in rows]
        cs = [float(r["c"] or 0) for r in rows]
        return statistics.fmean(qs), statistics.fmean(cs), len(rows)

    def _record(self, kind: str, target: str, old: Any, new: Any, reason: str,
                task_type: Optional[str], apply: bool, changes: list) -> None:
        bq, bc, bn = self._task_metrics(task_type) if task_type else (0.0, 0.0, 0)
        changes.append({"kind": kind, "target": target, "old": old, "new": new, "reason": reason})
        if apply:
            self.store.execute(
                "INSERT INTO improvements(ts,kind,target,old_value,new_value,reason,baseline_quality,baseline_cost,"
                "baseline_n,status) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (time.time(), kind, target, json.dumps(old), json.dumps(new), reason, bq, bc, bn,
                 "active" if kind == "tier_policy" else "applied"),
            )

    # -- main entry --------------------------------------------------------- #
    def run(self, apply: bool = True) -> list[dict]:
        changes: list[dict] = []
        min_n = int(self.cfg.get("min_samples", 20))
        target = float(self.cfg.get("target_quality", 0.72))
        margin = float(self.cfg.get("upgrade_margin", 0.15))

        # 6. rollback first, so we evaluate before stacking new changes
        self._rollbacks(apply, changes, min_n)

        # 1. tier policy per task type
        policy = self.gw.task_policy()
        recently_changed = {
            r["target"] for r in self.store.query(
                "SELECT target FROM improvements WHERE kind='tier_policy' AND status='active'")
        }
        for task in TASK_TYPES:
            if task in recently_changed:
                continue  # wait until the active change is evaluated
            cur = policy.get(task, "standard")
            rank = TIER_RANK[cur]
            q_cur, c_cur, n_cur = self._task_metrics(task, tier=cur)
            if rank > 0:
                lower = TIERS[rank - 1]
                q_low, c_low, n_low = self._task_metrics(task, tier=lower)
                if n_low >= min_n and q_low >= target and (n_cur == 0 or q_low >= q_cur - 0.05):
                    new = dict(policy, **{task: lower})
                    reason = (f"{lower} tier quality {q_low:.2f} (n={n_low}) meets target {target}; "
                              f"avg cost {c_low:.5f} vs {c_cur:.5f}")
                    self._record("tier_policy", task, cur, lower, reason, task, apply, changes)
                    if apply:
                        self.store.set_policy("task_policy", new)
                    policy = new
                    continue
            if rank < len(TIERS) - 1 and n_cur >= min_n and q_cur < target - margin:
                higher = TIERS[rank + 1]
                new = dict(policy, **{task: higher})
                reason = f"{cur} tier quality {q_cur:.2f} (n={n_cur}) below target {target}-{margin}"
                self._record("tier_policy", task, cur, higher, reason, task, apply, changes)
                if apply:
                    self.store.set_policy("task_policy", new)
                policy = new

        # 2. route order per model
        order = self.store.get_policy("route_order", {})
        for spec in self.gw.models.values():
            rows = self.store.query(
                "SELECT via, SUM(status='ok') ok, COUNT(*) n FROM attempts WHERE alias=? AND cached=0 GROUP BY via",
                (spec.alias,))
            rel = {r["via"]: (r["ok"] / r["n"], r["n"]) for r in rows}
            if "direct" in rel and "openrouter" in rel:
                (rd, nd), (ro, no) = rel["direct"], rel["openrouter"]
                cur_first = order.get(spec.alias, "direct")
                if nd >= 10 and no >= 5:
                    want = "openrouter" if ro - rd > 0.2 else ("direct" if rd >= ro else cur_first)
                    if want != cur_first:
                        self._record("route_order", spec.alias, cur_first, want,
                                     f"reliability direct={rd:.2f} (n={nd}) openrouter={ro:.2f} (n={no})",
                                     None, apply, changes)
                        order[spec.alias] = want
        if apply:
            self.store.set_policy("route_order", order)

        # 3. expected output tokens per task (p75 of observed)
        est = self.store.get_policy("expected_output_tokens", {})
        for task in TASK_TYPES:
            rows = self.store.query(
                "SELECT completion_tokens t FROM attempts WHERE status='ok' AND cached=0 AND task_type=? "
                "ORDER BY ts DESC LIMIT 200", (task,))
            toks = sorted(int(r["t"] or 0) for r in rows)
            if len(toks) >= 10:
                p75 = toks[int(0.75 * (len(toks) - 1))]
                old = est.get(task, self.gw.defaults.get("expected_output_tokens", 600))
                if old and abs(p75 - old) / old > 0.25:
                    self._record("output_tokens", task, old, p75, f"p75 of last {len(toks)} responses", None, apply, changes)
                    est[task] = p75
        if apply:
            self.store.set_policy("expected_output_tokens", est)

        # 4. retries: if retries almost never rescue a route, stop wasting time on them
        r = self.store.query("SELECT SUM(status='ok') ok, COUNT(*) n FROM attempts WHERE retry_index>0")[0]
        retry_n, retry_ok = int(r["n"] or 0), int(r["ok"] or 0)
        cur_retries = int(self.store.get_policy("max_retries_per_route", self.gw.defaults.get("max_retries_per_route", 2)))
        if retry_n >= min_n:
            rate = retry_ok / retry_n
            new_r = cur_retries
            if rate < 0.2 and cur_retries > 0:
                new_r = cur_retries - 1
            elif rate > 0.6 and cur_retries < 3:
                new_r = cur_retries + 1
            if new_r != cur_retries:
                self._record("retries", "max_retries_per_route", cur_retries, new_r,
                             f"retry success rate {rate:.2f} over {retry_n} retries", None, apply, changes)
                if apply:
                    self.store.set_policy("max_retries_per_route", new_r)

        # 7. compression tuning: compress less if it hurts quality, more if it is harmless
        rows = self.store.query(
            """SELECT a.compressed c, AVG(COALESCE(f.score, a.auto_quality)) q, COUNT(*) n FROM attempts a
               LEFT JOIN feedback f ON f.request_id=a.request_id
               WHERE a.status='ok' AND a.cached=0 GROUP BY a.compressed""")
        cq = {r["c"]: (float(r["q"] or 0), int(r["n"])) for r in rows}
        if 1 in cq and 0 in cq and cq[1][1] >= min_n:
            (q_c, n_c), (q_u, _) = cq[1], cq[0]
            trig = self.gw.compression_trigger()
            keep = self.gw.compression_keep_turns()
            if q_c < q_u - 0.10:
                new_t, new_k = int(trig * 1.25), min(keep + 2, 20)
                why = f"compressed quality {q_c:.2f} < uncompressed {q_u:.2f} (n={n_c}); compress less"
            elif q_c >= q_u - 0.03:
                new_t, new_k = max(8_000, int(trig * 0.85)), keep
                why = f"compressed quality {q_c:.2f} ~ uncompressed {q_u:.2f} (n={n_c}); compress earlier to save cost"
            else:
                new_t, new_k = trig, keep
                why = ""
            if new_t != trig or new_k != keep:
                self._record("compression", "trigger_tokens/keep_turns", [trig, keep], [new_t, new_k], why,
                             None, apply, changes)
                if apply:
                    self.store.set_policy("compression_trigger_tokens", new_t)
                    self.store.set_policy("compression_keep_turns", new_k)

        # 5. quarantine models whose recent reliability collapsed
        q_rel = float(self.cfg.get("quarantine_reliability", 0.5))
        q_secs = float(self.cfg.get("quarantine_s", 3600))
        quarantine = {k: v for k, v in self.store.get_policy("quarantine", {}).items() if v > time.time()}
        for spec in self.gw.models.values():
            rows = self.store.query(
                "SELECT status FROM attempts WHERE alias=? AND cached=0 ORDER BY ts DESC LIMIT 20", (spec.alias,))
            if len(rows) >= 20:
                rel = sum(r["status"] == "ok" for r in rows) / len(rows)
                if rel < q_rel and spec.alias not in quarantine:
                    self._record("quarantine", spec.alias, None, int(q_secs),
                                 f"reliability {rel:.2f} over last 20 attempts", None, apply, changes)
                    quarantine[spec.alias] = time.time() + q_secs
        if apply:
            self.store.set_policy("quarantine", quarantine)
            self.store.set_policy("last_improve_at_count", self.store.request_count())
            self.gw.learner.invalidate()
        return changes

    def _rollbacks(self, apply: bool, changes: list, min_n: int) -> None:
        drop = float(self.cfg.get("rollback_drop", 0.10))
        active = self.store.query("SELECT * FROM improvements WHERE kind='tier_policy' AND status='active'")
        for imp in active:
            task = imp["target"]
            q_after, c_after, n_after = self._task_metrics(task, since=imp["ts"])
            if n_after < min_n:
                continue
            if imp["baseline_n"] and q_after < imp["baseline_quality"] - drop:
                policy = self.gw.task_policy()
                old = json.loads(imp["old_value"])
                changes.append({"kind": "rollback", "target": task, "old": policy.get(task), "new": old,
                                "reason": f"quality fell {imp['baseline_quality']:.2f} -> {q_after:.2f}"})
                if apply:
                    policy[task] = old
                    self.store.set_policy("task_policy", policy)
                    self.store.execute("UPDATE improvements SET status='rolled_back' WHERE id=?", (imp["id"],))
            elif apply:
                self.store.execute("UPDATE improvements SET status='kept' WHERE id=?", (imp["id"],))
                changes.append({"kind": "confirm", "target": task, "old": None, "new": None,
                                "reason": f"kept: quality {q_after:.2f} vs baseline {imp['baseline_quality']:.2f}, "
                                          f"cost {c_after:.5f} vs {imp['baseline_cost']:.5f}"})


# --------------------------------------------------------------------------- #
# Gateway
# --------------------------------------------------------------------------- #
class Gateway:
    def __init__(self, config_path: str = "models.json", db_path: str = "gateway_usage.db",
                 mock: Optional[bool] = None):
        cfg = json.loads(Path(config_path).read_text())
        self.defaults: dict = cfg.get("defaults", {})
        self._default_task_policy: dict = cfg.get("task_policy", {})
        self.models: dict[str, ModelSpec] = {}
        for m in cfg["models"]:
            self.models[m["alias"]] = ModelSpec(
                alias=m["alias"], provider=m["provider"], tier=m["tier"], quality=int(m.get("quality", 5)),
                routes=[build_route(r) for r in m["routes"]],
            )
            # routes with unknown prices inherit from a priced sibling (same model, other transport)
            spec = self.models[m["alias"]]
            priced = [r for r in spec.routes if r.price_in or r.price_out]
            for r in spec.routes:
                if not (r.price_in or r.price_out) and priced:
                    r.price_in, r.price_out = priced[0].price_in, priced[0].price_out
        self.mock = bool(int(os.getenv("GATEWAY_MOCK", "0"))) if mock is None else mock
        self.mock_fail: set[str] = set(filter(None, os.getenv("GATEWAY_MOCK_FAIL", "").split(",")))
        self.mock_hook = None  # optional callable(route, messages) -> (text, finish_reason) for simulations
        self.store = Store(db_path, self.defaults.get("storage", {}))
        self.learner = Learner(self.store, self.defaults.get("learning", {}))
        self.breaker = CircuitBreaker(int(self.defaults.get("circuit_breaker_failures", 3)),
                                      float(self.defaults.get("circuit_breaker_cooldown_s", 120)))
        self.optimizer = Optimizer(self)
        self.compressor = Compressor(self)
        self._cache: dict[str, tuple[float, GatewayResponse]] = {}
        self._baseline_spec = max(self.models.values(), key=lambda s: s.price()[0] + s.price()[1])

    # -- policy accessors (learned values override config) ------------------ #
    def task_policy(self) -> dict:
        return dict(self._default_task_policy, **self.store.get_policy("task_policy", {}))

    def expected_output_tokens(self, task_type: str) -> int:
        learned = self.store.get_policy("expected_output_tokens", {})
        return int(learned.get(task_type, self.defaults.get("expected_output_tokens", 600)))

    def compression_trigger(self) -> int:
        return int(self.store.get_policy("compression_trigger_tokens",
                                         self.defaults.get("compression", {}).get("trigger_tokens", 120_000)))

    def compression_keep_turns(self) -> int:
        return int(self.store.get_policy("compression_keep_turns",
                                         self.defaults.get("compression", {}).get("keep_last_turns", 6)))

    def _compression_target(self, p_tok: int, task_type: str, tier: Optional[str], max_cost: float,
                            models: Optional[list[str]]) -> Optional[int]:
        """Return a token target if compression is needed for this request, else None."""
        if not self.defaults.get("compression", {}).get("enabled", True):
            return None
        out_tok = self.expected_output_tokens(task_type)
        min_rank = TIER_RANK[tier or self.task_policy().get(task_type, "standard")]
        routes = [(s, r) for s in self.models.values() if (not models or s.alias in models)
                  and TIER_RANK[s.tier] >= min_rank for r in s.routes if self._route_available(s, r)]
        if not routes:
            return None
        targets = []
        trigger = self.compression_trigger()
        if p_tok > trigger:
            targets.append(int(trigger * 0.75))
        max_ctx = max(r.max_input_tokens for _, r in routes)
        if p_tok + out_tok > max_ctx * 0.95:
            targets.append(int(max_ctx * 0.9) - out_tok)
        cheapest = min(routes, key=lambda sr: sr[1].price_in)[1]
        if self._cost(cheapest, p_tok, out_tok) > max_cost and cheapest.price_in > 0:
            targets.append(int((max_cost - out_tok * cheapest.price_out) / cheapest.price_in * 0.95))
        targets = [t for t in targets if t > 0]
        return min(targets) if targets else None

    def max_retries(self) -> int:
        return int(self.store.get_policy("max_retries_per_route", self.defaults.get("max_retries_per_route", 2)))

    # -- availability ------------------------------------------------------- #
    def _route_available(self, spec: ModelSpec, route: Route) -> bool:
        if LITE and route.via != "openrouter" and spec.provider not in ("openai", "deepseek"):
            return False  # LITE (Android) mode: only OpenAI-compatible HTTPS APIs can be called directly
        if self.mock:
            return True
        prov = "openrouter" if route.via == "openrouter" else spec.provider
        return all(os.getenv(k) for k in PROVIDER_ENV.get(prov, []))

    def _ordered_routes(self, spec: ModelSpec) -> list[Route]:
        first = self.store.get_policy("route_order", {}).get(spec.alias, "direct")
        return sorted(spec.routes, key=lambda r: 0 if r.via == first else 1)

    # -- cost estimation ---------------------------------------------------- #
    @staticmethod
    def _count_tokens(messages: list[dict]) -> int:
        try:
            return int(litellm.token_counter(model="gpt-4o", messages=messages))
        except Exception:
            return sum(len(str(m.get("content", ""))) for m in messages) // 4 + 4 * len(messages)

    @staticmethod
    def _cost(route: Route, p_tok: int, c_tok: int) -> float:
        return p_tok * route.price_in + c_tok * route.price_out

    # -- candidate selection ------------------------------------------------ #
    def plan(self, messages: list[dict], strategy: str, task_type: str, tier: Optional[str],
             max_cost: float, models: Optional[list[str]] = None) -> tuple[list[tuple[ModelSpec, Route, bool]], str, int, int]:
        p_tok = self._count_tokens(messages)
        out_tok = self.expected_output_tokens(task_type)
        policy_tier = tier or self.task_policy().get(task_type, "standard")
        min_rank = TIER_RANK[policy_tier]
        quarantine = {k for k, v in self.store.get_policy("quarantine", {}).items() if v > time.time()}

        lcfg = self.defaults.get("learning", {})
        explore_down = (strategy == "balanced" and tier is None and min_rank > 0
                        and self.learner.rng.random() < float(lcfg.get("explore_rate", 0.1)))

        pool: list[tuple[ModelSpec, float, bool]] = []
        for spec in self.models.values():
            if models and spec.alias not in models:
                continue
            if spec.alias in quarantine and not models:
                continue
            rank = TIER_RANK[spec.tier]
            exploratory = explore_down and rank == min_rank - 1
            if rank < min_rank and not exploratory:
                continue
            routes = [r for r in spec.routes if self._route_available(spec, r) and p_tok < r.max_input_tokens]
            if not routes:
                continue
            est = min(self._cost(r, p_tok, out_tok) for r in routes)
            if est > max_cost:
                continue
            pool.append((spec, est, exploratory))

        if not pool:
            raise GatewayError(
                f"No eligible models (tier>={policy_tier}, est. cost<={max_cost}). "
                "Check API keys, budgets, or pass --tier / --max-cost.")

        if strategy == "cost":
            pool.sort(key=lambda x: (x[1], -self.learner.expected_quality(x[0], task_type)))
        elif strategy == "quality":
            pool.sort(key=lambda x: (-self.learner.expected_quality(x[0], task_type), x[1]))
        else:  # balanced: Thompson sampling over learned quality, reliability, cost, latency
            max_c = max(e for _, e, _ in pool) or 1e-9
            max_l = max((self.learner.stats(s.alias, task_type).latency_ms for s, _, _ in pool), default=0) or 1.0
            scored = [(self.learner.sample_utility(s, task_type, e, max_c, max_l), s, e, x) for s, e, x in pool]
            scored.sort(key=lambda t: -t[0])
            # an exploratory probe goes first so it actually gets traffic
            if explore_down:
                scored.sort(key=lambda t: 0 if t[3] else 1)
            pool = [(s, e, x) for _, s, e, x in scored]

        chain: list[tuple[ModelSpec, Route, bool]] = []
        for spec, _, exploratory in pool:
            for r in self._ordered_routes(spec):
                if self._route_available(spec, r) and p_tok < r.max_input_tokens:
                    chain.append((spec, r, exploratory))
        return chain, policy_tier, p_tok, out_tok

    # -- low-level call ----------------------------------------------------- #
    def _call(self, route: Route, messages: list[dict], **kw) -> Any:
        if self.mock:
            if route.model in self.mock_fail or route.model.split("/", 1)[-1] in self.mock_fail:
                raise litellm.RateLimitError(message="mock rate limit", llm_provider=route.via, model=route.model)
            if self.mock_hook:
                text, finish = self.mock_hook(route, messages)
            else:
                text, finish = f"[mock:{route.model}] OK", "stop"
            p_tok = self._count_tokens(messages)
            c_tok = max(1, len(text) // 4)
            return litellm.ModelResponse(
                model=route.model,
                choices=[{"index": 0, "finish_reason": finish, "message": {"role": "assistant", "content": text}}],
                usage={"prompt_tokens": p_tok, "completion_tokens": c_tok, "total_tokens": p_tok + c_tok})
        params = dict(model=route.model, messages=messages,
                      timeout=float(self.defaults.get("request_timeout_s", 60)), **kw)
        if route.model.startswith("vertex_ai/"):
            params.setdefault("vertex_project", os.getenv("VERTEXAI_PROJECT"))
            params.setdefault("vertex_location", os.getenv("VERTEXAI_LOCATION", "global"))
        return litellm.completion(**params)

    # -- public API --------------------------------------------------------- #
    def chat(self, messages: list[dict] | str, *, strategy: Optional[str] = None, tier: Optional[str] = None,
             models: Optional[list[str]] = None, max_cost: Optional[float] = None,
             use_cache: bool = True, task_type: Optional[str] = None, _allow_compress: bool = True,
             **completion_kwargs) -> GatewayResponse:
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]
        strategy = strategy or self.defaults.get("strategy", "balanced")
        task_type = task_type or classify_task(messages)
        max_cost = float(max_cost if max_cost is not None else self.defaults.get("max_cost_per_request_usd", 0.5))
        wants_json = (completion_kwargs.get("response_format") or {}).get("type") == "json_object"

        # cache (cost optimization: identical prompts are free)
        key = hashlib.sha256(json.dumps([messages, tier, models, completion_kwargs], sort_keys=True,
                                        default=str).encode()).hexdigest()
        ttl = float(self.defaults.get("cache_ttl_s", 900))
        if use_cache and key in self._cache and time.time() - self._cache[key][0] < ttl:
            cached = self._cache[key][1]
            rid = uuid.uuid4().hex[:12]
            self.store.log_attempt(request_id=rid, alias=cached.model_alias, provider=self.models[cached.model_alias].provider,
                                   tier=self.models[cached.model_alias].tier, model=cached.model, via=cached.via,
                                   task_type=task_type, status="ok", cached=1, baseline_cost_usd=cached.baseline_cost_usd)
            return GatewayResponse(**{**cached.__dict__, "request_id": rid, "cost_usd": 0.0, "cached": True, "latency_ms": 0})

        # budget
        daily = float(self.defaults.get("daily_budget_usd", 10.0))
        remaining = daily - self.store.spent_today()
        if remaining <= 0:
            raise BudgetExceeded(f"Daily budget ${daily:.2f} exhausted")
        max_cost = min(max_cost, remaining)

        # self data compression: only when the request would not fit context/budget/trigger
        comp_info: Optional[dict] = None
        if _allow_compress:
            target = self._compression_target(self._count_tokens(messages), task_type, tier, max_cost, models)
            if target:
                messages, comp_info = self.compressor.compress(messages, target)
                log.info("compressed request %s -> %s tokens (%s)", comp_info["original_tokens"],
                         comp_info["compressed_tokens"], "+".join(comp_info["stages"]))
        orig_tok = comp_info["original_tokens"] if comp_info else 0

        chain, policy_tier, p_est, out_est = self.plan(messages, strategy, task_type, tier, max_cost, models)
        rid = uuid.uuid4().hex[:12]
        attempts: list[dict] = []
        retries = self.max_retries()

        dead_transports: set[str] = set()  # e.g. a bad OpenRouter key fails every OpenRouter route
        for spec, route, exploratory in chain:
            bkey = f"{spec.alias}|{route.via}"
            tkey = "openrouter" if route.via == "openrouter" else spec.provider
            if tkey in dead_transports or not self.breaker.available(bkey):
                continue
            for i in range(retries + 1):
                t0 = time.time()
                try:
                    resp = self._call(route, messages, **completion_kwargs)
                except Exception as e:  # noqa: BLE001
                    ms = int((time.time() - t0) * 1000)
                    etype = type(e).__name__
                    attempts.append({"model": route.model, "error": f"{etype}: {str(e)[:160]}"})
                    self.store.log_attempt(request_id=rid, alias=spec.alias, provider=spec.provider, tier=spec.tier,
                                           model=route.model, via=route.via, task_type=task_type, status="error",
                                           error_type=etype, error=str(e)[:500], latency_ms=ms, retry_index=i,
                                           exploratory=int(exploratory))
                    self.breaker.failure(bkey)
                    if isinstance(e, (litellm.AuthenticationError, litellm.PermissionDeniedError)):
                        dead_transports.add(tkey)
                        break
                    if isinstance(e, litellm.ContextWindowExceededError) and _allow_compress and comp_info is None:
                        messages, comp_info = self.compressor.compress(
                            messages, int(min(route.max_input_tokens, self._count_tokens(messages)) * 0.7))
                        orig_tok = comp_info["original_tokens"]
                        continue  # retry same route with the compressed request
                    if isinstance(e, TRANSIENT_ERRORS) and i < retries and self.breaker.available(bkey):
                        time.sleep(0 if self.mock else min(8, 0.5 * 2 ** i + random.random() * 0.25))
                        continue
                    break  # next route
                ms = int((time.time() - t0) * 1000)
                usage = getattr(resp, "usage", None)
                p_tok = int(getattr(usage, "prompt_tokens", 0) or p_est)
                c_tok = int(getattr(usage, "completion_tokens", 0) or 0)
                cost = self._cost(route, p_tok, c_tok)
                hidden = getattr(resp, "_hidden_params", {}) or {}
                if not self.mock and hidden.get("response_cost"):
                    cost = float(hidden["response_cost"])
                baseline = self._cost(self._baseline_spec.routes[0], p_tok, c_tok)
                text = resp.choices[0].message.content or ""
                finish = resp.choices[0].finish_reason or ""
                aq = auto_evaluate(text, finish, task_type, wants_json)
                self.breaker.success(bkey)
                self.store.log_attempt(request_id=rid, alias=spec.alias, provider=spec.provider, tier=spec.tier,
                                       model=route.model, via=route.via, task_type=task_type, status="ok",
                                       prompt_tokens=p_tok, completion_tokens=c_tok, cost_usd=cost,
                                       baseline_cost_usd=baseline, latency_ms=ms, retry_index=i,
                                       exploratory=int(exploratory), auto_quality=aq, finish_reason=finish,
                                       original_tokens=orig_tok, compressed=int(bool(comp_info)))
                out = GatewayResponse(
                    request_id=rid, text=text, model_alias=spec.alias, model=route.model, via=route.via,
                    task_type=task_type, tier_policy=policy_tier, prompt_tokens=p_tok, completion_tokens=c_tok,
                    cost_usd=cost, baseline_cost_usd=baseline, latency_ms=ms, attempts=len(attempts) + 1,
                    exploratory=exploratory, auto_quality=aq, finish_reason=finish, compression=comp_info, raw=resp)
                if use_cache:
                    self._cache[key] = (time.time(), out)
                self._maybe_judge(out, messages)
                self._maybe_auto_improve()
                return out
        raise AllRoutesFailed(attempts)

    # -- learning signals --------------------------------------------------- #
    def feedback(self, request_id: str, score: float, note: str = "", source: str = "user") -> None:
        """Record explicit quality feedback in [0, 1] for a request. Overrides auto-eval."""
        score = max(0.0, min(1.0, float(score)))
        self.store.execute(
            "INSERT INTO feedback(request_id,score,source,note,ts) VALUES(?,?,?,?,?) "
            "ON CONFLICT(request_id) DO UPDATE SET score=excluded.score, source=excluded.source, note=excluded.note",
            (request_id, score, source, note, time.time()))
        self.learner.invalidate()

    def _maybe_judge(self, resp: GatewayResponse, messages: list[dict]) -> None:
        """Optional LLM-as-judge on a sample of traffic, using a cheap model."""
        lcfg = self.defaults.get("learning", {})
        rate = float(lcfg.get("judge_sample_rate", 0.0))
        judge = lcfg.get("judge_model")
        if rate <= 0 or not judge or judge == resp.model_alias or random.random() > rate:
            return
        prompt = messages[-1].get("content", "") if messages else ""
        jm = [{"role": "system", "content": "Rate the answer's correctness and helpfulness from 0 to 10. "
                                            "Reply with only the number."},
              {"role": "user", "content": f"QUESTION:\n{str(prompt)[:4000]}\n\nANSWER:\n{resp.text[:6000]}"}]
        try:
            r = self.chat(jm, models=[judge], use_cache=False, task_type="judge", strategy="cost")
            m = re.search(r"\d+(\.\d+)?", r.text)
            if m:
                self.feedback(resp.request_id, float(m.group()) / 10, source="judge")
        except Exception as e:  # noqa: BLE001
            log.debug("judge failed: %s", e)

    def _maybe_auto_improve(self) -> None:
        every = int(self.defaults.get("auto_improve_every_n_requests", 50))
        if every <= 0:
            return
        count = self.store.request_count()
        last = int(self.store.get_policy("last_improve_at_count", 0))
        if count - last >= every:
            if self.store.compaction_needed():
                res = self.store.compact()
                log.info("storage compacted: %s", res)
            changes = self.optimizer.run(apply=True)
            for c in changes:
                log.info("auto-improve: %s %s %s -> %s (%s)", c["kind"], c["target"], c["old"], c["new"], c["reason"])

    # -- reporting ---------------------------------------------------------- #
    def report(self, days: int = 7) -> dict:
        since = time.time() - days * 86400
        q = self.store.query
        totals = dict(q("""SELECT SUM(CASE WHEN status='ok' THEN n END) requests, SUM(CASE WHEN status='ok' THEN n END) ok,
                      SUM(CASE WHEN status='error' THEN n END) errors, SUM(cached_n) cache_hits,
                      SUM(prompt_tokens) prompt_tokens, SUM(completion_tokens) completion_tokens,
                      ROUND(SUM(cost_usd),6) cost_usd,
                      ROUND(SUM(CASE WHEN status='ok' THEN baseline_cost_usd END),6) baseline_usd,
                      SUM(compressed_n) compressed_requests,
                      SUM(CASE WHEN compressed_n>0 THEN original_tokens - prompt_tokens END) tokens_saved_by_compression
                      FROM usage_all WHERE ts>=?""", (since,))[0])
        for k in list(totals):
            totals[k] = totals[k] or 0
        attempts_total = totals["ok"] + totals["errors"]
        totals["success_rate"] = round(totals["ok"] / attempts_total, 4) if attempts_total else None
        totals["savings_vs_premium_usd"] = round(totals["baseline_usd"] - totals["cost_usd"], 6)
        totals["savings_pct"] = round(100 * totals["savings_vs_premium_usd"] / totals["baseline_usd"], 1) \
            if totals["baseline_usd"] else 0.0
        qrow = q("""SELECT AVG(COALESCE(f.score,a.auto_quality)) q FROM attempts a LEFT JOIN feedback f
                    ON f.request_id=a.request_id WHERE a.ts>=? AND a.status='ok' AND a.cached=0""", (since,))[0]
        totals["avg_quality"] = round(qrow["q"], 3) if qrow["q"] is not None else None

        daily = q("""SELECT day, SUM(CASE WHEN status='ok' THEN n END) requests, ROUND(SUM(cost_usd),6) cost,
                     ROUND(SUM(CASE WHEN status='ok' THEN baseline_cost_usd END),6) baseline,
                     SUM(prompt_tokens) p_tok, SUM(completion_tokens) c_tok,
                     SUM(CASE WHEN status='error' THEN n END) errors
                     FROM usage_all WHERE ts>=? GROUP BY day ORDER BY day""", (since,))
        by_provider = q("""SELECT provider, ROUND(SUM(cost_usd),6) cost, SUM(prompt_tokens+completion_tokens) tokens,
                           SUM(CASE WHEN status='ok' THEN n END) ok FROM usage_all WHERE ts>=? AND cached_n=0
                           GROUP BY provider ORDER BY cost DESC""", (since,))
        by_model = q("""SELECT alias, via, tier, SUM(n) attempts, SUM(CASE WHEN status='ok' THEN n ELSE 0 END) ok,
                        SUM(prompt_tokens) p_tok, SUM(completion_tokens) c_tok, ROUND(SUM(cost_usd),6) cost,
                        CAST(SUM(latency_sum)/SUM(n) AS INT) avg_ms
                        FROM usage_all WHERE ts>=? AND cached_n=0 GROUP BY alias, via ORDER BY cost DESC""", (since,))
        by_task = q("""SELECT a.task_type, COUNT(*) n, ROUND(AVG(COALESCE(f.score,a.auto_quality)),3) quality,
                       ROUND(AVG(a.cost_usd),6) avg_cost FROM attempts a LEFT JOIN feedback f ON f.request_id=a.request_id
                       WHERE a.ts>=? AND a.status='ok' AND a.cached=0 GROUP BY a.task_type""", (since,))
        policy = self.task_policy()
        by_task = [dict(r, tier_policy=policy.get(r["task_type"], "-")) for r in by_task]
        errors = q("""SELECT error_type, COUNT(*) n FROM attempts WHERE ts>=? AND status='error'
                      GROUP BY error_type ORDER BY n DESC LIMIT 8""", (since,))
        arms = []
        for (alias, task), st in sorted(self.learner.all_stats().items()):
            if alias not in self.models:
                continue
            tot = st.ok + st.fail
            arms.append({"alias": alias, "task_type": task, "n": st.n,
                         "quality": round(self.learner.expected_quality(self.models[alias], task), 3),
                         "reliability": round(st.ok / tot, 3) if tot else None,
                         "avg_ms": int(st.latency_ms), "avg_out_tokens": int(st.out_tokens)})
        imps = q("SELECT ts,kind,target,old_value,new_value,reason,status FROM improvements ORDER BY id DESC LIMIT 50")
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "days": days,
            "mode": ("lite" if LITE else "litellm") + (" + mock" if self.mock else ""),
            "totals": totals,
            "daily": [dict(r) for r in daily],
            "by_provider": [dict(r) for r in by_provider],
            "by_model": [dict(r) for r in by_model],
            "by_task": by_task,
            "errors": [dict(r) for r in errors],
            "learned": arms,
            "policy": {"task_policy": policy,
                       "route_order": self.store.get_policy("route_order", {}),
                       "expected_output_tokens": self.store.get_policy("expected_output_tokens", {}),
                       "max_retries_per_route": self.max_retries(),
                       "compression_trigger_tokens": self.compression_trigger(),
                       "compression_keep_turns": self.compression_keep_turns(),
                       "quarantine": {k: v for k, v in self.store.get_policy("quarantine", {}).items()
                                      if v > time.time()}},
            "storage": self.store.storage_stats(),
            "spent_today_usd": round(self.store.spent_today(), 6),
            "daily_budget_usd": float(self.defaults.get("daily_budget_usd", 10.0)),
            "recent_improvements": [dict(r) for r in imps],
            "models": [{"alias": m.alias, "provider": m.provider, "tier": m.tier, "quality": m.quality,
                        "price_in_per_m": round(m.routes[0].price_in * 1e6, 3),
                        "price_out_per_m": round(m.routes[0].price_out * 1e6, 3),
                        "routes": [{"via": r.via, "model": r.model, "available": self._route_available(m, r)}
                                   for r in m.routes]} for m in self.models.values()],
        }


# --------------------------------------------------------------------------- #
# Offline simulation (demonstrates learning + improvement without API keys)
# --------------------------------------------------------------------------- #
SIM_PROMPTS = {
    "simple": ["What's the capital of France?", "Say hello in Spanish.", "What day comes after Monday?"],
    "extraction": ["Extract the name and email fields as JSON from: Jane Doe, jane@x.com"],
    "summarization": ["Summarize the key points of this memo about Q3 hiring plans."],
    "creative": ["Write a short poem about Minneapolis winters."],
    "code": ["Write a python function to debug a failing regex for email validation."],
    "reasoning": ["Analyze the trade-offs of event sourcing vs CRUD for a payments system, step by step."],
}
# hidden "true" quality per (tier, task) used by the simulator
SIM_TRUTH = {
    "economy": {"simple": 0.9, "extraction": 0.85, "summarization": 0.8, "creative": 0.62, "code": 0.55, "reasoning": 0.45},
    "standard": {"simple": 0.92, "extraction": 0.9, "summarization": 0.88, "creative": 0.85, "code": 0.82, "reasoning": 0.7},
    "premium": {"simple": 0.93, "extraction": 0.92, "summarization": 0.9, "creative": 0.9, "code": 0.92, "reasoning": 0.9},
}


def simulate(gw: Gateway, n: int, seed: int = 7) -> None:
    rng = random.Random(seed)
    gw.learner.rng.seed(seed)
    tier_of = {r.model: s.tier for s in gw.models.values() for r in s.routes}

    def hook(route: Route, messages: list[dict]) -> tuple[str, str]:
        if rng.random() < (0.35 if route.model.startswith("deepseek/") else 0.03):  # flaky direct DeepSeek
            raise litellm.ServiceUnavailableError(message="sim 503", llm_provider="sim", model=route.model)
        return "x" * rng.randint(200, 1600), "stop"

    gw.mock, gw.mock_hook = True, hook
    for i in range(n):
        task = rng.choice(TASK_TYPES)
        prompt = rng.choice(SIM_PROMPTS[task]) + f" #{i}"
        try:
            r = gw.chat(prompt, use_cache=False)
        except GatewayError as e:
            print("request failed:", e)
            continue
        truth = SIM_TRUTH[tier_of[r.model]][r.task_type]
        gw.feedback(r.request_id, min(1, max(0, rng.gauss(truth, 0.08))), source="sim")


# --------------------------------------------------------------------------- #
# OpenAI model discovery: add every chat model your key can use to models.json
# --------------------------------------------------------------------------- #
_OPENAI_NON_CHAT = re.compile(r"(embedding|moderation|whisper|tts|transcribe|realtime|audio|image|dall-e|"
                              r"davinci|babbage|search|live|sora|cyber|rosalind|computer-use)", re.I)


def openai_tier(model_id: str) -> tuple[str, int]:
    m = model_id.lower()
    if any(x in m for x in ("luna", "nano")):
        return "economy", 5
    if any(x in m for x in ("terra", "mini")):
        return "standard", 7
    if any(x in m for x in ("astra", "pro")):
        return "premium", 10
    return "premium", 9


def discover_openai(config_path: str, write: bool = False) -> list[dict]:
    """List models from GET /v1/models and add missing chat models (direct + OpenRouter routes)."""
    import urllib.request
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise GatewayError("OPENAI_API_KEY is not set")
    req = urllib.request.Request("https://api.openai.com/v1/models", headers={"Authorization": f"Bearer {key}"})
    import urllib.error
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            ids = sorted(m["id"] for m in json.loads(r.read())["data"])
    except urllib.error.HTTPError as e:
        raise GatewayError(f"OpenAI rejected the request (HTTP {e.code}); check OPENAI_API_KEY") from None
    except (urllib.error.URLError, OSError) as e:
        raise GatewayError(f"could not reach OpenAI: {e}") from None
    chat = [i for i in ids if (i.startswith("gpt-") or re.match(r"^o\d", i)) and not _OPENAI_NON_CHAT.search(i)
            and not re.search(r"-\d{4}-\d{2}-\d{2}$", i)]  # skip dated snapshots of aliases
    cfg = json.loads(Path(config_path).read_text())
    known = {r["model"].split("/")[-1] for m in cfg["models"] for r in m["routes"]} | {m["alias"] for m in cfg["models"]}
    added = []
    for mid in chat:
        if mid in known:
            continue
        tier, quality = openai_tier(mid)
        added.append({"alias": mid, "provider": "openai", "tier": tier, "quality": quality, "discovered": True,
                      "routes": [{"model": mid, "via": "direct"},
                                 {"model": f"openrouter/openai/{mid}", "via": "openrouter"}]})
    if write and added:
        cfg["models"].extend(added)
        Path(config_path).write_text(json.dumps(cfg, indent=2) + "\n")
    return added


# --------------------------------------------------------------------------- #
# GUI report server (stdlib only, so it also runs on Android/Termux)
# --------------------------------------------------------------------------- #
HERE = Path(__file__).resolve().parent
MANIFEST = {
    "name": "MCUBED Gateway", "short_name": "MCUBED", "start_url": "/", "display": "standalone",
    "background_color": "#0f1417", "theme_color": "#0f1417", "orientation": "any",
    "icons": [{"src": "/icon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any maskable"}],
}
ICON_SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="14" '
            'fill="#14b8a6"/><path d="M14 46V18l9 14 9-14 9 14 9-14v28" fill="none" stroke="#0f1417" '
            'stroke-width="5" stroke-linejoin="round"/></svg>')
# network-first service worker: works offline with the last report, never serves stale data when online
SERVICE_WORKER = """
const C='mcubed-v1';
self.addEventListener('install',e=>{self.skipWaiting();e.waitUntil(caches.open(C).then(c=>c.addAll(['/','/game.html','/manifest.webmanifest','/icon.svg'])))});
self.addEventListener('activate',e=>e.waitUntil(self.clients.claim()));
self.addEventListener('fetch',e=>{if(e.request.method!=='GET')return;
  e.respondWith(fetch(e.request).then(r=>{const c=r.clone();caches.open(C).then(x=>x.put(e.request,c));return r})
  .catch(()=>caches.match(e.request)))});
"""


def export_html(gw: "Gateway", path: str, days: int = 7) -> str:
    """Write a self-contained static HTML report (open it on any device, no server needed)."""
    html = (HERE / "dashboard.html").read_text()
    data = json.dumps(gw.report(days), default=str).replace("</", "<\\/")
    html = html.replace("<script>\nconst STATIC", f"<script>window.__REPORT__={data};</script>\n<script>\nconst STATIC", 1)
    Path(path).write_text(html)
    return path


def serve_gui(gw: "Gateway", host: str = "127.0.0.1", port: int = 8765, token: Optional[str] = None) -> None:
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from urllib.parse import parse_qs, urlparse

    lock = threading.Lock()  # one gateway, many phone/browser clients

    class H(BaseHTTPRequestHandler):
        server_version = "MCUBED/1.0"

        def log_message(self, fmt: str, *a: Any) -> None:
            log.debug("gui " + fmt, *a)

        def _send(self, code: int, body: Any, ctype: str = "application/json") -> None:
            raw = body if isinstance(body, bytes) else (
                body.encode() if isinstance(body, str) else json.dumps(body, default=str).encode())
            gz = "gzip" in (self.headers.get("Accept-Encoding") or "") and len(raw) > 1024
            if gz:  # compress responses: smaller payloads on mobile data
                import gzip
                raw = gzip.compress(raw, 6)
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            if gz:
                self.send_header("Content-Encoding", "gzip")
            self.end_headers()
            self.wfile.write(raw)

        def _authorized(self, q: dict) -> bool:
            if not token:
                return True
            got = self.headers.get("X-Gateway-Token") or (q.get("token") or [""])[0] or \
                (self.headers.get("Cookie") or "").partition("mcubed_token=")[2].split(";")[0]
            import hmac
            return bool(got) and hmac.compare_digest(got, token)

        def _body(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            if n > 1_000_000:
                raise GatewayError("request body too large")
            return json.loads(self.rfile.read(n) or b"{}")

        def do_GET(self) -> None:  # noqa: N802
            u = urlparse(self.path)
            q = parse_qs(u.query)
            static = {"/manifest.webmanifest": (json.dumps(MANIFEST), "application/manifest+json"),
                      "/icon.svg": (ICON_SVG, "image/svg+xml"),
                      "/sw.js": (SERVICE_WORKER, "text/javascript")}
            if u.path in static:
                return self._send(200, *static[u.path])
            if not self._authorized(q):
                return self._send(401, {"error": "token required: open /?token=..."})
            if u.path in ("/", "/index.html"):
                body = (HERE / "dashboard.html").read_bytes()
                self.send_response(200)
                if token:
                    self.send_header("Set-Cookie", f"mcubed_token={token}; Path=/; SameSite=Strict; HttpOnly")
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if u.path == "/game.html" and (HERE / "game.html").exists():
                return self._send(200, (HERE / "game.html").read_bytes(), "text/html; charset=utf-8")
            if u.path == "/api/report":
                days = int((q.get("days") or ["7"])[0])
                with lock:
                    return self._send(200, gw.report(days))
            self._send(404, {"error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            u = urlparse(self.path)
            q = parse_qs(u.query)
            if not self._authorized(q):
                return self._send(401, {"error": "unauthorized"})
            origin = self.headers.get("Origin")  # CSRF guard: reject cross-site browser POSTs
            if origin and origin != "null" and urlparse(origin).netloc != self.headers.get("Host"):
                return self._send(403, {"error": "cross-origin request blocked"})
            try:
                with lock:
                    if u.path == "/api/chat":
                        b = self._body()
                        r = gw.chat(str(b.get("prompt", ""))[:200_000], strategy=b.get("strategy"), tier=b.get("tier"))
                        return self._send(200, {**r.summary(), "text": r.text})
                    if u.path == "/api/feedback":
                        b = self._body()
                        gw.feedback(str(b["request_id"]), float(b["score"]), source="gui")
                        return self._send(200, {"ok": True})
                    if u.path == "/api/improve":
                        apply = (q.get("apply") or ["0"])[0] == "1"
                        return self._send(200, {"changes": gw.optimizer.run(apply=apply)})
                    if u.path == "/api/compact":
                        return self._send(200, gw.store.compact(force=True))
            except (GatewayError, KeyError, ValueError) as e:
                return self._send(400, {"error": str(e)})
            except Exception as e:  # noqa: BLE001
                log.exception("gui error")
                return self._send(500, {"error": f"{type(e).__name__}: {e}"})
            self._send(404, {"error": "not found"})

    srv = ThreadingHTTPServer((host, port), H)
    shown = "localhost" if host in ("127.0.0.1", "0.0.0.0") else host
    print(f"MCUBED GUI on http://{shown}:{port}/" + (f"?token={token}" if token else ""))
    if host == "0.0.0.0":
        print("Listening on all interfaces: open it from your phone with this machine's LAN IP.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(description="MCUBED multi-model AI gateway")
    ap.add_argument("--config", default=os.getenv("GATEWAY_CONFIG", "models.json"))
    ap.add_argument("--db", default=os.getenv("GATEWAY_DB", "gateway_usage.db"))
    ap.add_argument("--mock", action="store_true", help="use LiteLLM mock responses (no API keys)")
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("chat", help="send a prompt through the gateway")
    c.add_argument("prompt")
    c.add_argument("--system")
    c.add_argument("--strategy", choices=["balanced", "cost", "quality"])
    c.add_argument("--tier", choices=TIERS)
    c.add_argument("--models", help="comma-separated aliases to restrict routing")
    c.add_argument("--max-cost", type=float)
    c.add_argument("--max-tokens", type=int)
    c.add_argument("--no-cache", action="store_true")

    f = sub.add_parser("feedback", help="rate a response 0..1 (teaches the router)")
    f.add_argument("request_id")
    f.add_argument("score", type=float)
    f.add_argument("--note", default="")

    i = sub.add_parser("improve", help="run the automated process-improvement optimizer")
    i.add_argument("--dry-run", action="store_true")

    r = sub.add_parser("report", help="usage, cost, savings, learned policy")
    r.add_argument("--days", type=int, default=7)
    r.add_argument("--html", metavar="FILE", help="export a self-contained GUI report instead of JSON")

    g = sub.add_parser("gui", help="serve the live GUI dashboard (phone-friendly, installable)")
    g.add_argument("--host", default="127.0.0.1", help="use 0.0.0.0 to reach it from a phone on your LAN")
    g.add_argument("--port", type=int, default=8765)
    g.add_argument("--token", default=os.getenv("GATEWAY_GUI_TOKEN"), help="require a token (recommended with 0.0.0.0)")

    sub.add_parser("compact", help="force storage compaction (roll old rows into daily totals)")

    sub.add_parser("models", help="list model pool, prices, availability")

    d = sub.add_parser("discover-openai", help="find every OpenAI chat model your key can use")
    d.add_argument("--write", action="store_true", help="add the new models to models.json")

    s = sub.add_parser("simulate", help="offline learning demo with synthetic traffic")
    s.add_argument("--n", type=int, default=300)

    args = ap.parse_args()
    try:
        _run(args)
    except GatewayError as e:
        raise SystemExit(f"gateway error: {e}")


def _run(args: argparse.Namespace) -> None:
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s %(message)s")
    gw = Gateway(args.config, args.db, mock=True if args.mock or args.cmd == "simulate" else None)

    if args.cmd == "chat":
        msgs = ([{"role": "system", "content": args.system}] if args.system else []) + \
               [{"role": "user", "content": args.prompt}]
        kw = {"max_tokens": args.max_tokens} if args.max_tokens else {}
        resp = gw.chat(msgs, strategy=args.strategy, tier=args.tier, max_cost=args.max_cost,
                       models=args.models.split(",") if args.models else None, use_cache=not args.no_cache, **kw)
        print(resp.text)
        print("\n---", json.dumps(resp.summary(), indent=2))
    elif args.cmd == "feedback":
        gw.feedback(args.request_id, args.score, args.note)
        print("feedback recorded")
    elif args.cmd == "improve":
        changes = gw.optimizer.run(apply=not args.dry_run)
        print(json.dumps(changes, indent=2) if changes else "No changes: not enough evidence or policy already optimal.")
    elif args.cmd == "report":
        if args.html:
            print("wrote", export_html(gw, args.html, args.days))
        else:
            print(json.dumps(gw.report(args.days), indent=2, default=str))
    elif args.cmd == "gui":
        if args.host == "0.0.0.0" and not args.token:
            args.token = uuid.uuid4().hex[:16]
            print("No --token given for a network-exposed GUI; generated one.")
        serve_gui(gw, args.host, args.port, args.token)
    elif args.cmd == "compact":
        print(json.dumps(gw.store.compact(force=True), indent=2))
    elif args.cmd == "discover-openai":
        added = discover_openai(args.config, write=args.write)
        for m in added:
            print(f"{'added' if args.write else 'new'}  {m['alias']:28} {m['tier']}")
        print(f"{len(added)} new OpenAI chat models" + ("" if args.write or not added else "; rerun with --write to add them"))
    elif args.cmd == "models":
        for s_ in gw.models.values():
            for rt in s_.routes:
                print(f"{s_.alias:22} {s_.provider:10} {s_.tier:9} q={s_.quality:<3} {rt.via:10} "
                      f"${rt.price_in * 1e6:6.2f}/${rt.price_out * 1e6:6.2f} per 1M  "
                      f"{'available' if gw._route_available(s_, rt) else 'no key'}  {rt.model}")
    elif args.cmd == "simulate":
        before = gw.task_policy()
        simulate(gw, args.n)
        rep = gw.report(days=1)
        print("policy before:", json.dumps(before))
        print("policy after: ", json.dumps(rep["policy"]["task_policy"]))
        print(json.dumps({k: rep[k] for k in ("totals", "by_task")}, indent=2))
        print("improvements:")
        for imp in reversed(rep["recent_improvements"]):
            print(f"  [{imp['status']}] {imp['kind']} {imp['target']}: {imp['old_value']} -> {imp['new_value']} ({imp['reason']})")


if __name__ == "__main__":
    main()
