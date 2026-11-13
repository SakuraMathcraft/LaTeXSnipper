using System;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Text;
using System.Windows.Forms;
using System.Xml;
using System.Xml.Linq;

namespace LaTeXSnipper.OfficePlugin.PowerPointAddIn;

internal static class PowerPointClipboard
{
    public static (int Start, int Length) PasteAtRange(dynamic range, string mathMl)
    {
        if (string.IsNullOrWhiteSpace(mathMl)) throw new ArgumentException("MathML 不能为空。", nameof(mathMl));
        return WithSavedClipboard<(int Start, int Length)>(() =>
        {
            string normalized = CompactMathMl(mathMl);
            Clipboard.SetText(normalized, TextDataFormat.UnicodeText);
            dynamic pasted = range.Paste();
            return (Convert.ToInt32(pasted.Start), Convert.ToInt32(pasted.Length));
        });
    }

    public static T WithSavedClipboard<T>(Func<T> action)
    {
        IDataObject? previous = SnapshotClipboard();
        try
        {
            return action();
        }
        finally
        {
            if (previous == null) Clipboard.Clear();
            else Clipboard.SetDataObject(previous, true, 10, 100);
        }
    }

    private static IDataObject? SnapshotClipboard()
    {
        IDataObject? current = Clipboard.GetDataObject();
        if (current == null) return null;
        var snapshot = new DataObject();
        int copied = 0;
        foreach (string format in current.GetFormats(false))
        {
            object? value;
            try { value = CloneClipboardValue(current.GetData(format, false)); }
            catch { continue; }
            if (value == null) continue;
            snapshot.SetData(format, false, value);
            copied++;
        }
        if (copied == 0 && current.GetFormats(false).Length != 0)
            throw new InvalidOperationException("无法暂存当前剪贴板内容，公式未插入。");
        return copied == 0 ? null : snapshot;
    }

    private static object? CloneClipboardValue(object? value)
    {
        if (value is string text) return text;
        if (value is string[] paths) return (string[])paths.Clone();
        if (value is byte[] bytes) return (byte[])bytes.Clone();
        if (value is Bitmap bitmap) return new Bitmap(bitmap);
        if (value is MemoryStream memory) return new MemoryStream(memory.ToArray());
        if (value is Stream stream && stream.CanSeek)
        {
            long position = stream.Position;
            try
            {
                stream.Position = 0;
                var copy = new MemoryStream();
                stream.CopyTo(copy);
                copy.Position = 0;
                return copy;
            }
            finally { stream.Position = position; }
        }
        return null;
    }

    private static string CompactMathMl(string mathMl)
    {
        using var reader = XmlReader.Create(new StringReader(mathMl), new XmlReaderSettings
        {
            DtdProcessing = DtdProcessing.Prohibit,
            XmlResolver = null
        });
        XElement root = XElement.Load(reader, LoadOptions.PreserveWhitespace);
        if (root.Name != XName.Get("math", "http://www.w3.org/1998/Math/MathML"))
            throw new ArgumentException("MathML 根节点无效。", nameof(mathMl));
        foreach (XText whitespace in root.DescendantNodes().OfType<XText>()
            .Where(node => string.IsNullOrWhiteSpace(node.Value) && node.Parent?.Elements().Any() == true)
            .ToArray())
            whitespace.Remove();
        // Encode non-ASCII text and attribute values as numeric references so
        // PowerPoint's MathML paste parser accepts formulas containing Chinese.
        string compact = root.ToString(SaveOptions.DisableFormatting);
        var encoded = new StringBuilder(compact.Length);
        for (int index = 0; index < compact.Length; index++)
        {
            char character = compact[index];
            if (character < 128)
            {
                encoded.Append(character);
                continue;
            }
            int codePoint = char.ConvertToUtf32(compact, index);
            if (char.IsHighSurrogate(character)) index++;
            encoded.Append("&#x").Append(codePoint.ToString("X", System.Globalization.CultureInfo.InvariantCulture)).Append(';');
        }
        return encoded.ToString();
    }
}
