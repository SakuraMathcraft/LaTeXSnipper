using System;
using System.Security;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

internal static class WordEquationNumbering
{
    public const string SequenceName = "LaTeXSnipperEquation";
    public const string BookmarkPrefix = "LaTeXSnipperEq_";

    public static string BuildSequenceFieldCode(
        bool reset,
        WordNumberFormat format,
        string prefix,
        WordNumberEnclosure enclosure)
    {
        string resetSwitch = reset ? " \\r 1" : string.Empty;
        string numberPicture = BuildNumberPicture(prefix, enclosure);
        string formatSwitch = string.IsNullOrWhiteSpace(numberPicture)
            ? " \\* " + BuildNumberFormatSwitch(format)
            : " \\# \"" + numberPicture + "\"";
        return " SEQ " + SequenceName + resetSwitch + formatSwitch + " ";
    }

    public static string GetLeftEnclosure(WordNumberEnclosure enclosure)
    {
        return enclosure switch
        {
            WordNumberEnclosure.Parentheses => "(",
            WordNumberEnclosure.SquareBrackets => "[",
            WordNumberEnclosure.Braces => "{",
            WordNumberEnclosure.None => string.Empty,
            _ => "(",
        };
    }

    public static string GetRightEnclosure(WordNumberEnclosure enclosure)
    {
        return enclosure switch
        {
            WordNumberEnclosure.Parentheses => ")",
            WordNumberEnclosure.SquareBrackets => "]",
            WordNumberEnclosure.Braces => "}",
            WordNumberEnclosure.None => string.Empty,
            _ => ")",
        };
    }

    private static string BuildNumberFormatSwitch(WordNumberFormat format)
    {
        return format switch
        {
            WordNumberFormat.LowerRoman => "roman",
            WordNumberFormat.UpperRoman => "ROMAN",
            WordNumberFormat.LowerLetter => "alphabetic",
            WordNumberFormat.UpperLetter => "ALPHABETIC",
            _ => "Arabic",
        };
    }

    private static string BuildNumberPicture(string prefix, WordNumberEnclosure enclosure)
    {
        string left = GetLeftEnclosure(enclosure) + prefix;
        string right = GetRightEnclosure(enclosure);
        if (string.IsNullOrEmpty(left) && string.IsNullOrEmpty(right))
        {
            return string.Empty;
        }

        return QuoteNumberPictureLiteral(left) + "0" + QuoteNumberPictureLiteral(right);
    }

    private static string QuoteNumberPictureLiteral(string value)
    {
        return string.IsNullOrEmpty(value)
            ? string.Empty
            : "'" + value.Replace("'", "''") + "'";
    }

    public static string BuildBookmarkName(string equationId)
    {
        if (string.IsNullOrWhiteSpace(equationId))
        {
            throw new ArgumentException("Equation ID is required.", nameof(equationId));
        }

        return BookmarkPrefix + equationId;
    }

    public static string EscapeXml(string value)
    {
        return SecurityElement.Escape(value) ?? string.Empty;
    }
}
