using System;
using System.Globalization;
using System.Text;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public static class WordAutomaticNumberFormatter
{
    public static string Format(int number)
    {
        WordPluginSettings settings = WordPluginSettings.Load();
        return Format(number, settings.NumberFormat, settings.NumberEnclosure);
    }

    public static string Format(int chapter, int section, int equation, WordPluginSettings settings)
    {
        var parts = new System.Collections.Generic.List<string>();
        if (settings.IncludeChapter)
        {
            parts.Add(chapter.ToString(CultureInfo.InvariantCulture));
        }

        if (settings.IncludeSection)
        {
            parts.Add(section.ToString(CultureInfo.InvariantCulture));
        }

        parts.Add(FormatBody(equation, settings.NumberFormat));
        return Enclose(string.Join(settings.NumberSeparator, parts), settings.NumberEnclosure);
    }

    public static string Format(int number, WordNumberFormat format, WordNumberEnclosure enclosure)
    {
        return Enclose(FormatBody(number, format), enclosure);
    }

    private static string FormatBody(int number, WordNumberFormat format)
    {
        return format switch
        {
            WordNumberFormat.LowerRoman => ToRoman(number).ToLowerInvariant(),
            WordNumberFormat.UpperRoman => ToRoman(number),
            WordNumberFormat.LowerLetter => ToLetters(number).ToLowerInvariant(),
            WordNumberFormat.UpperLetter => ToLetters(number),
            _ => number.ToString(CultureInfo.InvariantCulture),
        };
    }

    private static string Enclose(string body, WordNumberEnclosure enclosure)
    {
        return enclosure switch
        {
            WordNumberEnclosure.SquareBrackets => "[" + body + "]",
            WordNumberEnclosure.Braces => "{" + body + "}",
            WordNumberEnclosure.None => body,
            _ => "(" + body + ")",
        };
    }

    private static string ToRoman(int number)
    {
        if (number <= 0)
        {
            return "0";
        }

        (int Value, string Text)[] tokens =
        {
            (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
            (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
            (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
        };
        var builder = new StringBuilder();
        int remaining = number;
        foreach ((int value, string text) in tokens)
        {
            while (remaining >= value)
            {
                builder.Append(text);
                remaining -= value;
            }
        }

        return builder.ToString();
    }

    private static string ToLetters(int number)
    {
        if (number <= 0)
        {
            return "0";
        }

        var builder = new StringBuilder();
        int value = number;
        while (value > 0)
        {
            value--;
            builder.Insert(0, (char)('A' + value % 26));
            value /= 26;
        }

        return builder.ToString();
    }
}
