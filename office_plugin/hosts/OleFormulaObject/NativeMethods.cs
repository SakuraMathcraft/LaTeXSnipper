using System;
using System.Runtime.InteropServices;

namespace LaTeXSnipper.OfficePlugin.OleFormulaObject;

internal static class NativeMethods
{
    [DllImport("ole32.dll")]
    public static extern int CoRegisterClassObject(
        ref Guid rclsid,
        [MarshalAs(UnmanagedType.Interface)] IClassFactory pUnk,
        uint dwClsContext,
        uint flags,
        out uint lpdwRegister);

    [DllImport("ole32.dll")]
    public static extern int CoRevokeClassObject(uint dwRegister);

    [DllImport("ole32.dll")]
    public static extern int CoResumeClassObjects();

    [DllImport("ole32.dll")]
    public static extern int OleInitialize(IntPtr pvReserved);

    [DllImport("ole32.dll")]
    public static extern void OleUninitialize();

    [DllImport("gdi32.dll", SetLastError = true)]
    public static extern IntPtr SetEnhMetaFileBits(uint cbBuffer, byte[] lpData);

    [DllImport("gdi32.dll", SetLastError = true)]
    public static extern bool DeleteEnhMetaFile(IntPtr hemf);

    [DllImport("gdi32.dll", SetLastError = true)]
    public static extern bool PlayEnhMetaFile(IntPtr hdc, IntPtr hemf, ref RECT lpRect);
}
