# PowerPointAddIn Host

This folder is reserved for the PowerPoint VSTO add-in.

Responsibilities:

- Register a persistent LaTeXSnipper Ribbon in PowerPoint.
- Insert compatibility formula images rendered from LaTeX.
- Insert, load, update, and delete LaTeXSnipper-managed formula objects.
- Keep PowerPoint numbering intentionally simpler than Word numbering.

Feature boundary:

- Inline and display formulas are inserted as high-DPI images cropped to the formula bounds. The image renderer must trim transparent padding before insertion so the slide object size matches the visible formula.
- Numbered formulas are inserted as a layout object containing the formula image and the user-provided number. Numbered formulas are not cropped as a single formula image, because the number and formula require stable alignment.
- Automatic numbering in PowerPoint is not a Word-style document field. If enabled, it only increments from the current session counter and cannot safely renumber arbitrary slides. For predictable documents, users must manually fill the number text for numbered formulas.
- Renumber All, document-wide automatic numbering repair, and Word-style numbered table normalization are out of scope for the first PowerPoint implementation.
- OLE object insertion should be added only after the Word OLE identity model is stable.

First implementation step:

1. Create the VSTO PowerPoint Add-in project with Visual Studio Office tooling.
2. Reference the shared `src/` contracts.
3. Implement high-DPI cropped image insertion against the shared Bridge/rendering contracts.
4. Implement manual-number numbered formula image layout.
5. Add OLE object insertion only after Word OLE object identity is stable.
