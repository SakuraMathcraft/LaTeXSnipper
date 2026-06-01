#include "FormulaOleObject.h"

#include "NativeLog.h"
#include "OleFormulaIds.h"
#include "PendingPayload.h"
#include "StorageUtil.h"
#include "Win32Check.h"

#include <atlconv.h>
#include <comdef.h>
#include <new>
#include <shellapi.h>

namespace
{
volatile LONG g_objectCount = 0;
volatile LONG g_lockCount = 0;

HRESULT ValidateContentAspect(DWORD aspect)
{
    return aspect == DVASPECT_CONTENT ? S_OK : DV_E_DVASPECT;
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
    else if (iid == IID_IPersist || iid == IID_IPersistStorage)
    {
        *object = static_cast<IPersistStorage*>(this);
    }
    else
    {
        *object = nullptr;
        return E_NOINTERFACE;
    }

    AddRef();
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

STDMETHODIMP FormulaOleObject::DoVerb(LONG verb, LPMSG, IOleClientSite*, LONG, HWND parentWindow, LPCRECT)
{
    if (verb == OLEIVERB_PRIMARY || verb == OLEIVERB_SHOW || verb == OLEIVERB_OPEN)
    {
        StoreEditorPayload(presentation_.payloadJson);
        std::wstring renderer = ResolveRendererPath();
        if (renderer.empty())
        {
            return OLEOBJ_S_CANNOT_DOVERB_NOW;
        }

        SHELLEXECUTEINFOW executeInfo{};
        executeInfo.cbSize = sizeof(executeInfo);
        executeInfo.fMask = SEE_MASK_NOCLOSEPROCESS;
        executeInfo.hwnd = parentWindow;
        executeInfo.lpVerb = L"open";
        executeInfo.lpFile = renderer.c_str();
        executeInfo.lpParameters = L"/EditPayload";
        executeInfo.nShow = SW_SHOWNORMAL;
        if (!ShellExecuteExW(&executeInfo))
        {
            return OLEOBJ_S_CANNOT_DOVERB_NOW;
        }

        if (executeInfo.hProcess != nullptr)
        {
            WaitForSingleObject(executeInfo.hProcess, INFINITE);
            CloseHandle(executeInfo.hProcess);
        }

        std::wstring updatedPayload = ConsumeEditorPayloadResult();
        if (updatedPayload.empty() || updatedPayload == presentation_.payloadJson)
        {
            return S_OK;
        }

        FormulaPresentation updatedPresentation = CreatePresentationFromPayload(updatedPayload);
        if (updatedPresentation.latex.empty())
        {
            return OLEOBJ_S_CANNOT_DOVERB_NOW;
        }

        presentation_ = std::move(updatedPresentation);
        dirty_ = true;
        if (viewAdviseSink_ != nullptr)
        {
            viewAdviseSink_->OnViewChange(DVASPECT_CONTENT, -1);
        }

        if (clientSite_ != nullptr)
        {
            clientSite_->SaveObject();
        }

        return S_OK;
    }

    return S_OK;
}

STDMETHODIMP FormulaOleObject::EnumVerbs(IEnumOLEVERB** enumOleVerb)
{
    if (enumOleVerb == nullptr)
    {
        return E_POINTER;
    }

    return OleRegEnumVerbs(CLSID_LaTeXSnipperFormula, enumOleVerb);
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

STDMETHODIMP FormulaOleObject::Advise(IAdviseSink*, DWORD* connection)
{
    if (connection == nullptr)
    {
        return E_POINTER;
    }

    *connection = 0;
    return OLE_E_ADVISENOTSUPPORTED;
}

STDMETHODIMP FormulaOleObject::Unadvise(DWORD)
{
    return OLE_E_ADVISENOTSUPPORTED;
}

STDMETHODIMP FormulaOleObject::EnumAdvise(IEnumSTATDATA** enumAdvise)
{
    if (enumAdvise == nullptr)
    {
        return E_POINTER;
    }

    *enumAdvise = nullptr;
    return OLE_E_ADVISENOTSUPPORTED;
}

STDMETHODIMP FormulaOleObject::GetMiscStatus(DWORD aspect, DWORD* status)
{
    if (status == nullptr)
    {
        return E_POINTER;
    }

    HRESULT aspectResult = ValidateContentAspect(aspect);
    if (FAILED(aspectResult))
    {
        return aspectResult;
    }

    *status = OLEMISC_RECOMPOSEONRESIZE | OLEMISC_CANTLINKINSIDE | OLEMISC_INSIDEOUT;
    return S_OK;
}

STDMETHODIMP FormulaOleObject::SetColorScheme(LOGPALETTE*)
{
    return S_OK;
}

STDMETHODIMP FormulaOleObject::GetData(FORMATETC* format, STGMEDIUM* medium)
{
    if (format == nullptr || medium == nullptr)
    {
        return E_POINTER;
    }

    HRESULT queryResult = QueryGetData(format);
    if (FAILED(queryResult))
    {
        return queryResult;
    }

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

    if (format->cfFormat != CF_ENHMETAFILE)
    {
        return DV_E_FORMATETC;
    }

    if ((format->tymed & TYMED_ENHMF) == 0)
    {
        return DV_E_TYMED;
    }

    return ValidateContentAspect(format->dwAspect);
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

STDMETHODIMP FormulaOleObject::SetData(FORMATETC*, STGMEDIUM*, BOOL)
{
    return E_NOTIMPL;
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

STDMETHODIMP FormulaOleObject::DAdvise(FORMATETC*, DWORD, IAdviseSink*, DWORD* connection)
{
    if (connection == nullptr)
    {
        return E_POINTER;
    }

    *connection = 0;
    return OLE_E_ADVISENOTSUPPORTED;
}

STDMETHODIMP FormulaOleObject::DUnadvise(DWORD)
{
    return OLE_E_ADVISENOTSUPPORTED;
}

STDMETHODIMP FormulaOleObject::EnumDAdvise(IEnumSTATDATA** enumAdvise)
{
    if (enumAdvise == nullptr)
    {
        return E_POINTER;
    }

    *enumAdvise = nullptr;
    return OLE_E_ADVISENOTSUPPORTED;
}

STDMETHODIMP FormulaOleObject::Draw(DWORD drawAspect, LONG, void*, DVTARGETDEVICE*, HDC, HDC drawContext, LPCRECTL bounds, LPCRECTL, BOOL(__stdcall*)(ULONG_PTR), ULONG_PTR)
{
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
    HRESULT result = SavePresentationToStorage(storage, presentation_);
    if (SUCCEEDED(result))
    {
        dirty_ = false;
    }

    return result;
}

STDMETHODIMP FormulaOleObject::Load(IStorage* storage)
{
    FormulaPresentation loaded;
    HRESULT result = LoadPresentationFromStorage(storage, &loaded);
    if (SUCCEEDED(result))
    {
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
    return S_OK;
}

STDMETHODIMP FormulaOleObject::HandsOffStorage()
{
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
