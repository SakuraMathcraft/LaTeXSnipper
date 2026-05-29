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
        int schemaVersion)
    {
        Identity = identity;
        Latex = latex ?? string.Empty;
        DisplayMode = displayMode;
        NumberingMode = numberingMode;
        NumberText = numberText ?? string.Empty;
        RenderEngine = renderEngine;
        SchemaVersion = schemaVersion;
    }

    public FormulaIdentity Identity { get; }

    public string Latex { get; }

    public FormulaDisplayMode DisplayMode { get; }

    public NumberingMode NumberingMode { get; }

    public string NumberText { get; }

    public RenderEngineKind RenderEngine { get; }

    public int SchemaVersion { get; }
}
