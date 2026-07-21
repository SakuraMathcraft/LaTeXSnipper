using System;
using System.Collections.Generic;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

internal enum LatexDelimiterKind
{
    InlineDollar,
    InlineParenthesis,
    DisplayDollar,
    DisplayBracket
}

internal sealed class LatexDelimiterMatch
{
    public LatexDelimiterMatch(
        int offset,
        int length,
        string originalText,
        string latex,
        LatexDelimiterKind delimiterKind,
        FormulaDisplayMode displayMode)
    {
        Offset = offset;
        Length = length;
        OriginalText = originalText;
        Latex = latex;
        DelimiterKind = delimiterKind;
        DisplayMode = displayMode;
    }

    public int Offset { get; }

    public int Length { get; }

    public string OriginalText { get; }

    public string Latex { get; }

    public LatexDelimiterKind DelimiterKind { get; }

    public FormulaDisplayMode DisplayMode { get; }
}

internal static class LatexDelimiterScanner
{
    private const char UnsafeBoundary = '\0';
    private const char TableCellBoundary = '\a';

    public static IReadOnlyList<LatexDelimiterMatch> Scan(string text)
    {
        var matches = new List<LatexDelimiterMatch>();
        if (string.IsNullOrEmpty(text))
        {
            return matches;
        }

        int index = 0;
        while (index < text.Length)
        {
            if (!TryReadOpeningDelimiter(text, index, out Delimiter delimiter))
            {
                index++;
                continue;
            }

            int contentStart = index + delimiter.Open.Length;
            int close = FindClosingDelimiter(text, contentStart, delimiter);
            if (close < 0)
            {
                index += delimiter.Open.Length;
                continue;
            }

            string latex = text.Substring(contentStart, close - contentStart).Trim();
            int end = close + delimiter.Close.Length;
            if (latex.Length > 0)
            {
                matches.Add(new LatexDelimiterMatch(
                    index,
                    end - index,
                    text.Substring(index, end - index),
                    latex,
                    delimiter.Kind,
                    delimiter.DisplayMode));
            }

            index = end;
        }

        return matches;
    }

    private static bool TryReadOpeningDelimiter(string text, int index, out Delimiter delimiter)
    {
        delimiter = default;
        if (IsHardBoundary(text[index]))
        {
            return false;
        }

        if (Matches(text, index, "$$") && !IsEscaped(text, index))
        {
            delimiter = new Delimiter("$$", "$$", LatexDelimiterKind.DisplayDollar, FormulaDisplayMode.Display);
            return true;
        }

        if (text[index] == '$' && !IsEscaped(text, index))
        {
            delimiter = new Delimiter("$", "$", LatexDelimiterKind.InlineDollar, FormulaDisplayMode.Inline);
            return true;
        }

        if (Matches(text, index, "\\(") && !IsEscaped(text, index))
        {
            delimiter = new Delimiter("\\(", "\\)", LatexDelimiterKind.InlineParenthesis, FormulaDisplayMode.Inline);
            return true;
        }

        if (Matches(text, index, "\\[") && !IsEscaped(text, index))
        {
            delimiter = new Delimiter("\\[", "\\]", LatexDelimiterKind.DisplayBracket, FormulaDisplayMode.Display);
            return true;
        }

        return false;
    }

    private static int FindClosingDelimiter(string text, int start, Delimiter delimiter)
    {
        for (int index = start; index <= text.Length - delimiter.Close.Length; index++)
        {
            char current = text[index];
            if (IsHardBoundary(current))
            {
                return -1;
            }

            if (delimiter.DisplayMode == FormulaDisplayMode.Inline && (current == '\r' || current == '\n'))
            {
                return -1;
            }

            if (Matches(text, index, delimiter.Close) && !IsEscaped(text, index))
            {
                return index;
            }
        }

        return -1;
    }

    private static bool Matches(string text, int index, string value)
    {
        return index >= 0
            && index + value.Length <= text.Length
            && string.CompareOrdinal(text, index, value, 0, value.Length) == 0;
    }

    private static bool IsEscaped(string text, int index)
    {
        int backslashes = 0;
        for (int cursor = index - 1; cursor >= 0 && text[cursor] == '\\'; cursor--)
        {
            backslashes++;
        }

        return backslashes % 2 != 0;
    }

    private static bool IsHardBoundary(char value)
    {
        return value == UnsafeBoundary || value == TableCellBoundary;
    }

    private readonly struct Delimiter
    {
        public Delimiter(string open, string close, LatexDelimiterKind kind, FormulaDisplayMode displayMode)
        {
            Open = open;
            Close = close;
            Kind = kind;
            DisplayMode = displayMode;
        }

        public string Open { get; }

        public string Close { get; }

        public LatexDelimiterKind Kind { get; }

        public FormulaDisplayMode DisplayMode { get; }
    }
}
