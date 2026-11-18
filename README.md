# MCUBED

A multi-model AI gateway with a phone-friendly web dashboard. One entry point for OpenAI, Anthropic, Google and DeepSeek models, with OpenRouter as a fallback route for every model.

## Features

- Automatic fallback routing with retries, circuit breakers and quarantine
- Usage and cost ledger (SQLite), daily and per-request budgets, response cache
- Self-learning router that balances quality, cost and latency per task type
- Automated process improvement: the optimizer tunes tiers, route order, token estimates and quarantines every 50 requests and every 6 hours while the dashboard or app runs, with a change log and automatic rollback
- Conversation compression for long chats and automatic storage compaction
- Lite mode for Android/Termux: standard library only, no native builds
- Installable web dashboard (overview, models, learning, chat, storage)
- Gateway Doom: a touch-friendly game where the demons are your real error types
- Native Android APK built automatically by GitHub Actions

## Quick start (no API keys)

```bash
python gateway.py simulate --n 300        # offline learning demo
GATEWAY_MOCK=1 python gateway.py gui      # dashboard at http://localhost:8765
```

## Real models

```bash
cp .env.example .env                      # add keys, then load them:
set -a; . ./.env; set +a
pip install -r requirements.txt           # optional; skip on Android
python gateway.py models                  # shows which routes have keys
python gateway.py chat "Explain CAP theorem"
python gateway.py gui
```

An OpenRouter key alone is enough to reach every model in `models.json`. Each provider key you add opens its direct routes:

| Key | Opens |
|---|---|
| `OPENROUTER_API_KEY` | Every model, as the fallback route |
| `OPENAI_API_KEY` | GPT-6 Astra, GPT-6.1 Sol/Terra, GPT-6 Luna, GPT-5.6, GPT-5.5, GPT-5.4 (direct) |
| `ANTHROPIC_API_KEY` | Claude models (direct, desktop mode) |
| `DEEPSEEK_API_KEY` | DeepSeek models (direct) |
| `VERTEXAI_PROJECT` | Gemini models (direct, desktop mode) |

Find every OpenAI chat model your key can use and add the new ones:

```bash
python gateway.py discover-openai          # preview
python gateway.py discover-openai --write  # add to models.json
```

## Repositories

With `GITHUB_TOKEN` set, MCUBED finds every repository you own, collaborate on, or reach through an organization, and records it in `repos.json`. New repositories are added automatically every 6 hours while the dashboard or app runs (`repo_sync_every_hours` in `models.json`), and the Storage tab has a "Sync now" button. Run `python gateway.py repos --clone repos` to also clone them and fast-forward existing copies; the token is sent per command and never written into `.git/config`. Archived repositories are skipped unless you pass `--include-archived`. Use a fine-grained token with read-only access.

## Android app (native APK)

The `android/` project packages the gateway as a real Android app. It embeds Python with [Chaquopy](https://chaquo.com/chaquopy/), runs the gateway on `127.0.0.1` inside the app, and shows the dashboard (including the Doom tab) full screen.

- Get the APK: open the repo's Actions tab, choose the latest "Build Android APK" run, and download `MCUBED-apk`. Pushing a tag like `v0.1.0` also attaches the APK to a GitHub Release.
- First launch asks for OpenRouter, OpenAI and DeepSeek keys (any or all), stored only on the device. Choose "Demo mode" to try it with simulated replies. Change keys later from the "AI keys" menu. On Android, OpenAI and DeepSeek are called directly; Claude and Gemini go through OpenRouter.
- Requires Android 8.0+ on a 64-bit device. Release builds are signed with a debug key; configure your own keystore before publishing to the Play Store.
- Build locally: `cd android && gradle assembleRelease` (JDK 17, Android SDK, Python 3.13 on PATH).

## Android (Termux)

One-step setup: `bash termux-setup.sh`. Or manually:

```bash
pkg install python git
git clone https://github.com/dconcretemick-netizen/MCUBED && cd MCUBED
export GATEWAY_LITE=1 OPENROUTER_API_KEY=...
python gateway.py gui
```

Open http://localhost:8765 in Chrome, then use "Add to Home screen" to install it like an app.

## Commands

| Command | Purpose |
|---|---|
| `chat "prompt"` | Send a prompt (`--strategy balanced\|cost\|quality`, `--tier`, `--models`) |
| `feedback <id> <0..1>` | Rate a response to teach the router |
| `improve [--dry-run]` | Run the policy optimizer |
| `report [--days 7] [--html FILE]` | Usage, cost and learned policy as JSON, or a static HTML report |
| `compact` | Force storage compaction |
| `models` | Model pool, prices and key availability |
| `discover-openai [--write]` | Find OpenAI chat models your key can use |
| `repos [--clone DIR] [--list]` | Auto-add every GitHub repository your token can access; optionally clone/update them |
| `gui [--host --port --token]` | Serve the web dashboard and Doom game |
| `simulate [--n 300]` | Offline demo with synthetic traffic |

## Security

- The dashboard listens on `127.0.0.1` by default. Binding to `0.0.0.0` uses `--token` (or `GATEWAY_GUI_TOKEN`), generating one if missing; open `/?token=...` once and a cookie is set.
- Cross-origin POSTs are rejected. API keys stay in environment variables and never reach the browser.
- Configure models, prices and budgets in `models.json`.

## How a request flows

1. **Classify** the prompt (simple, extraction, summarization, creative, code, reasoning).
2. **Look up the tier** that the learned policy requires for that task (economy, standard, premium).
3. **Check the budget.** Requests stop at the per-request cap and the daily budget. If nothing fits, the gateway drops to a cheaper tier before it gives up.
4. **Compress if needed.** Compression runs only when a request would overflow the context window, exceed the cost cap, or pass the learned trigger size.
5. **Rank candidates.**
   - `cost`: cheapest first.
   - `quality`: best first.
   - `balanced` (the default): Thompson sampling over learned quality, reliability, latency, and real dollar cost.
6. **Execute with fallback.** If a route fails, the gateway switches to the same model on its other route (direct ↔ OpenRouter) right away, then moves to the next model.
   - Transient errors are retried with backoff.
   - Auth errors disable that whole transport for the request.
   - Circuit breakers skip routes that keep failing.
   - Each request is capped at 8 attempts and has a deadline.
7. **Record** tokens, cost, the all-premium baseline cost, latency and auto-evaluated quality in a SQLite ledger.
8. **Learn.** Explicit feedback (or an optional LLM judge) overrides the auto score. The optimizer runs every 50 requests.

## Balanced self-learning

For each model × task pair, the gateway learns a Beta posterior over quality (seeded from the config's quality score), a reliability posterior, and running averages for latency and output size. The `balanced` strategy maximizes:

```
utility = quality_value_usd × q_eff × reliability − estimated_cost − latency_penalty
q_eff   = min(q, target) + 0.25 × max(0, q − target)
```

Quality counts fully up to the "good enough" target and only partly above it. The gateway therefore pays for quality where it matters and saves money where it doesn't. Sampling instead of averaging keeps uncertain models in play. A 10% probe of the next-lower tier gives the optimizer evidence for safe downgrades.

## Self data compression

- **Context.** Stages run cheapest-first and stop once the request fits:
  1. Normalize whitespace and remove duplicate lines.
  2. Summarize older turns with an economy model, or drop them with a marker.
  3. Map-reduce long documents chunk by chunk.
  4. Trim from the middle, keeping the head and tail.

  System messages and recent turns are always kept.
- **Storage.** When the database passes its size or row limit, old rows roll up into exact daily totals and the file is vacuumed. In testing, 400k rows went from 103 MB to 13 MB with costs preserved to the cent.
- **Network.** GUI API responses are gzip-compressed for mobile data.

## Limits

`python limits.py` stress-tests the gateway and writes [LIMITS.md](LIMITS.md) with measured numbers. Every test passes in both full and lite mode:

- Prompts up to 6M tokens are compressed to fit.
- Conversations up to 2,000 turns are trimmed.
- During a provider outage, every request still gets an answer within at most 2 attempts.
- When every route is down, it fails cleanly within 8 attempts.
- Budget caps hold with no overspend.
- 64 threads put 1,920 requests through one gateway with zero errors.
- On a 400k-row ledger, compaction takes about 4 s.

The main remaining limit: a single process tops out at about 220 requests/sec of gateway overhead, because of SQLite writes and the Python GIL. That's far above what real model latency allows. Run several processes on separate databases to go further.
