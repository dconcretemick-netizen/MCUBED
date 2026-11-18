# MCUBED

A multi-model AI gateway with a phone-friendly web dashboard. One entry point for OpenAI, Anthropic, Google and DeepSeek models, with OpenRouter as a fallback route for every model.

## Features

- Automatic fallback routing with retries, circuit breakers and quarantine
- Usage ledger (SQLite) for requests, tokens, latency and quality, plus a response cache
- Self-learning router that balances quality, reliability, speed and effort per task type
- Automated process improvement: the optimizer tunes tiers, route order, token estimates and quarantines every 50 requests and every 6 hours while the dashboard or app runs, with a change log and automatic rollback
- Conversation compression for long chats and automatic storage compaction
- Lite mode for Android/Termux: standard library only, no native builds
- OpenAI-style chat as the main screen: multi-turn conversations, model picker (MCUBED auto, fast, best quality, or any model with a key), ratings that teach the router
- OpenAI-compatible API: MCUBED acts as a model named `mcubed` at `/v1/chat/completions` and `/v1/models`, including streaming
- Web browser tab: search or open any address in a reader view, follow links, open the full page, or send the page to the chat
- Installable web dashboard (chat, overview, models, learning, storage, games, web)
- Gateway Doom: a touch-friendly game where the demons are your real error types
- Solitaire (Klondike): tap or drag, undo, hints, draw 1 or 3, saved progress
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

With `GITHUB_TOKEN` set (or the GitHub CLI signed in via `gh auth login`), MCUBED finds every repository you own, collaborate on, or reach through an organization, and records it in `repos.json`. New repositories are added automatically every 6 hours while the dashboard or app runs (`repo_sync_every_hours` in `models.json`), and the Storage tab has a "Sync now" button. Run `python gateway.py repos --clone repos` to also clone them and fast-forward existing copies; the token is sent per command and never written into `.git/config`. Archived repositories are skipped unless you pass `--include-archived`. Use a fine-grained token with read-only access.

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
| `chat "prompt"` | Send a prompt (`--strategy balanced\|efficient\|quality`, `--tier`, `--models`) |
| `feedback <id> <0..1>` | Rate a response to teach the router |
| `improve [--dry-run]` | Run the policy optimizer |
| `report [--days 7] [--html FILE]` | Usage, quality and learned policy as JSON, or a static HTML report |
| `compact` | Force storage compaction |
| `models` | Model pool and key availability |
| `discover-openai [--write]` | Find OpenAI chat models your key can use |
| `repos [--clone DIR] [--list]` | Auto-add every GitHub repository your token can access; optionally clone/update them |
| `gui [--host --port --token]` | Serve the web dashboard and Doom game |
| `simulate [--n 300]` | Offline demo with synthetic traffic |

## Security

- The dashboard listens on `127.0.0.1` by default. Binding to `0.0.0.0` uses `--token` (or `GATEWAY_GUI_TOKEN`), generating one if missing; open `/?token=...` once and a cookie is set.
- Cross-origin POSTs are rejected. API keys stay in environment variables and never reach the browser.
- Configure models, tiers and routing in `models.json`.

## Use MCUBED as an OpenAI model

Start the dashboard (`python gateway.py gui`, or open the Android app), then point any OpenAI SDK or tool at it:

```python
from openai import OpenAI
client = OpenAI(base_url="http://127.0.0.1:8765/v1", api_key="YOUR_GATEWAY_TOKEN")  # any text if no token is set
r = client.chat.completions.create(model="mcubed", messages=[{"role": "user", "content": "Hello"}])
print(r.choices[0].message.content)
```

- `mcubed` (or `mcubed-auto`) lets the router pick; `mcubed-efficient` prefers light models; `mcubed-quality` prefers the best.
- Any alias from `GET /v1/models` pins that exact model.
- `stream: true` returns server-sent events. Responses include an extra `mcubed` field showing which model answered.
- The key is the gateway token (`--token` / `GATEWAY_GUI_TOKEN`), sent as `Authorization: Bearer ...`.

## Web browser

The Web tab searches the web or opens an address through the gateway (`POST /api/fetch`) and shows a clean reader view with the page's links. "Open page" shows the full site; on Android it opens an in-app browser screen. "Ask MCUBED" attaches the page to the chat. Requests to localhost or private network addresses are blocked, including through redirects.

## How a request flows

1. **Classify** the prompt (simple, extraction, summarization, creative, code, reasoning).
2. **Look up the tier** that the learned policy requires for that task (economy, standard, premium).
3. **Check availability.** If no model in the required tier has a working key, the gateway drops to a lighter tier before it gives up.
4. **Compress if needed.** Compression runs only when a request would overflow the context window or pass the learned trigger size.
5. **Rank candidates.**
   - `efficient`: lightest tier first (fastest, least compute).
   - `quality`: best first.
   - `balanced` (the default): Thompson sampling over learned quality, reliability, latency, and effort (tokens × tier weight).
6. **Execute with fallback.** If a route fails, the gateway switches to the same model on its other route (direct ↔ OpenRouter) right away, then moves to the next model.
   - Transient errors are retried with backoff.
   - Auth errors disable that whole transport for the request.
   - Circuit breakers skip routes that keep failing.
   - Each request is capped at 8 attempts and has a deadline.
7. **Record** tokens, latency and auto-evaluated quality in a SQLite ledger.
8. **Learn.** Explicit feedback (or an optional LLM judge) overrides the auto score. The optimizer runs every 50 requests.

## Balanced self-learning

For each model × task pair, the gateway learns a Beta posterior over quality (seeded from the config's quality score), a reliability posterior, and running averages for latency and output size. The `balanced` strategy maximizes:

```
utility = w_q × q_eff × reliability − w_e × effort_norm − w_l × latency_norm
q_eff   = min(q, target) + 0.25 × max(0, q − target)
```

Quality counts fully up to the "good enough" target and only partly above it. Effort is tokens weighted by tier (economy 1, standard 3, premium 8), so the gateway uses heavy models where quality matters and lighter, faster ones where it doesn't. Sampling instead of averaging keeps uncertain models in play. A 10% probe of the next-lower tier gives the optimizer evidence for safe downgrades.

## Self data compression

- **Context.** Stages run lightest-first and stop once the request fits:
  1. Normalize whitespace and remove duplicate lines.
  2. Summarize older turns with an economy model, or drop them with a marker.
  3. Map-reduce long documents chunk by chunk.
  4. Trim from the middle, keeping the head and tail.

  System messages and recent turns are always kept.
- **Storage.** When the database passes its size or row limit, old rows roll up into exact daily totals and the file is vacuumed. In testing, 400k rows went from 103 MB to 13 MB with request and token totals preserved exactly.
- **Network.** GUI API responses are gzip-compressed for mobile data.

## Limits

`python limits.py` stress-tests the gateway and writes [LIMITS.md](LIMITS.md) with measured numbers. Every test passes in both full and lite mode:

- Prompts up to 6M tokens are compressed to fit.
- Conversations up to 2,000 turns are trimmed.
- During a provider outage, every request still gets an answer within at most 2 attempts.
- When every route is down, it fails cleanly within 8 attempts.
- 64 threads put 1,920 requests through one gateway with zero errors.
- On a 400k-row ledger, compaction takes about 4 s.

The main remaining limit: a single process tops out at about 220 requests/sec of gateway overhead, because of SQLite writes and the Python GIL. That's far above what real model latency allows. Run several processes on separate databases to go further.
