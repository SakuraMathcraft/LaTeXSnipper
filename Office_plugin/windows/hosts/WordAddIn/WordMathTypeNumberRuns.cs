using System;
using System.Globalization;
using System.Text.RegularExpressions;
using System.Xml.Linq;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

internal static class WordMathTypeNumberRuns
{
    public const string PlaceReference = "MACROBUTTON MTPlaceRef";
    public const string SectionBoundary = "MACROBUTTON MTEditEquationSection2";
    public const string EquationSequence = "MTEqn";
    private static readonly XNamespace W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main";
    private static readonly Regex FinalNumber = new(@"[0-9]+(?=[^0-9]*\z)", RegexOptions.CultureInvariant);

    public static string CreateMathTypeNumber(string label, NumberingMode mode, string? format = null, string sequenceSwitch = "")
    {
        var markup = new XElement("runs");
        markup.Add(FieldChar("begin"), Instruction(" " + PlaceReference + " \\* MERGEFORMAT "));
        markup.Add(FieldChar("begin"), Instruction(" SEQ " + EquationSequence + sequenceSwitch + " \\h \\* MERGEFORMAT "), FieldChar("end"));
        Match number = FinalNumber.Match(label);
        if (mode == NumberingMode.Automatic && number.Success)
        {
            string prefix = label.Substring(0, number.Index);
            MatchCollection names = Regex.Matches(format ?? "", "#([CS])1");
            MatchCollection values = Regex.Matches(prefix, "[0-9]+");
            int offset = 0;
            if (values.Count == names.Count)
            {
                for (int index = 0; index < names.Count; index++)
                {
                    Match value = values[index];
                    string sequence = names[index].Groups[1].Value == "C" ? "MTChap" : "MTSec";
                    markup.Add(Instruction(prefix.Substring(offset, value.Index - offset)), VisibleSequence(sequence, value.Value));
                    offset = value.Index + value.Length;
                }
            }
            markup.Add(Instruction(prefix.Substring(offset)), VisibleSequence(EquationSequence, number.Value),
                Instruction(label.Substring(number.Index + number.Length)));
        }
        else markup.Add(Instruction(label));
        markup.Add(FieldChar("end"));
        return Document(markup);
    }

    public static string CreateLaTeXSnipperNumber(string label, bool firstInSequence)
    {
        var markup = new XElement("runs");
        Match number = FinalNumber.Match(label);
        if (!number.Success) throw new ArgumentException("The automatic equation number has no Arabic counter.", nameof(label));
        string left = PictureLiteral(label.Substring(0, number.Index));
        string right = PictureLiteral(label.Substring(number.Index + number.Length));
        string reset = firstInSequence && int.TryParse(number.Value, NumberStyles.None, CultureInfo.InvariantCulture, out int index)
            ? " \\r " + index.ToString(CultureInfo.InvariantCulture) : string.Empty;
        markup.Add(FieldChar("begin"),
            Instruction(" SEQ " + WordEquationNumbering.SequenceName + reset + " \\# \"" + left + "0" + right + "\" \\* Charformat "),
            FieldChar("separate"), Run("t", label), FieldChar("end"));
        return Document(markup);
    }

    public static bool HasArabicCounter(string label) => FinalNumber.IsMatch(label);

    private static string PictureLiteral(string text) => text.Length == 0 ? string.Empty : "'" + text.Replace("'", "''") + "'";
    private static XElement FieldChar(string kind) => new(W + "r", new XElement(W + "fldChar", new XAttribute(W + "fldCharType", kind)));
    private static XElement VisibleSequence(string name, string value) =>
        new(W + "fldSimple", new XAttribute(W + "instr", " SEQ " + name + " \\c \\* Arabic \\* MERGEFORMAT "), Instruction(value));
    private static XElement Instruction(string text) => Run("instrText", text);
    private static XElement Run(string name, string text) => new(W + "r", new XElement(W + name, new XAttribute(XNamespace.Xml + "space", "preserve"), text));

    private static string Document(XElement runs) => WordOmmlDocumentBuilder.WrapFlatOpc(
        new XElement(W + "document", new XAttribute(XNamespace.Xmlns + "w", W),
            new XElement(W + "body", new XElement(W + "p", runs.Elements()))).ToString(SaveOptions.DisableFormatting));
}
