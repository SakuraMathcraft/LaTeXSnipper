# Office Plugin Release Artifact

This directory contains the locally built Office plugin installer consumed by
the GitHub Release workflow. The workflow validates the versioned filename and
SHA-256 checksum before publishing the installer.

Build a new installer with `office_plugin\installer\build.bat`, copy the
versioned executable from `office_plugin\dist`, and update its adjacent
`.sha256` file in the same commit.
