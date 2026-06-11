namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public sealed class WordFormulaFormat
{
    public WordFormulaFormat(
        string color,
        LaTeXSnipper.OfficePlugin.Abstractions.FormulaFontStyle fontStyle,
        double scale,
        int weightPercent)
    {
        Color = string.IsNullOrWhiteSpace(color) ? "#000000" : color;
        FontStyle = fontStyle;
        Scale = System.Math.Max(0.5, System.Math.Min(5, scale));
        WeightPercent = weightPercent is 5 or 10 or 15 ? weightPercent : 0;
    }

    public string Color { get; }

    public LaTeXSnipper.OfficePlugin.Abstractions.FormulaFontStyle FontStyle { get; }

    public double Scale { get; }

    public int WeightPercent { get; }
}
