using System;

namespace LaTeXSnipper.OfficePlugin.Abstractions;

/// <summary>New-formula preferences; following host text size is never stored in a formula snapshot.</summary>
public sealed class FormulaTypographyDefaults
{
    public FormulaTypographyDefaults(FormulaTypography typography, bool followHostFontSize)
    {
        Typography = typography ?? throw new ArgumentNullException(nameof(typography));
        FollowHostFontSize = followHostFontSize;
    }

    /// <summary>Fixed style and the explicit fallback point size when host text size is unavailable.</summary>
    public FormulaTypography Typography { get; }
    public bool FollowHostFontSize { get; }

    /// <summary>
    /// Resolves a new formula using an unambiguous host text size, or the configured fallback.
    /// Hosts pass null for absent/mixed text selection; undefined and invalid numeric values also fall back.
    /// Re-editing an existing formula uses its snapshot directly and does not call this method.
    /// </summary>
    public FormulaTypographyResolution ResolveForNewFormula(double? hostFontSizePoints)
    {
        if (!FollowHostFontSize) return new FormulaTypographyResolution(Typography, FormulaFontSizeSource.Fixed);
        if (hostFontSizePoints.HasValue && FormulaFontSize.IsValid(hostFontSizePoints.Value))
            return new FormulaTypographyResolution(Typography.WithFontSize(hostFontSizePoints.Value), FormulaFontSizeSource.Host);
        return new FormulaTypographyResolution(Typography, FormulaFontSizeSource.Fallback);
    }
}

/// <summary>The origin of a resolved point size, so the UI can explain fallback to the user.</summary>
public enum FormulaFontSizeSource { Fixed, Host, Fallback }

/// <summary>A resolved immutable snapshot and its new-formula context diagnostic.</summary>
public sealed class FormulaTypographyResolution
{
    internal FormulaTypographyResolution(FormulaTypography typography, FormulaFontSizeSource fontSizeSource)
    {
        Typography = typography;
        FontSizeSource = fontSizeSource;
    }

    public FormulaTypography Typography { get; }
    public FormulaFontSizeSource FontSizeSource { get; }
}
