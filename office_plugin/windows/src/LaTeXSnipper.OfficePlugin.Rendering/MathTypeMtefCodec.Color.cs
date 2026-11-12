using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Xml.Linq;

namespace LaTeXSnipper.OfficePlugin.Rendering;

internal static partial class MathTypeMtefCodec
{
    private sealed class ColorState { public int Current; }
    private static readonly ConditionalWeakTable<List<byte>, ColorState> ColorStates = new();

    private static void PrepareColors(XElement math, List<byte> definitions)
    {
        var palette = new List<string> { "#000000" };
        foreach (var element in math.DescendantsAndSelf())
        {
            string? color = element.AncestorsAndSelf().Select(e => (string?)e.Attribute("mathcolor")).FirstOrDefault(c => c != null);
            if (color == null) continue;
            color = NormalizeColor(color);
            int index = palette.IndexOf(color);
            if (index < 0)
            {
                index = palette.Count;
                palette.Add(color);
                definitions.Add(RecordColorDef);
                definitions.Add(0);
                for (int component = 0; component < 3; component++)
                {
                    int rgb = int.Parse(color.Substring(1 + component * 2, 2), NumberStyles.HexNumber, CultureInfo.InvariantCulture);
                    ushort value = (ushort)Math.Round(rgb * 1000d / 255);
                    definitions.Add((byte)value);
                    definitions.Add((byte)(value >> 8));
                }
            }
            element.SetAttributeValue("data-mtef-color", index + 1);
        }
    }

    private static string NormalizeColor(string color)
    {
        var named = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
        {
            ["black"] = "#000000", ["white"] = "#ffffff", ["red"] = "#ff0000", ["green"] = "#008000",
            ["blue"] = "#0000ff", ["yellow"] = "#ffff00", ["cyan"] = "#00ffff", ["magenta"] = "#ff00ff"
        };
        color = color.Trim();
        if (named.TryGetValue(color, out string? hex)) return hex;
        if (color.Length == 4 && color[0] == '#') color = "#" + string.Concat(color.Skip(1).Select(c => new string(c, 2)));
        if (color.Length != 7 || color[0] != '#' || !uint.TryParse(color.Substring(1), NumberStyles.HexNumber, CultureInfo.InvariantCulture, out _))
            throw new InvalidDataException("Unsupported MathML color: " + color);
        return color.ToLowerInvariant();
    }

    private static void EmitNode(XNode node, List<byte> output)
    {
        var state = ColorStates.GetOrCreateValue(output);
        int previous = state.Current;
        if (node is XElement element && int.TryParse((string?)element.Attribute("data-mtef-color"), out int color)) state.Current = color;
        output.Add(RecordColor);
        WriteUnsigned(output, state.Current);
        try { EmitNodeCore(node, output); }
        finally
        {
            state.Current = previous;
            output.Add(RecordColor);
            WriteUnsigned(output, previous);
        }
    }

    private sealed partial class MtefStructureReader
    {
        private readonly List<string> _colors = new() { "#000000" };
        private int _currentColor;

        private void ReadColorDefinition(int start)
        {
            int options = _data[start + 1];
            int count = (options & 1) == 0 ? 3 : 4;
            Require(_data, start + 2, count * 2);
            var values = Enumerable.Range(0, count).Select(i => BitConverter.ToUInt16(_data, start + 2 + i * 2) / 1000d).ToArray();
            if (values.Any(v => v > 1)) throw new InvalidDataException("Invalid MTEF color component at " + start);
            var rgb = count == 3 ? values : values.Take(3).Select(v => (1 - v) * (1 - values[3])).ToArray();
            _colors.Add("#" + string.Concat(rgb.Select(v => ((byte)Math.Round(v * 255)).ToString("x2", CultureInfo.InvariantCulture))));
            _position = SkipColorDefinition(_data, start);
        }

        private void ApplyCurrentColor(XElement node) => ApplyColor(node, _currentColor);

        private void ApplyColor(XElement node, int index)
        {
            if (index < 0 || index >= _colors.Count) throw new InvalidDataException("Undefined MTEF color index " + index);
            if (index != 0) node.SetAttributeValue("mathcolor", _colors[index]);
        }
    }
}
