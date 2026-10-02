using System;
using System.Linq;
using System.Xml.Linq;

namespace LaTeXSnipper.OfficePlugin.Rendering;

public static class MathTypeMathMl
{
    public static string PrepareForImport(string mathMl)
    {
        XNamespace ns = "http://www.w3.org/1998/Math/MathML";
        var root = XDocument.Parse(mathMl).Root;
        if (root?.Name != ns + "math")
            throw new ArgumentException("MathType 转换需要完整的 MathML 公式。", nameof(mathMl));
        // MathJax emits an empty closing operator for one-sided fences (cases,
        // \left...\right.). MathType rejects that operator with SDK -9999.
        root.Descendants(ns + "mo").Where(node => !node.HasElements && string.IsNullOrWhiteSpace(node.Value)).Remove();
        return root.ToString(SaveOptions.DisableFormatting);
    }
}
