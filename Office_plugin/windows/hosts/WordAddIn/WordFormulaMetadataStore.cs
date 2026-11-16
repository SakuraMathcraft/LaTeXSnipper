using System;
using System.Collections.Generic;
using System.Web.Script.Serialization;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

internal static class WordFormulaMetadataStore
{
    public const string EquationTagPrefix = "latexsnipper-eq-";
    private const string MetadataSeparator = "|";
    private const string MetadataVariablePrefix = "LS.E.";
    private const int MaxWordTagLength = 64;

    public static string BuildEquationTag(string equationId, string revision = "")
    {
        if (string.IsNullOrWhiteSpace(equationId))
        {
            throw new ArgumentException("公式标识不能为空。", nameof(equationId));
        }

        return ValidateTagLength(
            EquationTagPrefix + equationId +
            (string.IsNullOrWhiteSpace(revision) ? string.Empty : MetadataSeparator + revision));
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

    public static string Save(
        dynamic document,
        FormulaMetadata metadata)
    {
        if (metadata.SchemaVersion != FormulaMetadata.CurrentSchemaVersion)
        {
            throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaMetadataMissing"));
        }

        string documentId = WordDocumentIdentityStore.GetOrCreate(document);
        if (!string.Equals(metadata.Identity.DocumentId, documentId, StringComparison.Ordinal))
        {
            throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaMetadataMissing"));
        }

        string revision = Guid.NewGuid().ToString("N").Substring(0, 10);
        SaveVariable(
            document,
            BuildMetadataStorageKey(metadata.Identity.EquationId, revision),
            metadata.RenderEngine == RenderEngineKind.MathJaxSvg
                ? new JavaScriptSerializer().Serialize(new Dictionary<string, object>
                {
                    ["schemaVersion"] = metadata.SchemaVersion,
                    ["documentId"] = metadata.Identity.DocumentId,
                    ["equationId"] = metadata.Identity.EquationId
                })
                : Serialize(metadata));
        return BuildEquationTag(metadata.Identity.EquationId, revision);
    }

    public static FormulaMetadata Load(dynamic document, string tag)
    {
        string equationId = EquationIdFromTag(tag);
        FormulaMetadata metadata = Deserialize(LoadPayload(document, tag));
        if (!string.Equals(metadata.Identity.EquationId, equationId, StringComparison.Ordinal))
        {
            throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaMetadataMissing"));
        }

        return metadata;
    }

    public static FormulaIdentity LoadOleIdentity(dynamic document, string tag)
    {
        var fields = new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(LoadPayload(document, tag));
        if (ReadInt(fields, "schemaVersion") != FormulaMetadata.CurrentSchemaVersion
            || ReadString(fields, "equationId") != EquationIdFromTag(tag))
            throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaMetadataMissing"));
        return new FormulaIdentity(ReadRequiredNonEmptyString(fields, "documentId"), ReadString(fields, "equationId"));
    }

    public static FormulaIdentity? TryLoadOleIdentity(dynamic document, string tag)
    {
        string equationId = EquationIdFromTag(tag);
        string revision = RevisionFromTag(tag);
        if (string.IsNullOrWhiteSpace(equationId) || string.IsNullOrWhiteSpace(revision)) return null;
        string key = BuildMetadataStorageKey(equationId, revision);
        dynamic variables = document.Variables;
        int count = Convert.ToInt32(variables.Count);
        for (int index = 1; index <= count; index++)
        {
            if (string.Equals(Convert.ToString(variables.Item(index).Name), key, StringComparison.Ordinal))
                return LoadOleIdentity(document, tag);
        }
        return null;
    }

    public static string Serialize(
        FormulaMetadata metadata)
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
            ["typography"] = FormulaTypographyFields.Write(metadata.Typography),
        };
        return serializer.Serialize(dto);
    }

    private static string LoadPayload(dynamic document, string tag)
    {
        string equationId = EquationIdFromTag(tag);
        string revision = RevisionFromTag(tag);
        if (string.IsNullOrWhiteSpace(equationId) || string.IsNullOrWhiteSpace(revision))
        {
            throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaMetadataMissing"));
        }

        try
        {
            dynamic variable = document.Variables.Item(BuildMetadataStorageKey(equationId, revision));
            return Convert.ToString(variable.Value) ?? string.Empty;
        }
        catch (Exception exc)
        {
            throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaMetadataMissing"), exc);
        }
    }

    private static string RevisionFromTag(string tag)
    {
        int separatorIndex = tag.IndexOf(MetadataSeparator, StringComparison.Ordinal);
        return separatorIndex < 0 || separatorIndex == tag.Length - 1
            ? string.Empty
            : tag.Substring(separatorIndex + MetadataSeparator.Length);
    }

    private static string BuildMetadataStorageKey(string equationId, string revision)
    {
        return MetadataVariablePrefix + equationId + "." + revision;
    }

    private static FormulaMetadata Deserialize(string json)
    {
        try { return DeserializeCore(json); }
        catch (Exception error) when (error is ArgumentException || error is FormatException
            || error is InvalidCastException || error is KeyNotFoundException || error is NullReferenceException)
        {
            throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaMetadataMissing"), error);
        }
    }

    private static FormulaMetadata DeserializeCore(string json)
    {
        if (string.IsNullOrWhiteSpace(json))
        {
            throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaMetadataMissing"));
        }

        var serializer = new JavaScriptSerializer();
        var dto = serializer.Deserialize<Dictionary<string, object>>(json);
        int schemaVersion = ReadInt(dto, "schemaVersion");
        if (schemaVersion != FormulaMetadata.CurrentSchemaVersion)
        {
            throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaMetadataMissing"));
        }
        return DeserializeMetadata(dto, ReadRequiredNonEmptyString(dto, "documentId"));
    }

    private static FormulaMetadata DeserializeMetadata(
        Dictionary<string, object> dto,
        string documentId)
    {
        return new FormulaMetadata(
            new FormulaIdentity(documentId, ReadRequiredNonEmptyString(dto, "equationId")),
            ReadString(dto, "latex"),
            ReadEnum<FormulaDisplayMode>(dto, "displayMode"),
            ReadEnum<NumberingMode>(dto, "numberingMode"),
            ReadString(dto, "numberText"),
            ReadEnum<RenderEngineKind>(dto, "renderEngine"),
            FormulaMetadata.CurrentSchemaVersion,
            FormulaTypographyFields.Read((Dictionary<string, object>)dto["typography"]));
    }

    private static string ReadRequiredNonEmptyString(Dictionary<string, object> dto, string key)
    {
        string value = ReadString(dto, key);
        if (string.IsNullOrWhiteSpace(value))
        {
            throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaMetadataMissing"));
        }

        return value;
    }

    private static string ReadString(Dictionary<string, object> dto, string key)
    {
        if (!dto.TryGetValue(key, out object value))
        {
            throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaMetadataMissing"));
        }

        return Convert.ToString(value) ?? string.Empty;
    }

    private static int ReadInt(Dictionary<string, object> dto, string key)
    {
        if (!dto.TryGetValue(key, out object value) ||
            !int.TryParse(Convert.ToString(value), out int parsed))
        {
            throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaMetadataMissing"));
        }

        return parsed;
    }

    private static TEnum ReadEnum<TEnum>(Dictionary<string, object> dto, string key)
        where TEnum : struct
    {
        if (!dto.TryGetValue(key, out object value) ||
            !Enum.TryParse(Convert.ToString(value), ignoreCase: true, out TEnum parsed))
        {
            throw new InvalidOperationException(WordAddInText.Get("SelectedFormulaMetadataMissing"));
        }

        return parsed;
    }

    private static string ValidateTagLength(string tag)
    {
        if (tag.Length > MaxWordTagLength)
        {
            throw new InvalidOperationException("Word 公式标记超过 64 个字符的限制。");
        }

        return tag;
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
