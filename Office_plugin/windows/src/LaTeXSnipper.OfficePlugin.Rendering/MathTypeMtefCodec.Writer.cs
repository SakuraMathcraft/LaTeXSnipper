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

    private static XElement PrepareMathForMathType(XElement math)
    {
        var preparedMath = new XElement(math);
        MaterializeInheritedMathVariants(preparedMath, inheritedMathVariant: null);
        NormalizeMathJaxFenceRows(preparedMath);
        return preparedMath;
    }


    private static byte[] BuildRootStructure(
        XElement math,
        byte[] sourceMtef,
        out byte[] prefixDefinitions)
    {
        // The shared template writer emits COLOR 1 for matrix/pile slots. MTEF
        // definition indices start at 1; the standalone seed has no color table.
        // An undefined COLOR 1 lets MathPage omit the root polygon's fill brush,
        // leaving only thin fragments in its WMF despite intact root semantics.
        var requiredDefinitions = new List<byte> { RecordColorDef, 0, 0, 0, 0, 0, 0, 0 };
        var preparedMath = PrepareMathForMathType(math);
        PrepareColors(preparedMath, requiredDefinitions);
        prefixDefinitions = requiredDefinitions.ToArray();
        var topLevelElements = SignificantChildren(preparedMath)
            .OfType<XElement>()
            .Where(element => element.Name.LocalName is not ("annotation" or "annotation-xml"))
            .ToArray();
        if (topLevelElements.Length == 1
            && topLevelElements[0].Name.LocalName == "mtable")
        {
            // Font/encoding definitions are global MTEF records. MathType accepts
            // them inside an ordinary root LINE, but putting them inside a root
            // PILE makes its native editor preserve the glyphs while degrading
            // fnMARKER tabs into empty text. Build the aligned table on a clone,
            // emit any missing definitions into the global prefix instead, then
            // keep the PILE object list identical to MathType's native layout.
            var alignedTable = new XElement(topLevelElements[0]);
            var alignedPrefixDefinitions = new List<byte>(requiredDefinitions);
            EmitExplicitFontDefinitions(
                alignedTable,
                sourceMtef,
                alignedPrefixDefinitions);
            var alignedRoot = new List<byte>();
            if (TryEmitAlignedPile(alignedTable, alignedRoot))
            {
                prefixDefinitions = alignedPrefixDefinitions.ToArray();
                // MathType 7's own multi-point aligned equations use PILE as the
                // top-level equation structure. Keeping a synthetic root LINE
                // around that PILE causes MathType to export fnMARKER tabs as
                // literal text instead of alignment boundaries.
                alignedRoot.Add(RecordEnd); // equation
                return alignedRoot.ToArray();
            }
        }

        var output = new List<byte> { RecordLine, 0 };
        EmitExplicitFontDefinitions(preparedMath, sourceMtef, output);
        EmitContainerChildren(preparedMath, output, inheritedMathVariant: null);
        output.Add(RecordEnd); // root line
        output.Add(RecordEnd); // equation
        return output.ToArray();
    }


    private static byte[] AssembleRewrittenMtef(
        byte[] sourceMtef,
        int sourceStructureOffset,
        byte[] prefixDefinitions,
        byte[] rootStructure)
    {
        // MathType's global ENCODING_DEF/FONT_DEF/FONT_STYLE_DEF records belong
        // before the initial SIZE record. Putting them after SIZE or inside a root
        // PILE makes MathType preserve the styled glyphs but stop interpreting
        // fnMARKER/U+0009 as alignment tabs. Insert only the newly required
        // definitions at this prefix boundary and keep every original prefix byte.
        var insertionOffset = FindInitialSizeRecordOffset(
            sourceMtef,
            sourceStructureOffset);
        var rewritten = new byte[
            sourceStructureOffset + prefixDefinitions.Length + rootStructure.Length];
        Buffer.BlockCopy(sourceMtef, 0, rewritten, 0, insertionOffset);
        Buffer.BlockCopy(
            prefixDefinitions,
            0,
            rewritten,
            insertionOffset,
            prefixDefinitions.Length);
        Buffer.BlockCopy(
            sourceMtef,
            insertionOffset,
            rewritten,
            insertionOffset + prefixDefinitions.Length,
            sourceStructureOffset - insertionOffset);
        Buffer.BlockCopy(
            rootStructure,
            0,
            rewritten,
            sourceStructureOffset + prefixDefinitions.Length,
            rootStructure.Length);
        return rewritten;
    }


    private static int FindInitialSizeRecordOffset(byte[] mtef, int rootOffset)
    {
        var prefix = ReadPrefixLayout(mtef);
        if (prefix.Root != rootOffset)
            throw new InvalidDataException("MTEF rewrite root does not match its validated prefix.");
        foreach (var record in prefix.Records)
            if (record.Type == RecordSize || record.Type >= RecordFull && record.Type <= RecordSubSym)
                return record.Start;
        return prefix.Root;
    }


    private static void MaterializeInheritedMathVariants(
        XElement element,
        string? inheritedMathVariant)
    {
        var ownVariant = ((string?)element.Attribute("mathvariant"))?.Trim();
        var variant = string.IsNullOrWhiteSpace(ownVariant)
            ? inheritedMathVariant
            : ownVariant;
        if (element.Name.LocalName is "mi" or "mn" or "mo" or "mtext")
        {
            if (element.Attribute("mathvariant") is null
                && !string.IsNullOrWhiteSpace(variant))
                element.SetAttributeValue("mathvariant", variant);
            return;
        }
        foreach (var child in element.Elements())
            MaterializeInheritedMathVariants(child, variant);
    }


    private static void NormalizeMathJaxFenceRows(XElement root)
    {
        var rows = root.DescendantsAndSelf()
            .Where(element => element.Name.LocalName == "mrow")
            .Reverse()
            .ToArray();
        foreach (var row in rows)
        {
            if (!TryGetMathJaxFenceRow(row, out var open, out var close, out var children))
                continue;
            var fenced = new XElement(
                "mfenced",
                new XAttribute("open", NormalizeFence(open)),
                new XAttribute("close", NormalizeFence(close)),
                children.Select(child => new XElement(child)));
            row.ReplaceNodes(fenced);
        }
    }


    private static string CanonicalizeElementSequence(
        XElement[] elements,
        string? variant)
    {
        if (elements.Length == 0)
            return string.Empty;
        if (TryCanonicalizeSplitFencedScriptSequence(
                elements,
                variant,
                out var splitFencedScript))
            return splitFencedScript;
        if (TryCanonicalizeLooseBinomialSequence(
                elements,
                variant,
                out var looseBinomialSequence))
            return looseBinomialSequence;
        if (TryCanonicalizeLooseFenceSequence(
                elements,
                variant,
                out var looseFenceSequence))
            return looseFenceSequence;
        return string.Concat(
            elements.Select(
                child => CanonicalizeMathMl(
                    child,
                    variant)));
    }


    private static bool TryCanonicalizeLooseBinomialSequence(
        XElement[] elements,
        string? variant,
        out string signature)
    {
        signature = string.Empty;
        if (elements.Length < 3) return false;
        var builder = new StringBuilder();
        var replaced = false;
        for (var index = 0; index < elements.Length;)
        {
            if (index + 2 < elements.Length
                && TryGetLooseFenceToken(elements[index], out var open)
                && TryGetLooseFenceToken(elements[index + 2], out var close)
                && NormalizeFence(open) == "("
                && NormalizeFence(close) == ")")
            {
                if (TryCanonicalizeLooseBinomialBody(
                        elements[index + 1],
                        variant,
                        out var binomialBody))
                {
                    builder.Append(binomialBody);
                    index += 3;
                    replaced = true;
                    continue;
                }
            }
            builder.Append(CanonicalizeMathMl(elements[index], variant));
            index++;
        }
        if (!replaced) return false;
        signature = builder.ToString();
        return true;
    }


    private static bool TryCanonicalizeLooseFenceSequence(
        XElement[] elements,
        string? variant,
        out string signature)
    {
        signature = string.Empty;
        if (elements.Length < 2) return false;

        var builder = new StringBuilder();
        var replaced = false;
        for (var index = 0; index < elements.Length;)
        {
            if (TryGetLooseOpeningFenceToken(
                    elements[index],
                    out var open)
                && TryFindMatchingLooseFence(
                    elements,
                    index,
                    open,
                    out var closeIndex,
                    out var close))
            {
                var innerElements =
                    elements
                        .Skip(index + 1)
                        .Take(closeIndex - index - 1)
                        .ToArray();
                innerElements =
                    StripRedundantNestedLooseFenceLayers(
                        innerElements,
                        open,
                        close);
                var innerSignature =
                    CanonicalizeElementSequence(
                        innerElements,
                        variant);

                builder.Append(
                    CanonicalFenceSignature(
                        open,
                        close,
                        innerSignature));
                index = closeIndex + 1;
                replaced = true;
                continue;
            }

            builder.Append(
                CanonicalizeMathMl(
                    elements[index],
                    variant));
            index++;
        }

        if (!replaced) return false;
        signature = builder.ToString();
        return true;
    }


    private static bool TryFindMatchingLooseFence(
        XElement[] elements,
        int openIndex,
        string open,
        out int closeIndex,
        out string close)
    {
        closeIndex = -1;
        close = string.Empty;
        var normalizedOpen = NormalizeFence(open);
        var expectedClose =
            MatchingClosingFence(
                normalizedOpen);
        if (expectedClose.Length == 0)
            return false;

        var depth = 0;
        for (var index = openIndex + 1;
             index < elements.Length;
             index++)
        {
            if (TryGetLooseOpeningFenceToken(
                    elements[index],
                    out var nestedOpen)
                && string.Equals(
                    NormalizeFence(nestedOpen),
                    normalizedOpen,
                    StringComparison.Ordinal))
            {
                depth++;
                continue;
            }

            if (!TryGetLooseClosingFenceToken(
                    elements[index],
                    out var candidateClose)
                || !string.Equals(
                    NormalizeFence(candidateClose),
                    expectedClose,
                    StringComparison.Ordinal))
                continue;

            if (depth > 0)
            {
                depth--;
                continue;
            }

            closeIndex = index;
            close = candidateClose;
            return true;
        }

        return false;
    }


    private static bool TryGetLooseOpeningFenceToken(
        XElement candidate,
        out string fence)
    {
        if (!TryGetLooseFenceToken(
                candidate,
                out fence))
            return false;

        var normalized =
            NormalizeFence(
                fence);
        if (normalized is "(" or "[" or "{" or "⟨" or "⌈" or "⌊")
            return true;

        if (normalized is "|" or "‖")
            return HasExplicitFenceRole(
                candidate,
                "OPEN");

        return false;
    }


    private static bool TryGetLooseClosingFenceToken(
        XElement candidate,
        out string fence)
    {
        if (!TryGetLooseFenceToken(
                candidate,
                out fence))
            return false;

        var normalized =
            NormalizeFence(
                fence);
        if (normalized is ")" or "]" or "}" or "⟩" or "⌉" or "⌋")
            return true;

        if (normalized is "|" or "‖")
            return HasExplicitFenceRole(
                candidate,
                "CLOSE");

        return false;
    }


    private static bool HasExplicitFenceRole(
        XElement candidate,
        string expectedRole)
    {
        XElement token = candidate;
        if (candidate.Name.LocalName == "mrow")
        {
            var children = candidate.Elements().ToArray();
            if (children.Length != 1
                || children[0].Name.LocalName != "mo")
                return false;
            token = children[0];
        }

        var candidateClass =
            ((string?)candidate.Attribute(
                "data-mjx-texclass")
             ?? string.Empty).Trim();
        var tokenClass =
            ((string?)token.Attribute(
                "data-mjx-texclass")
             ?? string.Empty).Trim();
        if (string.Equals(
                candidateClass,
                expectedRole,
                StringComparison.OrdinalIgnoreCase)
            || string.Equals(
                tokenClass,
                expectedRole,
                StringComparison.OrdinalIgnoreCase))
            return true;

        return string.Equals(
                (string?)token.Attribute(
                    "fence"),
                "true",
                StringComparison.OrdinalIgnoreCase)
            && string.Equals(
                (string?)token.Attribute(
                    "stretchy"),
                "true",
                StringComparison.OrdinalIgnoreCase);
    }


    private static string MatchingClosingFence(
        string open) =>
        NormalizeFence(
            open) switch
        {
            "(" => ")",
            "[" => "]",
            "{" => "}",
            "⟨" => "⟩",
            "⌈" => "⌉",
            "⌊" => "⌋",
            "|" => "|",
            "‖" => "‖",
            _ => string.Empty,
        };


    private static XElement[] StripRedundantNestedLooseFenceLayers(
        XElement[] elements,
        string outerOpen,
        string outerClose)
    {
        var normalizedOuterOpen =
            NormalizeFence(
                outerOpen);
        var normalizedOuterClose =
            NormalizeFence(
                outerClose);
        var current =
            elements;
        while (current.Length >= 2
               && TryGetLooseOpeningFenceToken(
                    current[0],
                    out var nestedOpen)
               && TryFindMatchingLooseFence(
                    current,
                    0,
                    nestedOpen,
                    out var nestedCloseIndex,
                    out var nestedClose)
               && nestedCloseIndex ==
                    current.Length - 1
               && string.Equals(
                    NormalizeFence(
                        nestedOpen),
                    normalizedOuterOpen,
                    StringComparison.Ordinal)
               && string.Equals(
                    NormalizeFence(
                        nestedClose),
                    normalizedOuterClose,
                    StringComparison.Ordinal))
        {
            current =
                current
                    .Skip(1)
                    .Take(
                        current.Length - 2)
                    .ToArray();
        }

        return current;
    }


    private static string CanonicalFenceSignature(
        string open,
        string close,
        string innerSignature)
    {
        var normalizedOpen =
            NormalizeFence(
                open);
        var normalizedClose =
            NormalizeFence(
                close);

        if (normalizedOpen.Length > 0
            && normalizedClose.Length == 0)
        {
            return "o("
                + normalizedOpen
                + ")"
                + innerSignature;
        }

        if (normalizedOpen.Length == 0
            && normalizedClose.Length > 0)
        {
            return innerSignature
                + "o("
                + normalizedClose
                + ")";
        }

        return "fence("
            + normalizedOpen
            + ","
            + normalizedClose
            + ","
            + innerSignature
            + ")";
    }


    private static bool TryCanonicalizeLooseBinomialBody(
        XElement body,
        string? variant,
        out string signature)
    {
        signature = string.Empty;
        if (body.Name.LocalName == "mfrac")
        {
            var thickness = ((string?)body.Attribute("linethickness") ?? string.Empty).Trim();
            var fractionChildren = body.Elements().ToArray();
            if (!thickness.StartsWith("0", StringComparison.Ordinal)
                || fractionChildren.Length != 2)
                return false;
            signature = "binom("
                + CanonicalizeMathMl(fractionChildren[0], variant)
                + ","
                + CanonicalizeMathMl(fractionChildren[1], variant)
                + ")";
            return true;
        }

        body = UnwrapSingleTransparentContainer(body);
        if (body.Name.LocalName != "mtable"
            || !string.Equals(
                (string?)body.Attribute("data-mtef-pile"),
                "true",
                StringComparison.OrdinalIgnoreCase))
            return false;
        var rows = body.Elements()
            .Where(row => row.Name.LocalName is "mtr" or "mlabeledtr")
            .ToArray();
        if (rows.Length != 2) return false;
        var cells = rows.Select(row => row.Elements()
                .Where(cell => cell.Name.LocalName == "mtd")
                .ToArray())
            .ToArray();
        if (cells.Any(row => row.Length != 1)) return false;
        var top = string.Concat(cells[0][0].Elements()
            .Select(child => CanonicalizeMathMl(child, variant)));
        var bottom = string.Concat(cells[1][0].Elements()
            .Select(child => CanonicalizeMathMl(child, variant)));
        signature = "binom(" + top + "," + bottom + ")";
        return true;
    }


    private static XElement UnwrapSingleTransparentContainer(XElement element)
    {
        while (element.Name.LocalName is "mrow" or "mstyle" or "mpadded")
        {
            var children = element.Elements().ToArray();
            if (children.Length != 1) break;
            element = children[0];
        }
        return element;
    }


    private static bool TryCanonicalizeMathJaxBinomialFence(
        string open,
        string close,
        XElement[] children,
        string? variant,
        out string signature)
    {
        signature = string.Empty;
        if (NormalizeFence(open) != "(" || NormalizeFence(close) != ")") return false;
        if (children.Length != 1 || children[0].Name.LocalName != "mfrac") return false;
        var lineThickness = (children[0].Attribute("linethickness")?.Value ?? string.Empty).Trim();
        if (lineThickness.Length == 0 || !lineThickness.StartsWith("0", StringComparison.Ordinal)) return false;
        var fractionChildren = children[0].Elements().ToArray();
        if (fractionChildren.Length != 2) return false;
        var top = CanonicalizeMathMl(fractionChildren[0], variant);
        var bottom = CanonicalizeMathMl(fractionChildren[1], variant);
        signature = "binom(" + top + "," + bottom + ")";
        return true;
    }


    private static bool TryCanonicalizeMathTypeBinomialFence(
        XElement fenced,
        string? variant,
        out string signature)
    {
        signature = string.Empty;
        var open = NormalizeFence((string?)fenced.Attribute("open") ?? "(");
        var close = NormalizeFence((string?)fenced.Attribute("close") ?? ")");
        if (open != "(" || close != ")") return false;
        var table = fenced.Elements().SingleOrDefault();
        // Word's OMML round-trip commonly materializes a native no-bar
        // fraction as mfenced -> mrow -> mfrac(linethickness=0). Treat that
        // as the same binomial semantics before checking MathType's PILE form.
        if (table is not null
            && TryCanonicalizeLooseBinomialBody(table, variant, out signature))
            return true;
        if (table is not null)
            table = UnwrapSingleTransparentContainer(table);
        if (table?.Name.LocalName == "mfrac")
            return TryCanonicalizeMathJaxBinomialFence(
                open,
                close,
                new[] { table },
                variant,
                out signature);
        if (table is null || table.Name.LocalName != "mtable") return false;
        // A genuine MathType binomial reaches us through a PILE record. An
        // explicit 2x1 matrix inside parentheses is visually similar, but is a
        // MATRIX record and must remain a matrix. The old shape-only heuristic
        // collapsed both into binom(...), which made strict LaTeXSnipper→MathType
        // round-trip validation reject explicit column matrices such as the
        // binomial-theorem formula from 文档1.
        if (!string.Equals(
                (string?)table.Attribute("data-mtef-pile"),
                "true",
                StringComparison.OrdinalIgnoreCase))
            return false;
        var rows = table.Elements()
            .Where(row => row.Name.LocalName is "mtr" or "mlabeledtr")
            .ToArray();
        if (rows.Length != 2) return false;
        var cells = rows.Select(row => row.Elements()
                .Where(cell => cell.Name.LocalName == "mtd")
                .ToArray())
            .ToArray();
        if (cells.Any(row => row.Length != 1)) return false;
        var top = string.Concat(cells[0][0].Elements()
            .Select(child => CanonicalizeMathMl(child, variant)));
        var bottom = string.Concat(cells[1][0].Elements()
            .Select(child => CanonicalizeMathMl(child, variant)));
        signature = "binom(" + top + "," + bottom + ")";
        return true;
    }


    private static bool TryCanonicalizeSplitFencedScriptSequence(
        XElement[] elements,
        string? variant,
        out string signature)
    {
        signature = string.Empty;
        if (elements.Length < 3) return false;
        if (!TryGetLooseOpeningFenceToken(
                elements[0],
                out var open))
            return false;

        for (var scriptIndex = 2;
             scriptIndex < elements.Length;
             scriptIndex++)
        {
            var script = elements[scriptIndex];
            var scriptKind = script.Name.LocalName;
            if (scriptKind is not ("msub" or "msup" or "msubsup"))
                continue;

            var scriptChildren =
                script.Elements().ToArray();
            var minimumChildren =
                scriptKind == "msubsup"
                    ? 3
                    : 2;
            if (scriptChildren.Length < minimumChildren)
                continue;
            if (!TryGetLooseClosingFenceToken(
                    scriptChildren[0],
                    out var close))
                continue;
            if (!AreMatchingFences(
                    open,
                    close))
                continue;

            var innerElements =
                elements
                    .Skip(1)
                    .Take(scriptIndex - 1)
                    .ToArray();
            innerElements =
                StripRedundantNestedLooseFenceLayers(
                    innerElements,
                    open,
                    close);
            var innerSignature =
                CanonicalizeElementSequence(
                    innerElements,
                    variant);
            if (innerSignature.Length == 0)
                continue;

            var baseSignature =
                CanonicalFenceSignature(
                    open,
                    close,
                    innerSignature);
            string scriptedSignature;
            if (scriptKind == "msub")
            {
                var subSignature =
                    CanonicalizeMathMl(
                        scriptChildren[1],
                        variant);
                if (subSignature.Length == 0)
                    continue;
                scriptedSignature =
                    "sub("
                    + baseSignature
                    + ","
                    + subSignature
                    + ")";
            }
            else if (scriptKind == "msup")
            {
                var supSignature =
                    CanonicalizeMathMl(
                        scriptChildren[1],
                        variant);
                if (supSignature.Length == 0)
                    continue;
                scriptedSignature =
                    "sup("
                    + baseSignature
                    + ","
                    + supSignature
                    + ")";
            }
            else
            {
                var subSignature =
                    CanonicalizeMathMl(
                        scriptChildren[1],
                        variant);
                var supSignature =
                    CanonicalizeMathMl(
                        scriptChildren[2],
                        variant);
                if (subSignature.Length == 0
                    && supSignature.Length == 0)
                    continue;
                if (subSignature.Length == 0)
                {
                    scriptedSignature =
                        "sup("
                        + baseSignature
                        + ","
                        + supSignature
                        + ")";
                }
                else if (supSignature.Length == 0)
                {
                    scriptedSignature =
                        "sub("
                        + baseSignature
                        + ","
                        + subSignature
                        + ")";
                }
                else
                {
                    scriptedSignature =
                        "subsup("
                        + baseSignature
                        + ","
                        + subSignature
                        + ","
                        + supSignature
                        + ")";
                }
            }

            var tail =
                CanonicalizeElementSequence(
                    elements
                        .Skip(scriptIndex + 1)
                        .ToArray(),
                    variant);
            signature =
                scriptedSignature
                + tail;
            return true;
        }

        return false;
    }


    private static bool TryGetLooseFenceToken(XElement candidate, out string fence)
    {
        fence = string.Empty;
        XElement? token = candidate.Name.LocalName == "mo" ? candidate : null;
        if (token is null && candidate.Name.LocalName == "mrow")
        {
            var nested = candidate.Elements().ToArray();
            if (nested.Length == 1 && nested[0].Name.LocalName == "mo")
                token = nested[0];
        }
        if (token is null) return false;
        fence = NormalizeFence(token.Value.Trim());
        return fence is "(" or ")" or "[" or "]" or "{" or "}"
            or "⟨" or "⟩" or "⌈" or "⌉" or "⌊" or "⌋" or "|" or "‖";
    }


    private static bool AreMatchingFences(string open, string close) =>
        (NormalizeFence(open), NormalizeFence(close)) switch
        {
            ("(", ")") => true,
            ("[", "]") => true,
            ("{", "}") => true,
            ("⟨", "⟩") => true,
            ("⌈", "⌉") => true,
            ("⌊", "⌋") => true,
            ("|", "|") => true,
            ("‖", "‖") => true,
            _ => false,
        };


    private static bool TryCanonicalizeMathJaxFencedSuperscriptRow(
        XElement row,
        string? variant,
        out string signature)
    {
        signature = string.Empty;
        if (row.Name.LocalName != "mrow") return false;
        var elements = row.Elements().ToArray();
        if (elements.Length < 3) return false;
        if (!TryGetMathJaxFenceToken(elements[0], "OPEN", out var open)) return false;

        var script = elements[elements.Length - 1];
        if (script.Name.LocalName != "msup") return false;
        var scriptChildren = script.Elements().ToArray();
        if (scriptChildren.Length < 2) return false;
        if (!TryGetMathJaxFenceToken(scriptChildren[0], "CLOSE", out var close)) return false;
        if (!AreMatchingFences(open, close)) return false;

        var inner = string.Concat(elements
            .Skip(1)
            .Take(elements.Length - 2)
            .Select(child => CanonicalizeMathMl(child, variant)));
        var baseSignature = "o(" + NormalizeFence(open) + ")"
            + inner
            + "o(" + NormalizeFence(close) + ")";
        var exponentSignature = CanonicalizeMathMl(scriptChildren[1], variant);
        signature = exponentSignature.Length == 0
            ? baseSignature
            : "sup(" + baseSignature + "," + exponentSignature + ")";
        return true;
    }


    private static bool TryGetMathJaxFenceRow(
        XElement row,
        out string open,
        out string close,
        out XElement[] children)
    {
        open = string.Empty;
        close = string.Empty;
        children = Array.Empty<XElement>();
        if (row.Name.LocalName != "mrow") return false;
        var elements = row.Elements().ToArray();
        if (elements.Length < 3) return false;
        if (!TryGetMathJaxFenceToken(elements[0], "OPEN", out open)) return false;
        if (!TryGetMathJaxFenceToken(elements[elements.Length - 1], "CLOSE", out close)) return false;
        // MathJax represents \left\{ ... \right. with an explicit empty
        // closing fence. It is a one-sided delimiter template, not an empty
        // operator after an ordinary brace glyph. Use the same recognition for
        // MTEF geometry and semantic comparison.
        var oneSided = (open.Length == 0) != (close.Length == 0);
        if (!AreMatchingFences(open, close)
            && !(oneSided && SelectFenceTemplate(open, close).HasValue)) return false;
        children = elements.Skip(1).Take(elements.Length - 2).ToArray();
        return children.Length > 0;
    }


    private static bool TryGetMathJaxFenceToken(
        XElement candidate,
        string expectedClass,
        out string fence)
    {
        fence = string.Empty;
        XElement? token = null;
        if (candidate.Name.LocalName == "mo")
            token = candidate;
        else if (candidate.Name.LocalName == "mrow")
        {
            var nested = candidate.Elements().ToArray();
            if (nested.Length == 1 && nested[0].Name.LocalName == "mo")
                token = nested[0];
        }
        if (token is null) return false;

        var candidateClass = ((string?)candidate.Attribute("data-mjx-texclass") ?? string.Empty).Trim();
        var tokenClass = ((string?)token.Attribute("data-mjx-texclass") ?? string.Empty).Trim();
        var markerMatches = string.Equals(candidateClass, expectedClass, StringComparison.OrdinalIgnoreCase)
            || string.Equals(tokenClass, expectedClass, StringComparison.OrdinalIgnoreCase);
        fence = NormalizeFence(token.Value.Trim());
        if (markerMatches) return true;
        // Explicitly fixed CHAR delimiters must not become stretchable TMPL
        // fences merely because a read-back mrow groups their siblings.
        if (string.Equals((string?)token.Attribute("fence"), "false", StringComparison.OrdinalIgnoreCase)
            || string.Equals((string?)token.Attribute("stretchy"), "false", StringComparison.OrdinalIgnoreCase))
            return false;
        if (fence.Length == 0
            && string.Equals((string?)token.Attribute("fence"), "true", StringComparison.OrdinalIgnoreCase))
            return true;

        // Word's OMML->MathML transform emits structurally complete delimiter
        // rows without MathJax's data-mjx-texclass markers. MathType 7 otherwise
        // imports only the first opening delimiter into a big-operator main slot
        // and leaves the remaining operand as root siblings. Accept an unmarked
        // token only when its glyph unambiguously matches the requested side;
        // the caller also verifies that the two delimiters form a valid pair.
        return string.Equals(expectedClass, "OPEN", StringComparison.OrdinalIgnoreCase)
            ? fence is "(" or "[" or "{" or "⟨" or "⌈" or "⌊" or "|" or "‖"
            : string.Equals(expectedClass, "CLOSE", StringComparison.OrdinalIgnoreCase)
                && fence is ")" or "]" or "}" or "⟩" or "⌉" or "⌋" or "|" or "‖";
    }


    private static void EmitExplicitFontDefinitions(
        XElement math,
        byte[] sourceMtef,
        List<byte> output)
    {
        var specs = new[]
        {
            (Variant: "script", Encoding: "EuclidMath1", Font: "Euclid Math One", CharacterStyle: (byte)0),
            (Variant: "bold-script", Encoding: "EuclidMath1", Font: "Euclid Math One", CharacterStyle: (byte)1),
            (Variant: "double-struck", Encoding: "EuclidMath2", Font: "Euclid Math Two", CharacterStyle: (byte)0),
            (Variant: "fraktur", Encoding: "EuclidFraktur", Font: "Euclid Fraktur", CharacterStyle: (byte)0),
            (Variant: "bold-fraktur", Encoding: "EuclidFraktur", Font: "Euclid Fraktur", CharacterStyle: (byte)1),
            (Variant: "sans-serif", Encoding: "WindowsANSI", Font: "Arial", CharacterStyle: (byte)0),
            (Variant: "bold-sans-serif", Encoding: "WindowsANSI", Font: "Arial", CharacterStyle: (byte)1),
            (Variant: "sans-serif-italic", Encoding: "WindowsANSI", Font: "Arial", CharacterStyle: (byte)2),
            (Variant: "sans-serif-bold-italic", Encoding: "WindowsANSI", Font: "Arial", CharacterStyle: (byte)3),
            (Variant: "monospace", Encoding: "WindowsANSI", Font: "Courier New", CharacterStyle: (byte)0),
            (Variant: "bold-italic", Encoding: "WindowsANSI", Font: "Times New Roman", CharacterStyle: (byte)3),
        };
        var existing = CountPrefixDefinitions(sourceMtef);
        var created = 0;
        foreach (var spec in specs)
        {
            var tokens = math.DescendantsAndSelf()
                .Where(element => MatchesExplicitFontSpec(element, spec.Variant))
                .ToArray();
            if (tokens.Length == 0) continue;

            var existingStyleIndex = FindPrefixFontStyleIndex(
                sourceMtef,
                spec.Font,
                spec.CharacterStyle);
            if (existingStyleIndex is not null)
            {
                foreach (var token in tokens)
                    token.SetAttributeValue(
                        "data-mtef-explicit-typeface",
                        -existingStyleIndex.Value);
                continue;
            }

            created++;
            var encodingIndex = 4 + existing.EncodingDefinitions + created;
            var fontDefinitionIndex = existing.FontDefinitions + created;
            var fontStyleIndex = existing.FontStyleDefinitions + created;

            output.Add(RecordEncodingDef);
            WriteNullTerminatedAscii(output, spec.Encoding);
            output.Add(RecordFontDef);
            WriteUnsigned(output, encodingIndex);
            WriteNullTerminatedAscii(output, spec.Font);
            output.Add(RecordFontStyleDef);
            WriteUnsigned(output, fontDefinitionIndex);
            output.Add(spec.CharacterStyle);

            foreach (var token in tokens)
                token.SetAttributeValue("data-mtef-explicit-typeface", -fontStyleIndex);
        }
    }


    private static bool MatchesExplicitFontSpec(XElement element, string variant)
    {
        var local = element.Name.LocalName;
        var scalars = EnumerateBmpScalars(element.Value).ToArray();
        if (scalars.Length == 0) return false;

        if (local == "mi")
        {
            if (string.Equals(
                    ((string?)element.Attribute("mathvariant"))?.Trim(),
                    variant,
                    StringComparison.OrdinalIgnoreCase))
            {
                // The standard blackboard set letters use MathType's built-in
                // MT Extra style, so they do not require an explicit EuclidMath2
                // prefix even when MathML calls them double-struck.
                return !string.Equals(variant, "double-struck", StringComparison.OrdinalIgnoreCase)
                    || !scalars.All(scalar => TryMtExtraDoubleStruck(scalar, out _, out _));
            }

            if (string.Equals(variant, "script", StringComparison.OrdinalIgnoreCase)
                && (scalars.All(scalar => TryEuclidMathOneGreekVariantEncoded8(scalar, out _))
                    || scalars.All(scalar => TryEuclidMathOneDotlessJ(scalar, out _, out _))))
            {
                // MathType 7 stores TeX \epsilon / \varrho / \varkappa and
                // dotless-j in Euclid Math One even when MathML does not carry
                // a script mathvariant.
                return true;
            }
        }

        if (local == "mo")
        {
            if (string.Equals(variant, "script", StringComparison.OrdinalIgnoreCase)
                && scalars.All(scalar => TryEuclidMathOneOperatorEncoded8(scalar, out _)))
            {
                return true;
            }
            if (string.Equals(variant, "double-struck", StringComparison.OrdinalIgnoreCase)
                && scalars.All(scalar => TryEuclidMathTwoOperatorEncoded8(scalar, out _)))
            {
                return true;
            }
        }

        return false;
    }


    private static int? FindPrefixFontStyleIndex(
        byte[] mtef, string fontName, byte expectedCharacterStyle)
    {
        var fontDefinitions = new List<string>();
        var styleIndex = 0;
        foreach (var record in ReadPrefixLayout(mtef).Records)
        {
            var position = record.Start + 1;
            if (record.Type == RecordFontDef)
            {
                _ = ReadUnsigned(mtef, ref position);
                fontDefinitions.Add(ReadPrefixNullTerminatedString(mtef, ref position));
            }
            else if (record.Type == RecordFontStyleDef)
            {
                var fontDefinitionIndex = ReadUnsigned(mtef, ref position);
                var actualCharacterStyle = mtef[position];
                styleIndex++;
                if (actualCharacterStyle == expectedCharacterStyle
                    && fontDefinitionIndex > 0 && fontDefinitionIndex <= fontDefinitions.Count
                    && string.Equals(fontDefinitions[fontDefinitionIndex - 1], fontName, StringComparison.OrdinalIgnoreCase))
                    return styleIndex;
            }
        }
        return null;
    }


    private static string ReadPrefixNullTerminatedString(
        byte[] data,
        ref int position)
    {
        var start = position;
        while (position < data.Length && data[position] != 0) position++;
        if (position >= data.Length)
            throw new EndOfStreamException("MTEF prefix string is not null terminated.");
        var value = System.Text.Encoding.Default.GetString(
            data,
            start,
            position - start);
        position++;
        return value;
    }


    private static (int EncodingDefinitions, int FontDefinitions, int FontStyleDefinitions)
        CountPrefixDefinitions(byte[] mtef)
    {
        var records = ReadPrefixLayout(mtef).Records;
        return (records.Count(item => item.Type == RecordEncodingDef),
            records.Count(item => item.Type == RecordFontDef),
            records.Count(item => item.Type == RecordFontStyleDef));
    }


    private static void WriteNullTerminatedAscii(List<byte> output, string value)
    {
        output.AddRange(System.Text.Encoding.ASCII.GetBytes(value));
        output.Add(0);
    }


    private static void WriteUnsigned(List<byte> output, int value)
    {
        if (value < 0)
            throw new ArgumentOutOfRangeException(nameof(value));
        if (value < 255)
        {
            output.Add((byte)value);
            return;
        }
        output.Add(0xFF);
        output.Add((byte)(value & 0xFF));
        output.Add((byte)((value >> 8) & 0xFF));
    }


    private static void EmitNodeCore(XNode node, List<byte> output)
    {
        if (node is XText text)
        {
            EmitText(text.Value, TypefaceText, output);
            return;
        }
        if (node is not XElement element) return;
        var local = element.Name.LocalName;
        switch (local)
        {
            case "math":
            case "mrow":
            case "semantics":
            case "mpadded":
            case "mphantom":
                EmitContainerChildren(element, output, inheritedMathVariant: null);
                break;
            case "mstyle":
                EmitContainerChildren(
                    element,
                    output,
                    ((string?)element.Attribute("mathvariant"))?.Trim());
                break;
            case "mi":
                EmitIdentifier(element, output);
                break;
            case "mn":
                EmitText(element.Value, TypefaceNumber, output);
                break;
            case "mo":
            {
                var operatorValue = element.Value.Trim();
                if (TryResolveNativeIntegral(element, out var integral))
                    EmitIntegralTemplate(integral, main: null, lower: null, upper: null, output);
                else if (TryResolveNativeBigOperator(element, out var standaloneBigOperator))
                    EmitBigOperatorTemplate(standaloneBigOperator, main: null, lower: null, upper: null, output);
                else if (IsNamedLimitOperator(element)
                    || operatorValue.Length > 1 && operatorValue.All(char.IsLetter))
                    // MathJax emits alphabetic operators such as TeX `\bmod` as
                    // one upright <mo> token. Writing each ASCII letter through
                    // the Symbol typeface made the MTEF reader recover three
                    // unrelated operator tokens (`m`, `o`, `d`), tripping the
                    // strict standalone semantic gate. MathType's native
                    // function run is the matching MTEF representation for an
                    // upright alphabetic operator and round-trips as one run.
                    EmitFunctionRun(operatorValue, output);
                else
                    EmitOperator(element, output);
                break;
            }
            case "mtext":
                EmitText(element.Value, TypefaceText, output);
                break;
            case "mspace":
                EmitCharacter(' ', TypefaceSpace, output);
                break;
            case "mfrac":
                EmitFraction(element, output);
                break;
            case "msqrt":
                EmitSquareRoot(element, output);
                break;
            case "mroot":
                EmitNthRoot(element, output);
                break;
            case "msup":
                EmitScript(element, TemplateSup, output);
                break;
            case "msub":
                EmitScript(element, TemplateSub, output);
                break;
            case "msubsup":
                EmitScript(element, TemplateSubSup, output);
                break;
            case "mfenced":
                EmitFenced(element, output);
                break;
            case "mover":
                EmitOver(element, output);
                break;
            case "munder":
                EmitUnder(element, output);
                break;
            case "munderover":
                EmitUnderOver(element, output);
                break;
            case "mtable":
                EmitMatrix(element, output);
                break;
            case "mtr":
            case "mlabeledtr":
            case "mtd":
                EmitContainerChildren(element, output, inheritedMathVariant: null);
                break;
            case "menclose":
                EmitEnclose(element, output);
                break;
            case "mmultiscripts":
                EmitMultiScripts(element, output);
                break;
            case "none":
            case "annotation":
            case "annotation-xml":
                break;
            default:
                throw new InvalidDataException($"Unsupported MathML element <{local}>.");
        }
    }


    private static IEnumerable<XNode> SignificantChildren(XElement element) =>
        element.Nodes().Where(node =>
            node is XElement
            || node is XText text && !string.IsNullOrWhiteSpace(text.Value));


    private static bool RequiresGroupedScriptBase(XElement element)
    {
        var local = element.Name.LocalName;
        if (local is not ("mrow" or "mstyle" or "semantics" or "mpadded" or "math"))
            return false;
        var objectCount = 0;
        foreach (var child in SignificantChildren(element))
        {
            if (child is XElement childElement
                && childElement.Name.LocalName is "annotation" or "annotation-xml")
                continue;
            objectCount++;
            if (objectCount > 1) return true;
        }
        return false;
    }


    private static void EmitContainerChildren(
        XElement element,
        List<byte> output,
        string? inheritedMathVariant)
    {
        var children = new List<XNode>();
        foreach (var child in SignificantChildren(element))
        {
            if (child is XElement childElement
                && (childElement.Name.LocalName == "annotation"
                    || childElement.Name.LocalName == "annotation-xml"))
                continue;
            if (string.IsNullOrWhiteSpace(inheritedMathVariant)
                || child is not XElement styledChild)
            {
                children.Add(child);
                continue;
            }
            var clone = new XElement(styledChild);
            ApplyInheritedMathVariant(clone, inheritedMathVariant!);
            children.Add(clone);
        }

        for (var index = 0; index < children.Count; index++)
        {
            if (children[index] is XElement bigOperatorHead
                && TryResolveBigOperatorHead(bigOperatorHead, out var resolvedHead))
            {
                var mainNodes = new List<XNode>();
                var cursor = index + 1;
                while (cursor < children.Count && !IsBigOperatorMainBoundary(children[cursor]))
                {
                    mainNodes.Add(CloneNode(children[cursor]));
                    cursor++;
                }
                if (mainNodes.Count > 0)
                {
                    var main = new XElement("mrow", mainNodes);
                    EmitResolvedBigOperator(resolvedHead, main, output);
                    index = cursor - 1;
                    continue;
                }
            }
            EmitNode(children[index], output);
        }
    }


    private readonly struct ResolvedBigOperatorHead
    {
        public ResolvedBigOperatorHead(
            NativeIntegral integral,
            NativeBigOperator bigOperator,
            XElement? lower,
            XElement? upper)
        {
            Integral = integral;
            BigOperator = bigOperator;
            Lower = lower;
            Upper = upper;
        }

        public NativeIntegral Integral { get; }
        public NativeBigOperator BigOperator { get; }
        public XElement? Lower { get; }
        public XElement? Upper { get; }
        public bool IsIntegral => Integral.VariationKind != 0;
    }


    private static bool TryResolveBigOperatorHead(
        XElement element,
        out ResolvedBigOperatorHead resolved)
    {
        resolved = default;
        var local = element.Name.LocalName;
        var children = element.Elements().ToArray();
        XElement? baseElement = element;
        XElement? lower = null;
        XElement? upper = null;
        if (local is "msub" or "msup" or "msubsup" or "munder" or "mover" or "munderover")
        {
            if (children.Length < 2) return false;
            baseElement = children[0];
            if (local is "msub" or "munder") lower = children[1];
            else if (local is "msup" or "mover") upper = children[1];
            else
            {
                if (children.Length < 3) return false;
                lower = children[1];
                upper = children[2];
            }
        }
        else if (local != "mo")
        {
            return false;
        }

        if (TryResolveNativeIntegral(baseElement, out var integral))
        {
            resolved = new ResolvedBigOperatorHead(integral, default, lower, upper);
            return true;
        }
        if (TryResolveNativeBigOperator(
                baseElement,
                out var bigOperator,
                allowAmbiguousUnionIntersection: local != "mo"))
        {
            resolved = new ResolvedBigOperatorHead(default, bigOperator, lower, upper);
            return true;
        }
        return false;
    }


    private static void EmitResolvedBigOperator(
        ResolvedBigOperatorHead resolved,
        XElement main,
        List<byte> output)
    {
        if (resolved.IsIntegral)
            EmitIntegralTemplate(
                resolved.Integral,
                main,
                resolved.Lower,
                resolved.Upper,
                output);
        else
            EmitBigOperatorTemplate(
                resolved.BigOperator,
                main,
                resolved.Lower,
                resolved.Upper,
                output);
    }


    private static bool IsBigOperatorMainBoundary(XNode node)
    {
        if (node is not XElement element || element.Name.LocalName != "mo") return false;
        var value = element.Value.Trim();
        return value is "+" or "-" or "−" or "±" or "∓"
            or "=" or "≠" or "<" or ">" or "≤" or "≥" or "≈" or "≃" or "∼"
            or "≡" or "∝" or "∈" or "∉" or "⊂" or "⊆" or "⊃" or "⊇"
            or "," or ";";
    }


    private static XNode CloneNode(XNode node) => node switch
    {
        XElement element => new XElement(element),
        XText text => new XText(text.Value),
        _ => new XText(node.ToString()),
    };


    private static void ApplyInheritedMathVariant(XElement element, string mathVariant)
    {
        if (element.Name.LocalName is "mi" or "mn" or "mo" or "mtext")
        {
            if (element.Attribute("mathvariant") is null)
                element.SetAttributeValue("mathvariant", mathVariant);
            return;
        }
        foreach (var descendant in element.Descendants())
        {
            if (descendant.Name.LocalName is not ("mi" or "mn" or "mo" or "mtext"))
                continue;
            if (descendant.Attribute("mathvariant") is null)
                descendant.SetAttributeValue("mathvariant", mathVariant);
        }
    }


    private static void EmitFraction(XElement element, List<byte> output)
    {
        var children = element.Elements().ToArray();
        if (children.Length < 2)
            throw new InvalidDataException("MathML mfrac requires numerator and denominator.");

        var lineThickness = ((string?)element.Attribute("linethickness") ?? string.Empty).Trim();
        if (lineThickness.Length > 0 && lineThickness.StartsWith("0", StringComparison.Ordinal))
        {
            // MathJax represents \binom and related stacked expressions as an
            // mfrac with a zero rule. MathType's native equivalent is a centered
            // PILE, not the ordinary fraction template (which always draws a rule).
            output.AddRange(new byte[]
            {
                RecordPile,
                0,
                2, // horizontal alignment: centered
                1, // vertical alignment: centered
            });
            EmitLine(children[0], output);
            EmitLine(children[1], output);
            output.Add(RecordEnd);
            return;
        }

        output.AddRange(new byte[] { RecordTemplate, 0, TemplateFraction, 0, 0 });
        EmitLine(children[0], output);
        EmitLine(children[1], output);
        output.Add(RecordEnd);
        output.Add(RecordFull);
    }


    private static void EmitSquareRoot(XElement element, List<byte> output)
    {
        output.AddRange(new byte[] { RecordTemplate, 0, TemplateRoot, 0, 0 });
        EmitLineContents(SignificantChildren(element), output);
        output.Add(RecordSub);
        output.AddRange(new byte[] { RecordLine, LineNull });
        output.Add(RecordEnd);
        output.Add(RecordFull);
    }


    private static void EmitNthRoot(XElement element, List<byte> output)
    {
        var children = element.Elements().ToArray();
        if (children.Length < 2)
            throw new InvalidDataException("MathML mroot requires radicand and index.");
        output.AddRange(new byte[] { RecordTemplate, 0, TemplateRoot, 1, 0 });
        EmitLine(children[0], output);
        output.Add(RecordSub);
        EmitLine(children[1], output);
        output.Add(RecordEnd);
        output.Add(RecordFull);
    }


    private static void EmitScript(XElement element, byte selector, List<byte> output)
    {
        var children = element.Elements().ToArray();
        var required = selector == TemplateSubSup ? 3 : 2;
        if (children.Length < required)
            throw new InvalidDataException($"MathML {element.Name.LocalName} has too few children.");
        if (TryResolveNativeIntegral(children[0], out var integral))
        {
            EmitIntegralTemplate(
                integral,
                main: null,
                lower: selector is TemplateSub or TemplateSubSup ? children[1] : null,
                upper: selector == TemplateSup ? children[1] : selector == TemplateSubSup ? children[2] : null,
                output);
            return;
        }
        if (TryResolveNativeBigOperator(
                children[0],
                out var bigOperator,
                allowAmbiguousUnionIntersection: true))
        {
            EmitBigOperatorTemplate(
                bigOperator,
                main: null,
                lower: selector is TemplateSub or TemplateSubSup ? children[1] : null,
                upper: selector == TemplateSup ? children[1] : selector == TemplateSubSup ? children[2] : null,
                output);
            return;
        }
        if (IsNamedLimitOperator(children[0]))
        {
            EmitLimitTemplate(
                children[0],
                selector is TemplateSub or TemplateSubSup ? children[1] : null,
                selector == TemplateSup ? children[1] : selector == TemplateSubSup ? children[2] : null,
                output);
            return;
        }
        // MathType's postfix script template binds to exactly one preceding MTEF
        // object. Flattening a multi-object MathML mrow here makes a script on
        // `(1+1/n)` bind only to the final ')' when Equation Native is read back.
        // Preserve the whole composite base as one nested LINE object before
        // appending the script template. Atomic bases keep the old path so common
        // x^2 / a_i equations remain byte- and layout-compatible.
        if (RequiresGroupedScriptBase(children[0]))
            EmitLine(children[0], output);
        else
            EmitNode(children[0], output);
        output.AddRange(new byte[] { RecordTemplate, 0, selector, 0, 0 });
        output.Add(RecordSub);
        if (selector == TemplateSub)
        {
            EmitLine(children[1], output);
            output.AddRange(new byte[] { RecordLine, LineNull });
        }
        else if (selector == TemplateSup)
        {
            output.AddRange(new byte[] { RecordLine, LineNull });
            EmitLine(children[1], output);
        }
        else
        {
            EmitLine(children[1], output);
            EmitLine(children[2], output);
        }
        output.Add(RecordEnd);
        output.Add(RecordFull);
    }


    private static void EmitOver(XElement element, List<byte> output)
    {
        var children = element.Elements().ToArray();
        if (children.Length < 2)
        {
            EmitContainerChildren(element, output, inheritedMathVariant: null);
            return;
        }
        if (TryResolveNativeIntegral(children[0], out var integral))
        {
            EmitIntegralTemplate(integral, main: null, lower: null, upper: children[1], output);
            return;
        }
        if (TryResolveNativeBigOperator(
                children[0],
                out var bigOperator,
                allowAmbiguousUnionIntersection: true))
        {
            EmitBigOperatorTemplate(
                bigOperator,
                main: null,
                lower: null,
                upper: children[1],
                output);
            return;
        }
        if (TryGetAnnotatedHorizontalBraceBody(children[0], top: true, out var annotatedBraceBody))
        {
            EmitHorizontalFenceTemplate(
                TemplateHorizontalBrace,
                top: true,
                annotatedBraceBody,
                children[1],
                output);
            return;
        }
        var over = NormalizeAccentMark(children[1].Value.Trim());
        var embellishmentBody = UnwrapSingleTokenAccentBody(children[0]);
        if (embellishmentBody is not null
            && TryEmitSingleCharacterEmbellishment(embellishmentBody, over, output)) return;
        switch (over)
        {
            case "\u00AF":
            case "\u203E":
            case "\u2015":
            case "\u02C9":
                EmitSingleSlotTemplate(TemplateOverbar, 0, children[0], output);
                return;
            case "→":
                EmitVectorTemplate(0x02, 0x20D7, children[0], output);
                return;
            case "←":
                EmitVectorTemplate(0x01, 0x20D6, children[0], output);
                return;
            case "↔":
                EmitVectorTemplate(0x03, 0x20E1, children[0], output);
                return;
            case "^":
            case "ˆ":
                EmitSingleSlotTemplate(TemplateHat, 0, children[0], output);
                return;
            case "~":
            case "˜":
                EmitSingleSlotTemplate(TemplateTilde, 0, children[0], output);
                return;
            case "⌢":
            case "⏜":
                EmitSingleSlotTemplate(TemplateArc, 0, children[0], output);
                return;
            case "⏞":
                EmitHorizontalFenceTemplate(
                    TemplateHorizontalBrace,
                    top: true,
                    children[0],
                    annotation: null,
                    output);
                return;
        }
        EmitNode(children[0], output);
        EmitTrailingScript(children[1], isSubscript: false, output);
    }


    private static void EmitUnder(XElement element, List<byte> output)
    {
        var children = element.Elements().ToArray();
        if (children.Length < 2)
        {
            EmitContainerChildren(element, output, inheritedMathVariant: null);
            return;
        }
        if (TryResolveNativeIntegral(children[0], out var integral))
        {
            EmitIntegralTemplate(integral, main: null, lower: children[1], upper: null, output);
            return;
        }
        if (TryResolveNativeBigOperator(
                children[0],
                out var bigOperator,
                allowAmbiguousUnionIntersection: true))
        {
            EmitBigOperatorTemplate(
                bigOperator,
                main: null,
                lower: children[1],
                upper: null,
                output);
            return;
        }
        if (TryGetAnnotatedHorizontalBraceBody(children[0], top: false, out var annotatedBraceBody))
        {
            EmitHorizontalFenceTemplate(
                TemplateHorizontalBrace,
                top: false,
                annotatedBraceBody,
                children[1],
                output);
            return;
        }
        if (IsNamedLimitOperator(children[0]))
        {
            EmitLimitTemplate(children[0], children[1], upper: null, output);
            return;
        }
        var under = children[1].Value.Trim();
        if (under is "_" or "¯" or "‾" or "―" or "ˉ" or "̅" or "̲")
        {
            EmitSingleSlotTemplate(TemplateUnderbar, 0, children[0], output);
            return;
        }
        if (under == "⏟")
        {
            EmitHorizontalFenceTemplate(
                TemplateHorizontalBrace,
                top: false,
                children[0],
                annotation: null,
                output);
            return;
        }
        EmitNode(children[0], output);
        EmitTrailingScript(children[1], isSubscript: true, output);
    }


    private static void EmitUnderOver(XElement element, List<byte> output)
    {
        var children = element.Elements().ToArray();
        if (children.Length < 3)
        {
            EmitContainerChildren(element, output, inheritedMathVariant: null);
            return;
        }
        if (TryResolveNativeIntegral(children[0], out var integral))
        {
            EmitIntegralTemplate(
                integral,
                main: null,
                lower: children[1],
                upper: children[2],
                output);
            return;
        }
        if (TryResolveNativeBigOperator(
                children[0],
                out var bigOperator,
                allowAmbiguousUnionIntersection: true))
        {
            EmitBigOperatorTemplate(
                bigOperator,
                main: null,
                lower: children[1],
                upper: children[2],
                output);
            return;
        }
        if (IsNamedLimitOperator(children[0]))
        {
            EmitLimitTemplate(children[0], children[1], children[2], output);
            return;
        }
        EmitNode(children[0], output);
        output.AddRange(new byte[] { RecordTemplate, 0, TemplateSubSup, 0, 0, RecordSub });
        EmitLine(children[1], output);
        EmitLine(children[2], output);
        output.Add(RecordEnd);
        output.Add(RecordFull);
    }


    private readonly struct NativeIntegral
    {
        public NativeIntegral(int variationKind, int integralCount)
        {
            VariationKind = variationKind;
            IntegralCount = integralCount;
        }

        public int VariationKind { get; }
        public int IntegralCount { get; }
    }


    private static bool TryResolveNativeIntegral(
        XElement element,
        out NativeIntegral integral)
    {
        integral = default;
        if (element.Name.LocalName != "mo") return false;
        integral = element.Value.Trim() switch
        {
            "∫" => new NativeIntegral(0x01, 1),
            "∬" => new NativeIntegral(0x02, 2),
            "∭" => new NativeIntegral(0x03, 3),
            "∮" => new NativeIntegral(0x05, 1),
            "∲" => new NativeIntegral(0x08, 1),
            "∳" => new NativeIntegral(0x0C, 1),
            _ => default,
        };
        return integral.VariationKind != 0;
    }


    private static void EmitIntegralTemplate(
        NativeIntegral integral,
        XElement? main,
        XElement? lower,
        XElement? upper,
        List<byte> output)
    {
        // MathType 7 uses selector 15 for the integral family. Genuine native
        // equations encode lower/upper presence in 0x10/0x20 and the integral
        // kind in the low nibble (1=single, 2=double, 3=triple, 5=contour).
        // A contour template also requires MathType Extra's loop adornment
        // character before the ordinary integral glyph. Variation 4 with only
        // the integral character makes MathPage access invalid native state.
        var variation = integral.VariationKind
            | (lower is null ? 0 : 0x10)
            | (upper is null ? 0 : 0x20);
        EmitTemplateHeader(TemplateIntegral, variation, output);
        if (main is null) output.AddRange(new byte[] { RecordLine, LineNull });
        else EmitLine(main, output);
        // MathType stores integral limits in SUB size. SIZE records are stateful;
        // omitting this transition makes the lower/upper slots inherit FULL and
        // renders limits visibly too large even though the MTEF remains readable.
        if (lower is not null || upper is not null)
            output.Add(RecordSub);
        if (lower is null) output.AddRange(new byte[] { RecordLine, LineNull });
        else EmitLine(lower, output);
        if (upper is null) output.AddRange(new byte[] { RecordLine, LineNull });
        else EmitLine(upper, output);
        output.Add(RecordSym);
        if (integral.VariationKind == 0x05)
        {
            // Exact bytes emitted by genuine MathType 7 for the closed-loop
            // adornment: fnMTEXTRA, MTCode U+EE11, legacy position 0xD1.
            EmitScalar(
                0xEE11,
                TypefaceMtExtra,
                output,
                includeEncoded8: true,
                encoded8Override: 0xD1);
        }
        for (var index = 0; index < integral.IntegralCount; index++)
        {
            EmitScalar(
                0x222B,
                TypefaceSymbol,
                output,
                includeEncoded8: true,
                encoded8Override: 0xF2);
        }
        output.Add(RecordEnd);
        // SYM is a persistent MTEF typesize state. Genuine MathType BigOp
        // equations normally place the complete integrand in the template's
        // main slot, so there is no ordinary sibling text after the symbol.
        // LaTeXSnipper can encounter presentation MathML where the integrand is a
        // following sibling; always restore FULL after the template so that
        // subsequent ordinary characters cannot inherit symbol size.
        output.Add(RecordFull);
    }


    private readonly struct NativeBigOperator
    {
        public NativeBigOperator(
            byte selector,
            int mtCode,
            int typeface,
            byte encoded8)
        {
            Selector = selector;
            MtCode = mtCode;
            Typeface = typeface;
            Encoded8 = encoded8;
        }

        public byte Selector { get; }
        public int MtCode { get; }
        public int Typeface { get; }
        public byte Encoded8 { get; }
    }


    private static bool TryResolveNativeBigOperator(
        XElement element,
        out NativeBigOperator bigOperator,
        bool allowAmbiguousUnionIntersection = false)
    {
        bigOperator = default;
        if (element.Name.LocalName != "mo") return false;
        var value = element.Value.Trim();
        var explicitBigOperator = string.Equals(
                ((string?)element.Attribute("data-mjx-texclass"))?.Trim(),
                "OP",
                StringComparison.OrdinalIgnoreCase)
            || string.Equals(
                ((string?)element.Attribute("movablelimits"))?.Trim(),
                "true",
                StringComparison.OrdinalIgnoreCase);
        bigOperator = value switch
        {
            "∑" => new NativeBigOperator(TemplateSum, 0x2211, TypefaceSymbol, 0xE5),
            "∏" => new NativeBigOperator(TemplateProduct, 0x220F, TypefaceSymbol, 0xD5),
            "∐" => new NativeBigOperator(TemplateCoproduct, 0x2210, TypefaceMtExtra, 0x43),
            "⋃" => new NativeBigOperator(TemplateUnion, 0x222A, TypefaceMtExtra, 0x55),
            "⋂" => new NativeBigOperator(TemplateIntersection, 0x2229, TypefaceMtExtra, 0x49),
            "∪" when allowAmbiguousUnionIntersection || explicitBigOperator
                => new NativeBigOperator(TemplateUnion, 0x222A, TypefaceMtExtra, 0x55),
            "∩" when allowAmbiguousUnionIntersection || explicitBigOperator
                => new NativeBigOperator(TemplateIntersection, 0x2229, TypefaceMtExtra, 0x49),
            _ => default,
        };
        return bigOperator.Selector != 0;
    }


    private static void EmitBigOperatorTemplate(
        NativeBigOperator bigOperator,
        XElement? main,
        XElement? lower,
        XElement? upper,
        List<byte> output)
    {
        // MathType 7 native BigOp storage observed from genuine Equation.DSMT4:
        // variation 0x70 and line slots main/lower/upper followed by SYM + CHAR.
        EmitTemplateHeader(bigOperator.Selector, 0x70, output);
        if (main is null) output.AddRange(new byte[] { RecordLine, LineNull });
        else EmitLine(main, output);
        // Sum/product/union/intersection limits use the same script-size state as
        // native MathType. Without SUB, both limits are interpreted at FULL size.
        if (lower is not null || upper is not null)
            output.Add(RecordSub);
        if (lower is null) output.AddRange(new byte[] { RecordLine, LineNull });
        else EmitLine(lower, output);
        if (upper is null) output.AddRange(new byte[] { RecordLine, LineNull });
        else EmitLine(upper, output);
        output.Add(RecordSym);
        EmitScalar(
            bigOperator.MtCode,
            bigOperator.Typeface,
            output,
            includeEncoded8: true,
            encoded8Override: bigOperator.Encoded8);
        output.Add(RecordEnd);
        // Do not leak the SYM typesize used by the large operator glyph into
        // following siblings. MathType treats FULL/SUB/SYM as size state.
        output.Add(RecordFull);
    }


    private static bool IsNamedLimitOperator(XElement element)
    {
        if (element.Name.LocalName is not ("mi" or "mo")) return false;
        var value = element.Value.Trim();
        if (value.Length <= 1 || !value.All(char.IsLetter)) return false;
        var movableLimits = string.Equals(
            (string?)element.Attribute("movablelimits"),
            "true",
            StringComparison.OrdinalIgnoreCase);
        var texClass = ((string?)element.Attribute("data-mjx-texclass") ?? string.Empty).Trim();
        var variant = ((string?)element.Attribute("mathvariant") ?? string.Empty).Trim();
        return movableLimits
            || string.Equals(texClass, "OP", StringComparison.OrdinalIgnoreCase)
            || variant.IndexOf("normal", StringComparison.OrdinalIgnoreCase) >= 0
            || variant.IndexOf("upright", StringComparison.OrdinalIgnoreCase) >= 0;
    }


    private static void EmitLimitTemplate(
        XElement operatorElement,
        XElement? lower,
        XElement? upper,
        List<byte> output)
    {
        // Genuine MathType 7 stores named operators such as max/min/lim/sup/inf
        // as function-style CHAR records followed by the ordinary sub/sup
        // template. Writing selector 23 (tmLIM) here produced Equation Native
        // streams that our parser accepted but MathType could hang while opening.
        var name = operatorElement.Value.Trim();
        EmitFunctionRun(name, output);
        if (lower is null && upper is null) return;

        var selector = lower is not null && upper is not null
            ? TemplateSubSup
            : lower is not null
                ? TemplateSub
                : TemplateSup;
        output.AddRange(new byte[]
        {
            RecordTemplate,
            0,
            selector,
            0,
            0,
            RecordSub,
        });
        if (lower is null)
            output.AddRange(new byte[] { RecordLine, LineNull });
        else
            EmitLine(lower, output);
        if (upper is null)
            output.AddRange(new byte[] { RecordLine, LineNull });
        else
            EmitLine(upper, output);
        output.Add(RecordEnd);
        output.Add(RecordFull);
    }


    private static void EmitFunctionRun(string name, List<byte> output)
    {
        var functionScalars = EnumerateBmpScalars(name).ToArray();
        for (var index = 0; index < functionScalars.Length; index++)
        {
            EmitScalar(
                functionScalars[index],
                TypefaceFunction,
                output,
                functionStart: index == 0);
        }
    }


    private static void EmitTrailingScript(
        XElement script,
        bool isSubscript,
        List<byte> output)
    {
        output.AddRange(new byte[]
        {
            RecordTemplate,
            0,
            isSubscript ? TemplateSub : TemplateSup,
            0,
            0,
            RecordSub,
        });
        if (isSubscript)
        {
            EmitLine(script, output);
            output.AddRange(new byte[] { RecordLine, LineNull });
        }
        else
        {
            output.AddRange(new byte[] { RecordLine, LineNull });
            EmitLine(script, output);
        }
        output.Add(RecordEnd);
        output.Add(RecordFull);
    }


    private static void EmitSingleSlotTemplate(
        byte selector,
        int variation,
        XElement body,
        List<byte> output)
    {
        EmitTemplateHeader(selector, variation, output);
        EmitLine(body, output);
        output.Add(RecordEnd);
        output.Add(RecordFull);
    }


    private static void EmitVectorTemplate(
        int variation,
        int combiningArrow,
        XElement body,
        List<byte> output)
    {
        // Genuine MathType 7 tmVEC HatBox records are not a generic one-slot
        // template. After the body line MathType persists the selected combining
        // arrow as an explicit MTCode character using its expanding-glyph
        // typeface. Omitting this trailing character makes Word accept the CFB
        // initially but reject/rematerialize its OLE presentation for multi-token
        // vectors such as \overrightarrow{AB} / \overleftrightarrow{AB}.
        EmitTemplateHeader(TemplateVector, variation, output);
        EmitColor(0, output);
        EmitLine(body, output);
        EmitScalar(
            combiningArrow,
            TypefaceFence,
            output,
            includeEncoded8: false);
        output.Add(RecordEnd);
        output.Add(RecordFull);
    }


    private static bool TryGetAnnotatedHorizontalBraceBody(
        XElement candidate,
        bool top,
        out XElement body)
    {
        body = null!;
        var current = candidate;
        while (current.Name.LocalName == "mrow")
        {
            var wrapped = current.Elements().ToArray();
            if (wrapped.Length != 1) break;
            current = wrapped[0];
        }
        if (current.Name.LocalName != (top ? "mover" : "munder")) return false;
        var inner = current.Elements().ToArray();
        if (inner.Length < 2 || inner[1].Name.LocalName != "mo") return false;
        var marker = inner[1].Value.Trim();
        var expected = top ? "⏞" : "⏟";
        if (!IsHorizontalBraceMarker(marker, top)) return false;
        body = inner[0];
        return true;
    }


    private static void EmitHorizontalFenceTemplate(
        byte selector,
        bool top,
        XElement body,
        XElement? annotation,
        List<byte> output)
    {
        EmitTemplateHeader(selector, top ? 1 : 0, output);

        // Match MathType 7's native HorizontalBrace/HorizontalBracket layout.
        // A real Equation.DSMT4 stores the main body at full size, switches to
        // SUB for the annotation, restores FULL, then writes the private fence
        // glyph using the expanding-fence typeface. Writing the public Unicode
        // U+23DE/U+23DF operators here produces an MTEF stream that LaTeXSnipper can
        // parse itself but that MathType may reject while activating the OLE.
        EmitColor(0, output);
        EmitMathTypeColoredLine(body, output, resetColorAfter: false);
        output.Add(RecordSub);
        EmitColor(0, output);
        if (annotation is null)
            output.AddRange(new byte[] { RecordLine, LineNull });
        else
            EmitMathTypeColoredLine(annotation, output, resetColorAfter: false);
        output.Add(RecordFull);
        EmitScalar(
            top ? 0xFE37 : 0xFE38,
            TypefaceFence,
            output,
            includeEncoded8: false);
        output.Add(RecordEnd);
    }


    private static void EmitTemplateHeader(byte selector, int variation, List<byte> output)
    {
        output.Add(RecordTemplate);
        output.Add(0);
        output.Add(selector);
        if (variation < 0x80)
        {
            output.Add((byte)variation);
        }
        else
        {
            output.Add((byte)(0x80 | (variation & 0x7F)));
            output.Add((byte)(variation >> 8));
        }
        output.Add(0);
    }


    private static XElement? UnwrapSingleTokenAccentBody(XElement body)
    {
        var current = body;
        while (current.Name.LocalName == "mrow")
        {
            var children = current.Elements().ToArray();
            if (children.Length != 1) break;
            current = children[0];
        }
        return current.Name.LocalName is "mi" or "mn" or "mo" ? current : null;
    }


    private static string NormalizeAccentMark(string mark) => mark switch
    {
        "\u0305" or "\u203E" or "\u2015" or "\u02C9" => "¯",
        "\u0302" or "ˆ" => "^",
        "\u0303" or "˜" => "~",
        "\u20D7" => "→",
        "\u20D6" => "←",
        "\u20E1" => "↔",
        "." or "\u0307" => "˙",
        "\u0308" => "¨",
        "\u030C" => "ˇ",
        "\u0306" => "˘",
        "\u0301" => "´",
        "\u0300" => "`",
        "\u030A" => "˚",
        _ => mark,
    };


    private static bool TryEmitSingleCharacterEmbellishment(
        XElement body,
        string over,
        List<byte> output)
    {
        var code = NormalizeAccentMark(over) switch
        {
            "." or "˙" => EmbellDot,
            "¨" => EmbellDoubleDot,
            "~" or "˜" => EmbellTilde,
            "^" or "ˆ" => EmbellHat,
            "→" => EmbellRightArrow,
            "←" => EmbellLeftArrow,
            "↔" => EmbellBothArrow,
            "\u00AF" or "\u203E" or "\u2015" or "\u02C9" => EmbellOverbar,
            _ => (byte)0,
        };
        if (code == 0 || body.Name.LocalName is not ("mi" or "mn" or "mo"))
            return false;
        var scalars = EnumerateBmpScalars(body.Value).ToArray();
        if (scalars.Length != 1) return false;
        var typeface = ResolveTokenTypeface(body, scalars[0]);
        EmitScalar(
            scalars[0],
            typeface,
            output,
            includeEncoded8: body.Name.LocalName == "mo" && scalars[0] <= 0xFF,
            embellishments: new[] { code });
        return true;
    }


    private static bool TryEmitAlignedPile(
        XElement element,
        List<byte> output)
    {
        var rows = element.Elements()
            .Where(row => row.Name.LocalName is "mtr" or "mlabeledtr")
            .ToArray();
        if (rows.Length == 0) return false;

        var cells = rows.Select(row => row.Elements()
                .Where(cell => cell.Name.LocalName == "mtd")
                .ToArray())
            .ToArray();
        var columnCount = cells.Max(row => row.Length);
        if (columnCount < 2 || (columnCount & 1) != 0) return false;

        var columnAlignment = ((string?)element.Attribute("columnalign") ?? string.Empty)
            .Split((char[]?)null, StringSplitOptions.RemoveEmptyEntries);
        if (columnAlignment.Length < columnCount) return false;
        for (var column = 0; column < columnCount; column++)
        {
            var expected = (column & 1) == 0 ? "right" : "left";
            if (!string.Equals(
                    columnAlignment[column],
                    expected,
                    StringComparison.OrdinalIgnoreCase))
                return false;
        }

        var pairCount = columnCount / 2;
        var rulerText = ((string?)element.Attribute(MtefRulerStopsAttribute) ?? string.Empty)
            .Trim();
        var rulerStops = rulerText.Length == 0
            ? Array.Empty<int>()
            : rulerText.Split(',')
                .Select(value => int.TryParse(
                    value.Trim(),
                    NumberStyles.Integer,
                    CultureInfo.InvariantCulture,
                    out var parsed)
                    ? parsed
                    : -1)
                .ToArray();
        var hasExactRuler = rulerStops.Length == pairCount
            && rulerStops.All(stop => stop > 0 && stop <= ushort.MaxValue)
            && rulerStops.Zip(rulerStops.Skip(1), (left, right) => right > left).All(valid => valid);
        if (!hasExactRuler) return false;

        // MathType's true multi-point alignment has two distinct fnMARKER
        // primitives. U+0009 starts a tab group; MTCode 0xEF00 is MathType's
        // non-printing alignment symbol inside that group. With an explicit
        // RULER, each group is positioned so its alignment symbol lands exactly
        // on the supplied stop. This is the native equivalent of one TeX
        // right/left `&` pair. A plain sequence of Ctrl+Tab markers is not enough:
        // MathType's default stops are 0.5in apart, so a wide left operand can
        // skip a stop and visibly misalign one row.
        output.AddRange(new byte[]
        {
            RecordPile,
            0x02,
            1, // horizontal alignment: left; tab groups own their reference points
            1, // vertical alignment: center line
        });
        // LP_RULER is an inline field of LINE/PILE. MathType's native MTEF
        // readers consume n_stops immediately after the alignment bytes; the
        // enclosing option bit already identifies the payload as a RULER.
        // Emitting an additional standalone record tag (7) here shifts every
        // following byte and MathPage renders the equation blank.
        output.Add((byte)rulerStops.Length);
        foreach (var stop in rulerStops)
        {
            output.Add(0); // left tab; an in-group alignment symbol overrides it
            output.Add((byte)(stop & 0xff));
            output.Add((byte)((stop >> 8) & 0xff));
        }

        foreach (var row in cells)
        {
            output.AddRange(new byte[] { RecordLine, 0 });
            for (var pair = 0; pair < pairCount; pair++)
            {
                // Start the group at the next explicit ruler stop, then place
                // the TeX pair boundary at MathType's own alignment symbol.
                EmitScalar('\t', TypefaceMarker, output, includeEncoded8: false);
                var leftColumn = pair * 2;
                var rightColumn = leftColumn + 1;
                if (leftColumn < row.Length)
                    EmitContainerChildren(row[leftColumn], output, inheritedMathVariant: null);
                EmitScalar(
                    MathTypeAlignmentMarkerMtCode,
                    TypefaceMarker,
                    output,
                    includeEncoded8: false);
                if (rightColumn < row.Length)
                    EmitContainerChildren(row[rightColumn], output, inheritedMathVariant: null);
            }
            output.Add(RecordEnd);
        }
        output.Add(RecordEnd);
        return true;
    }


    private static void EmitMatrix(XElement element, List<byte> output)
    {
        var rows = element.Elements()
            .Where(row => row.Name.LocalName is "mtr" or "mlabeledtr")
            .ToArray();
        if (rows.Length == 0)
        {
            output.AddRange(new byte[] { RecordMatrix, 0, 1, 2, 1, 1, 1, 0, 0 });
            output.AddRange(new byte[] { RecordLine, LineNull, RecordEnd, RecordFull });
            return;
        }
        var cells = rows.Select(row => row.Elements()
                .Where(cell => cell.Name.LocalName == "mtd")
                .ToArray())
            .ToArray();
        var columnCount = Math.Max(1, cells.Max(row => row.Length));
        if (rows.Length > byte.MaxValue || columnCount > byte.MaxValue)
            throw new InvalidDataException("MathType MTEF matrix exceeds 255 rows or columns.");

        output.AddRange(new byte[]
        {
            RecordMatrix,
            0,
            1, // vertical alignment: center line
            1, // horizontal cell justification: centered (MathType 7 native value)
            1, // vertical cell justification: baseline center
            (byte)rows.Length,
            (byte)columnCount,
        });
        for (var index = 0; index < PartitionByteCount(rows.Length + 1); index++) output.Add(0);
        for (var index = 0; index < PartitionByteCount(columnCount + 1); index++) output.Add(0);
        for (var row = 0; row < rows.Length; row++)
        {
            for (var column = 0; column < columnCount; column++)
            {
                var isLastCell = row == rows.Length - 1 && column == columnCount - 1;
                if (column < cells[row].Length)
                    EmitMathTypeColoredLine(cells[row][column], output, resetColorAfter: !isLastCell);
                else output.AddRange(new byte[] { RecordLine, LineNull });
            }
        }
        output.Add(RecordEnd);
    }


    private static int PartitionByteCount(int partitionCount) =>
        Math.Max(1, (partitionCount + 3) / 4);


    private static void EmitEnclose(XElement element, List<byte> output)
    {
        var notation = ((string?)element.Attribute("notation") ?? string.Empty)
            .ToLowerInvariant();
        var significant = SignificantChildren(element).ToArray();
        var body = significant.Length == 1 && significant[0] is XElement singleElement
            ? new XElement(singleElement)
            : new XElement("mrow", significant);
        if (notation.Contains("radical"))
        {
            EmitSquareRoot(new XElement("msqrt", new XElement(body)), output);
            return;
        }
        if (notation.Contains("box"))
        {
            EmitSingleSlotTemplate(TemplateBox, 0x1E, body, output);
            return;
        }
        var strikeVariation = 0;
        if (notation.Contains("horizontalstrike")) strikeVariation |= 0x01;
        if (notation.Contains("updiagonalstrike")) strikeVariation |= 0x02;
        if (notation.Contains("downdiagonalstrike")) strikeVariation |= 0x04;
        if (strikeVariation != 0)
        {
            EmitSingleSlotTemplate(TemplateStrike, strikeVariation, body, output);
            return;
        }
        EmitNode(body, output);
    }


    private static void EmitMultiScripts(XElement element, List<byte> output)
    {
        var children = element.Elements().ToArray();
        if (children.Length == 0) return;
        if (RequiresGroupedScriptBase(children[0])) EmitLine(children[0], output);
        else EmitNode(children[0], output);
        var index = 1;
        while (index < children.Length
            && children[index].Name.LocalName != "mprescripts")
        {
            var sub = children[index];
            var sup = index + 1 < children.Length ? children[index + 1] : null;
            if (sub.Name.LocalName == "none" && (sup is null || sup.Name.LocalName == "none"))
            {
                index += 2;
                continue;
            }
            if (sub.Name.LocalName == "none" && sup is not null)
                EmitTrailingScript(sup, isSubscript: false, output);
            else if (sup is null || sup.Name.LocalName == "none")
                EmitTrailingScript(sub, isSubscript: true, output);
            else
            {
                output.AddRange(new byte[] { RecordTemplate, 0, TemplateSubSup, 0, 0, RecordSub });
                EmitLine(sub, output);
                EmitLine(sup, output);
                output.Add(RecordEnd);
                output.Add(RecordFull);
            }
            index += 2;
        }
        // MTEF v5 tvSU_PRECEDES=1 positions the script to the left of its base.
        // The record still follows its base in the object list; both script slots
        // are serialized, with LINE_NULL for a genuinely absent half.
        if (index < children.Length && children[index].Name.LocalName == "mprescripts")
        {
            index++;
            while (index < children.Length)
            {
                var sub = children[index];
                var sup = index + 1 < children.Length ? children[index + 1] : null;
                var hasSub = sub.Name.LocalName != "none";
                var hasSup = sup is not null && sup.Name.LocalName != "none";
                if (hasSub || hasSup)
                {
                    var selector = hasSub && hasSup ? TemplateSubSup : hasSub ? TemplateSub : TemplateSup;
                    output.AddRange(new byte[] { RecordTemplate, 0, selector, 1, 0, RecordSub });
                    if (hasSub) EmitLine(sub, output);
                    else output.AddRange(new byte[] { RecordLine, LineNull });
                    if (hasSup) EmitLine(sup!, output);
                    else output.AddRange(new byte[] { RecordLine, LineNull });
                    output.Add(RecordEnd);
                    output.Add(RecordFull);
                }
                index += 2;
            }
        }
    }


    private static void EmitFenced(XElement element, List<byte> output)
    {
        var open = NormalizeFence((string?)element.Attribute("open") ?? "(");
        var close = NormalizeFence((string?)element.Attribute("close") ?? ")");
        var selector = SelectFenceTemplate(open, close);
        if (selector is null)
        {
            if (!string.IsNullOrEmpty(open)) EmitOperator(open, output);
            foreach (var child in SignificantChildren(element)) EmitNode(child, output);
            if (!string.IsNullOrEmpty(close)) EmitOperator(close, output);
            return;
        }
        var variation = (string.IsNullOrEmpty(open) ? 0 : 1)
            | (string.IsNullOrEmpty(close) ? 0 : 2);
        EmitTemplateHeader(selector.Value, variation, output);
        EmitColor(0, output);
        EmitLineContents(SignificantChildren(element), output);
        if (!string.IsNullOrEmpty(open)) EmitFenceCharacter(open, opening: true, output);
        if (!string.IsNullOrEmpty(close)) EmitFenceCharacter(close, opening: false, output);
        output.Add(RecordEnd);
    }


    private static void EmitColor(int index, List<byte> output)
    {
        output.Add(RecordColor);
        WriteUnsigned(output, ColorStates.GetOrCreateValue(output).Current);
    }


    private static void EmitMathTypeColoredLine(
        XElement element,
        List<byte> output,
        bool resetColorAfter)
    {
        output.AddRange(new byte[] { RecordLine, 0 });
        EmitColor(1, output);
        EmitNode(element, output);
        output.Add(RecordEnd);
        if (resetColorAfter) EmitColor(0, output);
    }


    private static void EmitFenceCharacter(
        string value,
        bool opening,
        List<byte> output)
    {
        foreach (var scalar in EnumerateBmpScalars(value))
        {
            // MathType's fnFENCE typeface is MTCode-encoded rather than a
            // generic Unicode font. These values are captured from genuine
            // MathType 7 Equation Native streams for the same expandable
            // delimiters. Some delimiters (| and ||) use the same Unicode text
            // on both sides but distinct left/right MTCode glyphs, so the side
            // of the fence is part of the mapping.
            var mtCode = scalar switch
            {
                '(' => 0x0028,
                ')' => 0x0029,
                '[' => 0x005B,
                ']' => 0x005D,
                '{' => 0x007B,
                '}' => 0x007D,
                0x27E8 => 0x2329, // \langle
                0x27E9 => 0x232A, // \rangle
                '|' => opening ? 0xEC07 : 0xEC08,
                0x2016 => opening ? 0xEC09 : 0xEC0A, // \| / norm bars
                0x230A => 0xF8F0, // \lfloor
                0x230B => 0xF8FB, // \rfloor
                0x2308 => 0xF8EE, // \lceil
                0x2309 => 0xF8F9, // \rceil
                _ => scalar,
            };
            EmitScalar(mtCode, TypefaceFence, output, includeEncoded8: false);
        }
    }


    private static string NormalizeFence(string value) => value switch
    {
        "." => string.Empty,
        "〈" or "〈" or "⟨" => "⟨",
        "〉" or "〉" or "⟩" => "⟩",
        _ => value,
    };


    private static byte? SelectFenceTemplate(string open, string close)
    {
        var probe = !string.IsNullOrEmpty(open) ? open : close;
        if ((open is "⟨" or "〈" || string.IsNullOrEmpty(open))
            && (close is "⟩" or "〉" || string.IsNullOrEmpty(close))
            && probe is "⟨" or "〈" or "⟩" or "〉") return TemplateAngle;
        if ((open == "(" || string.IsNullOrEmpty(open))
            && (close == ")" || string.IsNullOrEmpty(close))
            && probe is "(" or ")") return TemplateParen;
        if ((open == "[" || string.IsNullOrEmpty(open))
            && (close == "]" || string.IsNullOrEmpty(close))
            && probe is "[" or "]") return TemplateBracket;
        if ((open == "{" || string.IsNullOrEmpty(open))
            && (close == "}" || string.IsNullOrEmpty(close))
            && probe is "{" or "}") return TemplateBrace;
        if ((open == "|" || string.IsNullOrEmpty(open))
            && (close == "|" || string.IsNullOrEmpty(close))
            && probe == "|") return TemplateBar;
        if ((open is "‖" or "||" || string.IsNullOrEmpty(open))
            && (close is "‖" or "||" || string.IsNullOrEmpty(close))
            && probe is "‖" or "||") return TemplateDoubleBar;
        if ((open == "⌊" || string.IsNullOrEmpty(open))
            && (close == "⌋" || string.IsNullOrEmpty(close))
            && probe is "⌊" or "⌋") return TemplateFloor;
        if ((open == "⌈" || string.IsNullOrEmpty(open))
            && (close == "⌉" || string.IsNullOrEmpty(close))
            && probe is "⌈" or "⌉") return TemplateCeiling;
        return null;
    }


    private static void EmitLine(XElement element, List<byte> output)
    {
        output.AddRange(new byte[] { RecordLine, 0 });
        EmitNode(element, output);
        output.Add(RecordEnd);
    }


    private static void EmitLineContents(IEnumerable<XNode> nodes, List<byte> output)
    {
        output.AddRange(new byte[] { RecordLine, 0 });
        foreach (var node in nodes) EmitNode(node, output);
        output.Add(RecordEnd);
    }

}
