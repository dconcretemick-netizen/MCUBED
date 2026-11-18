# MCUBED security

MCUBED has one source code editor: the repository owner, [@dconcretemick-netizen](https://github.com/dconcretemick-netizen), working with Perplexity Computer under that same account. No other collaborators, deploy keys, webhooks or forks are allowed.

## How code is protected

| Layer | Protection |
| --- | --- |
| Repository | Private, single collaborator, no deploy keys or webhooks. Dependabot security alerts and automatic security fixes are on. |
| Build | GitHub Actions runs only GitHub-owned actions plus `gradle/actions/setup-gradle` and `softprops/action-gh-release`, each pinned to a full commit SHA (pinning is enforced by a repository setting). The signing key is never given to pull request builds. |
| Signing | Every APK is signed with one permanent MCUBED key (v1, v2 and v3 signatures). The key lives only in GitHub Actions secrets and an offline backup. CI fails if an APK is signed by any other key. |
| Android install | Android refuses to install an update signed by a different key, so nobody else can replace the app. |
| In-app updates | Before installing, the app checks the APK's SHA-256 against GitHub's digest, checks the signing certificate against the MCUBED key built into the code, and refuses any build that does not continue from the installed version. |
| Desktop updates | Git copies update with `git pull --ff-only`. Downloaded copies check every file against GitHub's hash, require the new commit to build on the installed one, compile-check before replacing anything, and keep backups for rollback. |

MCUBED signing certificate SHA-256:
`53:B5:7E:B8:25:1C:65:...` (the full value is shown on the [MCUBED install](https://github.com/dconcretemick-netizen/MCUBED/releases/tag/latest) page and stored in `gateway.py` as `MCUBED_CERT_SHA256`).

## Keep the account safe

The repository is only as safe as the GitHub account that owns it.

- Keep two-factor authentication on, preferably with a passkey or security key.
- Give the MCUBED app a fine-grained token with read-only Contents access to this one repository, so a lost phone cannot push code.
- Review [tokens](https://github.com/settings/tokens), [SSH keys](https://github.com/settings/keys), [authorized apps](https://github.com/settings/applications) and [security log](https://github.com/settings/security-log) now and then, and remove anything you do not recognize.
- Keep the offline backup of the signing key somewhere safe. Anyone with it could sign an APK that Android accepts as MCUBED.

## Reporting a problem

Open a private issue in this repository or contact the owner directly.
