# Privacy Policy

LaTeXSnipper does not collect, store, sell, or transmit personal data.

The application may connect to GitHub to check for updates and download release files. It may also connect to model or dependency download sources when the user installs or updates MathCraft OCR dependencies.

Files, screenshots, images, PDFs, handwritten input, and OCR results processed locally by LaTeXSnipper are not uploaded by the application unless the user explicitly configures and uses an external model or API provider.

Automation API is disabled by default and listens only on the local loopback interface unless the user explicitly enables remote access. Local and remote API clients submit data directly to the user's LaTeXSnipper process. Remote access requires a user-generated key and an encrypted tunnel or HTTPS; the application does not relay requests through a LaTeXSnipper-operated cloud service.

Automation API credentials, uploaded images, and recognition text are excluded from service logs. Completed job results are retained only for a bounded in-memory period and are released when they expire or the application exits.

When an external model or API provider is configured by the user, any data sent to that provider is governed by the provider's own privacy policy and the user's configuration.

For questions, contact the project maintainer through GitHub:

https://github.com/SakuraMathcraft/LaTeXSnipper/issues
