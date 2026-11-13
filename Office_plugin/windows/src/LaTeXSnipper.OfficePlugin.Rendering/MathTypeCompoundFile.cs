using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;

namespace LaTeXSnipper.OfficePlugin.Rendering;

public static class MathTypeCompoundFile
{
    private const int StgmRead = 0;
    private const int StgmReadWrite = 2;
    private const int StgmShareExclusive = 16;
    private const int StgmCreate = 4096;
    private const int StatFlagNoName = 1;
    private static readonly Guid EquationClsid = new("0002CE03-0000-0000-C000-000000000046");

    public static byte[] Create(byte[] native)
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
            storage.Commit(0);
            Release(storage);
            storage = null;
            byte[] result = File.ReadAllBytes(path);
            _ = MathTypeNativeEquation.ReadMathMl(ReadNative(result));
            return result;
        }
        finally { Release(storage); File.Delete(path); }
    }

    public static byte[] ReadNative(byte[] compoundFile)
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
            return ReadStream(storage, "Equation Native");
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