using System;
using System.Runtime.InteropServices;

namespace LaTeXSnipper.OfficePlugin.OleFormulaObject;

[StructLayout(LayoutKind.Sequential)]
public struct RECT
{
    public int Left;
    public int Top;
    public int Right;
    public int Bottom;
}

[StructLayout(LayoutKind.Sequential)]
public struct SIZE
{
    public int Cx;
    public int Cy;
}

[StructLayout(LayoutKind.Sequential)]
public struct FORMATETC
{
    public short cfFormat;
    public IntPtr ptd;
    public int dwAspect;
    public int lindex;
    public int tymed;
}

[StructLayout(LayoutKind.Sequential)]
public struct STGMEDIUM
{
    public int tymed;
    public IntPtr unionmember;
    public IntPtr pUnkForRelease;
}

[StructLayout(LayoutKind.Sequential)]
public struct MSG
{
    public IntPtr hwnd;
    public uint message;
    public UIntPtr wParam;
    public IntPtr lParam;
    public uint time;
    public int ptX;
    public int ptY;
}

[StructLayout(LayoutKind.Sequential)]
public struct POINTL
{
    public int X;
    public int Y;
}

[StructLayout(LayoutKind.Sequential)]
public struct SIZEL
{
    public int Cx;
    public int Cy;
}

[StructLayout(LayoutKind.Sequential)]
public struct OLEVERB
{
    public int lVerb;
    public IntPtr lpszVerbName;
    public uint fuFlags;
    public uint grfAttribs;
}

[ComImport]
[Guid("00000001-0000-0000-C000-000000000046")]
[InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IClassFactory
{
    [PreserveSig]
    int CreateInstance(IntPtr pUnkOuter, ref Guid riid, out IntPtr ppvObject);

    [PreserveSig]
    int LockServer(bool fLock);
}

[ComImport]
[Guid("00000112-0000-0000-C000-000000000046")]
[InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IOleObject
{
    [PreserveSig] int SetClientSite(IntPtr pClientSite);
    [PreserveSig] int GetClientSite(out IntPtr ppClientSite);
    [PreserveSig] int SetHostNames([MarshalAs(UnmanagedType.LPWStr)] string szContainerApp, [MarshalAs(UnmanagedType.LPWStr)] string szContainerObj);
    [PreserveSig] int Close(uint dwSaveOption);
    [PreserveSig] int SetMoniker(uint dwWhichMoniker, IntPtr pmk);
    [PreserveSig] int GetMoniker(uint dwAssign, uint dwWhichMoniker, out IntPtr ppmk);
    [PreserveSig] int InitFromData(IntPtr pDataObject, bool fCreation, uint dwReserved);
    [PreserveSig] int GetClipboardData(uint dwReserved, out IntPtr ppDataObject);
    [PreserveSig] int DoVerb(int iVerb, IntPtr lpmsg, IntPtr pActiveSite, int lindex, IntPtr hwndParent, IntPtr lprcPosRect);
    [PreserveSig] int EnumVerbs(out IntPtr ppEnumOleVerb);
    [PreserveSig] int Update();
    [PreserveSig] int IsUpToDate();
    [PreserveSig] int GetUserClassID(out Guid pClsid);
    [PreserveSig] int GetUserType(uint dwFormOfType, out IntPtr pszUserType);
    [PreserveSig] int SetExtent(uint dwDrawAspect, ref SIZEL psizel);
    [PreserveSig] int GetExtent(uint dwDrawAspect, out SIZEL psizel);
    [PreserveSig] int Advise(IntPtr pAdvSink, out uint pdwConnection);
    [PreserveSig] int Unadvise(uint dwConnection);
    [PreserveSig] int EnumAdvise(out IntPtr ppenumAdvise);
    [PreserveSig] int GetMiscStatus(uint dwAspect, out uint pdwStatus);
    [PreserveSig] int SetColorScheme(IntPtr pLogpal);
}

[ComImport]
[Guid("0000010E-0000-0000-C000-000000000046")]
[InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IDataObject
{
    [PreserveSig] int GetData(ref FORMATETC pformatetcIn, out STGMEDIUM pmedium);
    [PreserveSig] int GetDataHere(ref FORMATETC pformatetc, ref STGMEDIUM pmedium);
    [PreserveSig] int QueryGetData(ref FORMATETC pformatetc);
    [PreserveSig] int GetCanonicalFormatEtc(ref FORMATETC pformatectIn, out FORMATETC pformatetcOut);
    [PreserveSig] int SetData(ref FORMATETC pformatetc, ref STGMEDIUM pmedium, bool fRelease);
    [PreserveSig] int EnumFormatEtc(uint dwDirection, out IntPtr ppenumFormatEtc);
    [PreserveSig] int DAdvise(ref FORMATETC pformatetc, uint advf, IntPtr pAdvSink, out uint pdwConnection);
    [PreserveSig] int DUnadvise(uint dwConnection);
    [PreserveSig] int EnumDAdvise(out IntPtr ppenumAdvise);
}

[ComImport]
[Guid("0000010D-0000-0000-C000-000000000046")]
[InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IViewObject
{
    [PreserveSig] int Draw(uint dwDrawAspect, int lindex, IntPtr pvAspect, IntPtr ptd, IntPtr hdcTargetDev, IntPtr hdcDraw, IntPtr lprcBounds, IntPtr lprcWBounds, IntPtr pfnContinue, IntPtr dwContinue);
    [PreserveSig] int GetColorSet(uint dwDrawAspect, int lindex, IntPtr pvAspect, IntPtr ptd, IntPtr hicTargetDev, out IntPtr ppColorSet);
    [PreserveSig] int Freeze(uint dwDrawAspect, int lindex, IntPtr pvAspect, out uint pdwFreeze);
    [PreserveSig] int Unfreeze(uint dwFreeze);
    [PreserveSig] int SetAdvise(uint aspects, uint advf, IntPtr pAdvSink);
    [PreserveSig] int GetAdvise(out uint pAspects, out uint pAdvf, out IntPtr ppAdvSink);
}

[ComImport]
[Guid("0000010B-0000-0000-C000-000000000046")]
[InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IPersistStorage
{
    [PreserveSig] int GetClassID(out Guid pClassID);
    [PreserveSig] int IsDirty();
    [PreserveSig] int InitNew(IntPtr pStg);
    [PreserveSig] int Load(IntPtr pStg);
    [PreserveSig] int Save(IntPtr pStgSave, bool fSameAsLoad);
    [PreserveSig] int SaveCompleted(IntPtr pStgNew);
    [PreserveSig] int HandsOffStorage();
}
