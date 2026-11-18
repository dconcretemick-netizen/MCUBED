# MCUBED install

The newest MCUBED is always at the **[MCUBED install](https://github.com/dconcretemick-netizen/MCUBED/releases/tag/latest)** page. It is rebuilt automatically every time `main` changes, and the links below never change.

| Device | Direct link |
| --- | --- |
| Android phone or tablet | [MCUBED.apk](https://github.com/dconcretemick-netizen/MCUBED/releases/download/latest/MCUBED.apk) |
| Windows, Mac or Linux | [MCUBED-desktop.zip](https://github.com/dconcretemick-netizen/MCUBED/releases/download/latest/MCUBED-desktop.zip) |

## Android

1. Sign in to GitHub in your phone's browser, then open the MCUBED.apk link.
2. When Android asks, allow your browser to install apps, then tap Install.
3. After that, the app's Update tab installs new versions for you.

If Android says the app conflicts with an existing package, you have an older build signed with a temporary key. Uninstall it once, then install again. Every build since then uses the same permanent key.

## If Android says the file is unsafe

Android and Chrome warn about every APK that does not come from the Play Store. That warning is about where the file came from, not what is in it. To install MCUBED safely:

1. Check that the file is genuine: the [MCUBED install](https://github.com/dconcretemick-netizen/MCUBED/releases/tag/latest) page lists the APK's SHA-256 and the MCUBED signing certificate. Only download from that page.
2. In Chrome, tap Download anyway (or Keep).
3. If Play Protect shows "Unsafe app blocked" or "Unknown app", tap More details, then Install anyway. You can also tap Scan app, which sends it to Google for a check.
4. After the first install, updates come through the app's Update tab, which checks the signature and SHA-256 for you.

The permanent way to remove the warning is to register the app with Google's [Android developer verification](https://developer.android.com/developer-verification). The free limited distribution account needs only an email address and covers up to 20 devices. Google plans to require registration for sideloaded apps on all certified devices in 2027.

## Windows, Mac or Linux

1. Install Python 3.10 or newer from [python.org](https://www.python.org/downloads/).
2. Download MCUBED-desktop.zip and unzip it.
3. Open a terminal in the `MCUBED` folder and run `python gateway.py gui`, then open http://localhost:8765 in a browser.
4. The Update tab keeps it current.

## Why the links ask you to sign in

The repository is private, so GitHub only serves these files to signed-in accounts that have access. To share MCUBED with anyone, make the repository public or add people as collaborators.
