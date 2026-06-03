using System;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.PowerPointAddIn;

public static class PowerPointFormulaMetadataStore
{
    public const string EquationIdTag = "LaTeXSnipperEquationId";
    public const string LatexTag = "LaTeXSnipperLatex";
    public const string DisplayModeTag = "LaTeXSnipperDisplayMode";
    public const string SchemaVersionTag = "LaTeXSnipperSchemaVersion";
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
        shape.Tags.Add(EquationIdTag, metadata.Identity.EquationId);
        shape.Tags.Add(LatexTag, metadata.Latex);
        shape.Tags.Add(DisplayModeTag, metadata.DisplayMode.ToString());
        shape.Tags.Add(SchemaVersionTag, metadata.SchemaVersion.ToString(System.Globalization.CultureInfo.InvariantCulture));
        shape.Tags.Add(NaturalWidthPointsTag, naturalWidthPoints.ToString(System.Globalization.CultureInfo.InvariantCulture));
        shape.Tags.Add(NaturalHeightPointsTag, naturalHeightPoints.ToString(System.Globalization.CultureInfo.InvariantCulture));
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
