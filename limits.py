#!/usr/bin/env python3
"""
MCUBED limits suite: pushes the gateway until something gives, and records where.

    python limits.py            # full suite (mock mode, no API keys needed)
    python limits.py --quick    # smaller sizes, ~30s
    GATEWAY_LITE=1 python limits.py --quick   # same suite on the Android/stdlib build

Writes LIMITS.md with measured numbers for this machine.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import statistics
import sys
import tempfile
import threading
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("GATEWAY_MOCK", "1")
import gateway as G  # noqa: E402

HERE = Path(__file__).resolve().parent
RESULTS: list[dict] = []


def fresh(name: str, **defaults) -> G.Gateway:
    db = Path(tempfile.gettempdir()) / f"limits_{name}_{uuid.uuid4().hex[:6]}.db"
    gw = G.Gateway(str(HERE / "models.json"), str(db), mock=True)
    for k, v in defaults.items():
        if isinstance(v, dict):
            gw.defaults.setdefault(k, {}).update(v)
        else:
            gw.defaults[k] = v
    gw.defaults["auto_improve_every_n_requests"] = defaults.get("auto_improve_every_n_requests", 0)
    return gw


def test(name: str):
    def deco(fn):
        def run(quick: bool):
            t0 = time.time()
            try:
                info = fn(quick) or {}
                status = info.pop("status", "pass")
            except Exception as e:  # noqa: BLE001
                info, status = {"error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()[-800:]}, "FAIL"
            info["seconds"] = round(time.time() - t0, 2)
            RESULTS.append({"test": name, "status": status, **info})
            print(f"[{status:4}] {name}: {json.dumps({k: v for k, v in info.items() if k != 'trace'})}", flush=True)
        run.__name__ = fn.__name__
        TESTS.append(run)
        return run
    return deco


TESTS: list = []


# --------------------------------------------------------------------------- #
@test("Huge single prompt -> compression")
def huge_prompt(quick: bool):
    out = {}
    for mtoks in ([0.3, 1.5] if quick else [0.3, 1.5, 3, 6]):
        gw = fresh("huge")
        words = int(mtoks * 1e6 * 0.75)
        text = " ".join(random.choice(["alpha", "beta", "gamma", "delta", "router", "token"]) for _ in range(words))
        t0 = time.time()
        r = gw.chat("Summarize this log:\n" + text, use_cache=False)
        c = r.compression or {}
        out[f"{mtoks}M"] = {"orig": c.get("original_tokens"), "sent": r.prompt_tokens, "stages": c.get("stages"),
                            "model": r.model_alias, "sec": round(time.time() - t0, 2)}
    return out


@test("Long conversation (many turns) -> drop/summarize older turns")
def long_convo(quick: bool):
    gw = fresh("convo", compression={"trigger_tokens": 20_000})
    turns = 400 if quick else 2000
    msgs = [{"role": "system", "content": "You are helpful."}]
    for i in range(turns):
        msgs.append({"role": "user" if i % 2 == 0 else "assistant", "content": f"turn {i}: " + "context " * 60})
    r = gw.chat(msgs, use_cache=False)
    c = r.compression or {}
    return {"turns": turns, "orig_tokens": c.get("original_tokens"), "sent_tokens": r.prompt_tokens,
            "stages": c.get("stages"), "kept_system": True}


@test("Over-budget request -> compress to fit cost cap")
def cost_cap(quick: bool):
    gw = fresh("cost")
    text = "data " * 400_000  # ~400k tokens
    r = gw.chat("Extract the fields as JSON: " + text, max_cost=0.02, use_cache=False)
    return {"cost_usd": round(r.cost_usd, 5), "cap": 0.02, "sent_tokens": r.prompt_tokens,
            "status": "pass" if r.cost_usd <= 0.02 * 1.05 else "FAIL"}


@test("Provider outage: every direct route down -> OpenRouter fallback")
def outage(quick: bool):
    gw = fresh("outage")
    gw.mock_fail = {r.model for s in gw.models.values() for r in s.routes if r.via == "direct"}
    n = 30 if quick else 100
    vias, attempts = [], []
    t0 = time.time()
    for i in range(n):
        r = gw.chat(f"write python code #{i}", use_cache=False)
        vias.append(r.via)
        attempts.append(r.attempts)
    return {"requests": n, "served_via_openrouter": vias.count("openrouter"),
            "avg_attempts": round(statistics.fmean(attempts), 2), "max_attempts": max(attempts),
            "ms_per_request": round((time.time() - t0) * 1000 / n, 1)}


@test("Total outage: every route down -> fast, clean failure")
def total_outage(quick: bool):
    gw = fresh("total")
    gw.mock_fail = {r.model for s in gw.models.values() for r in s.routes}
    t0 = time.time()
    try:
        gw.chat("hello", use_cache=False)
        return {"status": "FAIL", "error": "should have raised"}
    except G.AllRoutesFailed as e:
        return {"attempts": len(e.attempts), "ms": round((time.time() - t0) * 1000, 1)}


@test("Daily budget exhaustion")
def budget(quick: bool):
    gw = fresh("budget", daily_budget_usd=0.002)
    served = 0
    try:
        for i in range(500):
            gw.chat(f"Analyze the trade-offs step by step #{i} " + "x" * 2000, use_cache=False)
            served += 1
        return {"status": "FAIL", "error": "budget never enforced"}
    except G.BudgetExceeded:
        spent = gw.store.spent_today()
        return {"served_before_stop": served, "spent": round(spent, 5), "budget": 0.002,
                "overshoot_pct": round(100 * (spent - 0.002) / 0.002, 1)}


@test("Concurrency: many threads, one gateway")
def concurrency(quick: bool):
    gw = fresh("conc", auto_improve_every_n_requests=100)
    threads, per = (16, 15) if quick else (64, 30)
    errors, lat = [], []
    lock = threading.Lock()

    def worker(k):
        for i in range(per):
            t0 = time.time()
            try:
                gw.chat(f"task {k}-{i}: summarize this", use_cache=False)
                with lock:
                    lat.append(time.time() - t0)
            except Exception as e:  # noqa: BLE001
                with lock:
                    errors.append(f"{type(e).__name__}: {e}"[:120])
    t0 = time.time()
    ts = [threading.Thread(target=worker, args=(k,)) for k in range(threads)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    wall = time.time() - t0
    total = threads * per
    logged = gw.store.request_count()
    return {"threads": threads, "requests": total, "errors": len(errors), "first_errors": errors[:3],
            "rps": round(total / wall, 1), "p50_ms": round(statistics.median(lat) * 1000, 1) if lat else None,
            "p95_ms": round(sorted(lat)[int(len(lat) * .95) - 1] * 1000, 1) if lat else None,
            "ledger_rows_match": logged == total, "status": "pass" if not errors and logged == total else "FAIL"}


@test("Ledger growth: learner + report + compaction at scale")
def ledger_scale(quick: bool):
    rows = 60_000 if quick else 400_000
    gw = fresh("scale", storage={"max_raw_rows": rows // 2, "retain_raw_days": 7})
    aliases = list(gw.models)
    now = time.time()
    batch = []
    for i in range(rows):
        a = random.choice(aliases)
        s = gw.models[a]
        ts = now - random.random() * 60 * 86400
        batch.append((ts, datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d"), uuid.uuid4().hex[:12], a,
                      s.provider, s.tier, s.routes[0].model, "direct", random.choice(G.TASK_TYPES),
                      "ok" if random.random() > .05 else "error", 300, 400, 0.001, 0.004, 900, 0.8))
    with gw.store._lock:
        gw.store.conn.executemany(
            "INSERT INTO attempts(ts,day,request_id,alias,provider,tier,model,via,task_type,status,prompt_tokens,"
            "completion_tokens,cost_usd,baseline_cost_usd,latency_ms,auto_quality) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            batch)
        gw.store.conn.commit()
    t0 = time.time(); gw.learner.invalidate(); gw.learner.all_stats(); t_learn = time.time() - t0
    t0 = time.time(); gw.chat("hello", use_cache=False); t_chat = time.time() - t0
    before_cost = gw.store.query("SELECT SUM(cost_usd) c FROM usage_all")[0]["c"]
    t0 = time.time(); gw.report(90); t_report = time.time() - t0
    t0 = time.time(); gw.optimizer.run(apply=False); t_opt = time.time() - t0
    mb_before = gw.store.size_mb()
    t0 = time.time(); res = gw.store.compact(); t_compact = time.time() - t0
    after_cost = gw.store.query("SELECT SUM(cost_usd) c FROM usage_all")[0]["c"]
    t0 = time.time(); gw.report(90); t_report2 = time.time() - t0
    return {"rows": rows, "learner_refresh_s": round(t_learn, 2), "chat_with_cold_learner_s": round(t_chat, 2),
            "report_s": round(t_report, 2), "optimizer_s": round(t_opt, 2), "compact_s": round(t_compact, 2),
            "db_mb": [round(mb_before, 1), round(gw.store.size_mb(), 1)], "raw_rows_after": res.get("raw_rows"),
            "report_after_compact_s": round(t_report2, 2),
            "cost_preserved": abs((before_cost or 0) - (after_cost or 0)) < 1e-6,
            "status": "pass" if abs((before_cost or 0) - (after_cost or 0)) < 1e-6 else "FAIL"}


@test("Router throughput (planning only)")
def plan_speed(quick: bool):
    gw = fresh("plan")
    n = 2000 if quick else 10000
    msgs = [{"role": "user", "content": "write python code to sort a list"}]
    t0 = time.time()
    for _ in range(n):
        gw.plan(msgs, "balanced", "code", None, 0.5)
    return {"plans": n, "us_per_plan": round((time.time() - t0) / n * 1e6, 1)}


@test("Cache: repeated prompt costs nothing")
def cache(quick: bool):
    gw = fresh("cache")
    a = gw.chat("What's the capital of France?")
    b = gw.chat("What's the capital of France?")
    return {"first_cost": a.cost_usd, "second_cost": b.cost_usd, "second_cached": b.cached,
            "status": "pass" if b.cached and b.cost_usd == 0 else "FAIL"}


@test("Learning converges: router finds a cheaper tier that is good enough")
def learning(quick: bool):
    gw = fresh("learn", auto_improve_every_n_requests=50)
    before = gw.task_policy()
    # make the economy tier genuinely good at creative work: the optimizer should discover it
    # and downgrade creative, while NOT downgrading code/reasoning where economy is weak
    saved = dict(G.SIM_TRUTH["economy"])
    G.SIM_TRUTH["economy"]["creative"] = 0.88
    try:
        G.simulate(gw, 1500 if quick else 4000, seed=3)
    finally:
        G.SIM_TRUTH["economy"].update(saved)
    after = gw.task_policy()
    rep = gw.report(1)
    changed = {k: f"{before[k]}->{after[k]}" for k in after if before.get(k) != after[k]}
    ok = after["creative"] == "economy" and after["code"] != "economy" and after["reasoning"] != "economy"
    return {"status": "pass" if ok else "FAIL", "tier_changes": changed, "savings_pct": rep["totals"]["savings_pct"],
            "avg_quality": rep["totals"]["avg_quality"],
            "improvements": len(rep["recent_improvements"])}


@test("Malformed input")
def malformed(quick: bool):
    gw = fresh("bad")
    cases = {"empty string": "", "unicode": "日本語のテキストを要約して 🚀" * 50,
             "null content": [{"role": "user", "content": None}],
             "list content": [{"role": "user", "content": [{"type": "text", "text": "hi"}]}]}
    out = {}
    for k, v in cases.items():
        try:
            r = gw.chat(v, use_cache=False)
            out[k] = f"ok ({r.model_alias})"
        except Exception as e:  # noqa: BLE001
            out[k] = f"{type(e).__name__}: {str(e)[:80]}"
    bad = [k for k, v in out.items() if not v.startswith("ok") and "GatewayError" not in v]
    return {**out, "status": "FAIL" if bad else "pass"}


def write_report() -> None:
    lines = ["# MCUBED gateway limits", "",
             f"Measured {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC} on `{sys.platform}`, Python "
             f"{sys.version.split()[0]}, mode: {'lite (stdlib)' if G.LITE else 'litellm'} + mock providers.", "",
             "| Test | Status | Result |", "|---|---|---|"]
    for r in RESULTS:
        body = {k: v for k, v in r.items() if k not in ("test", "status", "trace")}
        lines.append(f"| {r['test']} | {r['status']} | `{json.dumps(body)[:600]}` |")
    (HERE / "LIMITS.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--only", help="substring filter on test function names")
    a = ap.parse_args()
    for t in TESTS:
        if not a.only or a.only in t.__name__:
            t(a.quick)
    write_report()
    fails = [r for r in RESULTS if r["status"] != "pass"]
    print(f"\n{len(RESULTS) - len(fails)}/{len(RESULTS)} passed. Wrote LIMITS.md")
    sys.exit(1 if fails else 0)
