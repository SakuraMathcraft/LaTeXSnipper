using System;
using System.Runtime.InteropServices;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.OleFormulaObject;

[ComVisible(true)]
[Guid(OleFormulaObjectIds.ClassIdString)]
[ProgId(OleFormulaObjectIds.ProgId)]
[ClassInterface(ClassInterfaceType.None)]
public sealed class FormulaOleObject : IOleObject, IDataObject, IViewObject, IPersistStorage
{
    private readonly OleFormulaPresentation _presentation;
    private IntPtr _clientSite;
    private uint _viewAdviseAspects;
    private uint _viewAdviseFlags;
    private IntPtr _viewAdviseSink;

    public FormulaOleObject()
    {
        OleServerLog.Write("FormulaOleObject constructing.");
        _presentation = OlePlaceholderPresentationFactory.CreateDefault();
        OleServerLog.Write("FormulaOleObject constructed.");
    }

    public IntPtr QueryInterface(Guid riid)
    {
        if (riid == typeof(IOleObject).GUID)
        {
            return Marshal.GetComInterfaceForObject(this, typeof(IOleObject));
        }

        if (riid == typeof(IDataObject).GUID)
        {
            return Marshal.GetComInterfaceForObject(this, typeof(IDataObject));
        }

        if (riid == typeof(IViewObject).GUID)
        {
            return Marshal.GetComInterfaceForObject(this, typeof(IViewObject));
        }

        if (riid == typeof(IPersistStorage).GUID)
        {
            return Marshal.GetComInterfaceForObject(this, typeof(IPersistStorage));
        }

        if (riid == typeof(object).GUID || riid == new Guid("00000000-0000-0000-C000-000000000046"))
        {
            return Marshal.GetIUnknownForObject(this);
        }

        return IntPtr.Zero;
    }

    public int SetClientSite(IntPtr pClientSite)
    {
        ReleaseClientSite();
        _clientSite = pClientSite;
        if (_clientSite != IntPtr.Zero)
        {
            Marshal.AddRef(_clientSite);
        }

        return ComConstants.SOk;
    }

    public int GetClientSite(out IntPtr ppClientSite)
    {
        ppClientSite = _clientSite;
        if (ppClientSite != IntPtr.Zero)
        {
            Marshal.AddRef(ppClientSite);
        }

        return ComConstants.SOk;
    }

    public int SetHostNames(string szContainerApp, string szContainerObj) => ComConstants.SOk;

    public int Close(uint dwSaveOption)
    {
        if (dwSaveOption == ComConstants.OleCloseSaveIfDirty || dwSaveOption == ComConstants.OleCloseNoSave)
        {
            ReleaseClientSite();
            return ComConstants.SOk;
        }

        return ComConstants.SOk;
    }

    public int SetMoniker(uint dwWhichMoniker, IntPtr pmk) => ComConstants.SOk;

    public int GetMoniker(uint dwAssign, uint dwWhichMoniker, out IntPtr ppmk)
    {
        ppmk = IntPtr.Zero;
        return ComConstants.ENotImpl;
    }

    public int InitFromData(IntPtr pDataObject, bool fCreation, uint dwReserved) => ComConstants.SOk;

    public int GetClipboardData(uint dwReserved, out IntPtr ppDataObject)
    {
        ppDataObject = Marshal.GetComInterfaceForObject(this, typeof(IDataObject));
        return ComConstants.SOk;
    }

    public int DoVerb(int iVerb, IntPtr lpmsg, IntPtr pActiveSite, int lindex, IntPtr hwndParent, IntPtr lprcPosRect)
    {
        return ComConstants.SOk;
    }

    public int EnumVerbs(out IntPtr ppEnumOleVerb)
    {
        ppEnumOleVerb = IntPtr.Zero;
        return ComConstants.ENotImpl;
    }

    public int Update() => ComConstants.SOk;

    public int IsUpToDate() => ComConstants.SOk;

    public int GetUserClassID(out Guid pClsid)
    {
        pClsid = OleFormulaObjectIds.ClassId;
        return ComConstants.SOk;
    }

    public int GetUserType(uint dwFormOfType, out IntPtr pszUserType)
    {
        pszUserType = Marshal.StringToCoTaskMemUni(OleFormulaObjectIds.FriendlyName);
        return ComConstants.SOk;
    }

    public int SetExtent(uint dwDrawAspect, ref SIZEL psizel) => ComConstants.SOk;

    public int GetExtent(uint dwDrawAspect, out SIZEL psizel)
    {
        if (dwDrawAspect != ComConstants.DvAspectContent)
        {
            psizel = default;
            return ComConstants.DvEDvaspect;
        }

        psizel = new SIZEL
        {
            Cx = PointsToHimetric(_presentation.Payload.WidthPoints),
            Cy = PointsToHimetric(_presentation.Payload.HeightPoints)
        };
        return ComConstants.SOk;
    }

    public int Advise(IntPtr pAdvSink, out uint pdwConnection)
    {
        pdwConnection = 0;
        return ComConstants.ENotImpl;
    }

    public int Unadvise(uint dwConnection) => ComConstants.ENotImpl;

    public int EnumAdvise(out IntPtr ppenumAdvise)
    {
        ppenumAdvise = IntPtr.Zero;
        return ComConstants.ENotImpl;
    }

    public int GetMiscStatus(uint dwAspect, out uint pdwStatus)
    {
        pdwStatus = ComConstants.OleMiscRecomposeOnResize
            | ComConstants.OleMiscInsideOut
            | ComConstants.OleMiscActivateWhenVisible;
        return ComConstants.SOk;
    }

    public int SetColorScheme(IntPtr pLogpal) => ComConstants.SOk;

    public int GetData(ref FORMATETC pformatetcIn, out STGMEDIUM pmedium)
    {
        pmedium = default;
        int queryResult = QueryGetData(ref pformatetcIn);
        if (queryResult != ComConstants.SOk)
        {
            return queryResult;
        }

        IntPtr hemf = NativeMethods.SetEnhMetaFileBits((uint)_presentation.EnhancedMetafile.Length, _presentation.EnhancedMetafile);
        if (hemf == IntPtr.Zero)
        {
            return ComConstants.EFail;
        }

        pmedium = new STGMEDIUM
        {
            tymed = ComConstants.TymedEnhmf,
            unionmember = hemf,
            pUnkForRelease = IntPtr.Zero
        };
        return ComConstants.SOk;
    }

    public int GetDataHere(ref FORMATETC pformatetc, ref STGMEDIUM pmedium) => ComConstants.ENotImpl;

    public int QueryGetData(ref FORMATETC pformatetc)
    {
        if (pformatetc.dwAspect != ComConstants.DvAspectContent)
        {
            return ComConstants.DvEDvaspect;
        }

        if ((pformatetc.tymed & ComConstants.TymedEnhmf) == 0)
        {
            return ComConstants.DvETymed;
        }

        return pformatetc.cfFormat == ComConstants.CfEnhmetafile
            ? ComConstants.SOk
            : ComConstants.DvEFormatEtc;
    }

    public int GetCanonicalFormatEtc(ref FORMATETC pformatectIn, out FORMATETC pformatetcOut)
    {
        pformatetcOut = pformatectIn;
        pformatetcOut.ptd = IntPtr.Zero;
        return ComConstants.SFalse;
    }

    public int SetData(ref FORMATETC pformatetc, ref STGMEDIUM pmedium, bool fRelease) => ComConstants.ENotImpl;

    public int EnumFormatEtc(uint dwDirection, out IntPtr ppenumFormatEtc)
    {
        ppenumFormatEtc = IntPtr.Zero;
        return ComConstants.ENotImpl;
    }

    public int DAdvise(ref FORMATETC pformatetc, uint advf, IntPtr pAdvSink, out uint pdwConnection)
    {
        pdwConnection = 0;
        return ComConstants.ENotImpl;
    }

    public int DUnadvise(uint dwConnection) => ComConstants.ENotImpl;

    public int EnumDAdvise(out IntPtr ppenumAdvise)
    {
        ppenumAdvise = IntPtr.Zero;
        return ComConstants.ENotImpl;
    }

    public int Draw(uint dwDrawAspect, int lindex, IntPtr pvAspect, IntPtr ptd, IntPtr hdcTargetDev, IntPtr hdcDraw, IntPtr lprcBounds, IntPtr lprcWBounds, IntPtr pfnContinue, IntPtr dwContinue)
    {
        if (dwDrawAspect != ComConstants.DvAspectContent)
        {
            return ComConstants.DvEDvaspect;
        }

        if (hdcDraw == IntPtr.Zero || lprcBounds == IntPtr.Zero)
        {
            return ComConstants.EPointer;
        }

        IntPtr hemf = NativeMethods.SetEnhMetaFileBits((uint)_presentation.EnhancedMetafile.Length, _presentation.EnhancedMetafile);
        if (hemf == IntPtr.Zero)
        {
            return ComConstants.EFail;
        }

        try
        {
            RECT bounds = Marshal.PtrToStructure<RECT>(lprcBounds);
            return NativeMethods.PlayEnhMetaFile(hdcDraw, hemf, ref bounds) ? ComConstants.SOk : ComConstants.EFail;
        }
        finally
        {
            NativeMethods.DeleteEnhMetaFile(hemf);
        }
    }

    public int GetColorSet(uint dwDrawAspect, int lindex, IntPtr pvAspect, IntPtr ptd, IntPtr hicTargetDev, out IntPtr ppColorSet)
    {
        ppColorSet = IntPtr.Zero;
        return ComConstants.SFalse;
    }

    public int Freeze(uint dwDrawAspect, int lindex, IntPtr pvAspect, out uint pdwFreeze)
    {
        pdwFreeze = 0;
        return ComConstants.ENotImpl;
    }

    public int Unfreeze(uint dwFreeze) => ComConstants.ENotImpl;

    public int SetAdvise(uint aspects, uint advf, IntPtr pAdvSink)
    {
        _viewAdviseAspects = aspects;
        _viewAdviseFlags = advf;
        _viewAdviseSink = pAdvSink;
        return ComConstants.SOk;
    }

    public int GetAdvise(out uint pAspects, out uint pAdvf, out IntPtr ppAdvSink)
    {
        pAspects = _viewAdviseAspects;
        pAdvf = _viewAdviseFlags;
        ppAdvSink = _viewAdviseSink;
        if (ppAdvSink != IntPtr.Zero)
        {
            Marshal.AddRef(ppAdvSink);
        }

        return ComConstants.SOk;
    }

    public int GetClassID(out Guid pClassID)
    {
        pClassID = OleFormulaObjectIds.ClassId;
        return ComConstants.SOk;
    }

    public int IsDirty() => ComConstants.SFalse;

    public int InitNew(IntPtr pStg) => ComConstants.SOk;

    public int Load(IntPtr pStg) => ComConstants.SOk;

    public int Save(IntPtr pStgSave, bool fSameAsLoad) => ComConstants.SOk;

    public int SaveCompleted(IntPtr pStgNew) => ComConstants.SOk;

    public int HandsOffStorage() => ComConstants.SOk;

    private void ReleaseClientSite()
    {
        if (_clientSite != IntPtr.Zero)
        {
            Marshal.Release(_clientSite);
            _clientSite = IntPtr.Zero;
        }
    }

    private static int PointsToHimetric(double points)
    {
        return (int)Math.Ceiling(points * 2540d / 72d);
    }
}
