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
    LocalTex,
    Image,
    MathJaxSvg
}

public enum FormulaInsertionBackend
{
    Ole,
    WordOmml,
    PowerPointCompatibility
}

public enum OlePresentationKind
{
    EnhancedMetafile,
    DirectGdi
}

public enum OfficeHostKind
{
    Word,
    PowerPoint
}
