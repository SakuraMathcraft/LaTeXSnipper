namespace LaTeXSnipper.OfficePlugin.Abstractions;

public enum FormulaDisplayMode
{
    Inline,
    Display
}

public enum NumberingMode
{
    None,
    Automatic,
    Manual
}

public enum RenderEngineKind
{
    Omml,
    Image,
    MathJaxSvg
}

public enum FormulaInsertionBackend
{
    Ole,
    WordOmml,
    PowerPointPng
}

public enum OlePresentationKind
{
    EnhancedMetafile
}
