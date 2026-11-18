namespace LaTeXSnipper.OfficePlugin.Abstractions;

public sealed class MathTypeFormulaContent
{
    public MathTypeFormulaContent(string mathMl, double fontSizePoints, FormulaDisplayMode displayMode,
        string? originalLatex = null, FormulaTypography? originalTypography = null)
    {
        MathMl = mathMl;
        FontSizePoints = FormulaFontSize.Validate(fontSizePoints);
        DisplayMode = displayMode;
        OriginalLatex = originalLatex;
        OriginalTypography = originalTypography;
    }

    public string MathMl { get; }
    public double FontSizePoints { get; }
    public FormulaDisplayMode DisplayMode { get; }
    public string? OriginalLatex { get; }
    public FormulaTypography? OriginalTypography { get; }
}
