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

## Android app (native APK)

The `android/` project packages the gateway as a real Android app. It embeds Python with [Chaquopy](https://chaquo.com/chaquopy/), runs the gateway on `127.0.0.1` inside the app, and shows the dashboard (including the Doom tab) full screen.

- Get the APK: open the repo's Actions tab, choose the latest "Build Android APK" run, and download `MCUBED-apk`. Pushing a tag like `v0.1.0` also attaches the APK to a GitHub Release.
- First launch asks for OpenRouter, OpenAI and DeepSeek keys (any or all), stored only on the device. Choose "Demo mode" to try it with simulated replies. Change keys later from the "AI keys" menu. On Android, OpenAI and DeepSeek are called directly; Claude and Gemini go through OpenRouter.
- Requires Android 8.0+ on a 64-bit device. Release builds are signed with a debug key; configure your own keystore before publishing to the Play Store.
- Build locally: `cd android && gradle assembleRelease` (JDK 17, Android SDK, Python 3.13 on PATH).

## Android (Termux)

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
| `gui [--host --port --token]` | Serve the web dashboard and Doom game |
| `simulate [--n 300]` | Offline demo with synthetic traffic |

## Security

- The dashboard listens on `127.0.0.1` by default. Binding to `0.0.0.0` uses `--token` (or `GATEWAY_GUI_TOKEN`), generating one if missing; open `/?token=...` once and a cookie is set.
- Cross-origin POSTs are rejected. API keys stay in environment variables and never reach the browser.
- Configure models, prices and budgets in `models.json`.
