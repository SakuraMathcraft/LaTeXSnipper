using System;
using System.Text;

namespace LaTeXSnipper.OfficePlugin.Abstractions;

public static class MathLiveLatexStyleNormalizer
{
    private static readonly string[] ColorCommands = { "\\textcolor", "\\colorbox", "\\color" };
    private static readonly string[] FontStyleCommands = { "\\mathrm", "\\mathbf", "\\bm", "\\mathit" };
    private static readonly string[] MultilineEnvironments = { "aligned", "gathered", "split", "multline" };

    public static string RemoveColorFormatting(string latex)
    {
        return RemoveColorFormattingCore(latex ?? string.Empty);
    }

    public static string ApplyRenderFontStyle(string latex, FormulaFontStyle fontStyle)
    {
        string source = latex ?? string.Empty;
        if (fontStyle == FormulaFontStyle.TeX || HasTopLevelFontStyleFormatting(source))
        {
            return source;
        }

        if (TryWrapDisplayLines(source, fontStyle, out string displayLines))
        {
            return displayLines;
        }

        if (TryWrapMultilineEnvironment(source, fontStyle, out string environment))
        {
            return environment;
        }

        return WrapFontStyle(source, fontStyle);
    }

    public static bool HasColorFormatting(string latex)
    {
        string source = latex ?? string.Empty;
        foreach (string command in ColorCommands)
        {
            if (source.IndexOf(command, StringComparison.Ordinal) >= 0)
            {
                return true;
            }
        }

        return false;
    }

    private static string RemoveColorFormattingCore(string source)
    {
        var result = new StringBuilder(source.Length);
        int cursor = 0;
        while (cursor < source.Length)
        {
            if (!TryReadColorCommand(source, cursor, out int end, out string body))
            {
                result.Append(source[cursor]);
                cursor++;
                continue;
            }

            result.Append(RemoveColorFormattingCore(TrimMathDelimiters(body)));
            cursor = end;
        }

        return result.ToString();
    }

    private static bool TryReadColorCommand(string source, int start, out int end, out string body)
    {
        end = start;
        body = string.Empty;
        foreach (string command in ColorCommands)
        {
            if (start + command.Length > source.Length
                || string.Compare(source, start, command, 0, command.Length, StringComparison.Ordinal) != 0)
            {
                continue;
            }

            int cursor = SkipWhitespace(source, start + command.Length);
            if (!TryReadGroup(source, cursor, out _, out cursor))
            {
                return false;
            }

            cursor = SkipWhitespace(source, cursor);
            if (!TryReadGroup(source, cursor, out body, out end))
            {
                end = cursor;
                body = string.Empty;
            }

            return true;
        }

        return false;
    }

    private static bool TryReadFontStyleCommand(string source, int start, out int end, out string body)
    {
        end = start;
        body = string.Empty;
        foreach (string command in FontStyleCommands)
        {
            if (start + command.Length > source.Length
                || string.Compare(source, start, command, 0, command.Length, StringComparison.Ordinal) != 0)
            {
                continue;
            }

            int cursor = SkipWhitespace(source, start + command.Length);
            return TryReadGroup(source, cursor, out body, out end);
        }

        return false;
    }

    private static bool HasTopLevelFontStyleFormatting(string source)
    {
        int cursor = SkipWhitespace(source, 0);
        return TryReadFontStyleCommand(source, cursor, out int end, out _)
            && SkipWhitespace(source, end) == source.Length;
    }

    private static string WrapFontStyle(string latex, FormulaFontStyle fontStyle)
    {
        return fontStyle switch
        {
            FormulaFontStyle.RomanUpright => "\\mathrm{" + latex + "}",
            FormulaFontStyle.Bold => "\\bm{" + latex + "}",
            FormulaFontStyle.Italic => "\\mathit{" + latex + "}",
            _ => latex,
        };
    }

    private static bool TryWrapDisplayLines(string source, FormulaFontStyle fontStyle, out string result)
    {
        result = string.Empty;
        int cursor = SkipWhitespace(source, 0);
        const string command = "\\displaylines";
        if (cursor + command.Length > source.Length
            || string.Compare(source, cursor, command, 0, command.Length, StringComparison.Ordinal) != 0)
        {
            return false;
        }

        int groupStart = SkipWhitespace(source, cursor + command.Length);
        if (!TryReadGroup(source, groupStart, out string body, out int end)
            || SkipWhitespace(source, end) != source.Length)
        {
            return false;
        }

        result = source.Substring(0, groupStart + 1)
            + WrapTopLevelSegments(body, fontStyle)
            + source.Substring(end - 1);
        return true;
    }

    private static bool TryWrapMultilineEnvironment(string source, FormulaFontStyle fontStyle, out string result)
    {
        result = string.Empty;
        int cursor = SkipWhitespace(source, 0);
        foreach (string environment in MultilineEnvironments)
        {
            string begin = "\\begin{" + environment + "}";
            string end = "\\end{" + environment + "}";
            if (cursor + begin.Length > source.Length
                || string.Compare(source, cursor, begin, 0, begin.Length, StringComparison.Ordinal) != 0)
            {
                continue;
            }

            int endStart = source.LastIndexOf(end, StringComparison.Ordinal);
            if (endStart < cursor + begin.Length
                || SkipWhitespace(source, endStart + end.Length) != source.Length)
            {
                return false;
            }

            string body = source.Substring(cursor + begin.Length, endStart - cursor - begin.Length);
            result = source.Substring(0, cursor + begin.Length)
                + WrapTopLevelSegments(body, fontStyle)
                + source.Substring(endStart);
            return true;
        }

        return false;
    }

    private static string WrapTopLevelSegments(string source, FormulaFontStyle fontStyle)
    {
        var result = new StringBuilder(source.Length + 32);
        var segment = new StringBuilder(source.Length);
        int depth = 0;
        for (int index = 0; index < source.Length; index++)
        {
            char current = source[index];
            if (current == '\\')
            {
                if (index + 1 < source.Length && source[index + 1] == '\\' && depth == 0)
                {
                    AppendWrappedSegment(result, segment.ToString(), fontStyle);
                    segment.Clear();
                    result.Append(@"\\");
                    index++;
                    continue;
                }

                segment.Append(current);
                if (index + 1 < source.Length && (source[index + 1] == '{' || source[index + 1] == '}'))
                {
                    segment.Append(source[index + 1]);
                    index++;
                }

                continue;
            }

            if (current == '{')
            {
                depth++;
            }
            else if (current == '}' && depth > 0)
            {
                depth--;
            }
            else if (current == '&' && depth == 0)
            {
                AppendWrappedSegment(result, segment.ToString(), fontStyle);
                segment.Clear();
                result.Append(current);
                continue;
            }

            segment.Append(current);
        }

        AppendWrappedSegment(result, segment.ToString(), fontStyle);
        return result.ToString();
    }

    private static void AppendWrappedSegment(StringBuilder result, string segment, FormulaFontStyle fontStyle)
    {
        if (string.IsNullOrWhiteSpace(segment) || HasTopLevelFontStyleFormatting(segment))
        {
            result.Append(segment);
            return;
        }

        int prefixLength = 0;
        while (prefixLength < segment.Length && char.IsWhiteSpace(segment[prefixLength]))
        {
            prefixLength++;
        }

        int suffixStart = segment.Length;
        while (suffixStart > prefixLength && char.IsWhiteSpace(segment[suffixStart - 1]))
        {
            suffixStart--;
        }

        result.Append(segment, 0, prefixLength);
        result.Append(WrapFontStyle(segment.Substring(prefixLength, suffixStart - prefixLength), fontStyle));
        result.Append(segment, suffixStart, segment.Length - suffixStart);
    }

    private static bool TryReadGroup(string source, int start, out string content, out int end)
    {
        content = string.Empty;
        end = start;
        if (start >= source.Length || source[start] != '{')
        {
            return false;
        }

        int depth = 0;
        for (int index = start; index < source.Length; index++)
        {
            if (source[index] == '\\')
            {
                index++;
                continue;
            }

            if (source[index] == '{')
            {
                depth++;
            }
            else if (source[index] == '}' && --depth == 0)
            {
                content = source.Substring(start + 1, index - start - 1);
                end = index + 1;
                return true;
            }
        }

        return false;
    }

    private static int SkipWhitespace(string source, int cursor)
    {
        while (cursor < source.Length && char.IsWhiteSpace(source[cursor]))
        {
            cursor++;
        }

        return cursor;
    }

    private static string TrimMathDelimiters(string source)
    {
        string trimmed = source.Trim();
        return trimmed.Length >= 2 && trimmed[0] == '$' && trimmed[trimmed.Length - 1] == '$'
            ? trimmed.Substring(1, trimmed.Length - 2)
            : source;
    }
}
