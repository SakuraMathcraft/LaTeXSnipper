#if NET48
using System;
using System.Drawing;
using System.Drawing.Text;
using System.Linq;
using System.Runtime.InteropServices;

namespace LaTeXSnipper.OfficePlugin.Editor;

public static class TypographySystemFonts
{
    private const string HanProbe = "中文汉字國學数式";
    private static readonly Lazy<(string[] All, string[] Cjk)> Cached = new Lazy<(string[], string[])>(Read);

    public static string[] List() => (string[])Cached.Value.All.Clone();

    public static string[] ListCjk() => (string[])Cached.Value.Cjk.Clone();

    private static (string[] All, string[] Cjk) Read()
    {
        using var installed = new InstalledFontCollection();
        var families = installed.Families;
        try
        {
            return (families.Select(font => font.Name).Distinct().OrderBy(name => name).ToArray(),
                families.Where(IsUsableHanFont).Select(font => font.Name).Distinct().OrderBy(name => name).ToArray());
        }
        finally { foreach (var family in families) family.Dispose(); }
    }

    private static bool IsUsableHanFont(FontFamily family)
    {
        try { return HasHanGlyph(family); }
        catch (ArgumentException) { return false; }
        catch (ExternalException) { return false; }
    }

    private static bool HasHanGlyph(FontFamily family)
    {
        var styles = new[] { FontStyle.Regular, FontStyle.Bold, FontStyle.Italic, FontStyle.Bold | FontStyle.Italic };
        var style = styles.FirstOrDefault(family.IsStyleAvailable);
        if (!family.IsStyleAvailable(style)) return false;
        using var font = new Font(family, 12, style, GraphicsUnit.Pixel);
        using var bitmap = new Bitmap(1, 1);
        using var graphics = Graphics.FromImage(bitmap);
        IntPtr handle = font.ToHfont();
        IntPtr dc = IntPtr.Zero;
        IntPtr previous = IntPtr.Zero;
        try
        {
            dc = graphics.GetHdc();
            previous = SelectObject(dc, handle);
            if (previous == IntPtr.Zero || previous == new IntPtr(-1))
                throw new InvalidOperationException("无法检查已安装字体。");
            var glyphs = new ushort[HanProbe.Length];
            if (GetGlyphIndices(dc, HanProbe, HanProbe.Length, glyphs, 1) == uint.MaxValue)
                throw new InvalidOperationException("无法检查汉字字体覆盖。");
            return glyphs.Any(glyph => glyph != ushort.MaxValue);
        }
        finally
        {
            if (previous != IntPtr.Zero && previous != new IntPtr(-1)) SelectObject(dc, previous);
            if (dc != IntPtr.Zero) graphics.ReleaseHdc(dc);
            DeleteObject(handle);
        }
    }

    [DllImport("gdi32.dll")]
    private static extern IntPtr SelectObject(IntPtr dc, IntPtr value);

    [DllImport("gdi32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool DeleteObject(IntPtr value);

    [DllImport("gdi32.dll", EntryPoint = "GetGlyphIndicesW", CharSet = CharSet.Unicode, ExactSpelling = true)]
    private static extern uint GetGlyphIndices(IntPtr dc, string text, int count, [Out] ushort[] glyphs, uint flags);
}
#endif
