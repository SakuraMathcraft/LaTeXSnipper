#if NET48
using System;
using System.Drawing.Drawing2D;
using System.Globalization;
using System.Text.RegularExpressions;

namespace LaTeXSnipper.OfficePlugin.Rendering;

internal static class SvgTransformParser
{
    private static readonly Regex TransformRegex = new Regex(
        @"(?<name>matrix|translate|scale)\s*\((?<args>[^)]*)\)",
        RegexOptions.Compiled | RegexOptions.CultureInvariant);

    public static Matrix? Parse(string? value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return null;
        }

        var result = new Matrix();
        foreach (Match match in TransformRegex.Matches(value))
        {
            string name = match.Groups["name"].Value;
            float[] args = ParseArgs(match.Groups["args"].Value);
            using Matrix local = CreateMatrix(name, args);
            result.Multiply(local, MatrixOrder.Prepend);
        }

        return result;
    }

    private static Matrix CreateMatrix(string name, float[] args)
    {
        if (name == "matrix" && args.Length >= 6)
        {
            return new Matrix(args[0], args[1], args[2], args[3], args[4], args[5]);
        }

        if (name == "translate")
        {
            float x = args.Length >= 1 ? args[0] : 0;
            float y = args.Length >= 2 ? args[1] : 0;
            var matrix = new Matrix();
            matrix.Translate(x, y, MatrixOrder.Append);
            return matrix;
        }

        if (name == "scale")
        {
            float x = args.Length >= 1 ? args[0] : 1;
            float y = args.Length >= 2 ? args[1] : x;
            var matrix = new Matrix();
            matrix.Scale(x, y, MatrixOrder.Append);
            return matrix;
        }

        return new Matrix();
    }

    private static float[] ParseArgs(string value)
    {
        string[] parts = value.Split(new[] { ' ', ',' }, StringSplitOptions.RemoveEmptyEntries);
        var result = new float[parts.Length];
        for (int i = 0; i < parts.Length; i++)
        {
            result[i] = float.Parse(parts[i], NumberStyles.Float, CultureInfo.InvariantCulture);
        }

        return result;
    }
}
#endif
