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
    Image
}

public enum OfficeHostKind
{
    Word,
    PowerPoint
}
