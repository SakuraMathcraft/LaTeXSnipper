using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Globalization;
using System.Text;
using System.Xml.Linq;

namespace LaTeXSnipper.OfficePlugin.Rendering;

/// <summary>
/// Dependency-free MTEF v5 structural codec for creating standalone native
/// equations and reading their current content without an equation server.
/// </summary>
internal static partial class MathTypeMtefCodec
{
    private const byte MtefVersion5 = 5;
    private const byte RecordEnd = 0;
    private const byte RecordLine = 1;
    private const byte RecordChar = 2;
    private const byte RecordTemplate = 3;
    private const byte RecordPile = 4;
    private const byte RecordMatrix = 5;
    private const byte RecordEmbellishment = 6;
    private const byte RecordFontStyleDef = 8;
    private const byte RecordSize = 9;
    private const byte RecordFull = 10;
    private const byte RecordSub = 11;
    private const byte RecordSym = 13;
    private const byte RecordSubSym = 14;
    private const byte RecordColor = 15;
    private const byte RecordColorDef = 16;
    private const byte RecordFontDef = 17;
    private const byte RecordEqnPrefs = 18;
    private const byte RecordEncodingDef = 19;

    private const byte LineNull = 0x01;
    private const byte CharHasEmbellishment = 0x01;
    private const byte CharFunctionStart = 0x02;
    private const byte CharEncoded8 = 0x04;

    private const byte TypefaceText = 1;
    private const byte TypefaceFunction = 2;
    private const byte TypefaceVariable = 3;
    private const byte TypefaceLowerGreek = 4;
    private const byte TypefaceUpperGreek = 5;
    private const byte TypefaceSymbol = 6;
    private const byte TypefaceVector = 7;
    private const byte TypefaceNumber = 8;
    private const byte TypefaceMtExtra = 11;
    // MathType 7 uses built-in typeface 12 for a small set of native glyphs
    // such as reverse membership (\\ni) and \\bigcirc. These are not Adobe
    // Symbol positions and carry no encoded8 byte.
    private const byte TypefaceMathTypeSpecial12 = 12;
    private const byte TypefaceMarker = 23;
    // MathType 7 persists expanding fence characters ((), [], {}, |, ...)
    // with typeface 22 and MTCode, not Symbol style. Using Symbol here makes
    // the same ASCII code point resolve to a different fence glyph.
    private const byte TypefaceFence = 22;
    private const byte TypefaceSpace = 24;

    private const int MathTypeAlignmentMarkerMtCode = 0xEF00;
    private const string MtefRulerStopsAttribute =
        "data-mtef-ruler-stops";

    private const byte TemplateAngle = 0;
    private const byte TemplateParen = 1;
    private const byte TemplateBrace = 2;
    private const byte TemplateBracket = 3;
    private const byte TemplateBar = 4;
    private const byte TemplateDoubleBar = 5;
    private const byte TemplateFloor = 6;
    private const byte TemplateCeiling = 7;
    private const byte TemplateRoot = 10;
    private const byte TemplateFraction = 11;
    private const byte TemplateUnderbar = 12;
    private const byte TemplateOverbar = 13;
    private const byte TemplateArrow = 14;
    private const byte TemplateIntegral = 15;
    private const byte TemplateSum = 16;
    private const byte TemplateProduct = 17;
    private const byte TemplateCoproduct = 18;
    private const byte TemplateUnion = 19;
    private const byte TemplateIntersection = 20;
    private const byte TemplateLimit = 23;
    private const byte TemplateHorizontalBrace = 24;
    private const byte TemplateHorizontalBracket = 25;
    private const byte TemplateSub = 27;
    private const byte TemplateSup = 28;
    private const byte TemplateSubSup = 29;
    private const byte TemplateVector = 31;
    private const byte TemplateTilde = 32;
    private const byte TemplateHat = 33;
    private const byte TemplateArc = 34;
    private const byte TemplateStrike = 36;
    private const byte TemplateBox = 37;

    private const byte EmbellDot = 2;
    private const byte EmbellDoubleDot = 3;
    private const byte EmbellPrime = 5;
    private const byte EmbellDoublePrime = 6;
    private const byte EmbellBackPrime = 7;
    private const byte EmbellTriplePrime = 18;
    private const byte EmbellTilde = 8;
    private const byte EmbellHat = 9;
    private const byte EmbellRightArrow = 11;
    private const byte EmbellLeftArrow = 12;
    private const byte EmbellBothArrow = 13;
    private const byte EmbellOverbar = 17;

    internal static string ReadEquationNativeMathMl(byte[] equationNative)
    {
        var mtef = ExtractNativeMtef(equationNative);
        return ReadMtefMathMl(mtef);
    }

    private static byte[] ExtractNativeMtef(byte[] equationNative)
    {
        if (equationNative is null || equationNative.Length < 40)
            throw new InvalidDataException("MathType Equation Native stream is too short.");
        var headerLength = BitConverter.ToUInt16(equationNative, 0);
        if (headerLength != 28 || headerLength >= equationNative.Length)
            throw new InvalidDataException(
                $"Unsupported MathType OLE native header length: {headerLength}.");
        var objectLength = checked((int)BitConverter.ToUInt32(equationNative, 8));
        if (objectLength <= 0 || headerLength + objectLength > equationNative.Length)
            throw new InvalidDataException(
                $"Invalid MathType OLE MTEF length: {objectLength}.");
        var mtef = new byte[objectLength];
        Buffer.BlockCopy(equationNative, headerLength, mtef, 0, objectLength);
        if (mtef[0] != MtefVersion5)
            throw new InvalidDataException(
                $"LaTeXSnipper currently reads MathType OLE directly for MTEF v5 only, actual={mtef[0]}.");

        return mtef;
    }

    private static string ReadMtefMathMl(byte[] mtef)
    {
        var structureOffset = FindRootStructureOffset(mtef);
        var isEmptyEquation =
            structureOffset == mtef.Length - 1
            && mtef[structureOffset] == RecordEnd;
        var reader = new MtefStructureReader(mtef, structureOffset);
        var content = isEmptyEquation ? Array.Empty<XNode>() : reader.ReadRoot();
        if (!isEmptyEquation && !reader.HasOnlyEquationEndRemaining())
            throw new InvalidDataException("MTEF has unexpected content after the root equation.");
        XNamespace mathMlNamespace = "http://www.w3.org/1998/Math/MathML";
        var math = new XElement(
            mathMlNamespace + "math",
            content);

        // MtefStructureReader deliberately builds compact XElement trees using
        // local names (mi/mo/mrow/...). Once those nodes are attached below a
        // namespaced <math>, LINQ to XML serializes them with xmlns="" unless we
        // promote their XName as well. That produced visually plausible MathML
        // which our LaTeX reader tolerated, but standards-based MathML->OMML XSLT
        // saw an empty equation. Normalize every parser-owned descendant into the
        // MathML namespace at the direct MTEF read boundary.
        foreach (var element in math.Descendants().ToArray())
        {
            if (element.Name.Namespace == XNamespace.None)
                element.Name = mathMlNamespace + element.Name.LocalName;
        }
        foreach (var marker in math.DescendantsAndSelf()
                     .Attributes("data-mtef-run")
                     .ToArray())
            marker.Remove();
        return new XDocument(math).ToString(SaveOptions.DisableFormatting);
    }

    private const string StandaloneMtefPrefixBase64 =
        "BQEABwhEU01UNwAAE1dpbkFsbEJhc2ljQ29kZVBhZ2VzABEFVGltZXMgTmV3IFJvbWFuABEDU3ltYm9sABEFQ291cmllciBOZXcAEQRNVCBFeHRyYQATV2luQWxsQ29kZVBhZ2VzABEGy87M5QASAAghL0WPRC9BUPQQD0dfQVDyHx5BUPQVD0EA9EX0JfSPQl9BAPQQD0NfQQD0j0X0Kl9I9I9BAPQQD0D0j0F/SPQQD0EqX0RfRfRfRfRfQQ8MAQABAAECAgICAAIAAQEBAAMAAQAEAAUACg==";

    private static readonly byte[] StandaloneEquationNativeHeader =
    {
        0x1C, 0x00,             // EQNOLEFILEHDR.cbHdr = 28
        0x00, 0x00, 0x02, 0x00, // Equation Native format version
        0x42, 0xC2,             // MathType native clipboard format used by DSMT7
        0x00, 0x00, 0x00, 0x00, // cbObject, filled below
        0x00, 0x00, 0x00, 0x00,
        0xFC, 0xDE, 0x56, 0x0A,
        0x2D, 0xDF, 0xD4, 0x00,
        0x0C, 0x00, 0x85, 0x09,
    };

    private static byte[] CreateEquationNative(
        string mathMl)
    {
        if (string.IsNullOrWhiteSpace(mathMl))
            throw new InvalidDataException("MathType creation requires MathML.");

        var prefix = Convert.FromBase64String(StandaloneMtefPrefixBase64);
        var seedMtef = new byte[prefix.Length + 4];
        Buffer.BlockCopy(prefix, 0, seedMtef, 0, prefix.Length);
        seedMtef[prefix.Length] = RecordLine;
        seedMtef[prefix.Length + 1] = 0;
        seedMtef[prefix.Length + 2] = RecordEnd;
        seedMtef[prefix.Length + 3] = RecordEnd;
        if (FindRootStructureOffset(seedMtef) != prefix.Length)
            throw new InvalidDataException(
                "LaTeXSnipper's standalone MathType MTEF prefix is internally inconsistent.");

        var document = XDocument.Parse(mathMl, LoadOptions.PreserveWhitespace);
        var math = document.Root?.DescendantsAndSelf()
            .FirstOrDefault(element => element.Name.LocalName == "math")
            ?? throw new InvalidDataException("MathML has no <math> root.");
        var generated = BuildRootStructure(math, seedMtef, out var prefixDefinitions);
        var mtef = AssembleRewrittenMtef(
            seedMtef,
            prefix.Length,
            prefixDefinitions,
            generated);

        var equationNative = new byte[StandaloneEquationNativeHeader.Length + mtef.Length];
        Buffer.BlockCopy(
            StandaloneEquationNativeHeader,
            0,
            equationNative,
            0,
            StandaloneEquationNativeHeader.Length);
        Buffer.BlockCopy(
            BitConverter.GetBytes((uint)mtef.Length),
            0,
            equationNative,
            8,
            sizeof(uint));
        Buffer.BlockCopy(
            mtef,
            0,
            equationNative,
            StandaloneEquationNativeHeader.Length,
            mtef.Length);

        return equationNative;
    }

    private static int FindRootStructureOffset(byte[] mtef)
        => ReadPrefixLayout(mtef).Root;

    private sealed class MtefPrefixLayout
    {
        internal MtefPrefixLayout(int root, int preferences,
            IReadOnlyList<(byte Type, int Start, int End)> records)
        { Root = root; Preferences = preferences; Records = records; }
        internal int Root { get; }
        internal int Preferences { get; }
        internal IReadOnlyList<(byte Type, int Start, int End)> Records { get; }
    }

    // The sole prefix boundary parser. Consumers inspect its typed record spans;
    // they must not independently guess where preferences, fonts, sizes or the
    // root begin. This also preserves unknown length-delimited vendor records.
    private static MtefPrefixLayout ReadPrefixLayout(byte[] mtef)
    {
        if (mtef is null || mtef.Length < 16 || mtef[0] != MtefVersion5)
            throw new InvalidDataException("Invalid or unsupported MTEF stream.");
        var position = FindEquationOptionsOffset(mtef) + 1;
        var sawPreferences = false;
        var preferencesOffset = -1;
        var sawInitialSize = false;
        var records = new List<(byte Type, int Start, int End)>();
        while (position < mtef.Length)
        {
            var recordStart = position;
            var record = mtef[position];
            switch (record)
            {
                case RecordEncodingDef:
                    position = SkipNullTerminated(mtef, position + 1);
                    break;
                case RecordFontDef:
                    position++;
                    _ = ReadUnsigned(mtef, ref position);
                    position = SkipNullTerminated(mtef, position);
                    break;
                case RecordFontStyleDef:
                    position++;
                    _ = ReadUnsigned(mtef, ref position);
                    Require(mtef, position, 1);
                    position++;
                    break;
                case RecordColorDef:
                    position = SkipColorDefinition(mtef, position);
                    break;
                case RecordEqnPrefs:
                    preferencesOffset = position;
                    position = SkipEquationPreferences(mtef, position);
                    sawPreferences = true;
                    break;
                case >= 100:
                    // MTEF v5 explicitly reserves record ids >= 100 for forward
                    // compatible extensions. MathType versions are free to emit
                    // them before the root; readers must skip the length-prefixed
                    // payload instead of treating the record as the initial SIZE.
                    position = SkipFutureRecord(mtef, position);
                    break;
                default:
                    if (!sawPreferences)
                        throw new InvalidDataException(
                            $"Unexpected MTEF record {record} before equation preferences at offset {position}.");
                    if (record is RecordLine or RecordPile or RecordMatrix)
                    {
                        if (!sawInitialSize)
                            System.Diagnostics.Trace.WriteLine(
                                $"mathtype-mtef-root-without-initial-size offset={position} record={record}");
                        return new MtefPrefixLayout(position, preferencesOffset, records);
                    }
                    if (record == RecordSize
                        || record >= RecordFull && record <= RecordSubSym)
                    {
                        // The published layout contains one initial size record,
                        // but accepting repeated size changes here is harmless and
                        // makes the reader tolerant of vendor/version prefixes while
                        // keeping all of them in the immutable source prefix.
                        position = SkipInitialSizeRecord(mtef, position);
                        sawInitialSize = true;
                        break;
                    }
                    if (record == RecordColor)
                    {
                        position++;
                        _ = ReadUnsigned(mtef, ref position);
                        break;
                    }
                    // Never search arbitrary preference/extension bytes for a
                    // plausible LINE. A malformed boundary must fail before any
                    // Word mutation, not silently adopt a nested sub-expression.
                    // A genuine empty MathType equation is encoded as the normal
                    // prefix/initial-size state followed directly by the final
                    // equation END. MathType 7.8.x therefore legitimately has a
                    // zero at the same offset where non-empty DSMT7 equations put
                    // their root LINE. Treat only the terminal END as empty; any
                    // other zero remains a hard parse failure.
                    if (record == RecordEnd && position == mtef.Length - 1)
                    {
                        System.Diagnostics.Trace.WriteLine(
                            $"mathtype-mtef-empty-equation endOffset={position}");
                        return new MtefPrefixLayout(position, preferencesOffset, records);
                    }
                    throw new InvalidDataException(
                        $"Unsupported MathType root record {record} at offset {position}.");
            }
            if (position <= recordStart || position > mtef.Length)
                throw new InvalidDataException($"Invalid MTEF prefix extent at {recordStart}.");
            records.Add((record, recordStart, position));
        }
        throw new InvalidDataException("MTEF has no root equation structure.");
    }

    private static int FindEquationOptionsOffset(byte[] mtef)
    {
        Require(mtef, 0, 6);
        var position = 5; // version/platform/product/version/subversion
        position = SkipNullTerminated(mtef, position);
        Require(mtef, position, 1);
        return position;
    }

    private static int SkipEquationPreferences(byte[] data, int position)
    {
        Require(data, position, 2);
        position += 2; // record type + options
        position = SkipDimensionArray(data, position);
        position = SkipDimensionArray(data, position);
        Require(data, position, 1);
        var styleCount = data[position++];
        for (var index = 0; index < styleCount; index++)
        {
            var fontIndex = ReadUnsigned(data, ref position);
            if (fontIndex != 0)
            {
                Require(data, position, 1);
                position++; // character style
            }
        }
        return position;
    }

    private static int SkipDimensionArray(byte[] data, int position)
    {
        Require(data, position, 1);
        var count = data[position++];
        var nibbleIndex = 0;
        byte ReadNibble()
        {
            Require(data, position, 1);
            var value = nibbleIndex == 0
                ? (byte)(data[position] >> 4)
                : (byte)(data[position] & 0x0F);
            if (nibbleIndex == 0) nibbleIndex = 1;
            else
            {
                nibbleIndex = 0;
                position++;
            }
            return value;
        }

        for (var dimension = 0; dimension < count; dimension++)
        {
            _ = ReadNibble(); // units
            while (ReadNibble() != 0x0F) { }
        }
        if (nibbleIndex != 0) position++; // padded low nibble
        return position;
    }

    private static int SkipColorDefinition(byte[] data, int position)
    {
        Require(data, position, 2);
        var options = data[position + 1];
        position += 2;
        var cmyk = (options & 0x01) != 0;
        var named = (options & 0x04) != 0;
        Require(data, position, cmyk ? 8 : 6);
        position += cmyk ? 8 : 6;
        if (named) position = SkipNullTerminated(data, position);
        return position;
    }

    private static int SkipFutureRecord(byte[] data, int position)
    {
        Require(data, position, 1);
        if (data[position] < 100)
            throw new InvalidDataException(
                $"MTEF record at offset {position} is not a future-extension record.");
        position++;
        var length = ReadUnsigned(data, ref position);
        Require(data, position, length);
        return position + length;
    }

    private static int SkipInitialSizeRecord(byte[] data, int position)
    {
        Require(data, position, 1);
        var record = data[position];
        if (record >= RecordFull && record <= RecordSubSym)
            return position + 1;
        if (record != RecordSize)
            throw new InvalidDataException(
                $"Expected initial MTEF size record at offset {position}, actual={record}.");
        Require(data, position, 2);
        var form = data[position + 1];
        if (form == 100 || form == 101)
        {
            Require(data, position, form == 100 ? 5 : 4);
            return position + (form == 100 ? 5 : 4);
        }
        Require(data, position, 3);
        return position + 3;
    }

    private static int SkipNullTerminated(byte[] data, int position)
    {
        while (position < data.Length && data[position] != 0) position++;
        if (position >= data.Length)
            throw new EndOfStreamException("MTEF null-terminated field is truncated.");
        return position + 1;
    }

    private static int ReadUnsigned(byte[] data, ref int position)
    {
        Require(data, position, 1);
        var value = data[position++];
        if (value != 0xFF) return value;
        Require(data, position, 2);
        var expanded = data[position] | (data[position + 1] << 8);
        position += 2;
        return expanded;
    }
}
