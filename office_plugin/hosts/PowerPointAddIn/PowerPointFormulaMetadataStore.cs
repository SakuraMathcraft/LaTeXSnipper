using System;
using System.Text;
using System.Web.Script.Serialization;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.PowerPointAddIn;

public static class PowerPointFormulaMetadataStore
{
    private const string MetadataPrefix = "latexsnipper-meta|";
    public const string EquationIdTag = "LaTeXSnipperEquationId";
    public const string NaturalWidthPointsTag = "LaTeXSnipperNaturalWidthPoints";
    public const string NaturalHeightPointsTag = "LaTeXSnipperNaturalHeightPoints";
    public const string ImagePathTag = "LaTeXSnipperImagePath";

    public static void ApplyToShape(dynamic shape, FormulaMetadata metadata, float naturalWidthPoints, float naturalHeightPoints)
    {
        if (shape == null)
        {
            throw new ArgumentNullException(nameof(shape));
        }

        if (metadata == null)
        {
            throw new ArgumentNullException(nameof(metadata));
        }

        shape.AlternativeText = MetadataPrefix + Convert.ToBase64String(
            Encoding.UTF8.GetBytes(Serialize(metadata)));
        shape.Tags.Add(EquationIdTag, metadata.Identity.EquationId);
        shape.Tags.Add(NaturalWidthPointsTag, naturalWidthPoints.ToString(System.Globalization.CultureInfo.InvariantCulture));
        shape.Tags.Add(NaturalHeightPointsTag, naturalHeightPoints.ToString(System.Globalization.CultureInfo.InvariantCulture));
    }

    public static FormulaMetadata LoadFromShape(dynamic shape)
    {
        string value = Convert.ToString(shape.AlternativeText) ?? string.Empty;
        if (!value.StartsWith(MetadataPrefix, StringComparison.Ordinal))
        {
            throw new InvalidOperationException(PowerPointAddInText.Get("SelectedFormulaMetadataMissing"));
        }

        string json = Encoding.UTF8.GetString(
            Convert.FromBase64String(value.Substring(MetadataPrefix.Length)));
        var serializer = new JavaScriptSerializer();
        var dto = serializer.Deserialize<System.Collections.Generic.Dictionary<string, object>>(json);
        return new FormulaMetadata(
            new FormulaIdentity(ReadString(dto, "documentId"), ReadString(dto, "equationId")),
            ReadString(dto, "latex"),
            ReadEnum(dto, "displayMode", FormulaDisplayMode.Display),
            NumberingMode.None,
            string.Empty,
            ReadEnum(dto, "renderEngine", RenderEngineKind.MathJaxSvg),
            ReadInt(dto, "schemaVersion", 1),
            ReadString(dto, "fontColor"),
            ReadEnum(dto, "fontStyle", FormulaFontStyle.TeX),
            ReadDouble(dto, "fontScale", 1));
    }

    private static string Serialize(FormulaMetadata metadata)
    {
        var serializer = new JavaScriptSerializer();
        return serializer.Serialize(new System.Collections.Generic.Dictionary<string, object>
        {
            ["schemaVersion"] = metadata.SchemaVersion,
            ["documentId"] = metadata.Identity.DocumentId,
            ["equationId"] = metadata.Identity.EquationId,
            ["latex"] = metadata.Latex,
            ["displayMode"] = metadata.DisplayMode.ToString(),
            ["renderEngine"] = metadata.RenderEngine.ToString(),
            ["fontColor"] = metadata.FontColor,
            ["fontStyle"] = metadata.FontStyle.ToString(),
            ["fontScale"] = metadata.FontScale,
        });
    }

    private static string ReadString(System.Collections.Generic.Dictionary<string, object> dto, string key)
    {
        return dto.TryGetValue(key, out object value) ? Convert.ToString(value) ?? string.Empty : string.Empty;
    }

    private static int ReadInt(System.Collections.Generic.Dictionary<string, object> dto, string key, int fallback)
    {
        return dto.TryGetValue(key, out object value) && int.TryParse(Convert.ToString(value), out int parsed)
            ? parsed
            : fallback;
    }

    private static double ReadDouble(
        System.Collections.Generic.Dictionary<string, object> dto,
        string key,
        double fallback)
    {
        return dto.TryGetValue(key, out object value)
            && double.TryParse(
                Convert.ToString(value),
                System.Globalization.NumberStyles.Float,
                System.Globalization.CultureInfo.InvariantCulture,
                out double parsed)
            ? parsed
            : fallback;
    }

    private static TEnum ReadEnum<TEnum>(
        System.Collections.Generic.Dictionary<string, object> dto,
        string key,
        TEnum fallback)
        where TEnum : struct
    {
        return dto.TryGetValue(key, out object value)
            && Enum.TryParse(Convert.ToString(value), true, out TEnum parsed)
            ? parsed
            : fallback;
    }

    public static void ApplyImagePath(dynamic shape, string imagePath)
    {
        if (shape == null)
        {
            throw new ArgumentNullException(nameof(shape));
        }

        shape.Tags.Add(ImagePathTag, imagePath ?? string.Empty);
    }
}
