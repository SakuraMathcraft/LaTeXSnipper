using System.Text.RegularExpressions;

namespace LaTeXSnipper.OfficePlugin.Abstractions;

public static class MathLiveLatexStyleNormalizer
{
    public static string NormalizeLatex(string latex)
    {
        return Regex.Replace(latex ?? string.Empty, @"\\bm(?=\s*\{)", "\\boldsymbol");
    }
}
