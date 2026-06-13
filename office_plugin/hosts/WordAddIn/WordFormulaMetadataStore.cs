using System;
using System.Collections.Generic;
using System.Text;
using System.Web.Script.Serialization;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

internal static class WordFormulaMetadataStore
{
    public const string EquationTagPrefix = "latexsnipper-eq-";
    public const string NumberControlTagPrefix = "latexsnipper-eqn-";
    public const string NumberControlAliasPrefix = "LaTeXSnipperEqNum-";
    private const string OleNaturalSizeVariablePrefix = "LaTeXSnipper.OleNaturalSize.";
    private const string OmmlNaturalFontSizeVariablePrefix = "LaTeXSnipper.OmmlNaturalFontSize.";
    private const string AutoNumberCounterKey = "LaTeXSnipper.AutoNumberCounter";
    private const string AutoNumberChapterKey = "LaTeXSnipper.AutoNumberChapter";
    private const string AutoNumberSectionKey = "LaTeXSnipper.AutoNumberSection";
    private const string MetadataSeparator = "|";

    public static string BuildEquationTag(string equationId, FormulaMetadata? metadata = null)
    {
        if (string.IsNullOrWhiteSpace(equationId))
        {
            throw new ArgumentException("Equation ID is required.", nameof(equationId));
        }

        string tag = EquationTagPrefix + equationId;
        return metadata == null
            ? tag
            : tag + MetadataSeparator + Convert.ToBase64String(Encoding.UTF8.GetBytes(Serialize(metadata)));
    }

    public static string EquationIdFromTag(string tag)
    {
        if (string.IsNullOrWhiteSpace(tag) || !tag.StartsWith(EquationTagPrefix, StringComparison.Ordinal))
        {
            return string.Empty;
        }

        string value = tag.Substring(EquationTagPrefix.Length);
        int separatorIndex = value.IndexOf(MetadataSeparator, StringComparison.Ordinal);
        return separatorIndex < 0 ? value : value.Substring(0, separatorIndex);
    }

    public static FormulaMetadata LoadFromEquationTag(string tag)
    {
        int separatorIndex = tag.IndexOf(MetadataSeparator, StringComparison.Ordinal);
        if (separatorIndex < 0 || separatorIndex == tag.Length - 1)
        {
            throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaMetadataMissing"));
        }

        string encoded = tag.Substring(separatorIndex + MetadataSeparator.Length);
        return Deserialize(Encoding.UTF8.GetString(Convert.FromBase64String(encoded)));
    }

    public static string BuildNumberTag(string equationId)
    {
        if (string.IsNullOrWhiteSpace(equationId))
        {
            throw new ArgumentException("Equation ID is required.", nameof(equationId));
        }

        return NumberControlTagPrefix + equationId;
    }

    public static string BuildNumberAlias(string equationId)
    {
        if (string.IsNullOrWhiteSpace(equationId))
        {
            throw new ArgumentException("Equation ID is required.", nameof(equationId));
        }

        return NumberControlAliasPrefix + equationId;
    }

    public static string EquationIdFromNumberTag(string tag)
    {
        if (string.IsNullOrWhiteSpace(tag) || !tag.StartsWith(NumberControlTagPrefix, StringComparison.Ordinal))
        {
            return string.Empty;
        }

        return tag.Substring(NumberControlTagPrefix.Length);
    }

    public static void SaveOleNaturalSize(dynamic document, string equationId, double widthPoints, double heightPoints)
    {
        if (widthPoints <= 0 || heightPoints <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(widthPoints), "OLE natural size must be positive.");
        }

        var serializer = new JavaScriptSerializer();
        string json = serializer.Serialize(new Dictionary<string, object>
        {
            ["widthPoints"] = widthPoints.ToString(System.Globalization.CultureInfo.InvariantCulture),
            ["heightPoints"] = heightPoints.ToString(System.Globalization.CultureInfo.InvariantCulture),
        });
        SaveVariable(document, BuildOleNaturalSizeStorageKey(equationId), json);
    }

    public static bool TryLoadOleNaturalSize(dynamic document, string equationId, out double widthPoints, out double heightPoints)
    {
        widthPoints = 0;
        heightPoints = 0;
        try
        {
            dynamic variable = document.Variables.Item(BuildOleNaturalSizeStorageKey(equationId));
            var serializer = new JavaScriptSerializer();
            var dto = serializer.Deserialize<Dictionary<string, object>>(Convert.ToString(variable.Value) ?? string.Empty);
            widthPoints = ReadDouble(dto, "widthPoints");
            heightPoints = ReadDouble(dto, "heightPoints");
            return widthPoints > 0 && heightPoints > 0;
        }
        catch
        {
            return false;
        }
    }

    public static void SaveOmmlNaturalFontSize(dynamic document, string equationId, double fontSizePoints)
    {
        if (fontSizePoints <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(fontSizePoints), "OMML natural font size must be positive.");
        }

        SaveVariable(
            document,
            OmmlNaturalFontSizeVariablePrefix + equationId,
            fontSizePoints.ToString(System.Globalization.CultureInfo.InvariantCulture));
    }

    public static bool TryLoadOmmlNaturalFontSize(dynamic document, string equationId, out double fontSizePoints)
    {
        fontSizePoints = 0;
        try
        {
            dynamic variable = document.Variables.Item(OmmlNaturalFontSizeVariablePrefix + equationId);
            fontSizePoints = Convert.ToDouble(
                variable.Value,
                System.Globalization.CultureInfo.InvariantCulture);
            return fontSizePoints > 0;
        }
        catch
        {
            return false;
        }
    }

    private static string BuildOleNaturalSizeStorageKey(string equationId)
    {
        if (string.IsNullOrWhiteSpace(equationId))
        {
            throw new ArgumentException("Equation ID is required.", nameof(equationId));
        }

        return OleNaturalSizeVariablePrefix + equationId;
    }

    public static string Serialize(FormulaMetadata metadata)
    {
        var serializer = new JavaScriptSerializer();
        var dto = new Dictionary<string, object>
        {
            ["schemaVersion"] = metadata.SchemaVersion,
            ["documentId"] = metadata.Identity.DocumentId,
            ["equationId"] = metadata.Identity.EquationId,
            ["latex"] = metadata.Latex,
            ["displayMode"] = metadata.DisplayMode.ToString(),
            ["numberingMode"] = metadata.NumberingMode.ToString(),
            ["numberText"] = metadata.NumberText,
            ["renderEngine"] = metadata.RenderEngine.ToString(),
            ["fontColor"] = metadata.FontColor,
            ["fontStyle"] = metadata.FontStyle.ToString(),
            ["fontScale"] = metadata.FontScale,
        };
        return serializer.Serialize(dto);
    }

    public static FormulaMetadata Deserialize(string json)
    {
        if (string.IsNullOrWhiteSpace(json))
        {
            throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaMetadataMissing"));
        }

        var serializer = new JavaScriptSerializer();
        var dto = serializer.Deserialize<Dictionary<string, object>>(json);
        string documentId = ReadString(dto, "documentId");
        string equationId = ReadString(dto, "equationId");
        return new FormulaMetadata(
            new FormulaIdentity(documentId, equationId),
            ReadString(dto, "latex"),
            ReadEnum(dto, "displayMode", FormulaDisplayMode.Display),
            ReadEnum(dto, "numberingMode", NumberingMode.None),
            ReadString(dto, "numberText"),
            ReadEnum(dto, "renderEngine", RenderEngineKind.Omml),
            ReadInt(dto, "schemaVersion", 1),
            ReadString(dto, "fontColor"),
            ReadEnum(dto, "fontStyle", FormulaFontStyle.TeX),
            ReadDouble(dto, "fontScale"));
    }

    private static string ReadString(Dictionary<string, object> dto, string key)
    {
        return dto.TryGetValue(key, out object value) ? Convert.ToString(value) ?? string.Empty : string.Empty;
    }

    private static int ReadInt(Dictionary<string, object> dto, string key, int fallback)
    {
        if (!dto.TryGetValue(key, out object value))
        {
            return fallback;
        }

        return int.TryParse(Convert.ToString(value), out int parsed) ? parsed : fallback;
    }

    private static double ReadDouble(Dictionary<string, object> dto, string key)
    {
        return dto.TryGetValue(key, out object value)
            && double.TryParse(Convert.ToString(value), System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out double parsed)
            ? parsed
            : 0;
    }

    private static TEnum ReadEnum<TEnum>(Dictionary<string, object> dto, string key, TEnum fallback)
        where TEnum : struct
    {
        if (!dto.TryGetValue(key, out object value))
        {
            return fallback;
        }

        return Enum.TryParse(Convert.ToString(value), ignoreCase: true, out TEnum parsed) ? parsed : fallback;
    }

    public static int GetAutoNumberCounter(dynamic document)
    {
        try
        {
            dynamic variable = document.Variables.Item(AutoNumberCounterKey);
            return Convert.ToInt32(variable.Value, System.Globalization.CultureInfo.InvariantCulture);
        }
        catch
        {
            return 1;
        }
    }

    public static void SetAutoNumberCounter(dynamic document, int value)
    {
        SetIntegerVariable(document, AutoNumberCounterKey, value);
    }

    public static int GetAutoNumberChapter(dynamic document)
    {
        return GetIntegerVariable(document, AutoNumberChapterKey, 1);
    }

    public static void SetAutoNumberChapter(dynamic document, int value)
    {
        SetIntegerVariable(document, AutoNumberChapterKey, value);
    }

    public static int GetAutoNumberSection(dynamic document)
    {
        return GetIntegerVariable(document, AutoNumberSectionKey, 1);
    }

    public static void SetAutoNumberSection(dynamic document, int value)
    {
        SetIntegerVariable(document, AutoNumberSectionKey, value);
    }

    private static int GetIntegerVariable(dynamic document, string key, int fallback)
    {
        try
        {
            dynamic variable = document.Variables.Item(key);
            return Convert.ToInt32(variable.Value, System.Globalization.CultureInfo.InvariantCulture);
        }
        catch
        {
            return fallback;
        }
    }

    private static void SetIntegerVariable(dynamic document, string key, int value)
    {
        SaveVariable(
            document,
            key,
            value.ToString(System.Globalization.CultureInfo.InvariantCulture));
    }

    private static void SaveVariable(dynamic document, string key, string value)
    {
        dynamic variables = document.Variables;
        try
        {
            dynamic variable = variables.Item(key);
            variable.Value = value;
        }
        catch
        {
            variables.Add(key, value);
        }
    }

}
