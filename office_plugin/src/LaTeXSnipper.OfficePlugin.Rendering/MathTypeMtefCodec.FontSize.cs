using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Globalization;

namespace LaTeXSnipper.OfficePlugin.Rendering;

internal static partial class MathTypeMtefCodec
{
    // MathType MTEF v5 EQN_PREFS stores logical sizes as packed decimal
    // dimensions. Full is element zero; the other sizes, spacing, fonts and
    // explicit SIZE records remain native MathType preferences.
    // https://docs.wiris.com/en_US/mathtype-mtef-v5-mathtype-40-and-later
    internal static byte[] CreateEquationNativeAtFontSize(string mathMl, double fontSizePt)
        => SetFullFontSize(CreateEquationNative(mathMl), fontSizePt);

    internal static double ReadEquationNativeFullFontSize(byte[] equationNative)
    {
        var mtef = ExtractNativeMtef(equationNative);
        var preferences = ReadPrefixLayout(mtef).Preferences;
        if (preferences < 0) throw new InvalidDataException("MathType equation preferences are missing.");
        var sizes = ReadSizeDimensions(mtef, preferences + 2, out _);
        if (sizes.Count == 0) throw new InvalidDataException("MathType Full size is not recorded.");
        var full = sizes[0];
        if (!double.TryParse(full.Value, NumberStyles.AllowDecimalPoint | NumberStyles.AllowLeadingSign,
                CultureInfo.InvariantCulture, out var value))
            throw new InvalidDataException("MathType Full size is not a valid decimal dimension.");
        var points = full.Units switch
        {
            0 => value * 72d,
            1 => value * 72d / 2.54d,
            2 => value,
            3 => value * 12d,
            _ => throw new InvalidDataException("MathType Full size needs an absolute dimension."),
        };
        if (points <= 0 || double.IsNaN(points) || double.IsInfinity(points))
            throw new InvalidDataException("MathType Full size must be a positive finite dimension.");
        return points;
    }

    private static byte[] SetFullFontSize(byte[] source, double fontSizePt)
    {
        if (fontSizePt <= 0 || fontSizePt > 200 || double.IsNaN(fontSizePt) || double.IsInfinity(fontSizePt))
            throw new ArgumentOutOfRangeException(nameof(fontSizePt));
        if (Math.Abs(ReadEquationNativeFullFontSize(source) - fontSizePt) < 0.000001d)
            return source;
        var sourceMtef = ExtractNativeMtef(source);
        var preferences = ReadPrefixLayout(sourceMtef).Preferences;
        var arrayStart = preferences + 2;
        var sizes = ReadSizeDimensions(sourceMtef, arrayStart, out var arrayEnd);
        if (sizes.Count == 0) throw new InvalidDataException("MathType Full size is not recorded.");
        sizes[0] = (2, fontSizePt.ToString("0.########", CultureInfo.InvariantCulture));
        var packed = WriteSizeDimensions(sizes);
        var mtef = new byte[sourceMtef.Length - (arrayEnd - arrayStart) + packed.Length];
        Buffer.BlockCopy(sourceMtef, 0, mtef, 0, arrayStart);
        Buffer.BlockCopy(packed, 0, mtef, arrayStart, packed.Length);
        Buffer.BlockCopy(sourceMtef, arrayEnd, mtef, arrayStart + packed.Length, sourceMtef.Length - arrayEnd);
        var native = new byte[28 + mtef.Length];
        Buffer.BlockCopy(source, 0, native, 0, 28);
        Buffer.BlockCopy(BitConverter.GetBytes((uint)mtef.Length), 0, native, 8, sizeof(uint));
        Buffer.BlockCopy(mtef, 0, native, 28, mtef.Length);
        return native;
    }

    private static List<(byte Units, string Value)> ReadSizeDimensions(byte[] data, int start, out int end)
    {
        Require(data, start, 1);
        var count = data[start];
        var nibble = (start + 1) * 2;
        byte Next()
        {
            Require(data, nibble / 2, 1);
            var value = (byte)((nibble % 2 == 0 ? data[nibble / 2] >> 4 : data[nibble / 2]) & 15);
            nibble++;
            return value;
        }
        var result = new List<(byte Units, string Value)>(count);
        for (var index = 0; index < count; index++)
        {
            var units = Next();
            if (units > 4) throw new InvalidDataException("Unsupported MathType size dimension unit.");
            var text = new System.Text.StringBuilder();
            for (var digit = Next(); digit != 15; digit = Next())
            {
                if (digit > 11) throw new InvalidDataException("Invalid MathType size dimension digit.");
                text.Append(digit <= 9 ? (char)('0' + digit) : digit == 10 ? '.' : '-');
            }
            result.Add((units, text.ToString()));
        }
        end = (nibble + 1) / 2;
        return result;
    }

    private static byte[] WriteSizeDimensions(IReadOnlyList<(byte Units, string Value)> sizes)
    {
        var nibbles = new List<byte>();
        foreach (var size in sizes)
        {
            nibbles.Add(size.Units);
            foreach (var character in size.Value)
                nibbles.Add(character is >= '0' and <= '9' ? (byte)(character - '0')
                    : character == '.' ? (byte)10 : character == '-' ? (byte)11
                    : throw new InvalidDataException("Invalid MathType size dimension character."));
            nibbles.Add(15);
        }
        var bytes = new byte[1 + (nibbles.Count + 1) / 2];
        bytes[0] = checked((byte)sizes.Count);
        for (var index = 0; index < nibbles.Count; index++)
            bytes[1 + index / 2] |= (byte)(index % 2 == 0 ? nibbles[index] << 4 : nibbles[index]);
        return bytes;
    }
}
