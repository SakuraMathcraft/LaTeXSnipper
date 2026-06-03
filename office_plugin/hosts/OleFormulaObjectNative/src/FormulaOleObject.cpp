#include "FormulaOleObject.h"

#include "NativeLog.h"
#include "OleFormulaIds.h"
#include "PendingPayload.h"
#include "StorageUtil.h"
#include "Win32Check.h"

#include <atlconv.h>
#include <comdef.h>
#include <new>
#include <vector>

namespace
{
volatile LONG g_objectCount = 0;
volatile LONG g_lockCount = 0;

void LogInterfaceQuery(REFIID iid, HRESULT result)
{
    LPOLESTR iidText = nullptr;
    if (FAILED(StringFromIID(iid, &iidText)))
    {
        return;
    }

    wchar_t message[160]{};
    swprintf_s(message, L"FormulaOleObject QueryInterface %s -> 0x%08X", iidText, static_cast<unsigned int>(result));
    WriteNativeOleLog(message);
    CoTaskMemFree(iidText);
}

HRESULT ValidateContentAspect(DWORD aspect)
{
    return aspect == DVASPECT_CONTENT ? S_OK : DV_E_DVASPECT;
}

HGLOBAL CreateMetaFilePictFromEnhancedMetafile(const FormulaPresentation& presentation)
{
    HENHMETAFILE enhancedMetafile = CopyEnhMetaFileFromBytes(presentation.enhancedMetafile);
    if (enhancedMetafile == nullptr)
    {
        return nullptr;
    }

    HDC screen = GetDC(nullptr);
    if (screen == nullptr)
    {
        DeleteEnhMetaFile(enhancedMetafile);
        return nullptr;
    }

    UINT byteCount = GetWinMetaFileBits(enhancedMetafile, 0, nullptr, MM_ANISOTROPIC, screen);
    std::vector<BYTE> bytes(byteCount);
    if (byteCount == 0 || GetWinMetaFileBits(enhancedMetafile, byteCount, bytes.data(), MM_ANISOTROPIC, screen) == 0)
    {
        ReleaseDC(nullptr, screen);
        DeleteEnhMetaFile(enhancedMetafile);
        return nullptr;
    }

    ReleaseDC(nullptr, screen);
    DeleteEnhMetaFile(enhancedMetafile);

    HMETAFILE metafile = SetMetaFileBitsEx(byteCount, bytes.data());
    if (metafile == nullptr)
    {
        return nullptr;
    }

    HGLOBAL handle = GlobalAlloc(GMEM_MOVEABLE | GMEM_ZEROINIT, sizeof(METAFILEPICT));
    if (handle == nullptr)
    {
        DeleteMetaFile(metafile);
        return nullptr;
    }

    auto* picture = static_cast<METAFILEPICT*>(GlobalLock(handle));
    if (picture == nullptr)
    {
        GlobalFree(handle);
        DeleteMetaFile(metafile);
        return nullptr;
    }

    picture->mm = MM_ANISOTROPIC;
    picture->xExt = presentation.himetricSize.cx;
    picture->yExt = presentation.himetricSize.cy;
    picture->hMF = metafile;
    GlobalUnlock(handle);
    return handle;
}
}

LONG GetNativeOleObjectCount()
{
    return g_objectCount;
}

LONG GetNativeOleLockCount()
{
    return g_lockCount;
}

FormulaOleObject::FormulaOleObject()
    : presentation_(CreatePresentationFromPayload(ConsumePendingPayload()))
{
    if (presentation_.latex.empty())
    {
        presentation_ = CreatePlaceholderPresentation(kFormulaDefaultLatex);
    }

    WriteNativeOleLog(L"FormulaOleObject constructed.");
    InterlockedIncrement(&g_objectCount);
}

FormulaOleObject::~FormulaOleObject()
{
    WriteNativeOleLog(L"FormulaOleObject destructed.");
    InterlockedDecrement(&g_objectCount);
}

void FormulaOleObject::NotifyPresentationChanged()
{
    if (viewAdviseSink_ != nullptr)
    {
        viewAdviseSink_->OnViewChange(DVASPECT_CONTENT, -1);
    }

    if (objectAdviseSink_ != nullptr)
    {
        objectAdviseSink_->OnViewChange(DVASPECT_CONTENT, -1);
    }

    if (dataAdviseSink_ != nullptr)
    {
        STGMEDIUM medium{};
        if (SUCCEEDED(GetData(&dataAdviseFormat_, &medium)))
        {
            dataAdviseSink_->OnDataChange(&dataAdviseFormat_, &medium);
            ReleaseStgMedium(&medium);
        }
    }

    if (clientSite_ != nullptr)
    {
        clientSite_->SaveObject();
    }
}

STDMETHODIMP FormulaOleObject::QueryInterface(REFIID iid, void** object)
{
    if (object == nullptr)
    {
        return E_POINTER;
    }

    if (iid == IID_IUnknown || iid == IID_IOleObject)
    {
        *object = static_cast<IOleObject*>(this);
    }
    else if (iid == IID_IDataObject)
    {
        *object = static_cast<IDataObject*>(this);
    }
    else if (iid == IID_IViewObject)
    {
        *object = static_cast<IViewObject*>(this);
    }
    else if (iid == IID_IViewObject2)
    {
        *object = static_cast<IViewObject2*>(this);
    }
    else if (iid == IID_IRunnableObject)
    {
        *object = static_cast<IRunnableObject*>(this);
    }
    else if (iid == IID_IOleCache)
    {
        *object = static_cast<IOleCache*>(this);
    }
    else if (iid == IID_IExternalConnection)
    {
        *object = static_cast<IExternalConnection*>(this);
    }
    else if (iid == IID_IPersist || iid == IID_IPersistStorage)
    {
        *object = static_cast<IPersistStorage*>(this);
    }
    else
    {
        *object = nullptr;
        LogInterfaceQuery(iid, E_NOINTERFACE);
        return E_NOINTERFACE;
    }

    AddRef();
    LogInterfaceQuery(iid, S_OK);
    return S_OK;
}

STDMETHODIMP_(ULONG) FormulaOleObject::AddRef()
{
    return static_cast<ULONG>(InterlockedIncrement(&refCount_));
}

STDMETHODIMP_(ULONG) FormulaOleObject::Release()
{
    const ULONG remaining = static_cast<ULONG>(InterlockedDecrement(&refCount_));
    if (remaining == 0)
    {
        delete this;
    }

    return remaining;
}

STDMETHODIMP FormulaOleObject::SetClientSite(IOleClientSite* clientSite)
{
    WriteNativeOleLog(L"FormulaOleObject SetClientSite.");
    clientSite_ = clientSite;
    return S_OK;
}

STDMETHODIMP FormulaOleObject::GetClientSite(IOleClientSite** clientSite)
{
    if (clientSite == nullptr)
    {
        return E_POINTER;
    }

    return clientSite_.CopyTo(clientSite);
}

STDMETHODIMP FormulaOleObject::SetHostNames(LPCOLESTR, LPCOLESTR)
{
    return S_OK;
}

STDMETHODIMP FormulaOleObject::Close(DWORD)
{
    clientSite_.Release();
    return S_OK;
}

STDMETHODIMP FormulaOleObject::SetMoniker(DWORD, IMoniker*)
{
    return S_OK;
}

STDMETHODIMP FormulaOleObject::GetMoniker(DWORD, DWORD, IMoniker** moniker)
{
    if (moniker == nullptr)
    {
        return E_POINTER;
    }

    *moniker = nullptr;
    return E_NOTIMPL;
}

STDMETHODIMP FormulaOleObject::InitFromData(IDataObject*, BOOL, DWORD)
{
    return S_OK;
}

STDMETHODIMP FormulaOleObject::GetClipboardData(DWORD, IDataObject** dataObject)
{
    if (dataObject == nullptr)
    {
        return E_POINTER;
    }

    return QueryInterface(IID_IDataObject, reinterpret_cast<void**>(dataObject));
}

STDMETHODIMP FormulaOleObject::DoVerb(LONG, LPMSG, IOleClientSite*, LONG, HWND, LPCRECT)
{
    WriteNativeOleLog(L"FormulaOleObject DoVerb.");
    return S_OK;
}

STDMETHODIMP FormulaOleObject::EnumVerbs(IEnumOLEVERB** enumOleVerb)
{
    if (enumOleVerb == nullptr)
    {
        return E_POINTER;
    }

    *enumOleVerb = nullptr;
    return OLEOBJ_E_NOVERBS;
}

STDMETHODIMP FormulaOleObject::Update()
{
    return S_OK;
}

STDMETHODIMP FormulaOleObject::IsUpToDate()
{
    return S_OK;
}

STDMETHODIMP FormulaOleObject::GetUserClassID(CLSID* classId)
{
    if (classId == nullptr)
    {
        return E_POINTER;
    }

    *classId = CLSID_LaTeXSnipperFormula;
    return S_OK;
}

STDMETHODIMP FormulaOleObject::GetUserType(DWORD, LPOLESTR* userType)
{
    if (userType == nullptr)
    {
        return E_POINTER;
    }

    const size_t length = wcslen(kFormulaFriendlyName) + 1;
    *userType = static_cast<LPOLESTR>(CoTaskMemAlloc(length * sizeof(wchar_t)));
    if (*userType == nullptr)
    {
        return E_OUTOFMEMORY;
    }

    wcscpy_s(*userType, length, kFormulaFriendlyName);
    return S_OK;
}

STDMETHODIMP FormulaOleObject::SetExtent(DWORD drawAspect, SIZEL* size)
{
    if (size == nullptr)
    {
        return E_POINTER;
    }

    HRESULT aspectResult = ValidateContentAspect(drawAspect);
    if (FAILED(aspectResult))
    {
        return aspectResult;
    }

    presentation_.himetricSize = {size->cx, size->cy};
    return S_OK;
}

STDMETHODIMP FormulaOleObject::GetExtent(DWORD drawAspect, SIZEL* size)
{
    if (size == nullptr)
    {
        return E_POINTER;
    }

    HRESULT aspectResult = ValidateContentAspect(drawAspect);
    if (FAILED(aspectResult))
    {
        return aspectResult;
    }

    size->cx = presentation_.himetricSize.cx;
    size->cy = presentation_.himetricSize.cy;
    return S_OK;
}

STDMETHODIMP FormulaOleObject::Advise(IAdviseSink* adviseSink, DWORD* connection)
{
    if (connection == nullptr)
    {
        return E_POINTER;
    }

    if (adviseSink == nullptr)
    {
        return E_POINTER;
    }

    objectAdviseSink_ = adviseSink;
    *connection = 1;
    return S_OK;
}

STDMETHODIMP FormulaOleObject::Unadvise(DWORD connection)
{
    if (connection != 1 || objectAdviseSink_ == nullptr)
    {
        return OLE_E_NOCONNECTION;
    }

    objectAdviseSink_.Release();
    return S_OK;
}

STDMETHODIMP FormulaOleObject::EnumAdvise(IEnumSTATDATA** enumAdvise)
{
    if (enumAdvise == nullptr)
    {
        return E_POINTER;
    }

    *enumAdvise = nullptr;
    return S_FALSE;
}

STDMETHODIMP FormulaOleObject::GetMiscStatus(DWORD aspect, DWORD* status)
{
    WriteNativeOleLog(L"FormulaOleObject GetMiscStatus.");
    if (status == nullptr)
    {
        return E_POINTER;
    }

    HRESULT aspectResult = ValidateContentAspect(aspect);
    if (FAILED(aspectResult))
    {
        return aspectResult;
    }

    *status = OLEMISC_STATIC
        | OLEMISC_CANTLINKINSIDE
        | OLEMISC_RENDERINGISDEVICEINDEPENDENT
        | OLEMISC_NOUIACTIVATE
        | OLEMISC_IGNOREACTIVATEWHENVISIBLE
        | OLEMISC_SETCLIENTSITEFIRST;
    return S_OK;
}

STDMETHODIMP FormulaOleObject::SetColorScheme(LOGPALETTE*)
{
    return S_OK;
}

STDMETHODIMP FormulaOleObject::GetData(FORMATETC* format, STGMEDIUM* medium)
{
    WriteNativeOleLog(L"FormulaOleObject GetData.");
    if (format == nullptr || medium == nullptr)
    {
        return E_POINTER;
    }

    HRESULT queryResult = QueryGetData(format);
    if (FAILED(queryResult))
    {
        return queryResult;
    }

    if (format->cfFormat == CF_ENHMETAFILE)
    {
        HENHMETAFILE metafile = CopyEnhMetaFileFromBytes(presentation_.enhancedMetafile);
        if (metafile == nullptr)
        {
            return E_FAIL;
        }

        medium->tymed = TYMED_ENHMF;
        medium->hEnhMetaFile = metafile;
        medium->pUnkForRelease = nullptr;
        return S_OK;
    }

    HGLOBAL metafilePict = CreateMetaFilePictFromEnhancedMetafile(presentation_);
    if (metafilePict == nullptr)
    {
        return E_FAIL;
    }

    medium->tymed = TYMED_MFPICT;
    medium->hMetaFilePict = metafilePict;
    medium->pUnkForRelease = nullptr;
    return S_OK;
}

STDMETHODIMP FormulaOleObject::GetDataHere(FORMATETC*, STGMEDIUM*)
{
    return DATA_E_FORMATETC;
}

STDMETHODIMP FormulaOleObject::QueryGetData(FORMATETC* format)
{
    if (format == nullptr)
    {
        return E_POINTER;
    }

    wchar_t message[160]{};
    swprintf_s(
        message,
        L"FormulaOleObject QueryGetData cf=%u tymed=0x%08X aspect=%u lindex=%ld",
        static_cast<unsigned int>(format->cfFormat),
        static_cast<unsigned int>(format->tymed),
        static_cast<unsigned int>(format->dwAspect),
        format->lindex);
    WriteNativeOleLog(message);

    if (format->cfFormat == CF_ENHMETAFILE)
    {
        return (format->tymed & TYMED_ENHMF) == 0 ? DV_E_TYMED : ValidateContentAspect(format->dwAspect);
    }

    if (format->cfFormat == CF_METAFILEPICT)
    {
        return (format->tymed & TYMED_MFPICT) == 0 ? DV_E_TYMED : ValidateContentAspect(format->dwAspect);
    }

    return DV_E_FORMATETC;
}

STDMETHODIMP FormulaOleObject::GetCanonicalFormatEtc(FORMATETC*, FORMATETC* output)
{
    if (output == nullptr)
    {
        return E_POINTER;
    }

    ZeroMemory(output, sizeof(*output));
    output->ptd = nullptr;
    return DATA_S_SAMEFORMATETC;
}

STDMETHODIMP FormulaOleObject::SetData(FORMATETC* format, STGMEDIUM* medium, BOOL release)
{
    if (format == nullptr || medium == nullptr)
    {
        return E_POINTER;
    }

    if (release)
    {
        ReleaseStgMedium(medium);
    }

    return S_OK;
}

STDMETHODIMP FormulaOleObject::EnumFormatEtc(DWORD, IEnumFORMATETC** enumFormatEtc)
{
    if (enumFormatEtc == nullptr)
    {
        return E_POINTER;
    }

    *enumFormatEtc = nullptr;
    return E_NOTIMPL;
}

STDMETHODIMP FormulaOleObject::DAdvise(FORMATETC* format, DWORD adviseFlags, IAdviseSink* adviseSink, DWORD* connection)
{
    if (connection == nullptr)
    {
        return E_POINTER;
    }

    if (format == nullptr || adviseSink == nullptr)
    {
        return E_POINTER;
    }

    HRESULT queryResult = QueryGetData(format);
    if (FAILED(queryResult))
    {
        return queryResult;
    }

    dataAdviseSink_ = adviseSink;
    dataAdviseFormat_ = *format;
    dataAdviseFlags_ = adviseFlags;
    *connection = 1;
    return S_OK;
}

STDMETHODIMP FormulaOleObject::DUnadvise(DWORD connection)
{
    if (connection != 1 || dataAdviseSink_ == nullptr)
    {
        return OLE_E_NOCONNECTION;
    }

    dataAdviseSink_.Release();
    dataAdviseFormat_ = {};
    dataAdviseFlags_ = 0;
    return S_OK;
}

STDMETHODIMP FormulaOleObject::EnumDAdvise(IEnumSTATDATA** enumAdvise)
{
    if (enumAdvise == nullptr)
    {
        return E_POINTER;
    }

    *enumAdvise = nullptr;
    return S_FALSE;
}

STDMETHODIMP FormulaOleObject::Draw(DWORD drawAspect, LONG, void*, DVTARGETDEVICE*, HDC, HDC drawContext, LPCRECTL bounds, LPCRECTL, BOOL(__stdcall*)(ULONG_PTR), ULONG_PTR)
{
    WriteNativeOleLog(L"FormulaOleObject Draw.");
    HRESULT aspectResult = ValidateContentAspect(drawAspect);
    if (FAILED(aspectResult))
    {
        return aspectResult;
    }

    if (drawContext == nullptr || bounds == nullptr)
    {
        return E_POINTER;
    }

    HENHMETAFILE metafile = CopyEnhMetaFileFromBytes(presentation_.enhancedMetafile);
    if (metafile == nullptr)
    {
        return E_FAIL;
    }

    RECT rect{bounds->left, bounds->top, bounds->right, bounds->bottom};
    BOOL played = PlayEnhMetaFile(drawContext, metafile, &rect);
    DeleteEnhMetaFile(metafile);
    return played ? S_OK : HResultFromWin32LastError();
}

STDMETHODIMP FormulaOleObject::GetColorSet(DWORD, LONG, void*, DVTARGETDEVICE*, HDC, LOGPALETTE** colorSet)
{
    if (colorSet == nullptr)
    {
        return E_POINTER;
    }

    *colorSet = nullptr;
    return S_FALSE;
}

STDMETHODIMP FormulaOleObject::Freeze(DWORD, LONG, void*, DWORD* freeze)
{
    if (freeze == nullptr)
    {
        return E_POINTER;
    }

    *freeze = 0;
    return E_NOTIMPL;
}

STDMETHODIMP FormulaOleObject::Unfreeze(DWORD)
{
    return E_NOTIMPL;
}

STDMETHODIMP FormulaOleObject::SetAdvise(DWORD aspects, DWORD advf, IAdviseSink* adviseSink)
{
    WriteNativeOleLog(L"FormulaOleObject SetAdvise.");
    viewAdviseAspects_ = aspects;
    viewAdviseFlags_ = advf;
    viewAdviseSink_ = adviseSink;
    return S_OK;
}

STDMETHODIMP FormulaOleObject::GetAdvise(DWORD* aspects, DWORD* advf, IAdviseSink** adviseSink)
{
    if (aspects != nullptr)
    {
        *aspects = viewAdviseAspects_;
    }

    if (advf != nullptr)
    {
        *advf = viewAdviseFlags_;
    }

    if (adviseSink != nullptr)
    {
        return viewAdviseSink_.CopyTo(adviseSink);
    }

    return S_OK;
}

STDMETHODIMP FormulaOleObject::GetExtent(DWORD drawAspect, LONG, DVTARGETDEVICE*, SIZEL* size)
{
    if (size == nullptr)
    {
        return E_POINTER;
    }

    HRESULT aspectResult = ValidateContentAspect(drawAspect);
    if (FAILED(aspectResult))
    {
        return aspectResult;
    }

    size->cx = presentation_.himetricSize.cx;
    size->cy = presentation_.himetricSize.cy;
    return S_OK;
}

STDMETHODIMP FormulaOleObject::GetRunningClass(LPCLSID classId)
{
    if (classId == nullptr)
    {
        return E_POINTER;
    }

    *classId = CLSID_LaTeXSnipperFormula;
    return S_OK;
}

STDMETHODIMP FormulaOleObject::Run(LPBINDCTX)
{
    WriteNativeOleLog(L"FormulaOleObject Run.");
    return S_OK;
}

STDMETHODIMP_(BOOL) FormulaOleObject::IsRunning()
{
    WriteNativeOleLog(L"FormulaOleObject IsRunning.");
    return TRUE;
}

STDMETHODIMP FormulaOleObject::LockRunning(BOOL lock, BOOL)
{
    WriteNativeOleLog(L"FormulaOleObject LockRunning.");
    if (lock)
    {
        InterlockedIncrement(&g_lockCount);
    }
    else
    {
        InterlockedDecrement(&g_lockCount);
    }

    return S_OK;
}

STDMETHODIMP FormulaOleObject::SetContainedObject(BOOL)
{
    WriteNativeOleLog(L"FormulaOleObject SetContainedObject.");
    return S_OK;
}

STDMETHODIMP FormulaOleObject::Cache(FORMATETC* format, DWORD, DWORD* connection)
{
    WriteNativeOleLog(L"FormulaOleObject Cache.");
    if (connection == nullptr)
    {
        return E_POINTER;
    }

    if (format != nullptr && format->cfFormat != 0)
    {
        HRESULT queryResult = QueryGetData(format);
        if (FAILED(queryResult))
        {
            return queryResult;
        }
    }

    *connection = cacheConnection_++;
    return S_OK;
}

STDMETHODIMP FormulaOleObject::Uncache(DWORD)
{
    WriteNativeOleLog(L"FormulaOleObject Uncache.");
    return S_OK;
}

STDMETHODIMP FormulaOleObject::EnumCache(IEnumSTATDATA** enumStatData)
{
    WriteNativeOleLog(L"FormulaOleObject EnumCache.");
    if (enumStatData == nullptr)
    {
        return E_POINTER;
    }

    *enumStatData = nullptr;
    return E_NOTIMPL;
}

STDMETHODIMP FormulaOleObject::InitCache(IDataObject*)
{
    WriteNativeOleLog(L"FormulaOleObject InitCache.");
    return S_OK;
}

STDMETHODIMP_(DWORD) FormulaOleObject::AddConnection(DWORD, DWORD)
{
    WriteNativeOleLog(L"FormulaOleObject AddConnection.");
    return static_cast<DWORD>(InterlockedIncrement(&g_lockCount));
}

STDMETHODIMP_(DWORD) FormulaOleObject::ReleaseConnection(DWORD, DWORD, BOOL)
{
    WriteNativeOleLog(L"FormulaOleObject ReleaseConnection.");
    LONG value = InterlockedDecrement(&g_lockCount);
    return value < 0 ? 0 : static_cast<DWORD>(value);
}

STDMETHODIMP FormulaOleObject::GetClassID(CLSID* classId)
{
    if (classId == nullptr)
    {
        return E_POINTER;
    }

    *classId = CLSID_LaTeXSnipperFormula;
    return S_OK;
}

STDMETHODIMP FormulaOleObject::IsDirty()
{
    return dirty_ ? S_OK : S_FALSE;
}

STDMETHODIMP FormulaOleObject::InitNew(IStorage* storage)
{
    WriteNativeOleLog(L"FormulaOleObject InitNew.");
    if (storage == nullptr)
    {
        return E_POINTER;
    }

    HRESULT result = WriteClassStg(storage, CLSID_LaTeXSnipperFormula);
    if (FAILED(result))
    {
        return result;
    }

    CLIPFORMAT nativeFormat = static_cast<CLIPFORMAT>(RegisterClipboardFormatW(kFormulaFriendlyName));
    result = WriteFmtUserTypeStg(storage, nativeFormat, const_cast<LPOLESTR>(kFormulaFriendlyName));
    if (FAILED(result))
    {
        return result;
    }

    storage_ = storage;
    dirty_ = true;
    return S_OK;
}

STDMETHODIMP FormulaOleObject::Load(IStorage* storage)
{
    FormulaPresentation loaded;
    HRESULT result = LoadPresentationFromStorage(storage, &loaded);
    if (SUCCEEDED(result))
    {
        storage_ = storage;
        presentation_ = std::move(loaded);
        dirty_ = false;
    }

    return SUCCEEDED(result) ? S_OK : result;
}

STDMETHODIMP FormulaOleObject::Save(IStorage* storage, BOOL)
{
    HRESULT result = SavePresentationToStorage(storage, presentation_);
    if (SUCCEEDED(result))
    {
        dirty_ = false;
    }

    return result;
}

STDMETHODIMP FormulaOleObject::SaveCompleted(IStorage*)
{
    if (storage_ != nullptr)
    {
        storage_->Commit(STGC_DEFAULT);
    }

    return S_OK;
}

STDMETHODIMP FormulaOleObject::HandsOffStorage()
{
    storage_.Release();
    return S_OK;
}

STDMETHODIMP FormulaClassFactory::QueryInterface(REFIID iid, void** object)
{
    if (object == nullptr)
    {
        return E_POINTER;
    }

    if (iid == IID_IUnknown || iid == IID_IClassFactory)
    {
        *object = static_cast<IClassFactory*>(this);
        AddRef();
        return S_OK;
    }

    *object = nullptr;
    return E_NOINTERFACE;
}

STDMETHODIMP_(ULONG) FormulaClassFactory::AddRef()
{
    return static_cast<ULONG>(InterlockedIncrement(&refCount_));
}

STDMETHODIMP_(ULONG) FormulaClassFactory::Release()
{
    const ULONG remaining = static_cast<ULONG>(InterlockedDecrement(&refCount_));
    if (remaining == 0)
    {
        delete this;
    }

    return remaining;
}

STDMETHODIMP FormulaClassFactory::CreateInstance(IUnknown* outer, REFIID iid, void** object)
{
    WriteNativeOleLog(L"ClassFactory CreateInstance entered.");
    if (object == nullptr)
    {
        return E_POINTER;
    }

    *object = nullptr;
    if (outer != nullptr)
    {
        WriteNativeOleLog(L"ClassFactory rejected aggregation.");
        return CLASS_E_NOAGGREGATION;
    }

    FormulaOleObject* formulaObject = new (std::nothrow) FormulaOleObject();
    if (formulaObject == nullptr)
    {
        WriteNativeOleLog(L"FormulaOleObject allocation failed.");
        return E_OUTOFMEMORY;
    }

    HRESULT queryResult = formulaObject->QueryInterface(iid, object);
    WriteNativeOleLog(SUCCEEDED(queryResult) ? L"ClassFactory QueryInterface succeeded." : L"ClassFactory QueryInterface failed.");
    formulaObject->Release();
    return queryResult;
}

STDMETHODIMP FormulaClassFactory::LockServer(BOOL lock)
{
    if (lock)
    {
        InterlockedIncrement(&g_lockCount);
    }
    else
    {
        InterlockedDecrement(&g_lockCount);
    }

    return S_OK;
}
