#if NET48
using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.Globalization;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.Rendering;

internal static class SvgEnhancedMetafileWriter
{
    private const int Dpi = 1200;
    private const int PointsPerInch = 72;

    public static byte[] Write(RenderResult intermediateRender, CancellationToken cancellationToken)
    {
        if (intermediateRender.MimeType != MathJaxSvgRenderer.SvgMimeType)
        {
            throw new ArgumentException("Enhanced Metafile presentation requires MathJax SVG intermediate render.", nameof(intermediateRender));
        }

        int widthPixels = Math.Max(1, PointsToPixels(intermediateRender.WidthPoints));
        int heightPixels = Math.Max(1, PointsToPixels(intermediateRender.HeightPoints));

        using var stream = new MemoryStream();
        IntPtr screen = GetDC(IntPtr.Zero);
        if (screen == IntPtr.Zero)
        {
            throw new InvalidOperationException("Cannot acquire a screen device context for EMF rendering.");
        }

        try
        {
            using (var metafile = new Metafile(
                stream,
                screen,
                new RectangleF(0, 0, widthPixels, heightPixels),
                MetafileFrameUnit.Pixel,
                EmfType.EmfPlusDual,
                "LaTeXSnipper Formula"))
            {
                using Graphics graphics = Graphics.FromImage(metafile);
                ConfigureGraphics(graphics);
                SvgVectorGraphicsRenderer.Draw(
                    intermediateRender,
                    graphics,
                    widthPixels,
                    heightPixels,
                    cancellationToken);
            }
        }
        finally
        {
            ReleaseDC(IntPtr.Zero, screen);
        }

        return stream.ToArray();
    }

    private static void ConfigureGraphics(Graphics graphics)
    {
        graphics.PageUnit = GraphicsUnit.Pixel;
        graphics.SmoothingMode = SmoothingMode.AntiAlias;
        graphics.PixelOffsetMode = PixelOffsetMode.HighQuality;
        graphics.CompositingQuality = CompositingQuality.HighQuality;
        graphics.InterpolationMode = InterpolationMode.HighQualityBicubic;
    }

    private static int PointsToPixels(double points)
    {
        return (int)Math.Ceiling(points / PointsPerInch * Dpi);
    }

    internal static float ParseFloat(string value)
    {
        return float.Parse(value, NumberStyles.Float, CultureInfo.InvariantCulture);
    }

    [DllImport("user32.dll")]
    private static extern IntPtr GetDC(IntPtr hwnd);

    [DllImport("user32.dll")]
    private static extern int ReleaseDC(IntPtr hwnd, IntPtr hdc);
}
#endif
