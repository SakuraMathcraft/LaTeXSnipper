using System;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

internal sealed class LatexTagPreprocessResult
{
    private LatexTagPreprocessResult(bool success, string latex, string? numberText)
    {
        Success = success;
        Latex = latex;
        NumberText = numberText;
    }

    public bool Success { get; }

    public string Latex { get; }

    public string? NumberText { get; }

    public bool HasTag => NumberText != null;

    public static LatexTagPreprocessResult Valid(string latex, string? numberText = null)
    {
        return new LatexTagPreprocessResult(true, latex, numberText);
    }

    public static LatexTagPreprocessResult Invalid()
    {
        return new LatexTagPreprocessResult(false, string.Empty, null);
    }
}

internal static class LatexTagPreprocessor
{
    private const string TagCommand = "\\tag";

    public static LatexTagPreprocessResult Process(string latex, bool display)
    {
        if (string.IsNullOrWhiteSpace(latex))
        {
            return LatexTagPreprocessResult.Invalid();
        }

        int braceDepth = 0;
        int? tagStart = null;
        int tagEnd = -1;
        string? numberText = null;
        bool inComment = false;

        for (int index = 0; index < latex.Length; index++)
        {
            char current = latex[index];
            if (inComment)
            {
                if (current == '\r' || current == '\n')
                {
                    inComment = false;
                }
                continue;
            }

            if (current == '%' && !IsEscaped(latex, index))
            {
                inComment = true;
                continue;
            }

            if (current == '{' && !IsEscaped(latex, index))
            {
                braceDepth++;
                continue;
            }

            if (current == '}' && !IsEscaped(latex, index))
            {
                braceDepth = Math.Max(0, braceDepth - 1);
                continue;
            }

            if (!MatchesTagCommand(latex, index))
            {
                continue;
            }

            if (!display || braceDepth != 0 || tagStart.HasValue)
            {
                return LatexTagPreprocessResult.Invalid();
            }

            int cursor = index + TagCommand.Length;
            if (cursor < latex.Length && latex[cursor] == '*')
            {
                return LatexTagPreprocessResult.Invalid();
            }

            while (cursor < latex.Length && char.IsWhiteSpace(latex[cursor]))
            {
                cursor++;
            }

            if (cursor >= latex.Length || latex[cursor] != '{')
            {
                return LatexTagPreprocessResult.Invalid();
            }

            int closingBrace = FindBalancedGroupEnd(latex, cursor);
            if (closingBrace < 0)
            {
                return LatexTagPreprocessResult.Invalid();
            }

            string value = latex.Substring(cursor + 1, closingBrace - cursor - 1).Trim();
            if (value.Length == 0)
            {
                return LatexTagPreprocessResult.Invalid();
            }

            tagStart = index;
            tagEnd = closingBrace + 1;
            numberText = value;
            index = closingBrace;
        }

        if (!tagStart.HasValue)
        {
            return LatexTagPreprocessResult.Valid(latex.Trim());
        }

        string cleaned = (latex.Substring(0, tagStart.Value) + latex.Substring(tagEnd)).Trim();
        return cleaned.Length == 0
            ? LatexTagPreprocessResult.Invalid()
            : LatexTagPreprocessResult.Valid(cleaned, numberText);
    }

    private static bool MatchesTagCommand(string latex, int index)
    {
        if (index < 0
            || index + TagCommand.Length > latex.Length
            || string.CompareOrdinal(latex, index, TagCommand, 0, TagCommand.Length) != 0
            || IsEscaped(latex, index))
        {
            return false;
        }

        int end = index + TagCommand.Length;
        return end >= latex.Length || !char.IsLetter(latex[end]);
    }

    private static int FindBalancedGroupEnd(string latex, int openingBrace)
    {
        int depth = 0;
        for (int index = openingBrace; index < latex.Length; index++)
        {
            if (latex[index] == '{' && !IsEscaped(latex, index))
            {
                depth++;
            }
            else if (latex[index] == '}' && !IsEscaped(latex, index))
            {
                depth--;
                if (depth == 0)
                {
                    return index;
                }
            }
        }

        return -1;
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
}
