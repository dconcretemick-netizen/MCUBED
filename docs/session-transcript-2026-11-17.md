# MCUBED build session transcript

Conversation between you and Perplexity Computer, November 17–18, 2026 (UTC). Text messages only; tool commands and outputs are left out.

**You:**

Continue Mcubed

**Perplexity Computer:**

I'll look up your prior work on Mcubed to pick up where we left off.

**Perplexity Computer:**

Let me read the latest session fully.

**You:**

Yes please

**Perplexity Computer:**

The repo already has a work-in-progress gateway, so I'll continue from that code instead of starting over.

**Perplexity Computer:**

The dashboard expects a `gui` command and `/api/*` endpoints that the gateway doesn't have yet — that's the missing piece. Checking what the Gateway class already exposes.

**Perplexity Computer:**

Next I'll confirm the existing gateway runs (offline simulation, no keys needed) and check the fields the dashboard expects.

**You:**

Add Nexen code named Mcubed

**Perplexity Computer:**

I'll check your past work for anything called "Nexen" so I know what code you mean.

**Perplexity Computer:**

Nothing called "Nexen" shows up in your history, so I'll finish adding this new code to the MCUBED repo and check with you on Nexen afterward. Testing the new web server now.

**Perplexity Computer:**

All API endpoints work. Next I'll check token protection, the static export, and how the dashboard looks on a phone-sized screen.

**Perplexity Computer:**

The dashboard renders cleanly on a phone screen with no errors. Now I'll write the setup guide and push everything to GitHub.

**You:**

Add native apk support

**Perplexity Computer:**

Someone pushed new commits to MCUBED while I worked, so I'll pull those in first, then add native APK support.

**You:**

Save all to github

**Perplexity Computer:**

Got it — I'll save everything to GitHub, including native APK support. First I'll check the current Android Python setup so the APK can run the gateway on the phone itself.

**Perplexity Computer:**

Chaquopy 17.2 is current and supports this setup. Now I'll rebase onto the latest MCUBED code and add the Android app project.

**Perplexity Computer:**

I'll add two small security fixes to the existing server (constant-time token check, block cross-site POSTs), then build the Android project.

**Perplexity Computer:**

Now writing the Android app: it embeds Python on the phone, runs the gateway locally, and shows the dashboard full-screen.

**You:**

Check ai connections

**You:**

Add doom game files

**Perplexity Computer:**

I'll test the Android entry point locally, then check the AI connections and confirm the Doom game files are included.

**You:**

Verify gui ops

**Perplexity Computer:**

Everything is saved to GitHub. While the APK builds in GitHub Actions, I'll test each dashboard operation in a real browser.

**You:**

Connecting to all available open ai

**Perplexity Computer:**

All dashboard operations passed on phone and desktop with no errors. Checking the Doom screen and the APK build, and looking up the current OpenAI model lineup.

**Perplexity Computer:**

On Android, the lightweight mode currently sends everything through OpenRouter only. I'll also let it call OpenAI directly with your own OpenAI key, and add OpenAI key entry to the app.

**You:**

Set all available ai keys to open

**You:**

Thank you, outside ai in imperitive

**Perplexity Computer:**

Understood — connecting to outside AI providers is the core of MCUBED, and that's what these changes do. I'll run a final test of the direct OpenAI path, then push.

**You:**

Get DeepSeek keys

**Perplexity Computer:**

I can't create a DeepSeek key for you since it's tied to your account, but I'll look up the exact steps while the APK finishes building.

**Perplexity Computer:**

Good news: the first APK build passed in GitHub Actions. DeepSeek's docs also show that the Flash model was renamed to `deepseek-flash`, so I'll update that route before you add your key.

**Perplexity Computer:**

Waiting for the latest APK build to finish.

**You:**

Automated process improvement

**Perplexity Computer:**

Automated process improvement is already built into the gateway; I'll check how it triggers and make it run on a schedule too, so it keeps tuning even when traffic is light.

**You:**

Always improve process and strive for perfect ion

**Perplexity Computer:**

I'll keep that as a standing principle for MCUBED. Checking the latest build result now.

**Perplexity Computer:**

MCUBED is saved to GitHub, and the Android APK now builds automatically. All four builds passed, including the latest one. You can [download the APK here](https://github.com/dconcretemick-netizen/MCUBED/actions/runs/44203880042) under "MCUBED-apk" (sign in to GitHub on your phone first).

## What's in the repo now

- **Android app:** it runs the gateway on the phone itself and shows the dashboard full screen. On first launch it asks for OpenRouter, OpenAI and DeepSeek keys. If you skip, it runs in demo mode with fake replies. You can change keys later from the "AI keys" menu. It needs Android 8 or newer on a 64-bit phone.
- **Dashboard:** I tested every screen in a browser at phone and desktop sizes, with no errors: overview, models, learning, Try it (sending a prompt and rating the reply), storage cleanup, dark mode and Doom. Doom (`game.html`) loads on its own tab and is bundled into the APK.
- **OpenAI:** I added the current models (GPT-6 Astra, GPT-6.1 Sol/Terra, GPT-6 Luna, GPT-5.6 Sol/Terra/Luna) using the [OpenAI model list](https://developers.openai.com/api/docs/models/all) and published prices. With an OpenAI key, the phone app calls OpenAI directly. A new `discover-openai` command finds every chat model your key can use. Two things aren't tested yet: the new model names against a real key, and a real install of the APK on a phone.
- **Automatic improvement:** the router already retuned itself every 50 requests. It now also retunes and cleans up storage every 6 hours while the dashboard or app is running. Every change is logged and undone automatically if quality drops. Each push to GitHub also runs a test before building the APK.
- **Other changes:** a setup guide in the README, and two security fixes for the dashboard. Another session had already added a dashboard server, so I kept that version.

## AI connections

No provider keys are set yet, so all models show "no key" and only demo mode works. Enter keys in the app, or in `.env` on a computer — not in this chat. One OpenRouter key reaches every model, Claude and Gemini included.

## Getting a DeepSeek key

1. Sign in at the [DeepSeek Platform](https://platform.deepseek.com/). This is a different site from chat.deepseek.com.
2. Add funds. The API is pay-as-you-go, and one [user guide](https://www.reddit.com/r/DeepSeek/comments/1tsmjxs/api_keys_how_to_get_and_use_one_without_writing_a/) suggests starting with about $10.
3. Open [API Keys](https://platform.deepseek.com/api_keys) and create a key (it starts with `sk-`).
4. Paste it into MCUBED's "AI keys" menu.

DeepSeek has [renamed its Flash model](https://api-docs.deepseek.com/quick_start/your_first_api_call.md) to `deepseek-flash`, and I've updated MCUBED to use the new name.

I couldn't find anything called "Nexen" in your past work, so I treated that request as adding this code to MCUBED. If Nexen is a separate project or file, tell me where it lives and I'll add it.

**You:**

Auto add all available repository

**Perplexity Computer:**

I'll check which repositories are in your GitHub account so I can see what can be added to MCUBED.

**Perplexity Computer:**

Testing against your real GitHub account now (registry sync, clone, and the dashboard card).

**Perplexity Computer:**

The sandbox's GitHub login works only through the `gh` tool, so my direct API test was rejected. I'll test the sync logic with a simulated GitHub response and a local test repo instead.

**Perplexity Computer:**

The test's fake GitHub response had a bug, not the feature. Fixing the test and rerunning.

**Perplexity Computer:**

The repository card works on a phone screen. Last step: add a GitHub token slot to the Android app, update the docs, and push.

**Perplexity Computer:**

Another session pushed to MCUBED again. Checking what changed before I merge.

**Perplexity Computer:**

Merged cleanly. Running the other session's new test suite (`limits.py`) plus my checks before pushing.

**Perplexity Computer:**

All 12 stress tests pass on the merged code. Pushing and confirming the APK build.

**Perplexity Computer:**

MCUBED now adds every GitHub repository your token can reach, automatically, and the change is pushed to GitHub. The [new APK built successfully](https://github.com/dconcretemick-netizen/MCUBED/actions/runs/44204574060).

## How it works

- **Automatic:** while the dashboard or Android app is running, it checks your GitHub account every 6 hours. Any repository you own, collaborate on, or reach through an organization is added to a local list.
- **On your phone:** the Storage tab has a Repositories card with a "Sync now" button. In the app, the "AI keys" menu now has a GitHub token field.
- **On a computer:** `python gateway.py repos` updates the list. Adding `--clone repos` also downloads every repository and pulls in their latest changes.
- **Safety:** the token is never saved inside the downloaded repositories, archived repositories are skipped, and the list itself is never uploaded to GitHub.

## What I tested

Your account currently has just one repository, MCUBED. The sandbox's GitHub login only works through GitHub's command-line tool, so it couldn't run MCUBED's own GitHub lookup. Instead I tested with a simulated GitHub account and a local test repository. Adding, downloading, updating and the phone card all worked, and the token was never written to disk. It hasn't run against your real account yet.

## Merged with your other session

Another session pushed new work while I was building this, including a stress-test suite and a Termux setup script. I combined both sets of changes, fixed two small file conflicts, and all 12 stress tests pass on the combined code.

To turn it on, create a read-only fine-grained token in GitHub under Settings → Developer settings → Personal access tokens. Then enter it in the app's "AI keys" menu, or set it as `GITHUB_TOKEN` in `.env`. Don't paste it here.

**You:**

Add my GitHub token and run the repository sync now

**Perplexity Computer:**

I'll run the sync now using the GitHub access already connected in this workspace, so you don't need to share a token here. First I'll let MCUBED use that connection directly, since it can't read the token itself.

**Perplexity Computer:**

The data folder didn't exist yet. I'll make MCUBED create it automatically and rerun.

**Perplexity Computer:**

The sync worked: it found and downloaded your one repository, MCUBED. Running it a second time to check updates, then pushing the change.

**You:**

Add apk support

**You:**

Remove financial aspects of program

**Perplexity Computer:**

I'll finish checking the build, then map every money-related part of MCUBED (prices, costs, budgets, savings, spend charts) before removing them.

**You:**

Add solitaire

**Perplexity Computer:**

I'll do both: remove the money features first, then add a Solitaire game tab next to Doom. Reading every cost-related part of the gateway now.

**You:**

Yes

**Perplexity Computer:**

Continuing with the money removal, then Solitaire.

**You:**

Add wine support

**Perplexity Computer:**

Noted, I'll add Wine support (for running Windows programs) after finishing the money removal and Solitaire. Continuing with the storage layer now.

**Perplexity Computer:**

Now the learner, compressor, optimizer and planner sections.

**Perplexity Computer:**

The core gateway and model config are converted. Running the simulation to make sure routing still learns and improves.

**Perplexity Computer:**

The gateway runs cleanly with no money fields. Next, the dashboard.

**Perplexity Computer:**

Dashboard is clean; Doom and the Termux setup had no money features. Updating the README.

**Perplexity Computer:**

All 10 stress tests pass, including the check that the router still learns to use lighter models. I'm regenerating the full limits report in the background while I build Solitaire.

**You:**

Run as as ai model

**Perplexity Computer:**

Writing the Solitaire game now: classic Klondike with tap-to-move, drag-and-drop, undo, draw-1/draw-3 and auto-finish, styled like the dashboard.

**Perplexity Computer:**

Now wiring Solitaire into the dashboard tabs, the server, the offline cache and the Android build.

**You:**

Allow open ai

**You:**

Yes

**Perplexity Computer:**

Got it. OpenAI direct calls are already supported, and the OpenAI-compatible "mcubed" model endpoint is next on my list. Full limits report: 10/10 passed. Testing Solitaire in the browser now.

**Perplexity Computer:**

Taps, drag, undo and draw mode all work at phone and desktop sizes, with no errors. Checking the screenshots.

**Perplexity Computer:**

Two layout fixes needed: on desktop the stacked cards hide their suit symbols, and on phones the toolbar wraps onto two lines. Fixing both.

**Perplexity Computer:**

Both layouts look right now. One small tweak gives the draw-3 fan more room on phones so "10" isn't cut off. Then I'll add the OpenAI-compatible "mcubed" model endpoint.

**You:**

Re configure as an open ai on main screen

**Perplexity Computer:**

The OpenAI-compatible endpoint is in. Testing it with curl and the official OpenAI Python client.

**You:**

Try out

**Perplexity Computer:**

I'll get it ready for you to try: finish the new chat main screen, push it, and publish an APK you can install. First, a check with the official OpenAI client library.

**Perplexity Computer:**

The official OpenAI client works against MCUBED: plain replies, streaming, and errors. Now the main screen chat.

**You:**

Add webbrowser

**You:**

Thank you!

**Perplexity Computer:**

You're welcome. The chat main screen passes every check at phone and desktop sizes. Checking how it looks.

**You:**

Perfect solution, we work well together

**Perplexity Computer:**

Thanks, I'm enjoying it too. The page reader works, search works, and local/private network addresses are blocked. One quick check on why example.com returned no links.

**Perplexity Computer:**

That page simply has no links now, so the reader is correct. Building the Web tab and the combined Games tab.

**You:**

Save all

**Perplexity Computer:**

Saving everything to GitHub now. I'll run a quick check first so nothing broken gets pushed.

**Perplexity Computer:**

That failure is in my test script (it typed into the Web tab before switching to it), not in the app. Fixing the script and rerunning.

**Perplexity Computer:**

The reader works, but it jumped past the address bar and showed the site's menu links. Two small fixes: scroll to the top and skip navigation menus. Then I'll commit.

**Perplexity Computer:**

That site builds its menu without standard menu tags. I'll have the reader prefer the page's main article content when there is one.

**Perplexity Computer:**

Wikipedia and most sites read cleanly now; a few sites put their menus inside the article itself, so a bit of menu text can still slip through. Running the full regression checks, then committing.

**Perplexity Computer:**

All checks pass. Adding README sections for the OpenAI-compatible API, the chat screen and the web browser, then pushing.

**Perplexity Computer:**

Saved to GitHub as commit c84344f. Next up: the in-app browser screen for Android, then Wine support.

**You:**

Create news tab with as Fair and honest news as possible

**Perplexity Computer:**

Android now opens web pages in the in-app browser. Next, I'm checking current Wine install options for each platform and which news outlets still publish feeds.

**Perplexity Computer:**

Most feeds work. Now looking up the current AllSides rating for each working outlet.

---

Later messages in this session:

**Perplexity Computer:**

Winlator is the established way to run Windows apps on Android, so the Android app will point there instead of bundling Wine. For News, outlet lean ratings shift over time, so I'll show each outlet's label alongside a link to its current rating. Checking which outlet feeds actually work.

**You:**

Amazing! Do you have a salutation?

**Perplexity Computer:**

Thanks. I don't have a set salutation, but "Hello, I'm Perplexity Computer" works. If you want one for MCUBED, I can put a greeting on the chat screen, something like "Good morning. What can MCUBED help with?" that changes with the time of day. Back to the News tab now.

**Perplexity Computer:**

The ratings are verified. The default feed list is symmetric: 1 Left, 4 Lean Left, 4 Center, 4 Lean Right and 1 Right outlet, plus DW as an unrated international source. Next I'll commit the pending Android browser work.

**Perplexity Computer:**

Grouping is clean now. The WSJ feed stopped updating in January 2025, so I replaced it with Newsweek, which AllSides also rates Center. Eight tabs won't fit at phone width, so Overview, Models, Learning and Storage are grouped under one Stats tab, leaving Chat, News, Web, Games and Stats.

**Perplexity Computer:**

The UI checks out at both widths with no console errors. The regression suite passes 10/10. News tab and Wine support committed and pushed.

**You:**

Add update tab that updates to the newest file

**Perplexity Computer:**

I'll add an Update tab that checks GitHub for the newest MCUBED, shows what changed, and installs it with one tap, keeping a backup so you can roll back. On a computer or Termux it updates the files in place and restarts; in the Android app it downloads the newest APK and opens the installer.

**Perplexity Computer:**

The Android build signs each APK with a throwaway debug key, so an update would fail to install over the previous version. I set up one permanent signing key, stored as an encrypted GitHub secret, so every future APK installs as an update.

**You:**

Add tetris to games

**Perplexity Computer:**

I'll add Tetris to the Games tab after finishing the Update tab. Update and rollback both work in testing.

**You:**

Thank you for telling me as we go, I appreciate it, if you have suggestions on my work I would like to hear it

**Perplexity Computer:**

Thanks, I'm glad the updates help. A few suggestions from working in the code:

- Back up the new signing key. Every Android update now depends on it. GitHub keeps the copy encrypted and nobody can read it back out, so it's worth also saving a copy somewhere safe.
- Split gateway.py. It's about 2,700 lines now. Separate files for routing, news, web, update and server would make each change safer and easier to review.
- Run the tests on every push. CI only runs a quick simulation right now. Adding the limits.py checks and a short browser test of the dashboard would catch problems before the APK ships.
- Keep a short roadmap. A one-page list of what's core and what's extra helps decide where polish matters most.
- Use version tags. Tagging a version (v0.1.0, v0.2.0) when something feels stable gives you known-good points to go back to.

**You:**

Perfect. Save this text transcript
