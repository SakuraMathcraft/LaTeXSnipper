# Office Plugin Release Artifact

This directory contains the locally built Office plugin installer consumed by
the GitHub Release workflow. The workflow validates the versioned filename and
SHA-256 checksum before publishing the installer.

Build a new installer with `Office_plugin\windows\installer\build.bat`. The build writes
`LaTeXSnipperOffice_<version>_windows_x86_64.exe` and its adjacent `.sha256` file
directly into this directory.
