# Privacy Policy

LaTeXSnipper has no built-in analytics or telemetry and does not sell personal data. Settings, recognition history, favorites, logs, and temporary processing files are stored locally; see the [user data storage map](docs/user_data_storage.md) for locations and cleanup.

The application may connect to GitHub to check for updates and download release files. Complete desktop installers include Python, inference dependencies, and model weights; installed desktop recognition does not download these resources. Source-mode recognition and the standalone MathCraft OCR library may download missing models from the sources declared in their model manifest. Exported standalone HTML uses a MathJax CDN when the recipient opens the file; the desktop preview uses bundled resources.

Files, screenshots, images, PDFs, handwritten input, and OCR results processed locally by LaTeXSnipper are not uploaded to a project-operated service. Recognition input is sent to an external model or API provider only when the user configures and uses that provider. Authorized Automation API clients receive the results of their jobs; a local client can also explicitly subscribe to the next desktop recognition result.

Automation API is disabled by default and listens only on the local loopback interface unless the user explicitly enables remote access. Local and remote API clients submit data directly to the user's LaTeXSnipper process. Remote access requires a user-generated key and an encrypted tunnel or HTTPS; the application does not relay requests through a LaTeXSnipper-operated cloud service.

Automation API credentials, uploaded images, and recognition text are excluded from service logs. Completed job results are retained only for a bounded in-memory period and are released when they expire or the application exits.

When an external model or API provider is configured by the user, any data sent to that provider is governed by the provider's own privacy policy and the user's configuration.

For questions, contact the project maintainer through GitHub:

https://github.com/SakuraMathcraft/LaTeXSnipper/issues
