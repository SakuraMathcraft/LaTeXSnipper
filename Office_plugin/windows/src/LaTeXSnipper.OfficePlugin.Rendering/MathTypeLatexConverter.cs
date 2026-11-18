using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text.RegularExpressions;
using System.Xml.Linq;

namespace LaTeXSnipper.OfficePlugin.Rendering;

internal static class MathTypeLatexConverter
{
    private static readonly Dictionary<char, string> Symbols = new()
    {
        ['α'] = @"\alpha", ['β'] = @"\beta", ['γ'] = @"\gamma", ['δ'] = @"\delta",
        ['ε'] = @"\varepsilon", ['ϵ'] = @"\epsilon", ['θ'] = @"\theta", ['ϑ'] = @"\vartheta",
        ['λ'] = @"\lambda", ['μ'] = @"\mu", ['π'] = @"\pi", ['ρ'] = @"\rho", ['σ'] = @"\sigma",
        ['φ'] = @"\varphi", ['ϕ'] = @"\phi", ['ω'] = @"\omega", ['Γ'] = @"\Gamma", ['Δ'] = @"\Delta",
        ['Σ'] = @"\Sigma", ['Ω'] = @"\Omega", ['∞'] = @"\infty", ['∂'] = @"\partial",
        ['∫'] = @"\int", ['∮'] = @"\oint", ['∬'] = @"\iint", ['∭'] = @"\iiint",
        ['∑'] = @"\sum", ['∏'] = @"\prod", ['⋃'] = @"\bigcup", ['⋂'] = @"\bigcap",
        ['≤'] = @"\leq", ['≥'] = @"\geq", ['≠'] = @"\neq", ['≈'] = @"\approx", ['≡'] = @"\equiv",
        ['±'] = @"\pm", ['∓'] = @"\mp", ['×'] = @"\times", ['÷'] = @"\div", ['⋅'] = @"\cdot", ['∘'] = @"\circ",
        ['∈'] = @"\in", ['∉'] = @"\notin", ['∩'] = @"\cap", ['∪'] = @"\cup", ['∣'] = @"\mid",
        ['→'] = @"\to", ['←'] = @"\leftarrow", ['↔'] = @"\leftrightarrow", ['‖'] = @"\Vert",
        ['⟮'] = @"\lgroup", ['⟯'] = @"\rgroup",
        ['⇒'] = @"\Rightarrow", ['⇔'] = @"\Leftrightarrow", ['…'] = @"\ldots", ['⋯'] = @"\cdots",
        ['−'] = "-", ['ℓ'] = @"\ell", ['′'] = @"\prime", ['″'] = @"\prime\prime",
        ['Ⓢ'] = @"\circledS", ['‵'] = @"\backprime", ['‶'] = @"\backdoubleprime",
        ['\uE409'] = @"\mhchemlongRightleftharpoons", ['\uE40A'] = @"\mhchemlongLeftrightharpoons",
    };

    public static string Convert(string mathMl)
    {
        XElement math = ReadMath(mathMl);
        string[] colors = TokenColors(math, "#000000").Distinct(StringComparer.OrdinalIgnoreCase).ToArray();
        if (colors.Length == 1 && colors[0] != "#000000")
        {
            math.DescendantsAndSelf().Attributes("mathcolor").Remove();
            math.SetAttributeValue("mathcolor", colors[0]);
        }
        return Emit(math).Trim();
    }

    public static void VerifyRoundTrip(string original, string reconstructed, string defaultColor)
    {
        if (MathTypeMtefCodec.SemanticSignature(original) != MathTypeMtefCodec.SemanticSignature(reconstructed))
            throw new InvalidDataException("MathType → LaTeX: the editable formula did not preserve the original structure.");
        if (!TokenColors(ReadMath(original), defaultColor).SequenceEqual(TokenColors(ReadMath(reconstructed), defaultColor)))
            throw new InvalidDataException("MathType → LaTeX: the editable formula did not preserve the original colors.");
    }

    private static XElement ReadMath(string input)
    {
        var root = XDocument.Parse(input, LoadOptions.PreserveWhitespace).Root;
        if (root?.Name.LocalName != "math") throw new InvalidDataException("MathType formula has no MathML root.");
        return root;
    }

    private static IEnumerable<string> TokenColors(XElement math, string defaultColor)
    {
        string color = (math.AncestorsAndSelf().Attributes("mathcolor").FirstOrDefault()?.Value ?? defaultColor).ToUpperInvariant();
        IEnumerable<string> Colors(string text) =>
            text.Where(c => !char.IsWhiteSpace(c) && c is not '\u2061' and not '\u2062')
                .SelectMany(c => Enumerable.Repeat(color, c switch { '″' or '‶' => 2, '‴' => 3, '⁗' => 4, _ => 1 }));
        if (math.Name.LocalName is "mi" or "mn" or "mo" or "mtext")
        {
            foreach (string current in Colors(math.Value)) yield return current;
            yield break;
        }
        bool fenced = math.Name.LocalName == "mfenced";
        if (fenced)
            foreach (string current in Colors((string?)math.Attribute("open") ?? "(")) yield return current;
        foreach (var child in math.Elements())
            foreach (string current in TokenColors(child, defaultColor)) yield return current;
        if (fenced)
            foreach (string current in Colors((string?)math.Attribute("close") ?? ")")) yield return current;
    }

    private static string Emit(XElement node)
    {
        if (node.Attribute("mathsize") is { Value: not "normal" })
            throw Unsupported("local MathType font size");
        var children = node.Elements().ToArray();
        string Group(int index) => "{" + Emit(children[index]) + "}";
        string local = node.Name.LocalName;
        string latex = local switch
        {
            "math" or "mrow" or "mstyle" or "mtd" => Join(children),
            "semantics" when children.Length >= 1 => Emit(children[0]),
            "mi" when node.Value is "limsup" or "liminf" => "\\" + node.Value + " ",
            "mi" or "mn" => MathText(node.Value),
            "mo" => Operator(node.Value),
            "mtext" => @"\text{" + EscapeText(node.Value) + "}",
            "mspace" => Space(node),
            "mfrac" when children.Length == 2 && node.Attribute("linethickness") == null => @"\frac" + Group(0) + Group(1),
            "msqrt" => @"\sqrt{" + Join(children) + "}",
            "mroot" when children.Length == 2 => @"\sqrt[" + Emit(children[1]) + "]" + Group(0),
            "msub" when children.Length == 2 => Group(0) + "_" + Group(1),
            "msup" when children.Length == 2 => Group(0) + "^" + Group(1),
            "msubsup" when children.Length == 3 => Group(0) + "_" + Group(1) + "^" + Group(2),
            "mmultiscripts" => MultiScripts(children),
            "munder" or "mover" or "munderover" => Decorated(node, children),
            "mfenced" => Fenced(node, children),
            "mtable" => Table(node, (string?)node.Attribute("data-mtef-tabs") == "true" ? "aligned"
                : (string?)node.Attribute("data-mtef-pile") == "true" ? "gathered" : "matrix"),
            "menclose" => Enclosed(node, children),
            "mphantom" => @"\phantom{" + Join(children) + "}",
            _ => throw Unsupported(local),
        };
        if (latex.Length == 0) return latex;
        if ((string?)node.Attribute("mathvariant") is { } variant && local != "mtext"
            && !(local == "mi" && node.Value is "limsup" or "liminf"))
        {
            string command = variant switch
            {
                "normal" => @"\mathrm", "italic" => @"\mathit", "bold" => @"\mathbf", "bold-italic" => @"\boldsymbol",
                "double-struck" => @"\mathbb", "script" => @"\mathcal", "fraktur" => @"\mathfrak",
                "sans-serif" => @"\mathsf", "monospace" => @"\mathtt",
                _ => throw Unsupported(variant),
            };
            latex = command + "{" + latex + "}";
        }
        if ((string?)node.Attribute("mathcolor") is { } color)
        {
            if (!Regex.IsMatch(color, @"\A#[0-9a-fA-F]{6}\z")) throw Unsupported("MathType color");
            latex = @"\textcolor{" + color + "}{" + latex + "}";
        }
        return latex;
    }

    private static string Join(IEnumerable<XElement> children) => string.Concat(children.Select(Emit));

    private static string MultiScripts(XElement[] children)
    {
        if (children.Length == 0) throw Unsupported("MathType scripts");
        string basis = Emit(children[0]);
        bool precedes = false;
        for (int index = 1; index < children.Length;)
        {
            if (children[index].Name.LocalName == "mprescripts" && !precedes)
            {
                precedes = true;
                index++;
                continue;
            }
            if (index + 1 >= children.Length) throw Unsupported("MathType scripts");
            string lower = ScriptSlot(children[index++]);
            string upper = ScriptSlot(children[index++]);
            if (lower.Length == 0 && upper.Length == 0) continue;
            basis = precedes
                ? @"\prescript{" + upper + "}{" + lower + "}{" + basis + "}"
                : "{" + basis + "}" + (lower.Length == 0 ? "" : "_{" + lower + "}") + (upper.Length == 0 ? "" : "^{" + upper + "}");
        }
        return basis;
    }

    private static string ScriptSlot(XElement slot) => slot.Name.LocalName == "none" ? "" : Emit(slot);

    private static string MathText(string value) => string.Concat(value.Trim().Select(character =>
    {
        if (Symbols.TryGetValue(character, out string? symbol)) return symbol.StartsWith("\\", StringComparison.Ordinal) ? symbol + " " : symbol;
        return character switch
        {
            '\u2061' or '\u2062' => string.Empty,
            '\\' => @"\backslash ", '{' => @"\{", '}' => @"\}", '^' => @"\hat{}", '~' => @"\sim ",
            '_' or '#' or '$' or '%' or '&' => "\\" + character,
            _ => character.ToString(),
        };
    }));

    private static string Operator(string value)
    {
        string name = value.Trim();
        if (name.Length > 1 && name.All(char.IsLetter)) return @"\operatorname{" + name + "}";
        return MathText(name);
    }

    private static string EscapeText(string value) => string.Concat(value.Select(c => c switch
    {
        '\\' => @"\textbackslash{}", '^' => @"\textasciicircum{}", '~' => @"\textasciitilde{}",
        '{' or '}' or '_' or '#' or '$' or '%' or '&' => "\\" + c,
        _ => c.ToString(),
    }));

    private static string Space(XElement node)
    {
        string width = (string?)node.Attribute("width") ?? "0em";
        if (!width.EndsWith("em", StringComparison.Ordinal) ||
            !double.TryParse(width.Substring(0, width.Length - 2), NumberStyles.Float, CultureInfo.InvariantCulture, out double em)
            || double.IsNaN(em) || double.IsInfinity(em)) throw Unsupported("MathType spacing");
        return em switch
        {
            0 => "", 0.167 => @"\,", 0.222 => @"\:", 0.278 => @"\;", 1 => @"\quad ", 2 => @"\qquad ",
            _ => @"\kern" + em.ToString("0.########", CultureInfo.InvariantCulture) + "em ",
        };
    }

    private static string Decorated(XElement node, XElement[] children)
    {
        string Group(int index) => "{" + Emit(children[index]) + "}";
        string local = node.Name.LocalName;
        if (children.Length >= 2 && (string?)children[0].Attribute("data-mtef-arrow") == "true"
            && children[0].Value is "→" or "←")
        {
            var command = children[0].Value == "→" ? @"\xrightarrow" : @"\xleftarrow";
            var below = local == "mover" ? "" : "[" + Emit(children[1]) + "]";
            var above = local == "munder" ? "{}" : Group(children.Length - 1);
            return command + below + above;
        }
        if (local == "munderover" && children.Length == 3)
            return @"\mathop" + Group(0) + @"\limits_" + Group(1) + "^" + Group(2);
        if (children.Length != 2) throw Unsupported(local);
        string mark = children[1].Value.Trim();
        string? accent = (local, mark) switch
        {
            ("munder", "_" or "¯" or "‾" or "―" or "ˉ") => @"\underline",
            ("munder", "⏟") => @"\underbrace",
            ("mover", "⏞") => @"\overbrace",
            ("mover", "¯" or "‾" or "―" or "ˉ") => @"\overline",
            ("mover", "→") => @"\overrightarrow", ("mover", "←") => @"\overleftarrow", ("mover", "↔") => @"\overleftrightarrow",
            ("mover", "^" or "ˆ") => @"\hat", ("mover", "~" or "˜") => @"\tilde",
            ("mover", "." or "˙") => @"\dot", ("mover", "¨") => @"\ddot",
            ("mover", "ˇ") => @"\check", ("mover", "˘") => @"\breve",
            ("mover", "´") => @"\acute", ("mover", "\u0060") => @"\grave", ("mover", "˚") => @"\mathring",
            _ => null,
        };
        return accent != null ? accent + Group(0)
            : (local == "munder" ? @"\underset" : @"\overset") + Group(1) + Group(0);
    }

    private static string Fenced(XElement node, XElement[] children)
    {
        string open = (string?)node.Attribute("open") ?? "(";
        string close = (string?)node.Attribute("close") ?? ")";
        if (children.Length == 1 && children[0].Name.LocalName == "mtable")
        {
            XElement table = children[0];
            string? environment = (open, close) switch
            {
                ("(", ")") => "pmatrix", ("[", "]") => "bmatrix", ("{", "}") => "Bmatrix",
                ("|", "|") => "vmatrix", ("‖", "‖") => "Vmatrix", ("{", "") => "cases",
                _ => null,
            };
            if (environment == "pmatrix" && (string?)table.Attribute("data-mtef-pile") == "true")
            {
                var rows = table.Elements().ToArray();
                if (rows.Length == 2 && rows.All(row => row.Elements().Count() == 1))
                    return @"\binom{" + Emit(rows[0].Elements().Single()) + "}{" + Emit(rows[1].Elements().Single()) + "}";
            }
            if (environment != null) return Table(table, environment);
        }
        string separator = (string?)node.Attribute("separators") ?? ",";
        if (separator.Length > 1 && children.Length > 2) throw Unsupported("MathType fence separators");
        return @"\left" + Delimiter(open) + " " + string.Join(MathText(separator), children.Select(Emit)) + @"\right" + Delimiter(close) + " ";
    }

    private static string Delimiter(string value) => value switch
    {
        "" or "." => ".", "(" or ")" or "[" or "]" or "|" or "/" => value,
        "{" => @"\{", "}" => @"\}", "‖" or "∥" => @"\Vert",
        "⟨" or "〈" => @"\langle", "⟩" or "〉" => @"\rangle",
        "⌊" => @"\lfloor", "⌋" => @"\rfloor", "⌈" => @"\lceil", "⌉" => @"\rceil",
        "⟦" => @"\llbracket", "⟧" => @"\rrbracket",
        _ => throw Unsupported("MathType delimiter"),
    };

    private static string Table(XElement table, string environment)
    {
        var rows = table.Elements().ToArray();
        if (rows.Length == 0 || rows.Any(row => row.Name.LocalName != "mtr" ||
            row.Elements().Any(cell => cell.Name.LocalName != "mtd")))
            throw Unsupported("MathType matrix rows");
        return @"\begin{" + environment + "}" + string.Join(@"\\", rows.Select(row => string.Join("&", row.Elements().Select(Emit))))
            + @"\end{" + environment + "}";
    }

    private static string Enclosed(XElement node, XElement[] children)
    {
        string command = (string?)node.Attribute("notation") switch
        {
            "box" => @"\boxed", "radical" => @"\sqrt", "updiagonalstrike" => @"\cancel",
            "horizontalstrike" => @"\enclose{horizontalstrike}",
            "downdiagonalstrike" => @"\bcancel", "updiagonalstrike downdiagonalstrike" => @"\xcancel",
            _ => throw Unsupported("MathType enclosure"),
        };
        return command + "{" + Join(children) + "}";
    }

    private static InvalidDataException Unsupported(string structure) =>
        new("MathType → LaTeX: unsupported " + structure + ".");
}
