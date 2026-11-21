# MHexeract security

MHexeract has one source code editor: the repository owner, [@dconcretemick-netizen](https://github.com/dconcretemick-netizen), working with Perplexity Computer under that same account. No other collaborators, deploy keys, webhooks or forks are allowed.

## How code is protected

| Layer | Protection |
| --- | --- |
| Repository | Public to read, but only the owner can write: single collaborator, no deploy keys or webhooks. Anyone can read or fork the code, but a fork cannot change this repository. |
| Main branch | A ruleset blocks force pushes and deletion of `main`, so published history cannot be rewritten. |
| Outside pull requests | Pull requests from anyone else never run Actions until the owner approves them, never receive secrets, and can only be merged by the owner. |
| Secret scanning | GitHub secret scanning and push protection are on: a push containing an API key or token is blocked. |
| Security updates | Dependabot alerts and security updates are on for Python packages, the Android Gradle build and GitHub Actions (`.github/dependabot.yml`). A fix arrives as a pull request labeled `security`, and nothing merges until the owner approves it. |
| Build | GitHub Actions runs only GitHub-owned actions plus `gradle/actions/setup-gradle` and `softprops/action-gh-release`, each pinned to a full commit SHA (pinning is enforced by a repository setting). The signing key is never given to pull request builds. |
| Signing | Every APK is signed with one permanent MHexeract key (v1, v2 and v3 signatures). The key lives only in GitHub Actions secrets and an offline backup. CI fails if an APK is signed by any other key. |
| Android install | Android refuses to install an update signed by a different key, so nobody else can replace the app. |
| In-app updates | Before installing, the app checks the APK's SHA-256 against GitHub's digest, checks the signing certificate against the MHexeract key built into the code, and refuses any build that does not continue from the installed version. |
| Desktop updates | Git copies update with `git pull --ff-only`. Downloaded copies check every file against GitHub's hash, require the new commit to build on the installed one, compile-check before replacing anything, and keep backups for rollback. |

MHexeract signing certificate SHA-256:
`53:B5:7E:B8:25:1C:65:...` (the full value is shown on the [MCUBED install](https://github.com/dconcretemick-netizen/MCUBED/releases/tag/latest) page and stored in `gateway.py` as `MCUBED_CERT_SHA256`).

## Keep the account safe

The repository is only as safe as the GitHub account that owns it.

- Keep two-factor authentication on, preferably with a passkey or security key.
- Updates no longer need a GitHub token. If you add one for repository sync, make it a fine-grained token with read-only access, so a lost phone cannot push code.
- Review [tokens](https://github.com/settings/tokens), [SSH keys](https://github.com/settings/keys), [authorized apps](https://github.com/settings/applications) and [security log](https://github.com/settings/security-log) now and then, and remove anything you do not recognize.
- Keep the offline backup of the signing key somewhere safe. Anyone with it could sign an APK that Android accepts as MHexeract.

## Reporting a problem

Use the private [Report a vulnerability](https://github.com/dconcretemick-netizen/MCUBED/security/advisories/new) form. Please do not open a public issue for security problems.
