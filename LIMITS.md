# MCUBED gateway limits

Measured 2026-11-18 02:24 UTC on `linux`, Python 3.14.8, mode: lite (stdlib) + mock providers.

| Test | Status | Result |
|---|---|---|
| Huge single prompt -> compression | pass | `{"0.3M": {"orig": 337499, "sent": 89961, "stages": ["normalize", "truncate"], "model": "gemini-3.5-flash-lite", "sec": 0.2}, "1.5M": {"orig": 1687537, "sent": 89961, "stages": ["normalize", "truncate"], "model": "gemini-3.5-flash", "sec": 0.96}, "3M": {"orig": 3375075, "sent": 89961, "stages": ["normalize", "truncate"], "model": "gemini-3.5-flash-lite", "sec": 2.05}, "6M": {"orig": 6750126, "sent": 89961, "stages": ["normalize", "truncate"], "model": "claude-haiku-5.5", "sec": 3.99}, "seconds": 9.2}` |
| Long conversation (many turns) -> drop/summarize older turns | pass | `{"turns": 2000, "orig_tokens": 253230, "sent_tokens": 785, "stages": ["normalize", "drop_older"], "kept_system": true, "seconds": 0.13}` |
| Provider outage: every direct route down -> OpenRouter fallback | pass | `{"requests": 100, "served_via_openrouter": 100, "avg_attempts": 1.19, "max_attempts": 2, "ms_per_request": 0.2, "seconds": 0.03}` |
| Total outage: every route down -> fast, clean failure | pass | `{"attempts": 8, "ms": 1.8, "seconds": 0.01}` |
| Concurrency: many threads, one gateway | pass | `{"threads": 64, "requests": 1920, "errors": 0, "first_errors": [], "rps": 215.8, "p50_ms": 291.1, "p95_ms": 565.2, "ledger_rows_match": true, "seconds": 8.9}` |
| Ledger growth: learner + report + compaction at scale | pass | `{"rows": 400000, "learner_refresh_s": 1.19, "chat_with_cold_learner_s": 0.0, "report_s": 1.61, "optimizer_s": 3.01, "compact_s": 4.51, "db_mb": [93.0, 12.3], "raw_rows_after": 46658, "report_after_compact_s": 0.37, "tokens_preserved": true, "seconds": 17.89}` |
| Router throughput (planning only) | pass | `{"plans": 10000, "us_per_plan": 114.8, "seconds": 1.15}` |
| Cache: repeated prompt is answered instantly | pass | `{"first_ms": 0, "second_ms": 0, "second_cached": true, "seconds": 0.01}` |
| Learning converges: router finds a lighter tier that is good enough | pass | `{"tier_changes": {"creative": "standard->economy"}, "tokens": 971776, "avg_quality": 0.848, "improvements": 13, "seconds": 40.73}` |
| Malformed input | pass | `{"empty string": "ok (gpt-6.1-terra)", "unicode": "ok (deepseek-v4-flash)", "null content": "ok (gemini-3.5-flash-lite)", "list content": "ok (gemini-3.5-flash)", "seconds": 0.01}` |
