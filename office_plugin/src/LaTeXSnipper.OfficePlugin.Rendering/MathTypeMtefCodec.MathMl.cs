using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Globalization;
using System.Text;
using System.Xml.Linq;

namespace LaTeXSnipper.OfficePlugin.Rendering;

internal static partial class MathTypeMtefCodec
{

    internal static string SemanticSignature(string mathMl)
    {
        if (string.IsNullOrWhiteSpace(mathMl)) return string.Empty;
        var document = XDocument.Parse(mathMl, LoadOptions.PreserveWhitespace);
        var math = document.Root?.DescendantsAndSelf()
            .FirstOrDefault(element => element.Name.LocalName == "math")
            ?? document.Root
            ?? throw new InvalidDataException("MathML has no root element.");
        var normalized = new XElement(math);
        NormalizeMathTypeExportedTabPiles(normalized);
        return CanonicalizeMathMl(normalized, inheritedMathVariant: null);
    }


    private static void NormalizeMathTypeExportedTabPiles(XElement root)
    {
        foreach (var table in root.DescendantsAndSelf()
                     .Where(element => element.Name.LocalName == "mtable")
                     .ToArray())
        {
            var sourceRows = table.Elements()
                .Where(row => row.Name.LocalName is "mtr" or "mlabeledtr")
                .ToArray();
            if (sourceRows.Length == 0) continue;

            var allowsEmptyComTabMarkers =
                IsMathTypeComExportedTabPile(table, sourceRows);
            var rebuiltRows = new List<XElement>();
            var sawTab = false;
            var supportedShape = true;
            foreach (var sourceRow in sourceRows)
            {
                var sourceCells = sourceRow.Elements()
                    .Where(cell => cell.Name.LocalName == "mtd")
                    .ToArray();
                if (sourceCells.Length != 1)
                {
                    supportedShape = false;
                    break;
                }

                if (sourceCells[0].Elements().Any(element =>
                        element.Name.LocalName is "maligngroup" or "malignmark"))
                {
                    var markedRow = RebuildMathTypeAlignmentMarkedRow(
                        sourceCells[0],
                        out var markedSawTab);
                    sawTab |= markedSawTab;
                    rebuiltRows.Add(markedRow);
                    continue;
                }

                var rebuiltRow = new XElement("mtr");
                var rebuiltCell = new XElement("mtd");
                foreach (var node in sourceCells[0].Nodes())
                {
                    if (node is XElement marker
                        && IsMathTypeExportedTabMarker(
                            marker,
                            allowsEmptyComTabMarkers))
                    {
                        sawTab = true;
                        NormalizeMathTypeExportedTabCell(rebuiltCell);
                        rebuiltRow.Add(rebuiltCell);
                        rebuiltCell = new XElement("mtd");
                        continue;
                    }
                    if (node is XText whitespace && string.IsNullOrWhiteSpace(whitespace.Value))
                        continue;
                    rebuiltCell.Add(CloneNode(node));
                }
                NormalizeMathTypeExportedTabCell(rebuiltCell);
                rebuiltRow.Add(rebuiltCell);
                rebuiltRows.Add(rebuiltRow);
            }
            if (!supportedShape || !sawTab) continue;

            while (rebuiltRows.Count > 1
                && !MathTypeTabRowHasMeaningfulContent(rebuiltRows[rebuiltRows.Count - 1]))
                rebuiltRows.RemoveAt(rebuiltRows.Count - 1);

            table.RemoveNodes();
            foreach (var row in rebuiltRows) table.Add(row);
            var columnCount = rebuiltRows
                .Select(row => row.Elements().Count(cell => cell.Name.LocalName == "mtd"))
                .DefaultIfEmpty(0)
                .Max();
            if (columnCount > 0)
            {
                table.SetAttributeValue(
                    "columnalign",
                    string.Join(" ", Enumerable.Range(0, columnCount)
                        .Select(column => (column & 1) == 0 ? "right" : "left")));
            }
        }
    }


    private static XElement RebuildMathTypeAlignmentMarkedRow(
        XElement sourceCell,
        out bool sawTab)
    {
        sawTab = false;
        var row = new XElement("mtr");
        var cell = new XElement("mtd");
        var emittedAnyCell = false;

        bool CellHasContent() => cell.Nodes().Any(node =>
            node is XElement
            || node is XText text && !string.IsNullOrWhiteSpace(text.Value));

        void EmitCell()
        {
            NormalizeMathTypeExportedTabCell(cell);
            row.Add(cell);
            cell = new XElement("mtd");
            emittedAnyCell = true;
        }

        foreach (var node in sourceCell.Nodes())
        {
            if (node is XText whitespace && string.IsNullOrWhiteSpace(whitespace.Value))
                continue;
            if (node is XElement element)
            {
                if (element.Name.LocalName == "maligngroup")
                    continue;
                if (element.Name.LocalName == "malignmark")
                {
                    EmitCell();
                    continue;
                }
                if (IsMathTypeExportedTabMarker(element, allowEmptyComMarker: false))
                {
                    sawTab = true;
                    // MathType emits one leading U+0009 after <maligngroup/> to
                    // enter the first ruler group. It is positioning metadata,
                    // not an empty TeX column. Later tabs terminate the current
                    // right-hand cell and start the next right/left pair.
                    if (!emittedAnyCell && !CellHasContent())
                        continue;
                    EmitCell();
                    continue;
                }
            }
            cell.Add(CloneNode(node));
        }
        EmitCell();
        return row;
    }


    private static bool IsMathTypeComExportedTabPile(
        XElement table,
        XElement[] rows)
    {
        var columnAlign = ((string?)table.Attribute("columnalign") ?? string.Empty)
            .Trim();
        if (!string.Equals(columnAlign, "left", StringComparison.OrdinalIgnoreCase)
            || rows.Length < 2
            || MathTypeTabRowHasMeaningfulContent(rows[rows.Length - 1]))
            return false;

        var nonTrailingRows = rows.Take(rows.Length - 1).ToArray();
        if (nonTrailingRows.Any(row => row.Elements()
                .Count(cell => cell.Name.LocalName == "mtd") != 1))
            return false;
        return nonTrailingRows.Any(row => row.Descendants()
            .Any(element => element.Name.LocalName == "mtext"
                && !element.HasElements
                && element.Value.Length == 0));
    }


    private static bool IsMathTypeExportedTabMarker(
        XElement element,
        bool allowEmptyComMarker)
    {
        if (element.Name.LocalName is not ("mtext" or "mi")) return false;
        var value = element.Value;
        if (value.Length > 0 && value.All(character => character == '\t'))
            return true;
        return allowEmptyComMarker
            && element.Name.LocalName == "mtext"
            && !element.HasElements
            && value.Length == 0;
    }


    private static bool MathTypeTabRowHasMeaningfulContent(XElement row)
    {
        foreach (var element in row.Descendants())
        {
            if (element.Name.LocalName is "mrow" or "mstyle" or "mpadded" or "mtd")
                continue;
            if (!string.IsNullOrWhiteSpace(element.Value.Replace("\t", string.Empty)))
                return true;
            if (element.HasElements) return true;
        }
        return false;
    }


    private static void NormalizeMathTypeExportedTabCell(XElement cell)
    {
        var elements = cell.Elements().ToList();
        for (var index = 0; index < elements.Count; index++)
        {
            var first = elements[index];
            if (first.Name.LocalName != "mtext" || string.IsNullOrWhiteSpace(first.Value))
                continue;
            var mergedText = first.Value;
            var cursor = index + 1;
            var consumed = new List<XElement>();
            while (cursor + 1 < elements.Count
                && IsMathTypeExportedTextSpace(elements[cursor])
                && elements[cursor + 1].Name.LocalName == "mtext"
                && !string.IsNullOrWhiteSpace(elements[cursor + 1].Value))
            {
                mergedText += " " + elements[cursor + 1].Value;
                consumed.Add(elements[cursor]);
                consumed.Add(elements[cursor + 1]);
                cursor += 2;
            }
            if (consumed.Count == 0) continue;
            first.Value = mergedText;
            foreach (var item in consumed) item.Remove();
            elements = cell.Elements().ToList();
        }

        // MathType can terminate an ordinary text run before punctuation even
        // though the source was one \text{...} node (for example it exports
        // "High word." as mtext("High word") + mtext(".")). Rejoin only an
        // immediately adjacent punctuation-only mtext fragment inside this
        // already-confirmed tab-aligned export shape.
        elements = cell.Elements().ToList();
        for (var index = 0; index + 1 < elements.Count; index++)
        {
            var current = elements[index];
            var next = elements[index + 1];
            if (current.Name.LocalName != "mtext"
                || next.Name.LocalName != "mtext"
                || current.HasElements
                || next.HasElements
                || next.Value.Length == 0
                || !next.Value.All(char.IsPunctuation))
                continue;
            current.Value += next.Value;
            next.Remove();
            elements = cell.Elements().ToList();
            index--;
        }

        elements = cell.Elements().ToList();
        for (var index = 0; index < elements.Count; index++)
        {
            if (!IsSingleUnstyledLatinIdentifier(elements[index])) continue;
            var end = index;
            var name = new StringBuilder();
            while (end < elements.Count && IsSingleUnstyledLatinIdentifier(elements[end]))
            {
                name.Append(elements[end].Value);
                end++;
            }
            if (name.Length < 2
                || end >= elements.Count
                || elements[end].Name.LocalName != "mo"
                || elements[end].Value.Trim() != "(")
            {
                index = Math.Max(index, end - 1);
                continue;
            }

            var function = new XElement(
                "mi",
                new XAttribute("mathvariant", "normal"),
                name.ToString());
            elements[index].ReplaceWith(function);
            for (var remove = index + 1; remove < end; remove++)
                elements[remove].Remove();
            elements = cell.Elements().ToList();
        }
    }


    private static bool IsMathTypeExportedTextSpace(XElement element)
    {
        if (element.HasElements) return false;
        if (element.Name.LocalName == "mi" && element.Value.Length == 0)
        {
            // MathType's IDataObject MathML exporter represents a word-space
            // inside text in a native tab-pile as an empty <mi/> rather than
            // mspace/whitespace text. This helper is used only after the table
            // has already been proven to be a MathType tab-pile export.
            return true;
        }
        return element.Name.LocalName is "mi" or "mtext"
            && element.Value.Length > 0
            && element.Value.All(char.IsWhiteSpace);
    }


    private static bool IsSingleUnstyledLatinIdentifier(XElement element)
    {
        if (element.Name.LocalName != "mi"
            || element.Attribute("mathvariant") is not null)
            return false;
        var value = element.Value;
        return value.Length == 1 && value[0] <= 0x7F && char.IsLetter(value[0]);
    }


    private static string CanonicalizeMathMl(XElement element, string? inheritedMathVariant)
    {
        var local = element.Name.LocalName;
        var ownVariant = ((string?)element.Attribute("mathvariant"))?.Trim();
        var variant = string.IsNullOrWhiteSpace(ownVariant) ? inheritedMathVariant : ownVariant;
        string Children(string? childVariant = null) =>
            CanonicalizeElementSequence(
                element.Elements()
                    .Where(child => child.Name.LocalName is not ("annotation" or "annotation-xml"))
                    .ToArray(),
                childVariant ?? variant);
        var children = element.Elements()
            .Where(child => child.Name.LocalName is not ("annotation" or "annotation-xml"))
            .ToArray();
        switch (local)
        {
            case "math":
            case "mpadded":
                return Children();
            case "mrow":
            {
                if (TryCanonicalizeMathJaxFencedSuperscriptRow(element, variant, out var fencedSuperscript))
                    return fencedSuperscript;
                if (TryGetMathJaxFenceRow(element, out var open, out var close, out var fenceChildren))
                {
                    if (TryCanonicalizeMathJaxBinomialFence(
                            open,
                            close,
                            fenceChildren,
                            variant,
                            out var binomial))
                        return binomial;
                    var normalizedOpen = NormalizeFence(open);
                    var normalizedClose = NormalizeFence(close);
                    var fencedChildrenSignature =
                        string.Concat(fenceChildren.Select(child => CanonicalizeMathMl(child, variant)));
                    return CanonicalFenceSignature(
                        normalizedOpen,
                        normalizedClose,
                        fencedChildrenSignature);
                }
                return Children();
            }
            case "mstyle":
                return Children(variant);
            case "semantics":
            case "maction":
                return children.Length == 0
                    ? string.Empty
                    : CanonicalizeMathMl(children[0], variant);
            case "annotation":
            case "annotation-xml":
            case "none":
            case "mspace":
                return string.Empty;
            case "mi":
            {
                var value = element.Value.Trim();
                if (value.Length == 0) return string.Empty;
                var primeSignature = CanonicalPrimeSignature(value);
                if (primeSignature is not null) return primeSignature;
                if (value == "ℓ")
                    return CanonicalToken("mi", "l", "script");
                if ((value is "ℵ" or "ℜ" or "ℑ")
                    && string.Equals(variant, "normal", StringComparison.OrdinalIgnoreCase))
                {
                    // Production MathJax marks these fixed letterlike symbols as
                    // upright, while MathType's direct MTEF readback omits an
                    // explicit mathvariant. The glyph identity already fixes their
                    // presentation, so the attribute is semantically redundant.
                    return CanonicalToken("mi", value, string.Empty);
                }
                // MathType 7 sometimes exports standalone mathematical glyphs
                // such as infinity as <mi> even though MathJax/LaTeXSnipper uses
                // <mo>.  That token-tag difference is not a semantic change.
                // Keep mtext distinct so an actual Symbol -> Text regression is
                // still rejected by the round-trip validator.
                if (IsMathematicalSymbolToken(value))
                    return "o(" + NormalizeOperatorToken(value) + ")";
                return CanonicalToken("mi", value, variant);
            }
            case "mn":
                return "n(" + element.Value.Trim() + ")";
            case "mo":
            {
                var value = element.Value.Trim();
                // MathJax inserts U+2061 FUNCTION APPLICATION between a named
                // function and its argument. It has no visible glyph and should
                // never become a literal MathType character or a fake '?'.
                if (value == "⁡") return string.Empty;
                var primeSignature = CanonicalPrimeSignature(value);
                if (primeSignature is not null) return primeSignature;
                if (value.Length > 1 && value.All(char.IsLetter))
                    return CanonicalToken("mi", value, "normal");
                // MathJax keeps the TeX definition operator := in one <mo>,
                // while MathType 7 serializes the same visible operator as two
                // adjacent operator records ':' and '='. Treat only this known
                // split as equivalent; other multi-character operators remain
                // strict so the MTEF round-trip gate still catches real changes.
                if (value == ":=") return "o(:)o(=)";
                // MathJax may coalesce adjacent non-ASCII mathematical symbols
                // into one <mo> (for example \mapsto\parallel\sim), while MTEF
                // persists one CHAR record per glyph. Normalize only a pure run
                // of Unicode math symbols into the same per-glyph signature.
                // ASCII composites such as := and alphabetic operators keep the
                // stricter handling above.
                if (value.Length > 1
                    && value.All(character => character > 0x7F
                        && IsMathematicalSymbolScalar(character)))
                {
                    return string.Concat(value.Select(character =>
                        "o(" + NormalizeOperatorToken(character.ToString()) + ")"));
                }
                return "o(" + NormalizeOperatorToken(value) + ")";
            }
            case "mtext":
            {
                var value = element.Value.Trim();
                // MathJax may serialize TeX spacing commands as whitespace-only
                // <mtext> (commonly NBSP), while MathType normalizes the same
                // presentation-only gap to <mspace> on MTEF read-back. Neither
                // carries mathematical semantics, so treating empty/whitespace
                // mtext as text() makes an otherwise exact equation fail the
                // standalone-MTEF round-trip gate. Keep real textual content
                // strict, but canonicalize pure spacing exactly like mspace.
                if (value.Length == 0) return string.Empty;
                if (value.All(char.IsLetter))
                    return CanonicalToken("mi", value, "normal");
                return "text(" + value + ")";
            }
            case "mfrac":
                return CanonicalBinary("frac", children, variant);
            case "msqrt":
                return "sqrt(" + Children() + ")";
            case "mroot":
                return CanonicalBinary("root", children, variant);
            case "msub":
                return CanonicalBinary("sub", children, variant);
            case "msup":
                return CanonicalBinary("sup", children, variant);
            case "msubsup":
            {
                if (children.Length < 3)
                    return string.Concat(children.Select(child => CanonicalizeMathMl(child, variant)));
                var baseSignature = CanonicalizeScriptBase(children[0], variant);
                var subSignature = CanonicalizeMathMl(children[1], variant);
                var supSignature = CanonicalizeMathMl(children[2], variant);
                if (subSignature.Length == 0 && supSignature.Length > 0)
                    return "sup(" + baseSignature + "," + supSignature + ")";
                if (supSignature.Length == 0 && subSignature.Length > 0)
                    return "sub(" + baseSignature + "," + subSignature + ")";
                if (subSignature.Length == 0 && supSignature.Length == 0)
                    return baseSignature;
                return "subsup(" + baseSignature + "," + subSignature + "," + supSignature + ")";
            }
            case "munder":
            {
                if (children.Length == 1)
                {
                    if (TryCanonicalizeWrappedHorizontalBrace(
                        children[0], variant, top: false, out var wrappedBrace))
                        return wrappedBrace;
                    return CanonicalizeMathMl(children[0], variant);
                }
                if (children.Length >= 2)
                {
                    var under = children[1].Value.Trim();
                    if (under is "_" or "\u00AF" or "\u203E" or "\u2015" or "\u02C9")
                        return "underbar(" + CanonicalizeMathMl(children[0], variant) + ")";
                    if (IsHorizontalBraceMarker(under, top: false))
                        return "hbrace-bottom(" + CanonicalizeMathMl(children[0], variant) + ")";
                }
                return CanonicalBinary("sub", children, variant);
            }
            case "mover":
            {
                if (children.Length == 1)
                {
                    if (TryCanonicalizeWrappedHorizontalBrace(
                        children[0], variant, top: true, out var wrappedBrace))
                        return wrappedBrace;
                    return CanonicalizeMathMl(children[0], variant);
                }
                if (children.Length < 2) return Children();
                var over = NormalizeAccentMark(children[1].Value.Trim());
                if (IsHorizontalBraceMarker(over, top: true))
                    return "hbrace-top(" + CanonicalizeMathMl(children[0], variant) + ")";
                if (over == "¯")
                    return "accent(overbar," + CanonicalizeMathMl(children[0], variant) + ")";
                var accent = over is "→" or "←" or "↔"
                    or "^" or "~" or "." or "˙" or "¨"
                    or "⌢" or "⏜" or "ˇ" or "˘" or "´" or "`" or "˚";
                return accent
                    ? "accent(" + over + "," + CanonicalizeMathMl(children[0], variant) + ")"
                    : CanonicalBinary("sup", children, variant);
            }
            case "munderover":
                return CanonicalTernary("subsup", children, variant);
            case "mfenced":
            {
                if (TryCanonicalizeMathTypeBinomialFence(element, variant, out var binomial))
                    return binomial;
                var open = NormalizeFence((string?)element.Attribute("open") ?? "(");
                var close = NormalizeFence((string?)element.Attribute("close") ?? ")");
                var fencedChildren = Children();
                // Word OMML materializes a one-sided system/cases delimiter as
                // a real delimiter object (m:d / MathML mfenced with an empty
                // opposite fence), while MathJax can represent the same visible
                // mathematics as a loose <mo> delimiter followed by the table.
                // Canonicalize only one-sided fences to that explicit token form;
                // paired fences remain structurally strict.
                return CanonicalFenceSignature(
                    open,
                    close,
                    fencedChildren);
            }
            case "mtable":
                return "table(" + string.Join(";", children.Select(row =>
                    CanonicalizeMathMl(row, variant))) + ")";
            case "mtr":
            case "mlabeledtr":
                return "row(" + string.Join(",", children.Select(cell =>
                    CanonicalizeMathMl(cell, variant))) + ")";
            case "mtd":
                return "cell(" + Children() + ")";
            case "menclose":
            {
                var notation = ((string?)element.Attribute("notation") ?? string.Empty)
                    .Trim()
                    .ToLowerInvariant();
                if (notation.Contains("radical")) return "sqrt(" + Children() + ")";
                if (notation.Contains("box")) return "box(" + Children() + ")";
                var strikeParts = new List<string>();
                if (notation.Contains("horizontalstrike")) strikeParts.Add("h");
                if (notation.Contains("updiagonalstrike")) strikeParts.Add("up");
                if (notation.Contains("downdiagonalstrike")) strikeParts.Add("down");
                if (strikeParts.Count > 0)
                    return "strike[" + string.Join("+", strikeParts) + "](" + Children() + ")";
                return Children();
            }
            case "mphantom":
                return "phantom(" + Children() + ")";
            case "mmultiscripts":
            {
                if (children.Length == 0) return string.Empty;
                var result = CanonicalizeScriptBase(children[0], variant);
                var precedes = false;
                for (var index = 1; index < children.Length;)
                {
                    if (children[index].Name.LocalName == "mprescripts")
                    {
                        if (precedes) throw new InvalidDataException("Duplicate MathML prescript separator.");
                        precedes = true; index++; continue;
                    }
                    if (index + 1 >= children.Length || children[index + 1].Name.LocalName == "mprescripts")
                        throw new InvalidDataException("MathML multiscripts require complete sub/sup pairs.");
                    var subSignature = children[index].Name.LocalName == "none" ? string.Empty : CanonicalizeMathMl(children[index], variant);
                    var supSignature = children[index + 1].Name.LocalName == "none" ? string.Empty : CanonicalizeMathMl(children[index + 1], variant);
                    if (subSignature.Length > 0 || supSignature.Length > 0)
                        result = precedes ? "pre(" + result + "," + subSignature + "," + supSignature + ")"
                            : subSignature.Length > 0 && supSignature.Length > 0 ? "subsup(" + result + "," + subSignature + "," + supSignature + ")"
                            : subSignature.Length > 0 ? "sub(" + result + "," + subSignature + ")"
                            : "sup(" + result + "," + supSignature + ")";
                    index += 2;
                }
                return result;
            }
            default:
                return children.Length > 0
                    ? Children()
                    : element.Value.Trim();
        }
    }


    private static string? CanonicalPrimeSignature(string value) => value switch
    {
        "'" => "o(′)",
        "′" => "o(′)",
        "″" => "o(′)o(′)",
        "‴" => "o(′)o(′)o(′)",
        "⁗" => "o(′)o(′)o(′)o(′)",
        _ => null,
    };


    private static bool IsReplacementGlyphOnly(string value) =>
        value.Length > 0 && value.All(character => character == '\uFFFD');


    private static bool IsMathematicalSymbolToken(string value) =>
        value.Length > 0 && value.All(character =>
        {
            var category = char.GetUnicodeCategory(character);
            return category == System.Globalization.UnicodeCategory.MathSymbol
                || category == System.Globalization.UnicodeCategory.CurrencySymbol
                || category == System.Globalization.UnicodeCategory.ModifierSymbol
                || category == System.Globalization.UnicodeCategory.OtherSymbol;
        });


    private static bool IsHorizontalBraceMarker(string value, bool top) =>
        value == (top ? "⏞" : "⏟")
        || value == (top ? "\uFE37" : "\uFE38")
        || IsReplacementGlyphOnly(value);


    private static bool TryCanonicalizeWrappedHorizontalBrace(
        XElement candidate,
        string? variant,
        bool top,
        out string signature)
    {
        signature = string.Empty;
        if (candidate.Name.LocalName != (top ? "mover" : "munder")) return false;
        var inner = candidate.Elements().ToArray();
        if (inner.Length < 2 || inner[1].Name.LocalName != "mo") return false;
        var marker = inner[1].Value.Trim();
        var stretchy = string.Equals(
            (string?)inner[1].Attribute("stretchy"),
            "true",
            StringComparison.OrdinalIgnoreCase);
        // MathType 7 can export its private horizontal-brace glyph as replacement
        // characters. The extra one-child mover/munder wrapper plus a stretchy
        // operator is the stable structural signal; ordinary overset/underset
        // expressions do not have this wrapper.
        if (!stretchy && !IsHorizontalBraceMarker(marker, top))
            return false;
        signature = (top ? "hbrace-top(" : "hbrace-bottom(")
            + CanonicalizeMathMl(inner[0], variant) + ")";
        return true;
    }


    private static string CanonicalBinary(
        string name,
        XElement[] children,
        string? variant)
    {
        if (children.Length < 2)
            return string.Concat(children.Select(child => CanonicalizeMathMl(child, variant)));
        return name + "("
            + (name is "sub" or "sup"
                ? CanonicalizeScriptBase(children[0], variant)
                : CanonicalizeMathMl(children[0], variant)) + ","
            + CanonicalizeMathMl(children[1], variant) + ")";
    }


    private static string CanonicalTernary(
        string name,
        XElement[] children,
        string? variant)
    {
        if (children.Length < 3)
            return string.Concat(children.Select(child => CanonicalizeMathMl(child, variant)));
        return name + "("
            + (name == "subsup"
                ? CanonicalizeScriptBase(children[0], variant)
                : CanonicalizeMathMl(children[0], variant)) + ","
            + CanonicalizeMathMl(children[1], variant) + ","
            + CanonicalizeMathMl(children[2], variant) + ")";
    }


    private static string CanonicalizeScriptBase(XElement element, string? variant)
    {
        if (element.Name.LocalName == "mo")
        {
            // MathType's BigOp templates export the ordinary set-union/
            // intersection code points while MathJax represents \bigcup/\bigcap
            // with U+22C3/U+22C2. They are the same semantic operator when used
            // as the base of a limit/script structure.
            var value = element.Value.Trim();
            if (value == "∪") return "o(⋃)";
            if (value == "∩") return "o(⋂)";
        }
        return CanonicalizeMathMl(element, variant);
    }


    private static string CanonicalToken(string kind, string value, string? mathVariant)
    {
        var token = value.Trim();
        var variant = (mathVariant ?? string.Empty).Trim().ToLowerInvariant();
        if (variant.Contains("sans-serif-bold-italic")) variant = "sans-serif-bold-italic";
        else if (variant.Contains("sans-serif-italic")) variant = "sans-serif-italic";
        else if (variant.Contains("bold-sans-serif")) variant = "bold-sans-serif";
        else if (variant.Contains("bold-script")) variant = "bold-script";
        else if (variant.Contains("bold-fraktur")) variant = "bold-fraktur";
        else if (variant.Contains("bold-italic")) variant = "bold-italic";
        else if (variant.Contains("double-struck")) variant = "double-struck";
        else if (variant.Contains("fraktur")) variant = "fraktur";
        else if (variant.Contains("script")) variant = "script";
        else if (variant.Contains("monospace")) variant = "monospace";
        else if (variant.Contains("sans-serif")) variant = "sans-serif";
        else if (variant.Contains("normal") || variant.Contains("upright")) variant = "normal";
        else if (variant.Contains("bold")) variant = "bold";
        else if (variant.Contains("italic")) variant = string.Empty;
        else variant = string.Empty;
        if (kind == "mi" && variant.Length == 0 && token.Length == 1)
        {
            switch (token[0])
            {
                case 'ℂ': token = "C"; variant = "double-struck"; break;
                case 'ℍ': token = "H"; variant = "double-struck"; break;
                case 'ℕ': token = "N"; variant = "double-struck"; break;
                case 'ℙ': token = "P"; variant = "double-struck"; break;
                case 'ℚ': token = "Q"; variant = "double-struck"; break;
                case 'ℝ': token = "R"; variant = "double-struck"; break;
                case 'ℤ': token = "Z"; variant = "double-struck"; break;
                case 'ℱ': token = "F"; variant = "script"; break;
                case 'ℒ': token = "L"; variant = "script"; break;
                case 'ℛ': token = "R"; variant = "script"; break;
            }
        }
        if (kind == "mi" && variant.Length == 0
            && token.Length == 1
            && IsUpperGreek(token[0]))
            variant = "normal";
        var explicitlyItalic = string.Equals(mathVariant?.Trim(), "italic", StringComparison.OrdinalIgnoreCase);
        if (kind == "mi" && variant.Length == 0 && !explicitlyItalic
            && token.Length > 1 && token.All(char.IsLetter))
            variant = "normal";
        // MTEF stores styled identifiers as individual CHAR records; exporters
        // may group or split an uninterrupted same-style alphabetic run. Compare
        // its ordered characters with the exact style retained on EVERY token.
        // This covers monospace/script/bold as well as upright runs without
        // equating fonts, symbols, digit tokens or different character contents.
        if (kind == "mi" && (variant.Length > 0 || explicitlyItalic)
            && token.Length > 1 && token.All(char.IsLetter))
            return string.Concat(token.Select(character =>
                "mi[" + variant + "](" + character + ")"));
        return kind + "[" + variant + "](" + token + ")";
    }

}