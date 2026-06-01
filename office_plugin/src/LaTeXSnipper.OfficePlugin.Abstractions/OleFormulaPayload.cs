namespace LaTeXSnipper.OfficePlugin.Abstractions;

public sealed class OleFormulaPayload
{
    public const int CurrentSchemaVersion = 1;

    public OleFormulaPayload(
        FormulaIdentity identity,
        string latex,
        FormulaDisplayMode displayMode,
        NumberingMode numberingMode,
        string numberText,
        string rendererVersion,
        double widthPoints,
        double heightPoints,
        double baselinePoints)
    {
        Identity = identity;
        Latex = latex ?? string.Empty;
        DisplayMode = displayMode;
        NumberingMode = numberingMode;
        NumberText = numberText ?? string.Empty;
        RendererVersion = rendererVersion ?? string.Empty;
        WidthPoints = widthPoints;
        HeightPoints = heightPoints;
        BaselinePoints = baselinePoints;
    }

    public int SchemaVersion { get; } = CurrentSchemaVersion;

    public FormulaIdentity Identity { get; }

    public string Latex { get; }

    public FormulaDisplayMode DisplayMode { get; }

    public NumberingMode NumberingMode { get; }

    public string NumberText { get; }

    public RenderEngineKind RenderEngine { get; } = RenderEngineKind.MathJaxSvg;

    public string RendererVersion { get; }

    public double WidthPoints { get; }

    public double HeightPoints { get; }

    public double BaselinePoints { get; }
}
