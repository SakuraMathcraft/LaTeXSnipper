#if NET48
using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.IO;
using System.Threading;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.Rendering;

public static class SvgPngRasterizer
{
    private const int DefaultDpi = 300;
    private const int PointsPerInch = 72;

    public static byte[] Rasterize(
        RenderResult svgRender,
        CancellationToken cancellationToken,
        int dpi = DefaultDpi,
        double horizontalPaddingPoints = 0,
        double verticalPaddingPoints = 0)
    {
        if (dpi <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(dpi));
        }

        if (horizontalPaddingPoints < 0)
        {
            throw new ArgumentOutOfRangeException(nameof(horizontalPaddingPoints));
        }

        if (verticalPaddingPoints < 0)
        {
            throw new ArgumentOutOfRangeException(nameof(verticalPaddingPoints));
        }

        int contentWidth = Math.Max(1, PointsToPixels(svgRender.WidthPoints, dpi));
        int contentHeight = Math.Max(1, PointsToPixels(svgRender.HeightPoints, dpi));
        int horizontalPadding = PointsToPixels(horizontalPaddingPoints, dpi);
        int verticalPadding = PointsToPixels(verticalPaddingPoints, dpi);
        int width = contentWidth + horizontalPadding * 2;
        int height = contentHeight + verticalPadding * 2;
        using var bitmap = new Bitmap(width, height, PixelFormat.Format32bppArgb);
        bitmap.SetResolution(dpi, dpi);
        using (Graphics graphics = Graphics.FromImage(bitmap))
        {
            graphics.Clear(Color.Transparent);
            graphics.SmoothingMode = SmoothingMode.AntiAlias;
            graphics.PixelOffsetMode = PixelOffsetMode.HighQuality;
            graphics.CompositingQuality = CompositingQuality.HighQuality;
            graphics.TranslateTransform(horizontalPadding, verticalPadding);
            SvgVectorGraphicsRenderer.Draw(svgRender, graphics, contentWidth, contentHeight, cancellationToken);
        }

        using var stream = new MemoryStream();
        bitmap.Save(stream, ImageFormat.Png);
        return stream.ToArray();
    }

    private static int PointsToPixels(double points, int dpi)
    {
        return Math.Max(0, (int)Math.Ceiling(points / PointsPerInch * dpi));
    }
}
#endif
