using System;

namespace LaTeXSnipper.OfficePlugin.Abstractions;

/// <summary>
/// Renderer input shared by OMML, image, and OLE object paths.
/// </summary>
public sealed class RenderRequest
{
    public RenderRequest(string latex, FormulaDisplayMode displayMode, RenderEngineKind engine)
    {
        Latex = latex ?? string.Empty;
        DisplayMode = displayMode;
        Engine = engine;
    }

    public string Latex { get; }

    public FormulaDisplayMode DisplayMode { get; }

    public RenderEngineKind Engine { get; }

    public int TargetDpi { get; set; } = 192;

    public string Theme { get; set; } = "light";

    public double FontScale { get; set; } = 1;

    public TimeSpan Timeout { get; set; } = OfficeCommandTimeouts.Render;
}
