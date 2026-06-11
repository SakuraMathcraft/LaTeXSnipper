using System;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.Rendering;

internal sealed class MathJaxRenderCacheKey : IEquatable<MathJaxRenderCacheKey>
{
    public MathJaxRenderCacheKey(RenderRequest request, string rendererVersion)
    {
        Latex = NormalizeLatex(request.Latex);
        DisplayMode = request.DisplayMode;
        TargetDpi = request.TargetDpi;
        Theme = request.Theme ?? string.Empty;
        FontScale = request.FontScale;
        FontWeightPercent = request.FontWeightPercent;
        RendererVersion = rendererVersion ?? string.Empty;
    }

    public string Latex { get; }

    public FormulaDisplayMode DisplayMode { get; }

    public int TargetDpi { get; }

    public string Theme { get; }

    public double FontScale { get; }

    public int FontWeightPercent { get; }

    public string RendererVersion { get; }

    public bool Equals(MathJaxRenderCacheKey? other)
    {
        return other != null
            && Latex == other.Latex
            && DisplayMode == other.DisplayMode
            && TargetDpi == other.TargetDpi
            && Theme == other.Theme
            && FontScale.Equals(other.FontScale)
            && FontWeightPercent == other.FontWeightPercent
            && RendererVersion == other.RendererVersion;
    }

    public override bool Equals(object? obj)
    {
        return Equals(obj as MathJaxRenderCacheKey);
    }

    public override int GetHashCode()
    {
        unchecked
        {
            int hash = 17;
            hash = hash * 31 + Latex.GetHashCode();
            hash = hash * 31 + DisplayMode.GetHashCode();
            hash = hash * 31 + TargetDpi.GetHashCode();
            hash = hash * 31 + Theme.GetHashCode();
            hash = hash * 31 + FontScale.GetHashCode();
            hash = hash * 31 + FontWeightPercent;
            hash = hash * 31 + RendererVersion.GetHashCode();
            return hash;
        }
    }

    private static string NormalizeLatex(string latex)
    {
        return (latex ?? string.Empty).Trim();
    }
}
