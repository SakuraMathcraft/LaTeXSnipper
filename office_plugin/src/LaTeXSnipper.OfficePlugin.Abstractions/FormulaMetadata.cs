namespace LaTeXSnipper.OfficePlugin.Abstractions;

/// <summary>
/// Source and rendering metadata that must travel with a formula object.
/// </summary>
public sealed class FormulaMetadata
{
    public const int CurrentSchemaVersion = 3;

    public FormulaMetadata(
        FormulaIdentity identity,
        string latex,
        FormulaDisplayMode displayMode,
        NumberingMode numberingMode,
        string numberText,
        RenderEngineKind renderEngine,
        int schemaVersion,
        FormulaTypography? typography = null)
    {
        Identity = identity;
        Latex = latex ?? string.Empty;
        DisplayMode = displayMode;
        NumberingMode = numberingMode;
        NumberText = numberText ?? string.Empty;
        RenderEngine = renderEngine;
        SchemaVersion = schemaVersion;
        Typography = typography ?? FormulaTypography.Default;
    }

    public FormulaIdentity Identity { get; }

    public string Latex { get; }

    public FormulaDisplayMode DisplayMode { get; }

    public NumberingMode NumberingMode { get; }

    public string NumberText { get; }

    public RenderEngineKind RenderEngine { get; }

    public int SchemaVersion { get; }

    public FormulaTypography Typography { get; }

    public FormulaMetadata WithTypography(FormulaTypography typography) =>
        new FormulaMetadata(Identity, Latex, DisplayMode, NumberingMode, NumberText,
            RenderEngine, SchemaVersion, typography ?? throw new System.ArgumentNullException(nameof(typography)));
}
