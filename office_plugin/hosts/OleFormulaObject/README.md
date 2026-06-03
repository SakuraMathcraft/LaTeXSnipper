# OLE Formula Helper

This folder contains the managed helper used by the native OLE formula object.

Responsibilities:

- Render LaTeX through the local MathJax pipeline without requiring Bridge conversion.
- Treat MathJax SVG as an internal vector intermediate and write EMF/GDI-compatible bytes for the native OLE object.
- Render stored OLE formula payloads for Office containers.

Rules:

- This process is not registered as the COM server. Registration and OLE persistence live in `hosts/OleFormulaObjectNative`.
- SVG/PNG must not be inserted into Office as normal pictures. MathJax SVG is only an internal render intermediate.
- Bridge may be used for screenshot recognition and PowerPoint PNG image insertion, but not for the OLE TeX render path.
