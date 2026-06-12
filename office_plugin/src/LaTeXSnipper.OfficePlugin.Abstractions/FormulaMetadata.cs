namespace LaTeXSnipper.OfficePlugin.Abstractions;

/// <summary>
/// Source and rendering metadata that must travel with a formula object.
/// </summary>
public sealed class FormulaMetadata
{
    public FormulaMetadata(
        FormulaIdentity identity,
        string latex,
        FormulaDisplayMode displayMode,
        NumberingMode numberingMode,
        string numberText,
        RenderEngineKind renderEngine,
        int schemaVersion,
        string fontColor = "#000000",
        FormulaFontStyle fontStyle = FormulaFontStyle.TeX,
        double fontScale = 1)
    {
        Identity = identity;
        Latex = latex ?? string.Empty;
        DisplayMode = displayMode;
        NumberingMode = numberingMode;
        NumberText = numberText ?? string.Empty;
        RenderEngine = renderEngine;
        SchemaVersion = schemaVersion;
        FontColor = string.IsNullOrWhiteSpace(fontColor) ? "#000000" : fontColor;
        FontStyle = fontStyle;
        FontScale = fontScale > 0 ? fontScale : 1;
    }

    public FormulaIdentity Identity { get; }

    public string Latex { get; }

    public FormulaDisplayMode DisplayMode { get; }

    public NumberingMode NumberingMode { get; }

    public string NumberText { get; }

    public RenderEngineKind RenderEngine { get; }

    public int SchemaVersion { get; }

    public string FontColor { get; }

    public FormulaFontStyle FontStyle { get; }

    public double FontScale { get; }
}
