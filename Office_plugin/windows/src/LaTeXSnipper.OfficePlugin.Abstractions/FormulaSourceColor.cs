using System;
using System.IO;
using System.Linq;
using System.Text.RegularExpressions;
using System.Xml;
using System.Xml.Linq;

namespace LaTeXSnipper.OfficePlugin.Abstractions;

internal static class FormulaSourceColor
{
    private static readonly Regex MathMlStart = new Regex(
        @"\A\s*(?:<\?xml\s[^?]*\?>\s*)?<(?:[\w.-]+:)?math(?=[\s/>])",
        RegexOptions.CultureInvariant);

    internal static string Reset(string source, string color) =>
        MathMlStart.IsMatch(source) ? ResetMathMl(source, color) : ResetLatex(source, color);

    private static string ResetMathMl(string source, string color)
    {
        using var reader = XmlReader.Create(new StringReader(source), new XmlReaderSettings { DtdProcessing = DtdProcessing.Prohibit });
        var document = XDocument.Load(reader, LoadOptions.PreserveWhitespace);
        var root = document.Root!;
        bool changed = SetMathMlColor(root, color == "#000000" ? null : color);

        // A style node spanning the whole expression sets the formula color.
        // Inner styles continue to override it, including explicit black.
        var content = root.Elements().Where(element => element.Name.LocalName is not ("annotation" or "annotation-xml")).Take(2).ToArray();
        if (content.Length == 1 && content[0].Name.Namespace == root.Name.Namespace
            && content[0].Name.LocalName is "mstyle" or "mrow")
            changed |= SetMathMlColor(content[0], null);
        return changed ? document.ToString(SaveOptions.DisableFormatting) : source;
    }

    private static bool SetMathMlColor(XElement element, string? color)
    {
        var legacy = element.Attribute("color");
        var math = element.Attribute("mathcolor");
        if (legacy is null && string.Equals(math?.Value, color, StringComparison.OrdinalIgnoreCase))
            return false;
        legacy?.Remove();
        element.SetAttributeValue("mathcolor", color);
        return true;
    }

    private static string ResetLatex(string source, string color)
    {
        int start = SkipTrivia(source, 0);
        if (start == source.Length) return source;

        bool hasGlobalColor = true;
        if (TryReadColor(source, start, @"\textcolor", out var previousColor, out int argument)
            && TryReadGroup(source, argument = SkipTrivia(source, argument), '{', '}', out int end)
            && SkipTrivia(source, end) == source.Length)
        {
            if (string.Equals(color, previousColor, StringComparison.OrdinalIgnoreCase)
                && argument == start + @"\textcolor{".Length + previousColor.Length + 1
                && string.IsNullOrWhiteSpace(source.Substring(0, start))
                && string.IsNullOrWhiteSpace(source.Substring(end)))
                return source;
            source = source.Substring(0, start) + source.Substring(argument + 1, end - argument - 2) + source.Substring(end);
        }
        else if (TryReadColor(source, start, @"\color", out _, out argument))
        {
            source = source.Remove(start, argument - start);
        }
        else if (source[start] == '{' && TryReadGroup(source, start, '{', '}', out end)
            && SkipTrivia(source, end) == source.Length
            && TryReadColor(source, SkipTrivia(source, start + 1), @"\color", out _, out argument)
            && argument < end)
        {
            int declaration = SkipTrivia(source, start + 1);
            source = source.Remove(declaration, argument - declaration);
        }
        else hasGlobalColor = false;

        if (color == "#000000" && !hasGlobalColor) return source;
        for (int i = 0; i < source.Length; i++)
        {
            bool comment = source[i] == '%';
            if (!SkipLiteral(source, ref i)) continue;
            if (comment && i == source.Length) return @"\textcolor{" + color + "}{" + source + "\n}";
            i--;
        }
        return @"\textcolor{" + color + "}{" + source + "}";
    }

    private static bool TryReadColor(string source, int start, string command, out string color, out int next)
    {
        color = string.Empty;
        next = start + command.Length;
        if (next > source.Length || string.CompareOrdinal(source, start, command, 0, command.Length) != 0)
            return false;
        int argument = SkipTrivia(source, next);
        if (argument < source.Length && source[argument] == '[')
        {
            if (!TryReadGroup(source, argument, '[', ']', out int modelEnd)) return false;
            argument = SkipTrivia(source, modelEnd);
        }
        if (!TryReadGroup(source, argument, '{', '}', out next)) return false;
        color = source.Substring(argument + 1, next - argument - 2);
        return true;
    }

    private static bool TryReadGroup(string source, int start, char open, char close, out int end)
    {
        end = start;
        if (start >= source.Length || source[start] != open) return false;
        int depth = 1;
        for (int i = start + 1; i < source.Length; i++)
        {
            if (SkipLiteral(source, ref i)) { i--; continue; }
            if (source[i] == open) depth++;
            else if (source[i] == close && --depth == 0)
            {
                end = i + 1;
                return true;
            }
        }
        return false;
    }

    private static int SkipTrivia(string source, int index)
    {
        while (index < source.Length)
        {
            if (char.IsWhiteSpace(source[index])) index++;
            else if (source[index] == '%') SkipLiteral(source, ref index);
            else break;
        }
        return index;
    }

    private static bool SkipLiteral(string source, ref int index)
    {
        if (source[index] == '%')
        {
            while (index < source.Length && source[index] is not ('\r' or '\n')) index++;
            return true;
        }
        if (source[index] != '\\') return false;
        int end = index + 5;
        if (end < source.Length && string.CompareOrdinal(source, index, @"\verb", 0, 5) == 0
            && !char.IsLetter(source[end]))
        {
            if (source[end] == '*') end++;
            if (end < source.Length)
            {
                int closing = source.IndexOf(source[end], end + 1);
                if (closing >= 0) { index = closing + 1; return true; }
            }
        }
        index = Math.Min(index + 2, source.Length);
        return true;
    }
}
