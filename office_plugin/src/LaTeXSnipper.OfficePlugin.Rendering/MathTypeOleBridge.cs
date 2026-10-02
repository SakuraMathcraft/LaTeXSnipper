#if NETFRAMEWORK
using System;
using System.ComponentModel;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;
using System.Text;
using System.Threading;
using System.Xml.Linq;
using Microsoft.Win32;

namespace LaTeXSnipper.OfficePlugin.Rendering;

/// <summary>Writes MathML into a host-created native MathType object using its installed SDK.</summary>
public static class MathTypeOleBridge
{
    public const string ProgId = "Equation.DSMT4";
    private static readonly object Gate = new();

    public static bool IsEquation(object shape)
    {
        try { return string.Equals(Convert.ToString(((dynamic)shape).OLEFormat.ProgID), ProgId, StringComparison.OrdinalIgnoreCase); }
        catch (COMException) { return false; }
        catch (Microsoft.CSharp.RuntimeBinder.RuntimeBinderException) { return false; }
    }

    public static void EnsureAvailable()
    {
        if (!File.Exists(SdkLibraryPath()))
            throw new InvalidOperationException("当前 MathType 安装缺少对应位数的桌面 SDK，无法转换公式。");
    }

    public static void WriteMathMl(object equation, string mathMl)
    {
        if (Thread.CurrentThread.GetApartmentState() != ApartmentState.STA)
            throw new InvalidOperationException("MathType 转换必须在 Office STA 线程执行。");
        mathMl = MathTypeMathMl.PrepareForImport(mathMl);
        lock (Gate)
        {
            using var sdk = new Sdk();
            IntPtr dispatch = IntPtr.Zero;
            try
            {
                dispatch = Marshal.GetIDispatchForObject(equation);
                try
                {
                    Check(sdk.SetEquation(dispatch, 2, mathMl, mathMl.Length), "导入 MathML");
                    // A successful SDK call alone is insufficient: require readable native content.
                    _ = ReadMathMl(equation);
                }
                finally { Check(sdk.CloseEquation(1, dispatch), "关闭公式"); }
            }
            finally
            {
                if (dispatch != IntPtr.Zero) Marshal.Release(dispatch);
            }
        }
    }

    public static string ReadMathMl(object equation)
    {
        var format = Format("MathML", TYMED.TYMED_HGLOBAL);
        ((IDataObject)equation).GetData(ref format, out STGMEDIUM medium);
        try
        {
            int size = checked((int)GlobalSize(medium.unionmember).ToUInt64());
            if (size <= 0 || size > 32 * 1024 * 1024) throw new InvalidDataException("MathType 返回了无效的 MathML 大小。");
            IntPtr data = GlobalLock(medium.unionmember);
            if (data == IntPtr.Zero) throw new Win32Exception(Marshal.GetLastWin32Error());
            try
            {
                var bytes = new byte[size];
                Marshal.Copy(data, bytes, 0, size);
                int end = Array.IndexOf(bytes, (byte)0);
                string xml = Encoding.UTF8.GetString(bytes, 0, end < 0 ? size : end);
                if (XDocument.Parse(xml).Root?.Name != XName.Get("math", "http://www.w3.org/1998/Math/MathML"))
                    throw new InvalidDataException("MathType 返回的内容不是 MathML 公式。");
                return xml;
            }
            finally { GlobalUnlock(medium.unionmember); }
        }
        finally { ReleaseStgMedium(ref medium); }
    }

    public static string ReadAndCloseMathMl(object equation)
    {
        if (Thread.CurrentThread.GetApartmentState() != ApartmentState.STA)
            throw new InvalidOperationException("MathType 转换必须在 Office STA 线程执行。");
        lock (Gate)
        {
            using var sdk = new Sdk();
            IntPtr dispatch = Marshal.GetIDispatchForObject(equation);
            try
            {
                var root = XDocument.Parse(ReadMathMl(equation)).Root!;
                // Store one complete MathML root, without translator comments,
                // XML declarations or the producer's namespace prefix aliases.
                foreach (var node in root.DescendantsAndSelf())
                    node.Attributes().Where(attribute => attribute.IsNamespaceDeclaration).Remove();
                return root.ToString(SaveOptions.DisableFormatting);
            }
            finally
            {
                try { Check(sdk.CloseEquation(1, dispatch), "关闭公式"); }
                finally { Marshal.Release(dispatch); }
            }
        }
    }

    private static FORMATETC Format(string name, TYMED medium) => new()
    {
        cfFormat = unchecked((short)RegisterClipboardFormat(name)),
        dwAspect = DVASPECT.DVASPECT_CONTENT, lindex = -1, tymed = medium
    };

    private static void Check(int result, string action)
    {
        if (result != 0) throw new InvalidOperationException($"MathType {action}失败（SDK {result}）。");
    }

    private static string SdkLibraryPath()
    {
        Type? type = Type.GetTypeFromProgID(ProgId);
        if (type == null) throw new InvalidOperationException("请先安装 MathType，再转换为 MathType 公式。");
        using var key = Registry.ClassesRoot.OpenSubKey(@"CLSID\" + type.GUID.ToString("B") + @"\LocalServer32");
        string command = Convert.ToString(key?.GetValue("")) ?? "";
        int end = command.IndexOf(".exe", StringComparison.OrdinalIgnoreCase);
        if (end < 0) throw new InvalidOperationException("未找到 MathType 安装路径。");
        string executable = command.Substring(0, end + 4).TrimStart('"');
        if (!File.Exists(executable)) throw new InvalidOperationException("MathType 注册的程序路径不存在，请修复 MathType 安装。");
        return Path.Combine(Path.GetDirectoryName(executable)!, "System", IntPtr.Size == 8 ? "64" : "32", "MT6.dll");
    }

    private sealed class Sdk : IDisposable
    {
        private readonly IntPtr library;
        private readonly Disconnect disconnect;
        public readonly SetEquationDelegate SetEquation;
        public readonly CloseEquationDelegate CloseEquation;

        public Sdk()
        {
            library = LoadLibraryEx(SdkLibraryPath(), IntPtr.Zero, 0x1100);
            if (library == IntPtr.Zero) throw new Win32Exception(Marshal.GetLastWin32Error(), "无法加载已安装的 MathType SDK。");
            try
            {
                disconnect = Function<Disconnect>("MTAPIDisconnect");
                SetEquation = Function<SetEquationDelegate>("MTSetEqnFromLangStr");
                CloseEquation = Function<CloseEquationDelegate>("MTCloseOleObject");
                Check(Function<Connect>("MTAPIConnect")(1, 10), "连接");
            }
            catch { FreeLibrary(library); throw; }
        }

        private T Function<T>(string name) where T : Delegate
        {
            IntPtr address = GetProcAddress(library, name);
            if (address == IntPtr.Zero) throw new EntryPointNotFoundException("MathType SDK 缺少 " + name);
            return Marshal.GetDelegateForFunctionPointer<T>(address);
        }

        public void Dispose() { try { disconnect(); } finally { FreeLibrary(library); } }
    }

    [UnmanagedFunctionPointer(CallingConvention.Winapi)] private delegate int Connect(short mode, short timeout);
    [UnmanagedFunctionPointer(CallingConvention.Winapi)] private delegate int Disconnect();
    [UnmanagedFunctionPointer(CallingConvention.Winapi, CharSet = CharSet.Unicode)] private delegate int SetEquationDelegate(IntPtr equation, int language, string value, int length);
    [UnmanagedFunctionPointer(CallingConvention.Winapi)] private delegate int CloseEquationDelegate(int save, IntPtr equation);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)] private static extern IntPtr LoadLibraryEx(string path, IntPtr file, uint flags);
    [DllImport("kernel32.dll", CharSet = CharSet.Ansi)] private static extern IntPtr GetProcAddress(IntPtr library, string name);
    [DllImport("kernel32.dll")] private static extern bool FreeLibrary(IntPtr library);
    [DllImport("kernel32.dll", SetLastError = true)] private static extern IntPtr GlobalLock(IntPtr memory);
    [DllImport("kernel32.dll")] private static extern bool GlobalUnlock(IntPtr memory);
    [DllImport("kernel32.dll")] private static extern UIntPtr GlobalSize(IntPtr memory);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] private static extern uint RegisterClipboardFormat(string name);
    [DllImport("ole32.dll")] private static extern void ReleaseStgMedium(ref STGMEDIUM medium);
}
#endif
