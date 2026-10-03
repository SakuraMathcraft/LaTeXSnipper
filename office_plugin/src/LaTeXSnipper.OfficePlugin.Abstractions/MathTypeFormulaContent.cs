namespace LaTeXSnipper.OfficePlugin.Abstractions;

public sealed class MathTypeFormulaContent
{
    public MathTypeFormulaContent(string mathMl, double fontSizePoints)
    {
        MathMl = mathMl;
        FontSizePoints = FormulaFontSize.Validate(fontSizePoints);
    }

    public string MathMl { get; }
    public double FontSizePoints { get; }
}
