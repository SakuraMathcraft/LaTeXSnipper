# OLE Formula Helper

This folder contains the managed helper used by the native OLE formula object.

Responsibilities:

- Render LaTeX through the local MathJax pipeline without requiring Bridge conversion.
- Treat MathJax SVG as an internal vector intermediate and write EMF/GDI-compatible bytes for the native OLE object.
- Open the payload editor requested by the native OLE object during double-click activation.

Rules:

- This process is not registered as the COM server. Registration and OLE persistence live in `hosts/OleFormulaObjectNative`.
- SVG/PNG must not be inserted into Office as normal pictures. MathJax SVG is only an internal render intermediate.
- Bridge may be used for screenshot recognition and explicit legacy compatibility backends, but not for the OLE TeX render path.
