using System;
using System.Text;

namespace LaTeXSnipper.OfficePlugin.Abstractions;

public static class MathLiveLatexStyleNormalizer
{
    private static readonly string[] ColorCommands = { "\\textcolor", "\\colorbox", "\\color" };

    public static string RemoveColorFormatting(string latex)
    {
        return RemoveColorFormattingCore(latex ?? string.Empty);
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
