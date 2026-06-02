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
    public const string RenderScaleTag = "LaTeXSnipperRenderScale";

    public static void ApplyToShape(dynamic shape, FormulaMetadata metadata, float naturalWidthPoints, float naturalHeightPoints, double renderScale)
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
        shape.Tags.Add(RenderScaleTag, renderScale.ToString(System.Globalization.CultureInfo.InvariantCulture));
    }
}
