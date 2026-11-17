# MCUBED gateway limits

Measured 2026-11-18 00:00 UTC on `linux`, Python 3.14.8, mode: litellm + mock providers.

| Test | Status | Result |
|---|---|---|
| Huge single prompt -> compression | pass | `{"0.3M": {"orig": 226256, "sent": 89984, "stages": ["normalize", "truncate"], "model": "gpt-6-luna", "sec": 0.96}, "1.5M": {"orig": 1131050, "sent": 89974, "stages": ["normalize", "truncate"], "model": "gpt-6-luna", "sec": 1.91}, "3M": {"orig": 2262027, "sent": 89981, "stages": ["normalize", "truncate"], "model": "gpt-5.6-luna", "sec": 3.03}, "6M": {"orig": 4524477, "sent": 89974, "stages": ["normalize", "truncate"], "model": "claude-haiku-5.5", "sec": 4.98}, "seconds": 12.7}` |
| Long conversation (many turns) -> drop/summarize older turns | pass | `{"turns": 2000, "orig_tokens": 139011, "sent_tokens": 443, "stages": ["normalize", "drop_older"], "kept_system": true, "seconds": 0.28}` |
| Over-budget request -> compress to fit cost cap | pass | `{"cost_usd": 0.009, "cap": 0.02, "sent_tokens": 89978, "seconds": 0.72}` |
| Provider outage: every direct route down -> OpenRouter fallback | pass | `{"requests": 100, "served_via_openrouter": 100, "avg_attempts": 1.27, "max_attempts": 2, "ms_per_request": 0.5, "seconds": 0.06}` |
| Total outage: every route down -> fast, clean failure | pass | `{"attempts": 8, "ms": 3.6, "seconds": 0.01}` |
| Daily budget exhaustion | pass | `{"served_before_stop": 40, "spent": 0.00169, "budget": 0.002, "overshoot_pct": -15.3, "seconds": 0.08}` |
| Concurrency: many threads, one gateway | pass | `{"threads": 64, "requests": 1920, "errors": 0, "first_errors": [], "rps": 246.3, "p50_ms": 255.3, "p95_ms": 552.2, "ledger_rows_match": true, "seconds": 7.8}` |
| Ledger growth: learner + report + compaction at scale | pass | `{"rows": 400000, "learner_refresh_s": 1.16, "chat_with_cold_learner_s": 0.01, "report_s": 1.6, "optimizer_s": 2.83, "compact_s": 3.9, "db_mb": [99.8, 13.2], "raw_rows_after": 46473, "report_after_compact_s": 0.39, "cost_preserved": true, "seconds": 15.93}` |
| Router throughput (planning only) | pass | `{"plans": 10000, "us_per_plan": 152.0, "seconds": 1.53}` |
| Cache: repeated prompt costs nothing | pass | `{"first_cost": 4.884e-05, "second_cost": 0.0, "second_cached": true, "seconds": 0.01}` |
| Learning converges: router finds a cheaper tier that is good enough | pass | `{"tier_changes": {"creative": "standard->economy"}, "savings_pct": 93.4, "avg_quality": 0.847, "improvements": 9, "seconds": 37.79}` |
| Malformed input | pass | `{"empty string": "ok (gpt-5.4-nano)", "unicode": "ok (gpt-6-luna)", "null content": "ok (claude-haiku-5.5)", "list content": "ok (deepseek-v4-flash)", "seconds": 0.01}` |
