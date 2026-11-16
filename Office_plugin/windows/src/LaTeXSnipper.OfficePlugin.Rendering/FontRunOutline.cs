using System;

namespace LaTeXSnipper.OfficePlugin.Rendering;

/// <summary>Supported physical styles of a system-font text run.</summary>
[Flags]
public enum FontRunStyle { Regular = 0, Bold = 1, Italic = 2 }

/// <summary>One baseline-relative outline and its metrics, in em units (SVG path coordinates use 1000 units/em).</summary>
public sealed class FontRunOutline
{
    internal FontRunOutline(string text, string requestedFamily, string actualFamily, FontRunStyle style,
        double advance, double height, double depth, double left, double right, string path, string? warning)
    {
        Text = text;
        RequestedFamily = requestedFamily;
        ActualFamily = actualFamily;
        Style = style;
        Advance = advance;
        Height = height;
        Depth = depth;
        Left = left;
        Right = right;
        Path = path;
        Warning = warning;
    }

    public string Text { get; }
    public string RequestedFamily { get; }
    public string ActualFamily { get; }
    public FontRunStyle Style { get; }
    public double Advance { get; }
    public double Height { get; }
    public double Depth { get; }
    /// <summary>Leftmost ink position; can be negative for italic overhang.</summary>
    public double Left { get; }
    /// <summary>Rightmost ink position, independent of the advance width.</summary>
    public double Right { get; }
    public string Path { get; }
    public string? Warning { get; }
}
