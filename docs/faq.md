# FAQ

## Where can I download LaTeXSnipper?

Download the latest installers from the [GitHub Releases](https://github.com/SakuraMathcraft/LaTeXSnipper/releases) page.

## Where is the full user manual?

The full PDF user manual is distributed as a release asset when available.

## Which platforms are supported?

LaTeXSnipper provides release builds for Windows, Linux, and macOS.

## Does LaTeXSnipper require an internet connection?

Core editing and local recognition workflows are designed to work locally after the required dependencies and models are installed. Some optional downloads, updates, and CDN fallbacks require network access.

## Where are models and dependency files stored?

Windows uses the packaged dependency environment. Linux and macOS store runtime dependency files under the user's application state directory, such as `~/.latexsnipper/deps`.

## Why do Linux and macOS need Python 3?

The packaged app itself does not run on the user's system Python. Linux and macOS use system Python 3.10+ only to create the isolated optional dependency environment under `~/.latexsnipper/deps`. Linux `.deb` installs declare `python3` and `python3-venv`; macOS users should install Python with Homebrew (`brew install python`) or the official python.org macOS installer if no usable `python3` is available.
