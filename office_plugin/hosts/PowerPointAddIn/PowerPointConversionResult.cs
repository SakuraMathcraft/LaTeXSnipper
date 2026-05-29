using System;
using System.Collections.Generic;

namespace LaTeXSnipper.OfficePlugin.PowerPointAddIn;

public sealed class PowerPointConversionResult
{
    public PowerPointConversionResult(string latex, bool display, string pngBase64, string? svg, IReadOnlyList<string> warnings)
    {
        Latex = latex ?? string.Empty;
        Display = display;
        PngBase64 = pngBase64 ?? string.Empty;
        Svg = svg;
        Warnings = warnings ?? Array.Empty<string>();
    }

    public string Latex { get; }

    public bool Display { get; }

    public string PngBase64 { get; }

    public string? Svg { get; }

    public IReadOnlyList<string> Warnings { get; }
}
