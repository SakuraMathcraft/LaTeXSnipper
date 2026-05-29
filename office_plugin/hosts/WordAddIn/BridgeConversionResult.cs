using System;
using System.Collections.Generic;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public sealed class BridgeConversionResult
{
    public BridgeConversionResult(string latex, bool display, string omml, IReadOnlyList<string> warnings)
    {
        Latex = latex ?? string.Empty;
        Display = display;
        Omml = omml ?? string.Empty;
        Warnings = warnings ?? Array.Empty<string>();
    }

    public string Latex { get; }

    public bool Display { get; }

    public string Omml { get; }

    public IReadOnlyList<string> Warnings { get; }
}
