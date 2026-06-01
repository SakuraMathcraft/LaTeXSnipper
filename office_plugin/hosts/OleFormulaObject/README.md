# OleFormulaObject Host

This folder owns the LaTeXSnipper OLE/COM formula object.

Responsibilities:

- Implement an out-of-proc COM/OLE local server so both 32-bit and 64-bit Office can activate the same object model.
- Store LaTeX source, render parameters, numbering data, object identity, renderer version, and schema version inside the embedded object.
- Render itself for Word and PowerPoint through the local MathJax pipeline without requiring Bridge conversion.
- Treat MathJax SVG as an internal vector intermediate, then expose an Office-safe OLE presentation through EMF/GDI-compatible drawing.
- Keep formulas clear when zoomed, printed, exported, or resized.
- Activate the LaTeXSnipper formula editor on double-click.
- Update the embedded object in place after editing without replacing unrelated Office content.
- Support transparent background, theme-aware rendering, baseline metrics, high-DPI redraw, and deterministic cache invalidation.

Rules:

- OLE is the default formula insertion backend.
- Bitmap-only formula insertion is forbidden for this backend.
- SVG/PNG must not be inserted into Office as normal pictures. The inserted content must be the OLE object.
- Enhanced Metafile or direct GDI/vector OLE drawing is the preferred Office presentation layer for Office 2016 compatibility.
- `MathJaxSvgRenderer` is an intermediate renderer only. It must feed an OLE presentation renderer before Word or PowerPoint insertion.
- MathJax is the default TeX renderer because complex TeX support is more important than minimal renderer size.
- Bridge may be used for screenshot recognition and explicit legacy compatibility backends, but not for the OLE TeX render path.
- The embedded object payload is the source of truth; cached render output is derived data.
