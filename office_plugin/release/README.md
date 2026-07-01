# Office Plugin Release Artifact

This directory contains the locally built Office plugin installer consumed by
the GitHub Release workflow. The workflow validates the versioned filename and
SHA-256 checksum before publishing the installer.

Build a new installer with `office_plugin\installer\build.bat`. The build writes
the versioned executable and adjacent `.sha256` file directly into this
directory.
