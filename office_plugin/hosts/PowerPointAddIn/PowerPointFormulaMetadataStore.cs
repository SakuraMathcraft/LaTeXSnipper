using System;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.PowerPointAddIn;

public static class PowerPointFormulaMetadataStore
{
    public const string EquationIdTag = "LaTeXSnipperEquationId";
    public const string LatexTag = "LaTeXSnipperLatex";
    public const string DisplayModeTag = "LaTeXSnipperDisplayMode";
    public const string SchemaVersionTag = "LaTeXSnipperSchemaVersion";
    public const string RenderEngineTag = "LaTeXSnipperRenderEngine";
    public const string FontColorTag = "LaTeXSnipperFontColor";
    public const string FontStyleTag = "LaTeXSnipperFontStyle";
    public const string FontScaleTag = "LaTeXSnipperFontScale";
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

        shape.AlternativeText = "LaTeXSnipper formula " + metadata.Identity.EquationId;
        ApplyMetadataTags(shape, metadata);
        shape.Tags.Add(NaturalWidthPointsTag, naturalWidthPoints.ToString(System.Globalization.CultureInfo.InvariantCulture));
        shape.Tags.Add(NaturalHeightPointsTag, naturalHeightPoints.ToString(System.Globalization.CultureInfo.InvariantCulture));
    }

    private static void ApplyMetadataTags(dynamic shape, FormulaMetadata metadata)
    {
        shape.Tags.Add(EquationIdTag, metadata.Identity.EquationId);
        shape.Tags.Add(LatexTag, metadata.Latex);
        shape.Tags.Add(DisplayModeTag, metadata.DisplayMode.ToString());
        shape.Tags.Add(SchemaVersionTag, metadata.SchemaVersion.ToString(System.Globalization.CultureInfo.InvariantCulture));
        shape.Tags.Add(RenderEngineTag, metadata.RenderEngine.ToString());
        shape.Tags.Add(FontColorTag, metadata.FontColor);
        shape.Tags.Add(FontStyleTag, metadata.FontStyle.ToString());
        shape.Tags.Add(FontScaleTag, metadata.FontScale.ToString(System.Globalization.CultureInfo.InvariantCulture));
    }

    public static FormulaMetadata LoadFromShape(dynamic shape)
    {
        string equationId = ReadTag(shape, EquationIdTag);
        if (string.IsNullOrWhiteSpace(equationId))
        {
            throw new InvalidOperationException(PowerPointAddInText.Get("SelectedFormulaMetadataMissing"));
        }

        return new FormulaMetadata(
            new FormulaIdentity("active-presentation", equationId),
            ReadTag(shape, LatexTag),
            ReadEnumTag(shape, DisplayModeTag, FormulaDisplayMode.Display),
            NumberingMode.None,
            string.Empty,
            ReadEnumTag(shape, RenderEngineTag, RenderEngineKind.MathJaxSvg),
            ReadIntTag(shape, SchemaVersionTag, 1),
            ReadTag(shape, FontColorTag),
            ReadEnumTag(shape, FontStyleTag, FormulaFontStyle.TeX),
            ReadDoubleTag(shape, FontScaleTag, 1));
    }

    private static string ReadTag(dynamic shape, string name)
    {
        try
        {
            return Convert.ToString(shape.Tags[name]) ?? string.Empty;
        }
        catch
        {
            return string.Empty;
        }
    }

    private static int ReadIntTag(dynamic shape, string name, int fallback)
    {
        return int.TryParse(ReadTag(shape, name), out int value) ? value : fallback;
    }

    private static double ReadDoubleTag(dynamic shape, string name, double fallback)
    {
        return double.TryParse(
            ReadTag(shape, name),
            System.Globalization.NumberStyles.Float,
            System.Globalization.CultureInfo.InvariantCulture,
            out double value)
            ? value
            : fallback;
    }

    private static TEnum ReadEnumTag<TEnum>(dynamic shape, string name, TEnum fallback)
        where TEnum : struct
    {
        return Enum.TryParse(ReadTag(shape, name), true, out TEnum value) ? value : fallback;
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
