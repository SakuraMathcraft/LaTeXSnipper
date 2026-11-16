using System;
using System.Text.RegularExpressions;

namespace LaTeXSnipper.OfficePlugin.Abstractions;

/// <summary>Complete immutable style intent. Actual font selection and diagnostics belong to rendering.</summary>
public sealed class FormulaTypography : IEquatable<FormulaTypography>
{
    /// <summary>Typography contract version, separate from the enclosing formula metadata schema.</summary>
    public const int CurrentVersion = 1;

    /// <summary>Built-in style used when creating defaults; it does not overwrite existing snapshots.</summary>
    public static FormulaTypography Default { get; } = new FormulaTypography(
        "mathjax-tex", null, "Microsoft YaHei", FormulaMathStyle.Automatic, 12, "#000000");

    /// <summary>Creates a validated snapshot. A null number family means following the symbol font.</summary>
    public FormulaTypography(string symbolFontId, string? numberFontFamily, string cjkFontFamily,
        FormulaMathStyle defaultMathStyle, double fontSizePoints, string color)
    {
        if (symbolFontId == null || !Regex.IsMatch(symbolFontId, @"\A[a-z0-9]+(?:-[a-z0-9]+)*\z"))
            throw new ArgumentException("数学字体必须使用稳定的字体方案 ID。", nameof(symbolFontId));
        ValidateStyle(defaultMathStyle);
        SymbolFontId = symbolFontId;
        NumberFontFamily = numberFontFamily == null ? null : ValidateFamily(numberFontFamily);
        CjkFontFamily = ValidateFamily(cjkFontFamily);
        DefaultMathStyle = defaultMathStyle;
        FontSizePoints = FormulaFontSize.Validate(fontSizePoints);
        Color = NormalizeColor(color);
    }

    public int TypographyVersion => CurrentVersion;
    public string SymbolFontId { get; }
    /// <summary>Null follows the symbol font; a non-null value requests one system font family.</summary>
    public string? NumberFontFamily { get; }
    public string CjkFontFamily { get; }
    public FormulaMathStyle DefaultMathStyle { get; }
    public double FontSizePoints { get; }
    /// <summary>Canonical opaque sRGB color in #RRGGBB format.</summary>
    public string Color { get; }

    /// <summary>Returns a new resolved snapshot without changing the original.</summary>
    public FormulaTypography WithFontSize(double points) => new FormulaTypography(
        SymbolFontId, NumberFontFamily, CjkFontFamily, DefaultMathStyle, points, Color);

    /// <summary>Local source style wins; Automatic preserves the parser's intrinsic mathematical style.</summary>
    public FormulaMathStyle ResolveMathStyle(FormulaMathStyle intrinsicStyle, FormulaMathStyle? localStyle = null)
    {
        ValidateStyle(intrinsicStyle);
        if (intrinsicStyle == FormulaMathStyle.Automatic)
            throw new ArgumentException("节点固有样式必须已经解析。", nameof(intrinsicStyle));
        if (localStyle.HasValue) ValidateStyle(localStyle.Value);
        FormulaMathStyle selected = localStyle ?? DefaultMathStyle;
        return selected == FormulaMathStyle.Automatic ? intrinsicStyle : selected;
    }

    /// <summary>Resolves an optional local color after the source parser has converted it to sRGB.</summary>
    public string ResolveColor(string? localColor = null) => localColor == null ? Color : NormalizeColor(localColor);

    public bool Equals(FormulaTypography? other) => other != null
        && SymbolFontId == other.SymbolFontId
        && StringComparer.OrdinalIgnoreCase.Equals(NumberFontFamily, other.NumberFontFamily)
        && StringComparer.OrdinalIgnoreCase.Equals(CjkFontFamily, other.CjkFontFamily)
        && DefaultMathStyle == other.DefaultMathStyle && FontSizePoints.Equals(other.FontSizePoints)
        && Color == other.Color;

    public override bool Equals(object? obj) => obj is FormulaTypography other && Equals(other);

    public override int GetHashCode()
    {
        unchecked
        {
            int hash = SymbolFontId.GetHashCode();
            hash = hash * 31 + (NumberFontFamily == null ? 0 : StringComparer.OrdinalIgnoreCase.GetHashCode(NumberFontFamily));
            hash = hash * 31 + StringComparer.OrdinalIgnoreCase.GetHashCode(CjkFontFamily);
            hash = hash * 31 + (int)DefaultMathStyle;
            hash = hash * 31 + FontSizePoints.GetHashCode();
            return hash * 31 + Color.GetHashCode();
        }
    }

    private static void ValidateStyle(FormulaMathStyle style)
    {
        if (!Enum.IsDefined(typeof(FormulaMathStyle), style)) throw new ArgumentOutOfRangeException(nameof(style));
    }

    private static string ValidateFamily(string family)
    {
        if (string.IsNullOrWhiteSpace(family)) throw new ArgumentException("字体家族不能为空。", nameof(family));
        foreach (char character in family)
            if (char.IsControl(character)) throw new ArgumentException("字体家族包含控制字符。", nameof(family));
        return family.Trim();
    }

    private static string NormalizeColor(string color)
    {
        if (color == null || !Regex.IsMatch(color, @"\A#[0-9a-fA-F]{6}\z"))
            throw new ArgumentException("颜色必须为 #RRGGBB 格式。", nameof(color));
        return color.ToUpperInvariant();
    }
}
