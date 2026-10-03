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

    private static void EmitIdentifier(XElement element, List<byte> output)
    {
        var value = element.Value;
        if (string.IsNullOrEmpty(value)) return;
        var scalars = EnumerateBmpScalars(value).ToArray();
        var variant = ((string?)element.Attribute("mathvariant") ?? string.Empty)
            .Trim()
            .ToLowerInvariant();
        var isFunction = scalars.Length > 1 && scalars.All(IsLetterScalar);
        var explicitTypeface = int.TryParse(
            (string?)element.Attribute("data-mtef-explicit-typeface"),
            out var parsedExplicitTypeface)
            ? parsedExplicitTypeface
            : (int?)null;
        foreach (var originalScalar in scalars)
        {
            // Word's OMML reverse transform represents a single prime in a
            // superscript as ASCII apostrophe, while MathJax/MathType use the
            // mathematical prime U+2032. Normalize before typeface/glyph lookup
            // so OMML→MathType writes MathType's native Symbol prime rather than
            // an italic variable apostrophe.
            var scalar = originalScalar == '\'' ? 0x2032 : originalScalar;
            var effectiveVariant = variant;
            if (string.IsNullOrWhiteSpace(effectiveVariant)
                && TryNormalizeLetterlikeForWrite(
                    originalScalar,
                    out var normalizedScalar,
                    out var normalizedVariant))
            {
                scalar = normalizedScalar;
                effectiveVariant = normalizedVariant;
            }

            if (scalar == 0x210F)
            {
                // Genuine MathType 7 persists \hbar / U+210F as an MT Extra
                // character, with the legacy 8-bit position 'h'. Writing the
                // same MTCode using Variable/Text typeface leaves MathType with
                // no glyph in that font and it renders an unknown-symbol box.
                // Keep this before mathvariant handling: MathJax commonly marks
                // the hbar <mi> as normal/upright, but MathType's native MTEF
                // representation is still fnMTEXTRA + encoded8 0x68.
                EmitScalar(
                    0x210F,
                    TypefaceMtExtra,
                    output,
                    includeEncoded8: true,
                    encoded8Override: 0x68);
                continue;
            }

            if (effectiveVariant.Contains("double-struck")
                && TryMtExtraDoubleStruck(scalar, out var mtExtraCode, out var mtExtraPosition))
            {
                // MathType 7 stores the five standard blackboard-bold set letters
                // in its built-in Extra Math style (fnMTEXTRA), not as an explicit
                // Euclid Math Two font. This exactly matches native MathType MTEF.
                EmitScalar(
                    mtExtraCode,
                    TypefaceMtExtra,
                    output,
                    includeEncoded8: true,
                    encoded8Override: mtExtraPosition);
                continue;
            }

            if (explicitTypeface is null
                && !effectiveVariant.Contains("bold")
                && !effectiveVariant.Contains("double-struck")
                && !effectiveVariant.Contains("script")
                && !effectiveVariant.Contains("fraktur")
                && TryResolveMathTypeGlyph(
                    scalar,
                    out var nativeMtCode,
                    out var nativeTypeface,
                    out var nativeEncoded8))
            {
                EmitScalar(
                    nativeMtCode,
                    nativeTypeface,
                    output,
                    includeEncoded8: true,
                    encoded8Override: nativeEncoded8);
                continue;
            }

            if (explicitTypeface is null
                && IsMathematicalSymbolScalar(scalar))
            {
                // MathType's built-in Symbol style is an 8-bit Adobe Symbol
                // encoding, not a generic Unicode font.  If a mathematical
                // symbol has no legacy Symbol position, keep its Unicode MTCode
                // in the text font instead of emitting a non-existent Symbol
                // glyph (which MathType renders as '?'/unknown-symbol).
                EmitScalar(
                    NormalizeMathTypeMtCode(scalar),
                    TypefaceText,
                    output);
                continue;
            }

            var typeface = explicitTypeface
                ?? ResolveTokenTypeface(element, scalar, effectiveVariant, isFunction);
            var dotlessJMtCode = 0;
            byte dotlessJEncoded8 = 0;
            var hasDotlessJ = explicitTypeface is < 0
                && TryEuclidMathOneDotlessJ(
                    scalar,
                    out dotlessJMtCode,
                    out dotlessJEncoded8);
            var mtCode = hasDotlessJ
                ? dotlessJMtCode
                : explicitTypeface is < 0
                    ? ExplicitVariantMtCode(effectiveVariant, scalar)
                    : effectiveVariant.Contains("double-struck")
                        && TryStandardDoubleStruckMtCode(scalar, out var standardDoubleStruck)
                            ? standardDoubleStruck
                            : scalar;
            var explicitEncoded8 = hasDotlessJ
                ? (byte?)dotlessJEncoded8
                : explicitTypeface is < 0
                    && TryEuclidMathOneGreekVariantEncoded8(scalar, out var greekVariantEncoded8)
                        ? (byte?)greekVariantEncoded8
                        : explicitTypeface is < 0 && scalar <= 0xFF
                            ? (byte?)scalar
                            : null;
            EmitScalar(
                mtCode,
                typeface,
                output,
                includeEncoded8: explicitEncoded8 is not null,
                encoded8Override: explicitEncoded8);
        }
    }


    private static bool TryNormalizeLetterlikeForWrite(
        int scalar,
        out int normalizedScalar,
        out string mathVariant)
    {
        switch (scalar)
        {
            case 0x2102: normalizedScalar = 'C'; mathVariant = "double-struck"; return true;
            case 0x210B: normalizedScalar = 'H'; mathVariant = "script"; return true;
            case 0x210C: normalizedScalar = 'H'; mathVariant = "fraktur"; return true;
            case 0x210D: normalizedScalar = 'H'; mathVariant = "double-struck"; return true;
            case 0x2110: normalizedScalar = 'I'; mathVariant = "script"; return true;
            case 0x2112: normalizedScalar = 'L'; mathVariant = "script"; return true;
            case 0x2115: normalizedScalar = 'N'; mathVariant = "double-struck"; return true;
            case 0x2119: normalizedScalar = 'P'; mathVariant = "double-struck"; return true;
            case 0x211A: normalizedScalar = 'Q'; mathVariant = "double-struck"; return true;
            case 0x211B: normalizedScalar = 'R'; mathVariant = "script"; return true;
            case 0x211D: normalizedScalar = 'R'; mathVariant = "double-struck"; return true;
            case 0x2124: normalizedScalar = 'Z'; mathVariant = "double-struck"; return true;
            case 0x212C: normalizedScalar = 'B'; mathVariant = "script"; return true;
            case 0x212D: normalizedScalar = 'C'; mathVariant = "fraktur"; return true;
            case 0x212F: normalizedScalar = 'e'; mathVariant = "script"; return true;
            case 0x2130: normalizedScalar = 'E'; mathVariant = "script"; return true;
            case 0x2131: normalizedScalar = 'F'; mathVariant = "script"; return true;
            case 0x2133: normalizedScalar = 'M'; mathVariant = "script"; return true;
            case 0x2134: normalizedScalar = 'o'; mathVariant = "script"; return true;
            default:
                normalizedScalar = scalar;
                mathVariant = string.Empty;
                return false;
        }
    }


    private static bool TryEuclidMathOneGreekVariantEncoded8(
        int scalar,
        out byte encoded8)
    {
        switch (scalar)
        {
            case 0x03F1: encoded8 = 0xF1; return true; // \varrho
            case 0x03F5: encoded8 = 0xF2; return true; // \epsilon
            case 0x03F0: encoded8 = 0xF9; return true; // \varkappa
            default:
                encoded8 = 0;
                return false;
        }
    }


    private static bool TryEuclidMathOneDotlessJ(
        int scalar,
        out int mtCode,
        out byte encoded8)
    {
        if (scalar == 0x0237) // \\jmath
        {
            mtCode = 0xED02;
            encoded8 = 0xF8;
            return true;
        }
        mtCode = 0;
        encoded8 = 0;
        return false;
    }


    private static bool TryEuclidMathOneOperatorEncoded8(
        int scalar,
        out byte encoded8)
    {
        switch (scalar)
        {
            case 0x2216: encoded8 = 0x82; return true; // \\setminus
            case 0x224D: encoded8 = 0xA9; return true; // \\asymp
            case 0x22A2: encoded8 = 0x90; return true; // \\vdash
            case 0x22A3: encoded8 = 0x94; return true; // \\dashv
            case 0x22A8: encoded8 = 0x91; return true; // \\models
            case 0x21BC: encoded8 = 0xB4; return true; // \\leftharpoonup
            case 0x21C1: encoded8 = 0xB7; return true; // \\rightharpoondown
            case 0x2296: encoded8 = 0x21; return true; // \\ominus
            case 0x2298: encoded8 = 0x25; return true; // \\oslash
            case 0x22A4: encoded8 = 0x95; return true; // \\top
            case 0x22C6: encoded8 = 0xE5; return true; // \\star
            case 0x2240: encoded8 = 0xAA; return true; // \\wr
            default:
                encoded8 = 0;
                return false;
        }
    }


    private static bool TryEuclidMathTwoOperatorEncoded8(
        int scalar,
        out byte encoded8)
    {
        switch (scalar)
        {
            // MathType's own TeX translator and Euclid Math Two font agree on
            // the private MTCode pair E938/E939 at legacy positions B0/B1 for
            // \preceq/\succeq. MathJax exposes the public Unicode pair
            // U+2AAF/U+2AB0; accept both at the codec boundary.
            case 0x2AAF:
            case 0xE938: encoded8 = 0xB0; return true; // \preceq
            case 0x2AB0:
            case 0xE939: encoded8 = 0xB1; return true; // \succeq
            case 0x227C: encoded8 = 0xB0; return true; // \preccurlyeq
            case 0x227D: encoded8 = 0xB1; return true; // \succcurlyeq
            case 0x228F: encoded8 = 0xF0; return true; // \\sqsubset
            case 0x2291: encoded8 = 0xF4; return true; // \\sqsubseteq
            case 0x2290: encoded8 = 0xF1; return true; // \\sqsupset
            case 0x2292: encoded8 = 0xF5; return true; // \\sqsupseteq
            case 0x228E: encoded8 = 0xE2; return true; // \\uplus
            case 0x2293: encoded8 = 0xF3; return true; // \\sqcap
            case 0x2294: encoded8 = 0xF2; return true; // \\sqcup
        }
        encoded8 = 0;
        return false;
    }


    private static bool TryMtExtraDoubleStruck(
        int scalar,
        out int mtCode,
        out byte fontPosition)
    {
        switch (scalar)
        {
            case 'R': mtCode = 0x211D; fontPosition = 0xA1; return true;
            case 'Z': mtCode = 0x2124; fontPosition = 0xA2; return true;
            case 'C': mtCode = 0x2102; fontPosition = 0xA3; return true;
            case 'Q': mtCode = 0x211A; fontPosition = 0xA4; return true;
            case 'N': mtCode = 0x2115; fontPosition = 0xA5; return true;
            default:
                mtCode = 0;
                fontPosition = 0;
                return false;
        }
    }


    private static bool TryStandardDoubleStruckMtCode(int scalar, out int mtCode)
    {
        mtCode = scalar switch
        {
            'C' => 0x2102,
            'H' => 0x210D,
            'N' => 0x2115,
            'P' => 0x2119,
            'Q' => 0x211A,
            'R' => 0x211D,
            'Z' => 0x2124,
            _ => 0,
        };
        return mtCode != 0;
    }


    private static int ExplicitVariantMtCode(string variant, int scalar)
    {
        if (variant.Contains("double-struck"))
        {
            // MathType's EuclidMath2 encoding uses its own BMP PUA MTCode
            // range, even for the familiar Unicode letterlike symbols such as
            // ℝ. These values are the mappings shipped in MathType 7's own
            // AMS/Desire2Learn translators.
            if (scalar is >= 'A' and <= 'Z') return 0xF080 + scalar - 'A';
            if (scalar is >= 'a' and <= 'z') return 0xF09A + scalar - 'a';
            if (scalar is >= '0' and <= '9') return 0xF0C0 + scalar - '0';
            return scalar;
        }
        if (variant.Contains("script"))
        {
            return scalar switch
            {
                'B' => 0x212C,
                'E' => 0x2130,
                'F' => 0x2131,
                'H' => 0x210B,
                'I' => 0x2110,
                'L' => 0x2112,
                'M' => 0x2133,
                'R' => 0x211B,
                'e' => 0x212F,
                'g' => 0x210A,
                'o' => 0x2134,
                _ => scalar,
            };
        }
        if (variant.Contains("fraktur"))
        {
            return scalar switch
            {
                'C' => 0x212D,
                'H' => 0x210C,
                'I' => 0x2111,
                'R' => 0x211C,
                'Z' => 0x2128,
                _ => scalar,
            };
        }
        return scalar;
    }


    private static int ResolveTokenTypeface(
        XElement element,
        int scalar,
        string? normalizedVariant = null,
        bool? functionHint = null)
    {
        var variant = normalizedVariant
            ?? (((string?)element.Attribute("mathvariant") ?? string.Empty)
                .Trim()
                .ToLowerInvariant());
        var tokenKind = element.Name.LocalName;

        // MTEF typeface is semantic, not merely visual.  In particular MathJax
        // can attach mathvariant="normal" to operator tokens such as infinity,
        // relations, arrows and set symbols.  Treating that visual hint as Text
        // changes the token to mtext on read-back (for example \infty becomes
        // \text{∞}) and makes otherwise-valid MathType MTEF fail semantic
        // round-trip validation.  Preserve the MathML token class first; apply
        // mathvariant only inside identifier-like tokens.
        if (tokenKind == "mtext") return TypefaceText;
        if (tokenKind == "mn") return TypefaceNumber;
        if (tokenKind == "mo")
            return functionHint == true ? TypefaceFunction : TypefaceSymbol;
        if (IsMathematicalSymbolScalar(scalar)) return TypefaceSymbol;

        if (variant.Contains("normal") || variant.Contains("upright"))
            return functionHint == true ? TypefaceFunction : TypefaceText;
        if (variant.Contains("bold")) return TypefaceVector;
        if (variant.Contains("italic"))
            return IsLowerGreek(scalar)
                ? TypefaceLowerGreek
                : IsUpperGreek(scalar)
                    ? TypefaceUpperGreek
                    : TypefaceVariable;
        if (functionHint == true) return TypefaceFunction;
        if (IsLowerGreek(scalar)) return TypefaceLowerGreek;
        if (IsUpperGreek(scalar)) return TypefaceUpperGreek;
        return TypefaceVariable;
    }


    private static bool IsMathematicalSymbolScalar(int scalar)
    {
        if (scalar < 0 || scalar > char.MaxValue) return false;
        if (scalar is 0x2020 or 0x2021
            or 0x2032 or 0x2033 or 0x2034
            // Unicode classifies floor/ceiling as opening/closing punctuation,
            // not MathSymbol. MathJax emits the common shorthand
            // \lfloor x\rfloor / \lceil x\rceil as standalone <mo> tokens, so
            // an MTEF Text-font fallback must still read them back as operators.
            // Otherwise they become mtext and semantic round-trip validation
            // rejects an otherwise valid MathType equation.
            or 0x2308 or 0x2309 or 0x230A or 0x230B
            or 0x2329 or 0x232A
            or 0x27E8 or 0x27E9)
            return true;
        var character = (char)scalar;
        var category = char.GetUnicodeCategory(character);
        return category == System.Globalization.UnicodeCategory.MathSymbol
            || category == System.Globalization.UnicodeCategory.CurrencySymbol
            || category == System.Globalization.UnicodeCategory.ModifierSymbol
            || category == System.Globalization.UnicodeCategory.OtherSymbol;
    }


    private static string NormalizeOperatorToken(string value) => value switch
    {
        "〈" or "〈" or "⟨" => "⟨",
        "〉" or "〉" or "⟩" => "⟩",
        // MathJax uses U+25C3/U+25B9 for TeX triangleleft/triangleright,
        // while MathType persists the same glyphs as U+22B2/U+22B3.
        "◃" or "⊲" => "⊲",
        "▹" or "⊳" => "⊳",
        // MathJax emits the mathematical minus U+2212 while Word OMML commonly
        // serializes the same binary subtraction operator as ASCII hyphen-minus.
        // They are semantically identical in an <mo> token and must compare equal
        // across LaTeXSnipper/OMML/MathType round trips.
        "−" => "-",
        // MathType 7 stores TeX \\sim as ASCII '~' in its Function typeface,
        // while MathJax represents the same operator as U+223C. This is an
        // operator-token equivalence only; accent \\tilde is represented by
        // mover/template structure and never reaches this normalization.
        "~" => "∼",
        _ => value,
    };


    private static int NormalizeMathTypeMtCode(int scalar) => scalar switch
    {
        // MathType 7/Adobe Symbol use the historical angle-bracket MTCode pair.
        0x27E8 => 0x2329,
        0x27E9 => 0x232A,
        _ => scalar,
    };


    private static bool TryResolveMathTypeGlyph(
        int scalar,
        out int mtCode,
        out int typeface,
        out byte encoded8)
    {
        mtCode = NormalizeMathTypeMtCode(scalar);
        typeface = TypefaceSymbol;
        encoded8 = 0;

        if (mtCode == 0x2223)
        {
            // \mid uses the ordinary vertical-bar position in Symbol while its
            // MTCode remains U+2223 so semantic readback is not degraded to '|'.
            encoded8 = 0x7C;
            return true;
        }
        if (mtCode == 0x2213)
        {
            // Genuine MathType 7 persists \mp / MINUS-OR-PLUS in MT Extra,
            // not Adobe Symbol: fnMTEXTRA + MTCode U+2213 + encoded8 0x6D.
            // Falling back to Unicode text changes the glyph metrics/baseline.
            typeface = TypefaceMtExtra;
            encoded8 = 0x6D;
            return true;
        }
        if (mtCode == 0x21A6)
        {
            // Genuine MathType 7 persists \mapsto in MT Extra:
            // fnMTEXTRA + MTCode U+21A6 + encoded8 0x61.
            typeface = TypefaceMtExtra;
            encoded8 = 0x61;
            return true;
        }
        if (mtCode == 0x2225)
        {
            // Genuine MathType 7 persists \parallel in MT Extra:
            // fnMTEXTRA + MTCode U+2225 + encoded8 0x50.
            typeface = TypefaceMtExtra;
            encoded8 = 0x50;
            return true;
        }

        if (mtCode == 0x2113)
        {
            // Genuine MathType 7 persists \\ell as MT Extra U+2113 / 0x6C.
            typeface = TypefaceMtExtra;
            encoded8 = 0x6C;
            return true;
        }

        if (!TryGetAdobeSymbolEncoded8(mtCode, out encoded8)) return false;
        if (IsLowerGreek(mtCode)) typeface = TypefaceLowerGreek;
        else if (IsUpperGreek(mtCode)) typeface = TypefaceUpperGreek;
        return true;
    }


    private static bool TryGetAdobeSymbolEncoded8(int scalar, out byte encoded8)
    {
        // Static Adobe Symbol encoding used by MathType's built-in Lower Greek,
        // Upper Greek and Symbol styles.  Keeping this table in LaTeXSnipper makes
        // standalone MTEF generation independent of MathType/MathPage at runtime.
        switch (scalar)
        {
            case 0x00AC: encoded8 = 0xD8; return true;
            case 0x00B0: encoded8 = 0xB0; return true;
            case 0x00B1: encoded8 = 0xB1; return true;
            case 0x00B5: encoded8 = 0x6D; return true;
            case 0x00D7: encoded8 = 0xB4; return true;
            case 0x00F7: encoded8 = 0xB8; return true;
            case 0x0192: encoded8 = 0xA6; return true;
            case 0x0391: encoded8 = 0x41; return true;
            case 0x0392: encoded8 = 0x42; return true;
            case 0x0393: encoded8 = 0x47; return true;
            case 0x0394: encoded8 = 0x44; return true;
            case 0x0395: encoded8 = 0x45; return true;
            case 0x0396: encoded8 = 0x5A; return true;
            case 0x0397: encoded8 = 0x48; return true;
            case 0x0398: encoded8 = 0x51; return true;
            case 0x0399: encoded8 = 0x49; return true;
            case 0x039A: encoded8 = 0x4B; return true;
            case 0x039B: encoded8 = 0x4C; return true;
            case 0x039C: encoded8 = 0x4D; return true;
            case 0x039D: encoded8 = 0x4E; return true;
            case 0x039E: encoded8 = 0x58; return true;
            case 0x039F: encoded8 = 0x4F; return true;
            case 0x03A0: encoded8 = 0x50; return true;
            case 0x03A1: encoded8 = 0x52; return true;
            case 0x03A3: encoded8 = 0x53; return true;
            case 0x03A4: encoded8 = 0x54; return true;
            case 0x03A5: encoded8 = 0x55; return true;
            case 0x03A6: encoded8 = 0x46; return true;
            case 0x03A7: encoded8 = 0x43; return true;
            case 0x03A8: encoded8 = 0x59; return true;
            case 0x03A9: encoded8 = 0x57; return true;
            case 0x03B1: encoded8 = 0x61; return true;
            case 0x03B2: encoded8 = 0x62; return true;
            case 0x03B3: encoded8 = 0x67; return true;
            case 0x03B4: encoded8 = 0x64; return true;
            case 0x03B5: encoded8 = 0x65; return true;
            case 0x03B6: encoded8 = 0x7A; return true;
            case 0x03B7: encoded8 = 0x68; return true;
            case 0x03B8: encoded8 = 0x71; return true;
            case 0x03B9: encoded8 = 0x69; return true;
            case 0x03BA: encoded8 = 0x6B; return true;
            case 0x03BB: encoded8 = 0x6C; return true;
            case 0x03BC: encoded8 = 0x6D; return true;
            case 0x03BD: encoded8 = 0x6E; return true;
            case 0x03BE: encoded8 = 0x78; return true;
            case 0x03BF: encoded8 = 0x6F; return true;
            case 0x03C0: encoded8 = 0x70; return true;
            case 0x03C1: encoded8 = 0x72; return true;
            case 0x03C2: encoded8 = 0x56; return true;
            case 0x03C3: encoded8 = 0x73; return true;
            case 0x03C4: encoded8 = 0x74; return true;
            case 0x03C5: encoded8 = 0x75; return true;
            case 0x03C6: encoded8 = 0x6A; return true;
            case 0x03C7: encoded8 = 0x63; return true;
            case 0x03C8: encoded8 = 0x79; return true;
            case 0x03C9: encoded8 = 0x77; return true;
            case 0x03D1: encoded8 = 0x4A; return true;
            case 0x03D2: encoded8 = 0xA1; return true;
            case 0x03D5: encoded8 = 0x66; return true;
            case 0x03D6: encoded8 = 0x76; return true;
            case 0x2022: encoded8 = 0xB7; return true;
            case 0x2026: encoded8 = 0xBC; return true;
            case 0x2032: encoded8 = 0xA2; return true;
            case 0x2033: encoded8 = 0xB2; return true;
            case 0x2044: encoded8 = 0xA4; return true;
            case 0x2111: encoded8 = 0xC1; return true;
            case 0x2118: encoded8 = 0xC3; return true;
            case 0x211C: encoded8 = 0xC2; return true;
            case 0x2126: encoded8 = 0x57; return true;
            case 0x2135: encoded8 = 0xC0; return true;
            case 0x2190: encoded8 = 0xAC; return true;
            case 0x2191: encoded8 = 0xAD; return true;
            case 0x2192: encoded8 = 0xAE; return true;
            case 0x2193: encoded8 = 0xAF; return true;
            case 0x2194: encoded8 = 0xAB; return true;
            case 0x21B5: encoded8 = 0xBF; return true;
            case 0x21D0: encoded8 = 0xDC; return true;
            case 0x21D1: encoded8 = 0xDD; return true;
            case 0x21D2: encoded8 = 0xDE; return true;
            case 0x21D3: encoded8 = 0xDF; return true;
            case 0x21D4: encoded8 = 0xDB; return true;
            case 0x2200: encoded8 = 0x22; return true;
            case 0x2202: encoded8 = 0xB6; return true;
            case 0x2203: encoded8 = 0x24; return true;
            case 0x2205: encoded8 = 0xC6; return true;
            case 0x2206: encoded8 = 0x44; return true;
            case 0x2207: encoded8 = 0xD1; return true;
            case 0x2208: encoded8 = 0xCE; return true;
            case 0x2209: encoded8 = 0xCF; return true;
            case 0x220B: encoded8 = 0x27; return true;
            case 0x220F: encoded8 = 0xD5; return true;
            case 0x2211: encoded8 = 0xE5; return true;
            case 0x2212: encoded8 = 0x2D; return true;
            case 0x2217: encoded8 = 0x2A; return true;
            case 0x221A: encoded8 = 0xD6; return true;
            case 0x221D: encoded8 = 0xB5; return true;
            case 0x221E: encoded8 = 0xA5; return true;
            case 0x2220: encoded8 = 0xD0; return true;
            case 0x2227: encoded8 = 0xD9; return true;
            case 0x2228: encoded8 = 0xDA; return true;
            case 0x2229: encoded8 = 0xC7; return true;
            case 0x222A: encoded8 = 0xC8; return true;
            case 0x222B: encoded8 = 0xF2; return true;
            case 0x2234: encoded8 = 0x5C; return true;
            case 0x223C: encoded8 = 0x7E; return true;
            case 0x2245: encoded8 = 0x40; return true;
            case 0x2248: encoded8 = 0xBB; return true;
            case 0x2260: encoded8 = 0xB9; return true;
            case 0x2261: encoded8 = 0xBA; return true;
            case 0x2264: encoded8 = 0xA3; return true;
            case 0x2265: encoded8 = 0xB3; return true;
            case 0x2282: encoded8 = 0xCC; return true;
            case 0x2283: encoded8 = 0xC9; return true;
            case 0x2284: encoded8 = 0xCB; return true;
            case 0x2286: encoded8 = 0xCD; return true;
            case 0x2287: encoded8 = 0xCA; return true;
            case 0x2295: encoded8 = 0xC5; return true;
            case 0x2297: encoded8 = 0xC4; return true;
            case 0x22A5: encoded8 = 0x5E; return true;
            case 0x22C5: encoded8 = 0xD7; return true;
            case 0x2320: encoded8 = 0xF3; return true;
            case 0x2321: encoded8 = 0xF5; return true;
            case 0x2329: encoded8 = 0xE1; return true;
            case 0x232A: encoded8 = 0xF1; return true;
            case 0x25CA: encoded8 = 0xE0; return true;
            case 0x2660: encoded8 = 0xAA; return true;
            case 0x2663: encoded8 = 0xA7; return true;
            case 0x2665: encoded8 = 0xA9; return true;
            case 0x2666: encoded8 = 0xA8; return true;
            default:
                encoded8 = 0;
                return false;
        }
    }


    private static void EmitOperator(XElement element, List<byte> output)
    {
        var explicitTypeface = int.TryParse(
            (string?)element.Attribute("data-mtef-explicit-typeface"),
            out var parsedExplicitTypeface)
            ? parsedExplicitTypeface
            : (int?)null;
        if (explicitTypeface is null)
        {
            EmitOperator(element.Value, output);
            return;
        }

        foreach (var scalar in EnumerateBmpScalars(element.Value))
        {
            if (TryEuclidMathOneOperatorEncoded8(scalar, out var encoded8)
                || TryEuclidMathTwoOperatorEncoded8(scalar, out encoded8))
            {
                var nativeScalar = scalar switch
                {
                    0x2AAF => 0xE938, // MathJax \preceq -> MathType private MTCode
                    0x2AB0 => 0xE939, // MathJax \succeq -> MathType private MTCode
                    _ => scalar,
                };
                EmitScalar(
                    nativeScalar,
                    explicitTypeface.Value,
                    output,
                    includeEncoded8: true,
                    encoded8Override: encoded8);
                continue;
            }

            EmitScalar(
                scalar,
                explicitTypeface.Value,
                output,
                includeEncoded8: scalar <= 0xFF,
                encoded8Override: scalar <= 0xFF ? (byte?)scalar : null);
        }
    }


    private static bool TryEmitMathTypeSpecialOperator(int scalar, List<byte> output)
    {
        switch (scalar)
        {
            case 0x2020: // \\dagger: genuine MathType uses Function typeface.
                EmitScalar(0x2020, TypefaceFunction, output, includeEncoded8: false);
                return true;
            case 0x2021: // \\ddagger: genuine MathType uses Function typeface.
                EmitScalar(0x2021, TypefaceFunction, output, includeEncoded8: false);
                return true;
            case 0x2218: // \\circ: MathType uses the degree glyph in Symbol.
                EmitScalar(0x00B0, TypefaceSymbol, output, includeEncoded8: true, encoded8Override: 0xB0);
                return true;
            case 0x2022: // \\bullet: genuine MathType uses Function, no encoded8.
                EmitScalar(0x2022, TypefaceFunction, output, includeEncoded8: false);
                return true;
            case 0x22C4: // \\diamond: Symbol position 0xE0.
                EmitScalar(0x22C4, TypefaceSymbol, output, includeEncoded8: true, encoded8Override: 0xE0);
                return true;
            case 0x22B2: // MathType-side \\triangleleft scalar.
            case 0x25C3: // MathJax-side \\triangleleft scalar.
                EmitScalar(0x22B2, TypefaceMtExtra, output, includeEncoded8: true, encoded8Override: 0x3C);
                return true;
            case 0x22B3: // MathType-side \\triangleright scalar.
            case 0x25B9: // MathJax-side \\triangleright scalar.
                EmitScalar(0x22B3, TypefaceMtExtra, output, includeEncoded8: true, encoded8Override: 0x3E);
                return true;
            case 0x2661: // \\heartsuit: built-in MathType typeface 12.
                EmitScalar(0x2661, TypefaceMathTypeSpecial12, output, includeEncoded8: false);
                return true;
            case 0x2662: // \\diamondsuit: MT Extra glyph position 0x6E.
                EmitScalar(0xFFFD, TypefaceMtExtra, output, includeEncoded8: true, encoded8Override: 0x6E);
                return true;
            case 0x2299: // \\odot: MT Extra position 0x65.
                EmitScalar(0x2299, TypefaceMtExtra, output, includeEncoded8: true, encoded8Override: 0x65);
                return true;
            case 0x25EF: // \\bigcirc: built-in typeface 12.
                EmitScalar(0x25EF, TypefaceMathTypeSpecial12, output, includeEncoded8: false);
                return true;
            case 0x226A: // \\ll: MT Extra position 0x3D.
                EmitScalar(0x226A, TypefaceMtExtra, output, includeEncoded8: true, encoded8Override: 0x3D);
                return true;
            case 0x226B: // \\gg: MT Extra position 0x3F.
                EmitScalar(0x226B, TypefaceMtExtra, output, includeEncoded8: true, encoded8Override: 0x3F);
                return true;
            case 0x2243: // \\simeq
                EmitScalar(0x2243, TypefaceMtExtra, output, includeEncoded8: true, encoded8Override: 0x3B);
                return true;
            case 0x2250: // \\doteq
                EmitScalar(0x2250, TypefaceMtExtra, output, includeEncoded8: true, encoded8Override: 0x42);
                return true;
            case 0x227A: // \\prec
                EmitScalar(0x227A, TypefaceMtExtra, output, includeEncoded8: true, encoded8Override: 0x70);
                return true;
            case 0x227B: // \\succ
                EmitScalar(0x227B, TypefaceMtExtra, output, includeEncoded8: true, encoded8Override: 0x66);
                return true;
            case 0x2195: // \\updownarrow
                EmitScalar(0x2195, TypefaceMtExtra, output, includeEncoded8: true, encoded8Override: 0x62);
                return true;
            case 0x21D5: // \\Updownarrow
                EmitScalar(0x21D5, TypefaceMtExtra, output, includeEncoded8: true, encoded8Override: 0x63);
                return true;
            case 0x21BD: // \\leftharpoondown
                EmitScalar(0x21BD, TypefaceMtExtra, output, includeEncoded8: true, encoded8Override: 0x87);
                return true;
            case 0x21C0: // \\rightharpoonup
                EmitScalar(0x21C0, TypefaceMtExtra, output, includeEncoded8: true, encoded8Override: 0x86);
                return true;
            case 0x2197: // \\nearrow
                EmitScalar(0x2197, TypefaceMtExtra, output, includeEncoded8: true, encoded8Override: 0x5A);
                return true;
            case 0x2198: // \\searrow
                EmitScalar(0x2198, TypefaceMtExtra, output, includeEncoded8: true, encoded8Override: 0x5D);
                return true;
            case 0x2199: // \\swarrow
                EmitScalar(0x2199, TypefaceMtExtra, output, includeEncoded8: true, encoded8Override: 0x5B);
                return true;
            case 0x2196: // \\nwarrow
                EmitScalar(0x2196, TypefaceMtExtra, output, includeEncoded8: true, encoded8Override: 0x5E);
                return true;
            case 0x2A3F: // \\amalg: MathType stores ordinary amalg as MT Extra U+2210 / 0x43.
                EmitScalar(0x2210, TypefaceMtExtra, output, includeEncoded8: true, encoded8Override: 0x43);
                return true;
            case 0x220B: // \\ni: built-in typeface 12, no encoded8.
                EmitScalar(0x220B, TypefaceMathTypeSpecial12, output, includeEncoded8: false);
                return true;
            case 0x22EF: // \\cdots
                EmitScalar(0x22EF, TypefaceMtExtra, output, includeEncoded8: true, encoded8Override: 0x4C);
                return true;
            case 0x22EE: // \\vdots
                EmitScalar(0x22EE, TypefaceMtExtra, output, includeEncoded8: true, encoded8Override: 0x4D);
                return true;
            case 0x22F1: // \\ddots
                EmitScalar(0x22F1, TypefaceMtExtra, output, includeEncoded8: true, encoded8Override: 0x4F);
                return true;
            default:
                return false;
        }
    }


    private static void EmitOperator(string value, List<byte> output)
    {
        if (value == "⁡") return;
        foreach (var scalar in EnumerateBmpScalars(value))
        {
            if (scalar is 0x223C or '~')
            {
                // Genuine MathType 7 represents TeX \sim as ASCII '~' in the
                // Function typeface, not U+223C in Adobe Symbol.
                EmitScalar('~', TypefaceFunction, output, includeEncoded8: false);
                continue;
            }
            if (TryEmitMathTypeSpecialOperator(scalar, output))
                continue;
            if (IsWhiteSpaceScalar(scalar))
            {
                EmitScalar(scalar, TypefaceSpace, output);
                continue;
            }

            if (TryResolveMathTypeGlyph(
                    scalar,
                    out var mtCode,
                    out var typeface,
                    out var encoded8))
            {
                EmitScalar(
                    mtCode,
                    typeface,
                    output,
                    includeEncoded8: true,
                    encoded8Override: encoded8);
                continue;
            }

            if (scalar <= 0xFF)
            {
                EmitScalar(
                    scalar,
                    TypefaceSymbol,
                    output,
                    includeEncoded8: true,
                    encoded8Override: (byte)scalar);
                continue;
            }

            // Do not pretend every Unicode operator lives in Adobe Symbol.
            // Times New Roman/MathType Text is Unicode-capable and is the safe
            // fallback for symbols not present in the legacy Symbol encoding.
            EmitScalar(NormalizeMathTypeMtCode(scalar), TypefaceText, output);
        }
    }


    private static void EmitText(string value, int typeface, List<byte> output)
    {
        foreach (var scalar in EnumerateBmpScalars(value))
        {
            if (IsWhiteSpaceScalar(scalar)) EmitScalar(scalar, TypefaceSpace, output);
            else EmitScalar(scalar, typeface, output);
        }
    }


    private static IEnumerable<int> EnumerateBmpScalars(string value)
    {
        foreach (var character in value)
        {
            if (char.IsSurrogate(character))
                throw new InvalidDataException(
                    "MathType MTEF v5 writer does not yet support non-BMP Unicode characters.");
            yield return character;
        }
    }


    private static bool IsLetterScalar(int scalar) =>
        scalar <= char.MaxValue && char.IsLetter((char)scalar);


    private static bool IsWhiteSpaceScalar(int scalar) =>
        scalar <= char.MaxValue && char.IsWhiteSpace((char)scalar);


    private static void EmitCharacter(char character, int typeface, List<byte> output) =>
        EmitScalar(character, typeface, output);


    private static void EmitScalar(
        int scalar,
        int typeface,
        List<byte> output,
        bool includeEncoded8 = false,
        IReadOnlyList<byte>? embellishments = null,
        byte? encoded8Override = null,
        bool functionStart = false)
    {
        if (scalar < 0 || scalar > 0xFFFF)
            throw new InvalidDataException(
                $"MathType MTEF v5 MTCode writer does not yet support non-BMP scalar U+{scalar:X}.");
        var hasEmbellishments = embellishments is { Count: > 0 };
        if (typeface == TypefaceText && scalar is >= 0x2E80 and <= 0x9FFF)
            typeface = TypefaceMathTypeSpecial12;
        var options = (byte)(includeEncoded8 ? CharEncoded8 : 0);
        if (hasEmbellishments) options |= CharHasEmbellishment;
        if (functionStart) options |= CharFunctionStart;
        output.Add(RecordChar);
        output.Add(options);
        WriteSigned(output, typeface);
        output.Add((byte)(scalar & 0xFF));
        output.Add((byte)((scalar >> 8) & 0xFF));
        if (includeEncoded8) output.Add(encoded8Override ?? (byte)scalar);
        if (!hasEmbellishments) return;
        foreach (var embellishment in embellishments!)
            output.AddRange(new byte[] { RecordEmbellishment, 0, embellishment });
        output.Add(RecordEnd);
    }


    private static void WriteSigned(List<byte> output, int value)
    {
        if (value is >= -128 and < 127)
        {
            output.Add(unchecked((byte)(value + 128)));
            return;
        }
        if (value < short.MinValue || value > short.MaxValue - 1)
            throw new ArgumentOutOfRangeException(nameof(value));
        var raw = value + 32768;
        output.Add(0xFF);
        output.Add((byte)(raw & 0xFF));
        output.Add((byte)((raw >> 8) & 0xFF));
    }


    private static bool IsLowerGreek(int scalar) =>
        scalar is >= 0x03B1 and <= 0x03C9
        || scalar is 0x03D1 or 0x03D5 or 0x03D6 or 0x03F1 or 0x03F5;


    private static bool IsUpperGreek(int scalar) => scalar is >= 0x0391 and <= 0x03A9;

}