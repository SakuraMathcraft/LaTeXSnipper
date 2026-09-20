using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Globalization;

namespace LaTeXSnipper.OfficePlugin.Abstractions;

/// <summary>Shared point-size input rules and Chinese size names for formula typography.</summary>
public static class FormulaFontSize
{
    /// <summary>Smallest point size accepted by the product.</summary>
    public const double MinimumPoints = 1;
    /// <summary>Largest point size accepted by the product.</summary>
    public const double MaximumPoints = 1638;

    /// <summary>The sole name-to-point table; callers cannot modify it.</summary>
    public static IReadOnlyDictionary<string, double> NamedSizes { get; } =
        new ReadOnlyDictionary<string, double>(new Dictionary<string, double>(StringComparer.Ordinal)
        {
            ["初号"] = 42, ["小初"] = 36, ["一号"] = 26, ["小一"] = 24,
            ["二号"] = 22, ["小二"] = 18, ["三号"] = 16, ["小三"] = 15,
            ["四号"] = 14, ["小四"] = 12, ["五号"] = 10.5, ["小五"] = 9,
            ["六号"] = 7.5, ["小六"] = 6.5, ["七号"] = 5, ["八号"] = 5.5
        });

    /// <summary>Rejects non-finite and out-of-range input, including Office's undefined-size sentinel.</summary>
    public static bool IsValid(double points) =>
        !double.IsNaN(points) && points >= MinimumPoints && points <= MaximumPoints;

    /// <summary>Enforces the same point-size domain for user input and persisted snapshots.</summary>
    public static double Validate(double points)
    {
        if (!IsValid(points)) throw new ArgumentOutOfRangeException(nameof(points), points,
            $"公式字号必须在 {MinimumPoints}–{MaximumPoints} pt 之间。");
        return points;
    }

    /// <summary>Accepts a Chinese size name or a decimal point size, without percent or unit suffixes.</summary>
    public static bool TryParse(string? text, out double points)
    {
        string input = (text ?? string.Empty).Trim();
        if (NamedSizes.TryGetValue(input, out points)) return true;
        if (double.TryParse(input, NumberStyles.AllowDecimalPoint, CultureInfo.InvariantCulture, out points)
            && IsValid(points)) return true;
        points = 0;
        return false;
    }

    /// <summary>Parses an absolute point size; invalid input is never silently replaced by a default.</summary>
    public static double Parse(string text) => TryParse(text, out double points)
        ? points : throw new FormatException("请输入有效的数字字号或中文字号名称。");
}
