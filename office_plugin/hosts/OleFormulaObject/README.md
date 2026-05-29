# OleFormulaObject Host

This folder is reserved for the LaTeXSnipper OLE/COM formula object.

Responsibilities:

- Store LaTeX source, render parameters, numbering data, and schema version inside the embedded object.
- Render itself for Word and PowerPoint using the local TeX rendering pipeline.
- Activate the LaTeXSnipper formula editor on double-click.
- Update the embedded object after editing without replacing unrelated Office content.
- Support scaling, transparent background, theme-aware rendering, and high-DPI redraw.

The OLE object does not require a from-scratch math layout engine. It should first consume a local renderer such as KaTeX, MathJax, or MathLive through the shared rendering contract, then draw the generated output through a native Office-friendly surface.
