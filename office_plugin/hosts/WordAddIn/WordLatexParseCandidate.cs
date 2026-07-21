using System;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public sealed class WordLatexParseCandidate
{
    public WordLatexParseCandidate(
        int start,
        int end,
        string originalText,
        string latex,
        FormulaDisplayMode displayMode)
    {
        if (start < 0 || end <= start)
        {
            throw new ArgumentOutOfRangeException(nameof(start));
        }

        Start = start;
        End = end;
        OriginalText = originalText ?? throw new ArgumentNullException(nameof(originalText));
        Latex = latex ?? throw new ArgumentNullException(nameof(latex));
        DisplayMode = displayMode;
    }

    public int Start { get; }

    public int End { get; }

    public string OriginalText { get; }

    public string Latex { get; }

    public FormulaDisplayMode DisplayMode { get; }
}
