using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.Globalization;
using System.IO;
using System.Text.RegularExpressions;

namespace LaTeXSnipper.OfficePlugin.PowerPointAddIn;

public sealed class PowerPointImageFileStore
{
    private const float PointsPerInch = 72f;
    private const float DefaultDpi = 180f;
    private const float MaxFormulaWidthPoints = 420f;
    private static readonly TimeSpan TemporaryFileLifetime = TimeSpan.FromDays(7);

    private static readonly Regex SvgViewBoxPattern = new(
        @"viewBox\s*=\s*""(?<x>[-\d.]+)\s+(?<y>[-\d.]+)\s+(?<w>[-\d.]+)\s+(?<h>[-\d.]+)""",
        RegexOptions.Compiled | RegexOptions.IgnoreCase);

    private readonly string _directory;

    public PowerPointImageFileStore(string? directory = null)
    {
        _directory = string.IsNullOrWhiteSpace(directory)
            ? Path.Combine(Path.GetTempPath(), "LaTeXSnipper", "OfficePlugin", "PowerPoint")
            : directory!;
    }

    public PowerPointRenderedImage SaveConversionResult(PowerPointConversionResult conversion)
    {
        CleanupExpiredFiles();

        // Determine crop bounds from PNG, then apply to SVG
        RectangleF? cropSvg = null;
        float? pngDpiX = null;
        float? pngDpiY = null;
        int? pngWidthPx = null;
        int? pngHeightPx = null;

        if (!string.IsNullOrWhiteSpace(conversion.PngBase64))
        {
            using var sourceStream = new MemoryStream(Convert.FromBase64String(conversion.PngBase64));
            using var source = new Bitmap(sourceStream);
            pngDpiX = source.HorizontalResolution > 1f ? source.HorizontalResolution : DefaultDpi;
            pngDpiY = source.VerticalResolution > 1f ? source.VerticalResolution : DefaultDpi;
            pngWidthPx = source.Width;
            pngHeightPx = source.Height;

            Rectangle pixelBounds = FindVisibleBounds(source);
            cropSvg = new RectangleF(
                (float)pixelBounds.X / source.Width,
                (float)pixelBounds.Y / source.Height,
                (float)pixelBounds.Width / source.Width,
                (float)pixelBounds.Height / source.Height);
        }

        string? svg = conversion.Svg;
        if (!string.IsNullOrWhiteSpace(svg) && cropSvg.HasValue)
        {
            try
            {
                return SaveSvgCropped(svg!, cropSvg.Value, pngDpiX!.Value, pngDpiY!.Value, pngWidthPx!.Value, pngHeightPx!.Value);
            }
            catch
            {
            }
        }

        if (!string.IsNullOrWhiteSpace(conversion.PngBase64))
        {
            return SavePngBase64(conversion.PngBase64, pngDpiX, pngDpiY, pngWidthPx, pngHeightPx);
        }

        throw new ArgumentException("Conversion result has no image data.");
    }

    public PowerPointRenderedImage SavePngBase64(string pngBase64)
    {
        return SavePngBase64(pngBase64, null, null, null, null);
    }

    private PowerPointRenderedImage SavePngBase64(string pngBase64, float? knownDpiX, float? knownDpiY, int? knownWidth, int? knownHeight)
    {
        if (string.IsNullOrWhiteSpace(pngBase64))
        {
            throw new ArgumentException("PNG data is required.", nameof(pngBase64));
        }

        Directory.CreateDirectory(_directory);
        CleanupExpiredFiles();
        string fileName = "formula-" + DateTime.UtcNow.ToString("yyyyMMddHHmmssfff", CultureInfo.InvariantCulture) + "-" + Guid.NewGuid().ToString("N") + ".png";
        string path = Path.Combine(_directory, fileName);

        if (knownDpiX.HasValue && knownDpiY.HasValue && knownWidth.HasValue && knownHeight.HasValue)
        {
            // Already decoded; re-decode to produce cropped output
            using var sourceStream = new MemoryStream(Convert.FromBase64String(pngBase64));
            using var source = new Bitmap(sourceStream);
            Rectangle bounds = FindVisibleBounds(source);
            using Bitmap output = source.Clone(bounds, PixelFormat.Format32bppArgb);
            output.SetResolution(knownDpiX.Value, knownDpiY.Value);
            output.Save(path, ImageFormat.Png);

            float width = output.Width / knownDpiX.Value * PointsPerInch;
            float height = output.Height / knownDpiY.Value * PointsPerInch;
            if (width > MaxFormulaWidthPoints)
            {
                float scale = MaxFormulaWidthPoints / width;
                width *= scale;
                height *= scale;
            }

            return new PowerPointRenderedImage(path, width, height);
        }
        else
        {
            using var sourceStream = new MemoryStream(Convert.FromBase64String(pngBase64));
            using var source = new Bitmap(sourceStream);
            float dpiX = source.HorizontalResolution > 1f ? source.HorizontalResolution : DefaultDpi;
            float dpiY = source.VerticalResolution > 1f ? source.VerticalResolution : DefaultDpi;
            Rectangle bounds = FindVisibleBounds(source);
            using Bitmap output = source.Clone(bounds, PixelFormat.Format32bppArgb);
            output.SetResolution(dpiX, dpiY);
            output.Save(path, ImageFormat.Png);

            float width = output.Width / dpiX * PointsPerInch;
            float height = output.Height / dpiY * PointsPerInch;
            if (width > MaxFormulaWidthPoints)
            {
                float scale = MaxFormulaWidthPoints / width;
                width *= scale;
                height *= scale;
            }

            return new PowerPointRenderedImage(path, width, height);
        }
    }

    private PowerPointRenderedImage SaveSvgCropped(
        string svg,
        RectangleF cropProportions,
        float pngDpiX,
        float pngDpiY,
        int pngFullWidth,
        int pngFullHeight)
    {
        string cleaned = CleanSvgForOffice(svg);

        // Map crop proportions to SVG viewBox coordinates
        var (vbX, vbY, vbW, vbH) = ParseSvgViewBoxFull(cleaned);
        if (vbW <= 0 || vbH <= 0)
        {
            // Can't parse viewBox; fall back to PNG
            throw new InvalidOperationException("SVG viewBox not found.");
        }

        float paddingPt = 4f;
        float croppedX = vbX + cropProportions.X * vbW - paddingPt;
        float croppedY = vbY + cropProportions.Y * vbH - paddingPt;
        float croppedW = cropProportions.Width * vbW + paddingPt * 2f;
        float croppedH = cropProportions.Height * vbH + paddingPt * 2f;

        croppedX = Math.Max(vbX, croppedX);
        croppedY = Math.Max(vbY, croppedY);
        croppedW = Math.Min(vbW, croppedW);
        croppedH = Math.Min(vbH, croppedH);

        string croppedViewBox = string.Format(
            CultureInfo.InvariantCulture,
            "{0:R} {1:R} {2:R} {3:R}",
            croppedX, croppedY, croppedW, croppedH);

        cleaned = SvgViewBoxPattern.Replace(cleaned, "viewBox=\"" + croppedViewBox + "\"", 1);

        Directory.CreateDirectory(_directory);
        CleanupExpiredFiles();
        string fileName = "formula-" + DateTime.UtcNow.ToString("yyyyMMddHHmmssfff", CultureInfo.InvariantCulture) + "-" + Guid.NewGuid().ToString("N") + ".svg";
        string path = Path.Combine(_directory, fileName);
        File.WriteAllText(path, cleaned, System.Text.Encoding.UTF8);

        float widthPoints = croppedW;
        float heightPoints = croppedH;
        if (widthPoints > MaxFormulaWidthPoints)
        {
            float scale = MaxFormulaWidthPoints / widthPoints;
            widthPoints *= scale;
            heightPoints *= scale;
        }

        return new PowerPointRenderedImage(path, widthPoints, heightPoints);
    }

    private void CleanupExpiredFiles()
    {
        try
        {
            if (!Directory.Exists(_directory))
            {
                return;
            }

            DateTime threshold = DateTime.UtcNow - TemporaryFileLifetime;
            foreach (string file in Directory.GetFiles(_directory, "*.*"))
            {
                string extension = Path.GetExtension(file);
                if (!string.Equals(extension, ".png", StringComparison.OrdinalIgnoreCase) &&
                    !string.Equals(extension, ".svg", StringComparison.OrdinalIgnoreCase))
                {
                    continue;
                }

                if (File.GetLastWriteTimeUtc(file) < threshold)
                {
                    File.Delete(file);
                }
            }
        }
        catch
        {
        }
    }

    private static (float X, float Y, float W, float H) ParseSvgViewBoxFull(string svg)
    {
        var match = SvgViewBoxPattern.Match(svg);
        if (match.Success
            && float.TryParse(match.Groups["x"].Value, NumberStyles.Float, CultureInfo.InvariantCulture, out float x)
            && float.TryParse(match.Groups["y"].Value, NumberStyles.Float, CultureInfo.InvariantCulture, out float y)
            && float.TryParse(match.Groups["w"].Value, NumberStyles.Float, CultureInfo.InvariantCulture, out float w)
            && float.TryParse(match.Groups["h"].Value, NumberStyles.Float, CultureInfo.InvariantCulture, out float h)
            && w > 0 && h > 0)
        {
            return (x, y, w, h);
        }

        return (0, 0, 0, 0);
    }

    private static string CleanSvgForOffice(string svg)
    {
        // Strip everything before <svg> and after </svg>
        int svgStart = svg.IndexOf("<svg", StringComparison.OrdinalIgnoreCase);
        int svgEnd = svg.LastIndexOf("</svg>", StringComparison.OrdinalIgnoreCase);

        if (svgStart < 0 || svgEnd <= svgStart)
        {
            return svg;
        }

        string result = svg.Substring(svgStart, svgEnd - svgStart + "</svg>".Length);

        // Fix matplotlib's deprecated xlink:href → href (PowerPoint doesn't support xlink namespace)
        result = SvgXlinkHrefPattern.Replace(result, " href=");

        // Remove xmlns:xlink declaration
        result = SvgXlinkNsPattern.Replace(result, string.Empty);

        return result;
    }

    private static readonly Regex SvgXlinkHrefPattern = new(
        @"\s*xlink:href\s*=\s*",
        RegexOptions.Compiled | RegexOptions.IgnoreCase);

    private static readonly Regex SvgXlinkNsPattern = new(
        @"\s*xmlns:xlink\s*=\s*""[^""]*""",
        RegexOptions.Compiled | RegexOptions.IgnoreCase);

    private static Rectangle FindVisibleBounds(Bitmap bitmap)
    {
        int left = bitmap.Width;
        int top = bitmap.Height;
        int right = -1;
        int bottom = -1;

        for (int y = 0; y < bitmap.Height; y++)
        {
            for (int x = 0; x < bitmap.Width; x++)
            {
                Color color = bitmap.GetPixel(x, y);
                if (IsVisible(color, Image.IsAlphaPixelFormat(bitmap.PixelFormat)))
                {
                    left = Math.Min(left, x);
                    top = Math.Min(top, y);
                    right = Math.Max(right, x);
                    bottom = Math.Max(bottom, y);
                }
            }
        }

        if (right < left || bottom < top)
        {
            return new Rectangle(0, 0, bitmap.Width, bitmap.Height);
        }

        int padding = 2;
        left = Math.Max(0, left - padding);
        top = Math.Max(0, top - padding);
        right = Math.Min(bitmap.Width - 1, right + padding);
        bottom = Math.Min(bitmap.Height - 1, bottom + padding);
        return Rectangle.FromLTRB(left, top, right + 1, bottom + 1);
    }

    private static bool IsVisible(Color color, bool hasAlpha)
    {
        if (hasAlpha)
        {
            return color.A > 12;
        }

        return color.R < 245 || color.G < 245 || color.B < 245;
    }
}
