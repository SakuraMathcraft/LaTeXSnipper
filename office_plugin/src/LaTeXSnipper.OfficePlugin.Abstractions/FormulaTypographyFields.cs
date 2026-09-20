using System;
using System.Collections.Generic;
using System.Globalization;

namespace LaTeXSnipper.OfficePlugin.Abstractions;

/// <summary>Canonical wire fields shared by document stores and OLE payloads.</summary>
public static class FormulaTypographyFields
{
    public static Dictionary<string, object> Write(FormulaTypography typography)
    {
        if (typography == null) throw new ArgumentNullException(nameof(typography));
        return new Dictionary<string, object>
        {
            ["typographyVersion"] = typography.TypographyVersion,
            ["symbolFontId"] = typography.SymbolFontId,
            ["numberFontFamily"] = typography.NumberFontFamily ?? string.Empty,
            ["cjkFontFamily"] = typography.CjkFontFamily,
            ["defaultMathStyle"] = typography.DefaultMathStyle.ToString(),
            ["fontSizePoints"] = typography.FontSizePoints,
            ["color"] = typography.Color
        };
    }

    public static FormulaTypography Read(IReadOnlyDictionary<string, object> fields)
    {
        string Required(string name)
        {
            if (!fields.TryGetValue(name, out object? value) || value == null)
                throw new FormatException("缺少公式样式字段：" + name);
            return Convert.ToString(value, CultureInfo.InvariantCulture) ?? string.Empty;
        }
        if (Required("typographyVersion") != FormulaTypography.CurrentVersion.ToString(CultureInfo.InvariantCulture))
            throw new FormatException("不支持的公式样式版本。");
        string style = Required("defaultMathStyle");
        if (!Enum.TryParse(style, out FormulaMathStyle parsed) || !Enum.IsDefined(typeof(FormulaMathStyle), parsed)
            || parsed.ToString() != style) throw new FormatException("无效的数学样式。");
        string number = Required("numberFontFamily");
        return new FormulaTypography(Required("symbolFontId"), number.Length == 0 ? null : number,
            Required("cjkFontFamily"), parsed, FormulaFontSize.Parse(Required("fontSizePoints")), Required("color"));
    }
}
