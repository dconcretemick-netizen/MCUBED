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

## Windows, Mac or Linux

1. Install Python 3.10 or newer from [python.org](https://www.python.org/downloads/).
2. Download MCUBED-desktop.zip and unzip it.
3. Open a terminal in the `MCUBED` folder and run `python gateway.py gui`, then open http://localhost:8765 in a browser.
4. The Update tab keeps it current.

## Why the links ask you to sign in

The repository is private, so GitHub only serves these files to signed-in accounts that have access. To share MCUBED with anyone, make the repository public or add people as collaborators.
