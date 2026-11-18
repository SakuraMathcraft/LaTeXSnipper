using System;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;
using System.Security.Cryptography;
using System.Text;
using System.Xml;
using System.Xml.Linq;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.Rendering;

public static class MathTypeCompoundFile
{
    private const int StgmRead = 0;
    private const int StgmReadWrite = 2;
    private const int StgmShareExclusive = 16;
    private const int StgmCreate = 4096;
    private const int StatFlagNoName = 1;
    private const int StreamNotFound = unchecked((int)0x80030002);
    private const string SourceStreamName = "LaTeXSnipper Source";
    private static readonly UTF8Encoding StrictUtf8 = new(false, true);
    private static readonly Guid EquationClsid = new("0002CE03-0000-0000-C000-000000000046");

    public static byte[] Create(byte[] native, FormulaMetadata? source = null)
    {
        _ = MathTypeNativeEquation.ReadMathMl(native);
        string path = Path.Combine(Path.GetTempPath(), "latexsnipper-mathtype-" + Guid.NewGuid().ToString("N") + ".ole");
        IStorageNative? storage = null;
        try
        {
            Marshal.ThrowExceptionForHR(StgCreateDocfile(path, StgmCreate | StgmReadWrite | StgmShareExclusive, 0, out storage));
            var clsid = EquationClsid;
            storage.SetClass(ref clsid);
            uint format = RegisterClipboardFormatW("MathType EF");
            if (format == 0) throw new IOException("Could not register MathType EF.");
            Marshal.ThrowExceptionForHR(WriteFmtUserTypeStg(storage, checked((ushort)format), "MathType 7.0 Equation"));
            CreateAndWriteStream(storage, "\u0001Ole", new byte[] { 1,0,0,2,8,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0 });
            CreateAndWriteStream(storage, "\u0003ObjInfo", new byte[] { 0,0,3,0,4,0 });
            CreateAndWriteStream(storage, "Equation Native", native);
            if (source != null && IsLatexSource(source.Latex))
            {
                var snapshot = new XElement("latexsnipper", new XAttribute("native", Digest(native)),
                    new XElement("latex", Convert.ToBase64String(StrictUtf8.GetBytes(source.Latex))),
                    new XElement("typography", FormulaTypographyFields.Write(source.Typography).Select(field =>
                        new XAttribute(field.Key, Convert.ToString(field.Value, CultureInfo.InvariantCulture)!))));
                CreateAndWriteStream(storage, SourceStreamName, StrictUtf8.GetBytes(snapshot.ToString(SaveOptions.DisableFormatting)));
            }
            storage.Commit(0);
            Release(storage);
            storage = null;
            byte[] result = File.ReadAllBytes(path);
            _ = MathTypeNativeEquation.ReadMathMl(ReadNative(result));
            return result;
        }
        finally { Release(storage); File.Delete(path); }
    }

    public static byte[] ReadNative(byte[] compoundFile) =>
        ReadCompoundFile(compoundFile, storage => ReadStream(storage, "Equation Native"));

    public static MathTypeFormulaContent ReadContent(byte[] compoundFile) => ReadCompoundFile(compoundFile, storage =>
    {
        byte[] native = ReadStream(storage, "Equation Native");
        var formula = MathTypeNativeEquation.ReadContent(native);
        try
        {
            var snapshot = XElement.Parse(StrictUtf8.GetString(ReadStream(storage, SourceStreamName)));
            if (snapshot.Name != "latexsnipper" || (string?)snapshot.Attribute("native") != Digest(native))
                return formula;
            string latex = StrictUtf8.GetString(Convert.FromBase64String((string?)snapshot.Element("latex") ?? ""));
            var fields = snapshot.Element("typography")?.Attributes()
                .ToDictionary(attribute => attribute.Name.LocalName, attribute => (object)attribute.Value);
            if (string.IsNullOrWhiteSpace(latex) || fields == null) return formula;
            var typography = FormulaTypographyFields.Read(fields);
            if (Math.Abs(typography.FontSizePoints - formula.FontSizePoints) > 0.001) return formula;
            return new MathTypeFormulaContent(formula.MathMl, formula.FontSizePoints, formula.DisplayMode, latex, typography);
        }
        catch (COMException exception) when (exception.ErrorCode == StreamNotFound) { return formula; }
        catch (Exception exception) when (exception is XmlException or FormatException or ArgumentException)
        {
            return formula;
        }
    });

    private static string Digest(byte[] native)
    {
        using var hash = SHA256.Create();
        return Convert.ToBase64String(hash.ComputeHash(native));
    }

    private static bool IsLatexSource(string source)
    {
        if (!source.TrimStart().StartsWith("<", StringComparison.Ordinal)) return true;
        try { return XElement.Parse(source).Name.LocalName != "math"; }
        catch (XmlException) { return true; }
    }

    private static T ReadCompoundFile<T>(byte[] compoundFile, Func<IStorageNative, T> read)
    {
        if (compoundFile == null || compoundFile.Length < 512 || compoundFile.Length > 64 * 1024 * 1024
            || BitConverter.ToUInt64(compoundFile, 0) != 0xE11AB1A1E011CFD0UL)
            throw new InvalidDataException("Invalid MathType compound file.");
        string path = Path.Combine(Path.GetTempPath(), "latexsnipper-mathtype-" + Guid.NewGuid().ToString("N") + ".ole");
        IStorageNative? storage = null;
        try
        {
            File.WriteAllBytes(path, compoundFile);
            Marshal.ThrowExceptionForHR(StgOpenStorage(path, IntPtr.Zero, StgmRead | StgmShareExclusive, IntPtr.Zero, 0, out storage));
            storage.Stat(out var stat, StatFlagNoName);
            if (stat.clsid != EquationClsid) throw new InvalidDataException("The compound file is not a MathType equation.");
            return read(storage);
        }
        finally { Release(storage); File.Delete(path); }
    }

    private static void Release(object? value)
    {
        if (value != null && Marshal.IsComObject(value)) Marshal.ReleaseComObject(value);
    }

    private static byte[] ReadStream(IStorageNative storage, string name)
    {
        storage.OpenStream(
            name,
            IntPtr.Zero,
            StgmRead | StgmShareExclusive,
            0,
            out var stream);
        try
        {
            stream.Stat(out var stat, StatFlagNoName);
            if (stat.cbSize < 0 || stat.cbSize > 64L * 1024 * 1024)
                throw new InvalidDataException(
                    $"Unexpected MathType storage stream '{name}' length: {stat.cbSize}.");
            var bytes = new byte[(int)stat.cbSize];
            stream.Seek(0, 0, IntPtr.Zero);
            var readPointer = Marshal.AllocHGlobal(sizeof(int));
            try
            {
                stream.Read(bytes, bytes.Length, readPointer);
                var read = Marshal.ReadInt32(readPointer);
                if (read != bytes.Length)
                    throw new EndOfStreamException(
                        $"MathType stream '{name}' expected {bytes.Length} bytes, read {read}.");
            }
            finally { Marshal.FreeHGlobal(readPointer); }
            return bytes;
        }
        finally { Release(stream); }
    }


    private static void CreateAndWriteStream(
        IStorageNative storage,
        string name,
        byte[] data)
    {
        storage.CreateStream(
            name,
            StgmCreate | StgmReadWrite | StgmShareExclusive,
            0,
            0,
            out var stream);
        try
        {
            stream.SetSize(data.LongLength);
            stream.Seek(0, 0, IntPtr.Zero);
            var writtenPointer = Marshal.AllocHGlobal(sizeof(int));
            try
            {
                stream.Write(data, data.Length, writtenPointer);
                var written = Marshal.ReadInt32(writtenPointer);
                if (written != data.Length)
                    throw new IOException(
                        $"MathType stream '{name}' expected to write {data.Length} bytes, wrote {written}.");
            }
            finally { Marshal.FreeHGlobal(writtenPointer); }
            stream.Commit(0);
        }
        finally { Release(stream); }
    }


    [ComImport]
    [Guid("0000000B-0000-0000-C000-000000000046")]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IStorageNative
    {
        void CreateStream(string name, int mode, int reserved1, int reserved2, out IStream stream);
        void OpenStream(string name, IntPtr reserved1, int mode, int reserved2, out IStream stream);
        void CreateStorage(string name, int mode, int reserved1, int reserved2, out IStorageNative storage);
        void OpenStorage(string name, IntPtr priority, int mode, IntPtr exclude, int reserved, out IStorageNative storage);
        void CopyTo(int ciidExclude, IntPtr rgiidExclude, IntPtr snbExclude, IStorageNative destination);
        void MoveElementTo(string name, IStorageNative destination, string newName, int flags);
        void Commit(int flags);
        void Revert();
        void EnumElements(int reserved1, IntPtr reserved2, int reserved3, out object enumerator);
        void DestroyElement(string name);
        void RenameElement(string oldName, string newName);
        void SetElementTimes(string name, IntPtr creation, IntPtr access, IntPtr modification);
        void SetClass(ref Guid clsid);
        void SetStateBits(int stateBits, int mask);
        void Stat(out System.Runtime.InteropServices.ComTypes.STATSTG stat, int flags);
    }


    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern uint RegisterClipboardFormatW(string format);


    [DllImport("ole32.dll", CharSet = CharSet.Unicode)]
    private static extern int WriteFmtUserTypeStg(
        IStorageNative storage,
        ushort clipboardFormat,
        string userType);


    [DllImport("ole32.dll", CharSet = CharSet.Unicode)]
    private static extern int StgCreateDocfile(
        string name,
        int mode,
        int reserved,
        out IStorageNative storage);


    [DllImport("ole32.dll", CharSet = CharSet.Unicode)]
    private static extern int StgOpenStorage(
        string name,
        IntPtr priority,
        int mode,
        IntPtr exclude,
        int reserved,
        out IStorageNative storage);

}
