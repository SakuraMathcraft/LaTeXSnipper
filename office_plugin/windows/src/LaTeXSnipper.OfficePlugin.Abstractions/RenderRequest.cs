using System;

namespace LaTeXSnipper.OfficePlugin.Abstractions;

/// <summary>
/// Renderer input shared by OMML, image, and OLE object paths.
/// </summary>
public sealed class RenderRequest
{
    public RenderRequest(string latex, FormulaDisplayMode displayMode, RenderEngineKind engine, FormulaTypography typography)
    {
        Latex = latex ?? string.Empty;
        DisplayMode = displayMode;
        Engine = engine;
        Typography = typography ?? throw new ArgumentNullException(nameof(typography));
    }

    public string Latex { get; }

    public FormulaDisplayMode DisplayMode { get; }

    public RenderEngineKind Engine { get; }

    public FormulaTypography Typography { get; }

    public TimeSpan Timeout { get; set; } = OfficeCommandTimeouts.Render;
}
