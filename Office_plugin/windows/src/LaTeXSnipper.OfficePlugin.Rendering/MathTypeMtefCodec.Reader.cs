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

    private sealed partial class MtefStructureReader
    {
        private sealed class FontDefinition
        {
            public int EncodingIndex { get; set; }
            public string Name { get; set; } = string.Empty;
        }

        private sealed class FontStyleDefinition
        {
            public int FontDefinitionIndex { get; set; }
            public byte CharacterStyle { get; set; }
        }

        private readonly byte[] _data;
        private readonly List<string> _encodingDefinitions = new()
        {
            "MTCode",
            "Unknown",
            "Symbol",
            "MTExtra",
        };
        private readonly List<FontDefinition> _fontDefinitions = new();
        private readonly List<FontStyleDefinition> _fontStyleDefinitions = new();
        private int _position;

        internal MtefStructureReader(byte[] data, int position)
        {
            _data = data;
            ScanPrefixDefinitions(position);
            _position = position;
        }

        private void ScanPrefixDefinitions(int rootPosition)
        {
            var prefix = ReadPrefixLayout(_data);
            if (rootPosition != prefix.Root)
                throw new InvalidDataException("MTEF structural reader received a non-root offset.");
            foreach (var record in prefix.Records)
            {
                if (record.Type == RecordColorDef) { ReadColorDefinition(record.Start); continue; }
                if (record.Type is not RecordEncodingDef and not RecordFontDef and not RecordFontStyleDef)
                    continue;
                _position = record.Start;
                ReadDefinitionRecord();
                if (_position != record.End)
                    throw new InvalidDataException($"MTEF definition reader diverged at offset {record.Start}.");
            }
        }

        private static string ReadNullTerminatedString(byte[] data, ref int position)
        {
            var start = position;
            while (position < data.Length && data[position] != 0) position++;
            if (position >= data.Length)
                throw new EndOfStreamException("MTEF string is not null terminated.");
            var value = System.Text.Encoding.Default.GetString(data, start, position - start);
            position++;
            return value;
        }

        private void ReadDefinitionRecord()
        {
            var record = Peek();
            switch (record)
            {
                case RecordEncodingDef:
                    _position++;
                    _encodingDefinitions.Add(ReadNullTerminatedString(_data, ref _position));
                    return;
                case RecordFontDef:
                    _position++;
                    _fontDefinitions.Add(new FontDefinition
                    {
                        EncodingIndex = ReadUnsigned(_data, ref _position),
                        Name = ReadNullTerminatedString(_data, ref _position),
                    });
                    return;
                case RecordFontStyleDef:
                    _position++;
                    _fontStyleDefinitions.Add(new FontStyleDefinition
                    {
                        FontDefinitionIndex = ReadUnsigned(_data, ref _position),
                        CharacterStyle = ReadByte(),
                    });
                    return;
                default:
                    throw new InvalidDataException(
                        $"MTEF record {record} is not a font/encoding definition.");
            }
        }

        internal IEnumerable<XNode> ReadRoot()
        {
            SkipFormattingRecords();
            if (Peek() == RecordLine)
                return ReadLine().Nodes().ToArray();
            if (Peek() == RecordPile)
                return new XNode[] { ReadPile() };
            if (Peek() == RecordMatrix)
                return new XNode[] { ReadMatrix() };
            throw new InvalidDataException(
                $"Unsupported MathType root record {Peek()} at offset {_position}.");
        }

        internal bool HasOnlyEquationEndRemaining()
        {
            SkipFormattingRecords();
            return _position == _data.Length - 1
                && Peek() == RecordEnd;
        }

        private XElement ReadLine()
        {
            Expect(RecordLine);
            var options = ReadByte();
            SkipNudge(options);
            if ((options & 0x04) != 0) Skip(2);
            if ((options & 0x02) != 0) SkipRuler();
            var row = new XElement("mrow");
            if ((options & LineNull) != 0) return row;
            ReadObjectList(row);
            return row;
        }

        private XElement ReadPile()
        {
            Expect(RecordPile);
            var options = ReadByte();
            SkipNudge(options);
            Skip(2); // horizontal and vertical alignment
            var rulerStops = (options & 0x02) != 0
                ? ReadRulerOffsets()
                : Array.Empty<int>();
            var table = new XElement("mtable");
            var hasAlignmentTabs = false;
            while (true)
            {
                SkipFormattingRecords();
                if (Peek() == RecordEnd)
                {
                    _position++;
                    break;
                }
                var line = ReadLine();
                var lineNodes = line.Nodes().ToArray();
                if (lineNodes.OfType<XElement>().Any(IsMtefAlignmentPoint)
                    && TryBuildAlignmentSymbolRow(lineNodes, out var alignedRow))
                {
                    hasAlignmentTabs = true;
                    table.Add(alignedRow);
                    continue;
                }

                var row = new XElement("mtr");
                var cell = new XElement("mtd");
                foreach (var node in lineNodes)
                {
                    if (node is XElement marker && IsMtefAlignmentTab(marker))
                    {
                        hasAlignmentTabs = true;
                        marker.Remove();
                        row.Add(cell);
                        cell = new XElement("mtd");
                        continue;
                    }
                    node.Remove();
                    cell.Add(node);
                }
                row.Add(cell);
                table.Add(row);
            }

            if (hasAlignmentTabs)
            {
                // MathType's native multi-point aligned equations are PILE rows
                // separated by fnMARKER/U+0009 tab characters. Reconstruct the
                // alternating right/left MathJax table shape so strict MTEF
                // round-trip validation and MathML->LaTeX recovery preserve every
                // `&`, including empty cells introduced by `&&`.
                table.SetAttributeValue("data-mtef-tabs", "true");
                var columnCount = table.Elements()
                    .Select(row => row.Elements().Count(cellNode => cellNode.Name.LocalName == "mtd"))
                    .DefaultIfEmpty(0)
                    .Max();
                if (columnCount > 0)
                {
                    table.SetAttributeValue(
                        "columnalign",
                        string.Join(" ", Enumerable.Range(0, columnCount)
                            .Select(column => (column & 1) == 0 ? "right" : "left")));
                    if (rulerStops.Length == columnCount / 2)
                    {
                        table.SetAttributeValue(
                            MtefRulerStopsAttribute,
                            string.Join(",", rulerStops.Select(stop =>
                                stop.ToString(CultureInfo.InvariantCulture))));
                    }
                }
            }
            else
            {
                // Preserve the MTEF container kind. A two-row/one-column PILE
                // inside ordinary parentheses is MathType's native binomial
                // representation, while a MATRIX of the same shape is not.
                table.SetAttributeValue("data-mtef-pile", "true");
            }
            return table;
        }

        private static bool IsMtefAlignmentTab(XElement element) =>
            element.Name.LocalName == "mspace"
            && string.Equals(
                (string?)element.Attribute("data-mtef-tab"),
                "true",
                StringComparison.OrdinalIgnoreCase);

        private static bool IsMtefAlignmentPoint(XElement element) =>
            element.Name.LocalName == "mspace"
            && string.Equals(
                (string?)element.Attribute("data-mtef-align"),
                "true",
                StringComparison.OrdinalIgnoreCase);

        private static bool TryBuildAlignmentSymbolRow(
            XNode[] lineNodes,
            out XElement row)
        {
            row = new XElement("mtr");
            var groups = new List<List<XNode>>();
            var current = new List<XNode>();
            foreach (var node in lineNodes)
            {
                if (node is XElement marker && IsMtefAlignmentTab(marker))
                {
                    // A LaTeXSnipper/MathType aligned PILE starts each tab group with
                    // a TAB. Do not materialize the leading empty group as a cell.
                    if (current.Count > 0) groups.Add(current);
                    current = new List<XNode>();
                    continue;
                }
                current.Add(node);
            }
            if (current.Count > 0) groups.Add(current);
            if (groups.Count == 0) return false;

            foreach (var group in groups)
            {
                var alignmentIndexes = group
                    .Select((node, index) => new { Node = node, Index = index })
                    .Where(item => item.Node is XElement element && IsMtefAlignmentPoint(element))
                    .Select(item => item.Index)
                    .ToArray();
                if (alignmentIndexes.Length != 1)
                {
                    row = new XElement("mtr");
                    return false;
                }

                var alignmentIndex = alignmentIndexes[0];
                row.Add(new XElement(
                    "mtd",
                    group.Take(alignmentIndex).Select(CloneNode)));
                row.Add(new XElement(
                    "mtd",
                    group.Skip(alignmentIndex + 1).Select(CloneNode)));
            }
            return row.Elements().Any();
        }

        private XElement ReadMatrix()
        {
            Expect(RecordMatrix);
            var options = ReadByte();
            SkipNudge(options);
            Skip(3); // vertical alignment, horizontal and vertical cell justification
            var rowCount = ReadByte();
            var columnCount = ReadByte();
            if (rowCount == 0 || columnCount == 0)
                throw new InvalidDataException("MathType MATRIX has zero rows or columns.");
            Skip(PartitionByteCount(rowCount + 1));
            Skip(PartitionByteCount(columnCount + 1));
            var table = new XElement("mtable");
            for (var rowIndex = 0; rowIndex < rowCount; rowIndex++)
            {
                var row = new XElement("mtr");
                for (var columnIndex = 0; columnIndex < columnCount; columnIndex++)
                {
                    SkipFormattingRecords();
                    if (Peek() != RecordLine)
                        throw new InvalidDataException(
                            $"MathType MATRIX cell {rowIndex},{columnIndex} is not a LINE record.");
                    var cell = ReadLine();
                    row.Add(new XElement("mtd", cell.Nodes()));
                }
                table.Add(row);
            }
            SkipFormattingRecords();
            if (Peek() != RecordEnd)
                throw new InvalidDataException(
                    $"MathType MATRIX has no END record at offset {_position}.");
            _position++;
            return table;
        }

        private void ReadObjectList(XElement row)
        {
            while (true)
            {
                SkipFormattingRecords();
                var record = Peek();
                if (record == RecordEnd)
                {
                    _position++;
                    return;
                }
                if (record == RecordChar)
                {
                    var character = ReadCharacter();
                    ApplyCurrentColor(character);
                    ApplyCurrentSize(character);
                    AppendNode(row, character);
                    continue;
                }
                if (record == RecordTemplate)
                {
                    int templateColor = _currentColor;
                    var template = ReadTemplate();
                    if (template.Node != null) ApplyColor(template.Node, templateColor);
                    if (template.ScriptKind != 0)
                    {
                        var baseNode = row.Nodes().LastOrDefault();
                        if (baseNode is null)
                            throw new InvalidDataException(
                                $"MathType script template at offset {_position} has no preceding base object.");
                        baseNode.Remove();
                        row.Add(BuildScriptNode(baseNode, template));
                    }
                    else if (template.Node is not null)
                    {
                        row.Add(template.Node);
                    }
                    continue;
                }
                if (record == RecordLine)
                {
                    row.Add(ReadLine());
                    continue;
                }
                if (record == RecordPile)
                {
                    row.Add(ReadPile());
                    continue;
                }
                if (record == RecordMatrix)
                {
                    row.Add(ReadMatrix());
                    continue;
                }
                if (record >= 100)
                {
                    SkipFutureRecord();
                    continue;
                }
                throw new InvalidDataException(
                    $"Unsupported MathType MTEF record {record} at offset {_position}.");
            }
        }

        private XElement ReadCharacter()
        {
            Expect(RecordChar);
            var options = ReadByte();
            SkipNudge(options);
            var typeface = ReadSigned();
            int scalar = -1;
            if ((options & 0x20) == 0)
            {
                Require(_data, _position, 2);
                scalar = _data[_position] | (_data[_position + 1] << 8);
                _position += 2;
            }
            int encoded = -1;
            if ((options & CharEncoded8) != 0) encoded = ReadByte();
            if ((options & 0x10) != 0)
            {
                Require(_data, _position, 2);
                encoded = _data[_position] | (_data[_position + 1] << 8);
                _position += 2;
            }
            if (scalar < 0) scalar = encoded;
            if (scalar < 0 || scalar > char.MaxValue)
                scalar = '?';

            var embellishments = (options & CharHasEmbellishment) != 0
                ? ReadEmbellishmentList()
                : Array.Empty<byte>();

            var text = ((char)scalar).ToString();
            string? explicitMathVariant = null;
            if (typeface < 0)
            {
                explicitMathVariant = ResolveExplicitMathVariant(
                    -typeface,
                    scalar,
                    encoded,
                    out var explicitText);
                if (!string.IsNullOrEmpty(explicitText)) text = explicitText;
                if (TryEuclidMathOneOperatorEncoded8(scalar, out _)
                    || TryEuclidMathTwoOperatorEncoded8(scalar, out _))
                {
                    // For explicit Euclid operator glyphs the encoded8 byte is
                    // only a font position. Normally MTCode remains the semantic
                    // Unicode character; MathType's preceq/succeq pair is the
                    // exception, using private MTCode E938/E939 internally.
                    text = scalar switch
                    {
                        0xE938 => "⪯",
                        0xE939 => "⪰",
                        _ => ((char)scalar).ToString(),
                    };
                    explicitMathVariant = null;
                }
                else if (scalar == 0xED02 && encoded == 0xF8)
                {
                    // Genuine MathType 7 dotless-j: Euclid Math One PUA MTCode
                    // 0xED02 / position 0xF8. Recover Unicode U+0237 so the
                    // public MathML/LaTeX layer sees \\jmath, not script PUA text.
                    text = "ȷ";
                    explicitMathVariant = null;
                }
            }

            XElement token;
            if (typeface == TypefaceMathTypeSpecial12 && scalar is >= 0x2E80 and <= 0x9FFF)
                token = new XElement("mtext", text);
            else if (typeface < 0)
            {
                if (TryEuclidMathOneOperatorEncoded8(scalar, out _)
                    || TryEuclidMathTwoOperatorEncoded8(scalar, out _))
                {
                    // Several MathType relation/harpoon glyphs live in explicit
                    // Euclid Math One/Two styles. They remain mathematical
                    // operators even though their MTEF typeface is negative.
                    token = new XElement("mo", text);
                }
                else
                {
                    token = new XElement("mi", text);
                    if (!string.IsNullOrWhiteSpace(explicitMathVariant))
                        token.SetAttributeValue("mathvariant", explicitMathVariant);
                }
            }
            else if (typeface != TypefaceSymbol
                && TryNormalizeLetterlikeScalar(
                         scalar,
                         out var normalizedLetterlikeText,
                         out var normalizedLetterlikeVariant))
            {
                token = new XElement(
                    "mi",
                    new XAttribute("mathvariant", normalizedLetterlikeVariant),
                    normalizedLetterlikeText);
            }
            else if (typeface == TypefaceNumber)
                token = new XElement("mn", text);
            else if (typeface == TypefaceMarker && scalar == '\t')
                token = new XElement("mspace", new XAttribute("data-mtef-tab", "true"));
            else if (typeface == TypefaceMarker && scalar == MathTypeAlignmentMarkerMtCode)
                token = new XElement("mspace", new XAttribute("data-mtef-align", "true"));
            else if (typeface == TypefaceMathTypeSpecial12 && scalar == 0x220B)
                token = new XElement("mo", "∋");
            else if (typeface == TypefaceMathTypeSpecial12 && scalar == 0x25EF)
                token = new XElement("mo", "◯");
            else if (typeface == TypefaceMathTypeSpecial12 && scalar == 0x2661)
                token = new XElement("mo", "♡");
            else if (typeface == TypefaceMtExtra && scalar == 0xFFFD && encoded == 0x6E)
            {
                // MathType 7 uses this MT Extra position for the diamondsuit glyph.
                // Some unsupported TeX imports may also collapse to the same
                // persisted glyph; once that happens the original command is no
                // longer recoverable, so preserve the actual stored glyph.
                token = new XElement("mo", "♢");
            }
            else if (typeface == TypefaceMtExtra && scalar == 0x2210 && encoded == 0x43)
            {
                // MathType reuses U+2210 internally for ordinary TeX \\amalg.
                // The dedicated COPRODUCT template is what represents \\coprod;
                // a plain MT Extra CHAR at position 0x43 is amalg instead.
                token = new XElement("mo", "⨿");
            }
            else if (typeface == TypefaceSpace)
                token = new XElement("mspace", new XAttribute("width", "0.2em"));
            else if (typeface == TypefaceSymbol
                && scalar is 0x2135 or 0x2118 or 0x211C or 0x2111)
            {
                // MathType stores \aleph, \wp, \Re and \Im in Symbol typeface,
                // but exports them as identifier tokens rather than operators.
                // Preserve that token class without misclassifying ℜ/ℑ as
                // Fraktur solely from their Unicode letterlike code points.
                token = new XElement("mi", text);
            }
            else if (typeface == TypefaceSymbol)
                token = new XElement("mo", text);
            else if (typeface == TypefaceText)
                token = IsMathematicalSymbolScalar(scalar)
                    ? new XElement("mo", text)
                    : new XElement("mtext", text);
            else if (typeface == TypefaceFunction)
            {
                if (text.All(char.IsLetter))
                {
                    token = new XElement(
                        "mi",
                        new XAttribute("mathvariant", "normal"),
                        new XAttribute("data-mtef-run", "function"),
                        text);
                }
                else if (text.All(char.IsWhiteSpace))
                    token = new XElement("mspace", new XAttribute("width", "0.2em"));
                else
                    token = new XElement("mo", text);
            }
            else if (typeface == TypefaceVector)
                token = new XElement("mi", new XAttribute("mathvariant", "bold"), text);
            else
                token = new XElement("mi", text);

            // A CHAR contains a fixed glyph; actual scalable delimiters are
            // decoded by the TMPL path as mfenced. Preserve that distinction for
            // nested bra/ket characters inside a scalable absolute-value pair.
            if (token.Name.LocalName == "mo"
                && NormalizeFence(text) is "(" or ")" or "[" or "]" or "{" or "}"
                    or "⟨" or "⟩" or "⌈" or "⌉" or "⌊" or "⌋" or "|" or "‖")
            {
                token.SetAttributeValue("fence", "false");
                token.SetAttributeValue("stretchy", "false");
            }

            // EMBELL is not restricted to over-accents: native MathType stores
            // primes here, including on characters nested inside another script.
            // Apply accents to the character, then attach all right/left primes
            // at that character's script level. Never silently discard a record.
            var rightPrimes = new StringBuilder();
            var leftPrimes = new StringBuilder();
            foreach (var embellishment in embellishments)
            {
                switch (embellishment)
                {
                    case EmbellPrime: rightPrimes.Append('′'); continue;
                    case EmbellDoublePrime: rightPrimes.Append('″'); continue;
                    case EmbellTriplePrime: rightPrimes.Append('‴'); continue;
                    case EmbellBackPrime: leftPrimes.Append('‵'); continue;
                }
                var mark = EmbellishmentMark(embellishment);
                if (mark.Length == 0)
                    throw new InvalidDataException(
                        $"Unsupported MathType character embellishment {embellishment}; conversion stopped to avoid losing a symbol.");
                token = new XElement(
                    "mover",
                    new XAttribute("accent", "true"),
                    token,
                    new XElement("mo", mark));
            }
            if (leftPrimes.Length > 0)
            {
                token = new XElement("mmultiscripts", token,
                    new XElement("none"),
                    rightPrimes.Length > 0 ? new XElement("mo", rightPrimes.ToString()) : new XElement("none"),
                    new XElement("mprescripts"), new XElement("none"),
                    new XElement("mo", leftPrimes.ToString()));
            }
            else if (rightPrimes.Length > 0)
                token = new XElement("msup", token, new XElement("mo", rightPrimes.ToString()));
            return token;
        }

        private string? ResolveExplicitMathVariant(
            int styleIndex,
            int scalar,
            int encoded,
            out string text)
        {
            text = encoded is >= 0x21 and <= 0x7E
                ? ((char)encoded).ToString()
                : ((char)scalar).ToString();
            string? fontName = null;
            byte characterStyle = 0;
            if (styleIndex > 0 && styleIndex <= _fontStyleDefinitions.Count)
            {
                var style = _fontStyleDefinitions[styleIndex - 1];
                characterStyle = style.CharacterStyle;
                if (style.FontDefinitionIndex > 0
                    && style.FontDefinitionIndex <= _fontDefinitions.Count)
                    fontName = _fontDefinitions[style.FontDefinitionIndex - 1].Name;
            }

            var font = fontName ?? string.Empty;
            if (font.IndexOf("Euclid Math One", StringComparison.OrdinalIgnoreCase) >= 0
                && TryEuclidMathOneGreekVariantEncoded8(scalar, out var expectedGreekEncoded8)
                && encoded == expectedGreekEncoded8)
            {
                // MathType uses Euclid Math One for several Greek variants
                // (\epsilon, \varrho, \varkappa). They remain ordinary Greek
                // identifiers, not \mathcal/script characters.
                text = ((char)scalar).ToString();
                return null;
            }
            if (font.IndexOf("Euclid Math One", StringComparison.OrdinalIgnoreCase) >= 0)
                return characterStyle is 1 or 3 ? "bold-script" : "script";
            if (font.IndexOf("Euclid Math Two", StringComparison.OrdinalIgnoreCase) >= 0)
                return "double-struck";
            if (font.IndexOf("Fraktur", StringComparison.OrdinalIgnoreCase) >= 0)
                return characterStyle is 1 or 3 ? "bold-fraktur" : "fraktur";
            if (string.Equals(font, "Courier New", StringComparison.OrdinalIgnoreCase))
                return "monospace";
            if (string.Equals(font, "Arial", StringComparison.OrdinalIgnoreCase))
                return characterStyle switch
                {
                    1 => "bold-sans-serif",
                    2 => "sans-serif-italic",
                    3 => "sans-serif-bold-italic",
                    _ => "sans-serif",
                };

            if (TryNormalizeLetterlikeScalar(scalar, out var letterlikeText, out var letterlikeVariant))
            {
                text = letterlikeText;
                return letterlikeVariant;
            }

            return characterStyle switch
            {
                1 => "bold",
                2 => "italic",
                3 => "bold-italic",
                _ => "normal",
            };
        }

        private static bool TryNormalizeLetterlikeScalar(
            int scalar,
            out string text,
            out string mathVariant)
        {
            text = string.Empty;
            mathVariant = string.Empty;
            switch (scalar)
            {
                case 0x2102: text = "C"; mathVariant = "double-struck"; return true;
                case 0x210B: text = "H"; mathVariant = "script"; return true;
                case 0x210C: text = "H"; mathVariant = "fraktur"; return true;
                case 0x210D: text = "H"; mathVariant = "double-struck"; return true;
                case 0x2110: text = "I"; mathVariant = "script"; return true;
                case 0x2111: text = "I"; mathVariant = "fraktur"; return true;
                case 0x2112: text = "L"; mathVariant = "script"; return true;
                case 0x2115: text = "N"; mathVariant = "double-struck"; return true;
                case 0x2119: text = "P"; mathVariant = "double-struck"; return true;
                case 0x211A: text = "Q"; mathVariant = "double-struck"; return true;
                case 0x211B: text = "R"; mathVariant = "script"; return true;
                case 0x211C: text = "R"; mathVariant = "fraktur"; return true;
                case 0x211D: text = "R"; mathVariant = "double-struck"; return true;
                case 0x2124: text = "Z"; mathVariant = "double-struck"; return true;
                case 0x2128: text = "Z"; mathVariant = "fraktur"; return true;
                case 0x212C: text = "B"; mathVariant = "script"; return true;
                case 0x212D: text = "C"; mathVariant = "fraktur"; return true;
                case 0x212F: text = "e"; mathVariant = "script"; return true;
                case 0x2130: text = "E"; mathVariant = "script"; return true;
                case 0x2131: text = "F"; mathVariant = "script"; return true;
                case 0x2133: text = "M"; mathVariant = "script"; return true;
                case 0x2134: text = "o"; mathVariant = "script"; return true;
                default: return false;
            }
        }

        private static void AppendNode(XElement row, XElement node)
        {
            var previous = row.Elements().LastOrDefault();
            if (node.Name.LocalName == "mtext" && !node.HasElements)
            {
                // MathType stores spaces inside an ordinary text run as its
                // Space typeface, so ReadCharacter() necessarily materializes
                // them first as <mspace width="0.2em">. Rejoin only a run of
                // those exact spaces when it is bounded by mtext on both sides.
                // This preserves `\text{Double word product}` as textual content
                // without treating general mathematical spacing as text.
                var trailingTextSpaces = row.Elements()
                    .Reverse()
                    .TakeWhile(IsMtefTextSpace)
                    .ToArray();
                if (trailingTextSpaces.Length > 0)
                {
                    var precedingText = trailingTextSpaces[trailingTextSpaces.Length - 1].PreviousNode as XElement;
                    if (precedingText is not null
                        && precedingText.Name.LocalName == "mtext"
                        && !precedingText.HasElements)
                    {
                        precedingText.Value += new string(' ', trailingTextSpaces.Length) + node.Value;
                        foreach (var space in trailingTextSpaces) space.Remove();
                        return;
                    }
                }
            }

            var mergeableRun = node.Name.LocalName is "mn" or "mtext"
                || node.Name.LocalName == "mi"
                    && string.Equals(
                        (string?)node.Attribute("data-mtef-run"),
                        "function",
                        StringComparison.Ordinal)
                    && string.Equals(
                        (string?)previous?.Attribute("data-mtef-run"),
                        "function",
                        StringComparison.Ordinal);
            if (previous is not null
                && mergeableRun
                && previous.Name.LocalName == node.Name.LocalName
                && (string?)previous.Attribute("mathcolor") == (string?)node.Attribute("mathcolor")
                && (string?)previous.Attribute("mathsize") == (string?)node.Attribute("mathsize")
                && string.Equals(
                    (string?)previous.Attribute("mathvariant") ?? string.Empty,
                    (string?)node.Attribute("mathvariant") ?? string.Empty,
                    StringComparison.OrdinalIgnoreCase)
                && !previous.HasElements
                && !node.HasElements)
            {
                previous.Value += node.Value;
                return;
            }
            row.Add(node);
        }

        private static bool IsMtefTextSpace(XElement element) =>
            element.Name.LocalName == "mspace"
            && string.Equals(
                (string?)element.Attribute("width"),
                "0.2em",
                StringComparison.OrdinalIgnoreCase)
            && !element.HasElements;

        private static string EmbellishmentMark(byte embellishment) => embellishment switch
        {
            EmbellDot => ".",
            EmbellDoubleDot => "¨",
            EmbellTilde => "~",
            EmbellHat => "^",
            EmbellRightArrow => "→",
            EmbellLeftArrow => "←",
            EmbellBothArrow => "↔",
            EmbellOverbar => "¯",
            _ => string.Empty,
        };

        private sealed class ParsedTemplate
        {
            internal byte ScriptKind { get; set; }
            internal bool ScriptPrecedes { get; set; }
            internal XElement? Node { get; set; }
            internal XElement? Subscript { get; set; }
            internal XElement? Superscript { get; set; }
        }

        private ParsedTemplate ReadTemplate()
        {
            Expect(RecordTemplate);
            var options = ReadByte();
            SkipNudge(options);
            var selector = ReadByte();
            var variationFirst = ReadByte();
            var variation = (variationFirst & 0x80) == 0
                ? variationFirst
                : (variationFirst & 0x7F) | (ReadByte() << 8);
            _ = ReadByte(); // template-specific options

            switch (selector)
            {
                case TemplateFraction:
                {
                    var numerator = ReadNextLineSlot();
                    var denominator = ReadNextLineSlot();
                    ConsumeTemplateEnd();
                    return new ParsedTemplate
                    {
                        Node = new XElement(
                            "mfrac",
                            CollapseRow(numerator),
                            CollapseRow(denominator)),
                    };
                }
                case TemplateRoot:
                {
                    var radicand = ReadNextLineSlot();
                    var index = ReadNextLineSlot();
                    ConsumeTemplateEnd();
                    return new ParsedTemplate
                    {
                        Node = variation == 1 && index.HasElements
                            ? new XElement(
                                "mroot",
                                CollapseRow(radicand),
                                CollapseRow(index))
                            : new XElement("msqrt", radicand.Nodes()),
                    };
                }
                case TemplateSub:
                case TemplateSup:
                case TemplateSubSup:
                {
                    var subscript = ReadNextLineSlot();
                    var superscript = ReadNextLineSlot();
                    ConsumeTemplateEnd();
                    return new ParsedTemplate
                    {
                        ScriptKind = selector,
                        ScriptPrecedes = (variation & 1) != 0,
                        Subscript = subscript,
                        Superscript = superscript,
                    };
                }
                case TemplateAngle:
                case TemplateParen:
                case TemplateBrace:
                case TemplateBracket:
                case TemplateBar:
                case TemplateDoubleBar:
                case TemplateFloor:
                case TemplateCeiling:
                {
                    var main = ReadNextLineSlot();
                    // MathType may include explicit left/right fence CHAR records.
                    // They are presentation metadata; consume all remaining
                    // subobjects until this template's END and reconstruct from
                    // selector/variation instead.
                    while (true)
                    {
                        SkipFormattingRecords();
                        if (Peek() == RecordEnd)
                        {
                            _position++;
                            break;
                        }
                        SkipOneObject();
                    }
                    var (open, close) = FenceCharacters(selector, variation);
                    return new ParsedTemplate
                    {
                        Node = new XElement(
                            "mfenced",
                            new XAttribute("open", open),
                            new XAttribute("close", close),
                            CollapseRow(main)),
                    };
                }
                case TemplateUnderbar:
                case TemplateOverbar:
                case TemplateArrow:
                case TemplateVector:
                case TemplateTilde:
                case TemplateHat:
                case TemplateArc:
                case TemplateStrike:
                case TemplateBox:
                {
                    var main = ReadNextLineSlot();
                    ConsumeRemainingTemplateObjects();
                    var body = CollapseRow(main);
                    XElement node;
                    if (selector == TemplateUnderbar)
                        node = new XElement("munder", body, new XElement("mo", "_"));
                    else if (selector == TemplateOverbar)
                        node = new XElement("mover", body, new XElement("mo", "¯"));
                    else if (selector is TemplateArrow or TemplateVector)
                    {
                        var arrow = (variation & 0x03) switch
                        {
                            1 => "←",
                            3 => "↔",
                            _ => "→",
                        };
                        node = new XElement("mover", body, new XElement("mo", arrow));
                    }
                    else if (selector == TemplateTilde)
                        node = new XElement("mover", body, new XElement("mo", "~"));
                    else if (selector == TemplateHat)
                        node = new XElement("mover", body, new XElement("mo", "^"));
                    else if (selector == TemplateArc)
                        node = new XElement("mover", body, new XElement("mo", "⌢"));
                    else if (selector == TemplateBox)
                        node = new XElement("menclose", new XAttribute("notation", "box"), body);
                    else
                    {
                        var strikeNotations = new List<string>();
                        if ((variation & 0x01) != 0) strikeNotations.Add("horizontalstrike");
                        if ((variation & 0x02) != 0) strikeNotations.Add("updiagonalstrike");
                        if ((variation & 0x04) != 0) strikeNotations.Add("downdiagonalstrike");
                        if (strikeNotations.Count == 0) strikeNotations.Add("horizontalstrike");
                        node = new XElement(
                            "menclose",
                            new XAttribute("notation", string.Join(" ", strikeNotations)),
                            body);
                    }
                    return new ParsedTemplate { Node = node };
                }
                case TemplateHorizontalBrace:
                case TemplateHorizontalBracket:
                {
                    var slots = ReadTemplateLineSlotsUntilEnd();
                    var main = slots.Count > 0
                        ? CollapseRow(slots[0])
                        : new XElement("mrow");
                    var annotation = slots.Count > 1 && slots[1].HasElements
                        ? CollapseRow(slots[1])
                        : null;
                    var top = (variation & 0x01) != 0;
                    var mark = selector == TemplateHorizontalBrace
                        ? (top ? "⏞" : "⏟")
                        : (top ? "⎴" : "⎵");
                    XNode decorated = top
                        ? new XElement("mover", main, new XElement("mo", mark))
                        : new XElement("munder", main, new XElement("mo", mark));
                    if (annotation is not null)
                        decorated = top
                            ? new XElement("mover", decorated, annotation)
                            : new XElement("munder", decorated, annotation);
                    return new ParsedTemplate { Node = (XElement)decorated };
                }
                case TemplateIntegral:
                case TemplateSum:
                case TemplateProduct:
                case TemplateCoproduct:
                case TemplateUnion:
                case TemplateIntersection:
                case 21: // integral-family variants in MathType's BigOp group
                case 22:
                    return ReadBigOperatorTemplate(selector, variation);
                case TemplateLimit:
                    return ReadLimitTemplate();
                default:
                    throw new InvalidDataException(
                        $"Unsupported MathType template selector {selector} at offset {_position}.");
            }
        }

        private ParsedTemplate ReadBigOperatorTemplate(byte selector, int variation)
        {
            var main = ReadNextLineSlot();
            // MathType 7's persisted BigOp objects are observed in Word as
            // main, lower, upper, operator. Keep the empirically verified order:
            // swapping these two slots makes i=1/n reopen with inverted limits.
            var lower = ReadNextLineSlot();
            var upper = ReadNextLineSlot();
            SkipFormattingRecords();
            XElement? serializedOperator = null;
            if (Peek() == RecordChar)
            {
                serializedOperator = ReadCharacter();
                while (serializedOperator.Name.LocalName == "mover")
                    serializedOperator = serializedOperator.Elements().FirstOrDefault()
                        ?? new XElement("mo", DefaultBigOperatorCharacter(selector));
            }
            ConsumeRemainingTemplateObjects();
            // MathType stores the large glyph in a font/MTCode-specific CHAR. For
            // the dedicated BigOp selectors the selector itself is the durable
            // semantic identity; using the decoded CHAR can leak a private glyph
            // or U+FFFD into LaTeXSnipper. Generic BigOp selectors still need the
            // serialized character because their selector does not name the op.
            var operatorNode = selector == TemplateIntegral
                ? new XElement("mo", IntegralOperatorCharacter(variation))
                : selector is >= TemplateSum and <= TemplateIntersection
                    ? new XElement("mo", DefaultBigOperatorCharacter(selector))
                    : serializedOperator ?? new XElement("mo", DefaultBigOperatorCharacter(selector));
            XNode decorated = DecorateWithLimits(operatorNode, lower, upper);
            var row = new XElement("mrow", decorated);
            foreach (var node in main.Nodes().ToArray())
            {
                node.Remove();
                row.Add(node);
            }
            return new ParsedTemplate { Node = row };
        }

        private ParsedTemplate ReadLimitTemplate()
        {
            var main = ReadNextLineSlot();
            var lower = ReadNextLineSlot();
            var upper = ReadNextLineSlot();
            ConsumeRemainingTemplateObjects();
            XNode baseNode = CollapseRow(main);
            return new ParsedTemplate
            {
                Node = (XElement)DecorateWithLimits(baseNode, lower, upper),
            };
        }

        private static XNode DecorateWithLimits(
            XNode baseNode,
            XElement lower,
            XElement upper)
        {
            var hasLower = lower.HasElements;
            var hasUpper = upper.HasElements;
            if (hasLower && hasUpper)
                return new XElement(
                    "msubsup",
                    baseNode,
                    CollapseRow(lower),
                    CollapseRow(upper));
            if (hasLower)
                return new XElement("msub", baseNode, CollapseRow(lower));
            if (hasUpper)
                return new XElement("msup", baseNode, CollapseRow(upper));
            return baseNode;
        }

        private static string IntegralOperatorCharacter(int variation) => (variation & 0x0F) switch
        {
            0x02 => "∬",
            0x03 => "∭",
            // MathType 7 persists the contour-integral BigOp as kind 5:
            // an MT Extra contour adornment followed by the ordinary integral.
            0x05 => "∮",
            0x08 => "∲",
            0x0C => "∳",
            _ => "∫",
        };

        private static string DefaultBigOperatorCharacter(byte selector) => selector switch
        {
            TemplateIntegral => "∫",
            TemplateSum => "∑",
            TemplateProduct => "∏",
            TemplateCoproduct => "∐",
            TemplateUnion => "⋃",
            TemplateIntersection => "⋂",
            21 => "∫",
            22 => "∫",
            _ => "∑",
        };

        private List<XElement> ReadTemplateLineSlotsUntilEnd()
        {
            var slots = new List<XElement>();
            while (true)
            {
                SkipFormattingRecords();
                if (Peek() == RecordEnd)
                {
                    _position++;
                    return slots;
                }
                if (Peek() == RecordLine)
                {
                    slots.Add(ReadLine());
                    continue;
                }
                SkipOneObject();
            }
        }

        private void ConsumeRemainingTemplateObjects()
        {
            while (true)
            {
                SkipFormattingRecords();
                if (Peek() == RecordEnd)
                {
                    _position++;
                    return;
                }
                SkipOneObject();
            }
        }

        private static XNode BuildScriptNode(XNode baseNode, ParsedTemplate template)
        {
            var sub = template.Subscript is null
                ? new XElement("mrow")
                : CollapseRow(template.Subscript);
            var sup = template.Superscript is null
                ? new XElement("mrow")
                : CollapseRow(template.Superscript);
            if (template.ScriptPrecedes)
                return new XElement("mmultiscripts", baseNode, new XElement("mprescripts"),
                    template.ScriptKind == TemplateSup ? new XElement("none") : sub,
                    template.ScriptKind == TemplateSub ? new XElement("none") : sup);
            if (template.ScriptKind == TemplateSub)
                return new XElement("msub", baseNode, sub);
            if (template.ScriptKind == TemplateSup)
                return new XElement("msup", baseNode, sup);
            return new XElement("msubsup", baseNode, sub, sup);
        }

        private static XNode CollapseRow(XElement row)
        {
            var nodes = row.Nodes().ToArray();
            if (nodes.Length == 1)
            {
                nodes[0].Remove();
                return nodes[0];
            }
            return new XElement("mrow", nodes);
        }

        private XElement ReadNextLineSlot()
        {
            SkipFormattingRecords();
            if (Peek() != RecordLine)
                throw new InvalidDataException(
                    $"Expected MathType template LINE slot at offset {_position}, actual={Peek()}.");
            return ReadLine();
        }

        private void ConsumeTemplateEnd()
        {
            SkipFormattingRecords();
            if (Peek() != RecordEnd)
                throw new InvalidDataException(
                    $"Expected MathType template END at offset {_position}, actual={Peek()}.");
            _position++;
        }

        private void SkipOneObject()
        {
            var record = Peek();
            switch (record)
            {
                case RecordChar:
                    _ = ReadCharacter();
                    return;
                case RecordLine:
                    _ = ReadLine();
                    return;
                case RecordTemplate:
                    _ = ReadTemplate();
                    return;
                case RecordPile:
                    _ = ReadPile();
                    return;
                case RecordMatrix:
                    _ = ReadMatrix();
                    return;
                default:
                    SkipFormattingRecords();
                    if (Peek() == record)
                        throw new InvalidDataException(
                            $"Cannot skip MathType MTEF record {record} at offset {_position}.");
                    return;
            }
        }

        private void SkipFormattingRecords()
        {
            while (_position < _data.Length)
            {
                var record = _data[_position];
                if (record >= RecordFull && record <= RecordSubSym)
                {
                    _position++;
                    _explicitSizePoints = null;
                    continue;
                }
                if (record == RecordSize)
                {
                    ReadSizeRecord();
                    continue;
                }
                if (record == 15)
                {
                    _position++;
                    _currentColor = ReadUnsigned(_data, ref _position);
                    continue;
                }
                if (record == RecordColorDef)
                {
                    ReadColorDefinition(_position);
                    continue;
                }
                if (record is RecordEncodingDef or RecordFontDef or RecordFontStyleDef)
                {
                    ReadDefinitionRecord();
                    continue;
                }
                if (record >= 100)
                {
                    SkipFutureRecord();
                    continue;
                }
                break;
            }
        }

        private void SkipFutureRecord()
        {
            _position++; // record type
            var length = ReadUnsigned(_data, ref _position);
            Skip(length);
        }

        private byte[] ReadEmbellishmentList()
        {
            var embellishments = new List<byte>();
            while (true)
            {
                var record = Peek();
                if (record == RecordEnd)
                {
                    _position++;
                    return embellishments.ToArray();
                }
                if (record != RecordEmbellishment)
                    throw new InvalidDataException(
                        $"Unexpected MTEF embellishment record {record} at offset {_position}.");
                _position++;
                var options = ReadByte();
                SkipNudge(options);
                embellishments.Add(ReadByte());
            }
        }

        private int[] ReadRulerOffsets()
        {
            // LP_RULER identifies the inline payload, which starts with its count.
            var count = ReadByte();
            var offsets = new int[count];
            for (var index = 0; index < count; index++)
            {
                _ = ReadByte(); // tab type: alignment symbol can override it
                var low = ReadByte();
                var high = ReadByte();
                offsets[index] = low | (high << 8);
            }
            return offsets;
        }

        private void SkipRuler() => _ = ReadRulerOffsets();

        private void SkipNudge(byte options)
        {
            if ((options & 0x08) == 0) return;
            var dx = ReadByte();
            var dy = ReadByte();
            if (dx == 128 && dy == 128) Skip(4);
        }

        private int ReadSigned()
        {
            var first = ReadByte();
            if (first != 0xFF) return first - 128;
            Require(_data, _position, 2);
            var raw = _data[_position] | (_data[_position + 1] << 8);
            _position += 2;
            return raw - 32768;
        }

        private byte ReadByte()
        {
            Require(_data, _position, 1);
            return _data[_position++];
        }

        private byte Peek()
        {
            Require(_data, _position, 1);
            return _data[_position];
        }

        private void Expect(byte expected)
        {
            var actual = ReadByte();
            if (actual != expected)
                throw new InvalidDataException(
                    $"Expected MTEF record {expected}, actual={actual} at offset {_position - 1}.");
        }

        private void Skip(int count)
        {
            Require(_data, _position, count);
            _position += count;
        }

        private static (string Open, string Close) FenceCharacters(byte selector, int variation)
        {
            var presentLeft = (variation & 0x01) != 0;
            var presentRight = (variation & 0x02) != 0;
            var pair = selector switch
            {
                TemplateAngle => ("⟨", "⟩"),
                TemplateParen => ("(", ")"),
                TemplateBrace => ("{", "}"),
                TemplateBracket => ("[", "]"),
                TemplateBar => ("|", "|"),
                TemplateDoubleBar => ("‖", "‖"),
                TemplateFloor => ("⌊", "⌋"),
                TemplateCeiling => ("⌈", "⌉"),
                _ => (string.Empty, string.Empty),
            };
            return (presentLeft ? pair.Item1 : string.Empty, presentRight ? pair.Item2 : string.Empty);
        }
    }


    private static void Require(byte[] data, int offset, int count)
    {
        if (offset < 0 || count < 0 || offset + count > data.Length)
            throw new EndOfStreamException(
                $"MTEF stream is truncated at offset {offset}, need {count} bytes.");
    }

}
