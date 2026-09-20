using System;
using System.Collections.Generic;
#if NET48
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Globalization;
using System.Runtime.InteropServices;
using System.Text;
#endif

namespace LaTeXSnipper.OfficePlugin.Rendering;

/// <summary>Measures and outlines each run with the same selected Windows font, before mathematical layout.</summary>
public sealed class SystemFontOutlineService
{
    /// <summary>
    /// Shapes a complete run, preserving whitespace and letter spacing. Fallback is explicit and ordered.
    /// Unavailable fonts, styles and glyphs never silently pass through GDI font substitution.
    /// </summary>
    public FontRunOutline Shape(string text, string family, FontRunStyle style,
        IReadOnlyList<string>? fallbackFamilies = null)
    {
        if (text == null) throw new ArgumentNullException(nameof(text));
        if (string.IsNullOrWhiteSpace(family)) throw new ArgumentException("字体家族不能为空。", nameof(family));
        if ((style & ~(FontRunStyle.Bold | FontRunStyle.Italic)) != 0)
            throw new ArgumentOutOfRangeException(nameof(style));
        foreach (char character in text)
            if (char.IsSurrogate(character) || char.IsControl(character))
                throw new NotSupportedException("系统字体轮廓暂不支持辅助平面字符或控制字符；请使用受支持的数学字形或显式换行结构。");
#if NET48
        string requested = family.Trim();
        var candidates = new List<string> { requested };
        if (fallbackFamilies != null) candidates.AddRange(fallbackFamilies);
        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        var failures = new List<string>();
        foreach (string candidate in candidates)
        {
            if (string.IsNullOrWhiteSpace(candidate)) throw new ArgumentException("后备字体家族不能为空。", nameof(fallbackFamilies));
            string name = candidate.Trim();
            if (!seen.Add(name)) continue;
            using FontFamily? selected = FindFamily(name);
            if (selected == null) { failures.Add(name + "：未安装"); continue; }
            if (!selected.IsStyleAvailable((FontStyle)style)) { failures.Add(name + "：字形样式不可用"); continue; }
            using var font = new Font(selected, 1000, (FontStyle)style, GraphicsUnit.Pixel);
            using var bitmap = new Bitmap(1, 1);
            using var graphics = Graphics.FromImage(bitmap);
            string missing = MissingCharacters(graphics, font, text);
            if (missing.Length != 0) { failures.Add(name + "：缺少 " + missing); continue; }
            string? warning = failures.Count == 0 ? null : string.Join("；", failures) + "；已使用 " + selected.Name;
            return Outline(graphics, font, text, requested, selected, style, warning);
        }
        throw new InvalidOperationException("无法为文字段选择字体：" + string.Join("；", failures));
#else
        throw new PlatformNotSupportedException("系统字体轮廓生成需要 Windows .NET Framework Office 渲染宿主。");
#endif
    }

#if NET48
    private static FontFamily? FindFamily(string name)
    {
        FontFamily family;
        try { family = new FontFamily(name); }
        catch (ArgumentException) { return null; }
        if (string.Equals(family.Name, name, StringComparison.OrdinalIgnoreCase)
            || string.Equals(family.GetName(1033), name, StringComparison.OrdinalIgnoreCase)) return family;
        family.Dispose();
        return null;
    }

    private static string MissingCharacters(Graphics graphics, Font font, string text)
    {
        if (text.Length == 0) return string.Empty;
        IntPtr handle = font.ToHfont();
        IntPtr dc = IntPtr.Zero;
        IntPtr previous = IntPtr.Zero;
        try
        {
            dc = graphics.GetHdc();
            previous = SelectObject(dc, handle);
            if (previous == IntPtr.Zero || previous == new IntPtr(-1)) throw new InvalidOperationException("无法选择字体设备对象。");
            var glyphs = new ushort[text.Length];
            if (GetGlyphIndices(dc, text, text.Length, glyphs, 1) == uint.MaxValue)
                throw new InvalidOperationException("无法检查字体字符覆盖。");
            var missing = new StringBuilder();
            for (int index = 0; index < glyphs.Length; index++)
                if (glyphs[index] == ushort.MaxValue) missing.Append("U+").Append(((int)text[index]).ToString("X4")).Append(' ');
            return missing.ToString().TrimEnd();
        }
        finally
        {
            if (previous != IntPtr.Zero && previous != new IntPtr(-1)) SelectObject(dc, previous);
            if (dc != IntPtr.Zero) graphics.ReleaseHdc(dc);
            DeleteObject(handle);
        }
    }

    private static FontRunOutline Outline(Graphics graphics, Font font, string text, string requested,
        FontFamily family, FontRunStyle style, string? warning)
    {
        using var format = (StringFormat)StringFormat.GenericTypographic.Clone();
        format.FormatFlags |= StringFormatFlags.MeasureTrailingSpaces | StringFormatFlags.NoWrap | StringFormatFlags.NoFontFallback;
        float ascent = 1000f * family.GetCellAscent((FontStyle)style) / family.GetEmHeight((FontStyle)style);
        double advance = text.Length == 0 ? 0 : graphics.MeasureString(text, font, PointF.Empty, format).Width / 1000d;
        using var path = new GraphicsPath(FillMode.Winding);
        if (text.Length != 0) path.AddString(text, family, (int)style, 1000, new PointF(0, -ascent), format);
        if (path.PointCount == 0)
            return new FontRunOutline(text, requested, family.GetName(1033), style, advance, 0, 0, 0, 0, string.Empty, warning);
        using var flip = new Matrix(1, 0, 0, -1, 0, 0);
        path.Transform(flip);
        RectangleF bounds = path.GetBounds();
        return new FontRunOutline(text, requested, family.GetName(1033), style, advance,
            Math.Max(0, bounds.Bottom) / 1000d, Math.Max(0, -bounds.Top) / 1000d,
            bounds.Left / 1000d, bounds.Right / 1000d, ToSvgPath(path), warning);
    }

    private static string ToSvgPath(GraphicsPath path)
    {
        PointF[] points = path.PathPoints;
        byte[] types = path.PathTypes;
        var result = new StringBuilder();
        for (int index = 0; index < points.Length; index++)
        {
            int kind = types[index] & 7;
            if (kind == (int)PathPointType.Start) result.Append('M');
            else if (kind == (int)PathPointType.Line) result.Append('L');
            else if (kind == (int)PathPointType.Bezier)
            {
                if (index + 2 >= points.Length) throw new InvalidOperationException("字形曲线路径不完整。");
                result.Append('C');
                AppendPoint(result, points[index++]);
                AppendPoint(result, points[index++]);
            }
            else throw new InvalidOperationException("字形路径类型无效。");
            AppendPoint(result, points[index]);
            if ((types[index] & (int)PathPointType.CloseSubpath) != 0) result.Append('Z');
        }
        return result.ToString().TrimEnd();
    }

    private static void AppendPoint(StringBuilder target, PointF point) => target
        .Append(point.X.ToString("0.###", CultureInfo.InvariantCulture)).Append(' ')
        .Append(point.Y.ToString("0.###", CultureInfo.InvariantCulture)).Append(' ');

    [DllImport("gdi32.dll", EntryPoint = "GetGlyphIndicesW", CharSet = CharSet.Unicode, ExactSpelling = true)]
    private static extern uint GetGlyphIndices(IntPtr dc, string text, int count, [Out] ushort[] glyphs, uint flags);
    [DllImport("gdi32.dll")]
    private static extern IntPtr SelectObject(IntPtr dc, IntPtr value);
    [DllImport("gdi32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool DeleteObject(IntPtr value);
#endif
}
