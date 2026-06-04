#pragma once

#include "Presentation.h"

#include <atlbase.h>
#include <oleidl.h>
#include <string>

class FormulaOleObject final
    : public IOleObject
    , public IDataObject
    , public IViewObject2
    , public IRunnableObject
    , public IOleCache
    , public IExternalConnection
    , public IPersistStorage
{
public:
    FormulaOleObject();
    ~FormulaOleObject();

    STDMETHOD(QueryInterface)(REFIID iid, void** object) override;
    STDMETHOD_(ULONG, AddRef)() override;
    STDMETHOD_(ULONG, Release)() override;

    STDMETHOD(SetClientSite)(IOleClientSite* clientSite) override;
    STDMETHOD(GetClientSite)(IOleClientSite** clientSite) override;
    STDMETHOD(SetHostNames)(LPCOLESTR containerApp, LPCOLESTR containerObject) override;
    STDMETHOD(Close)(DWORD saveOption) override;
    STDMETHOD(SetMoniker)(DWORD whichMoniker, IMoniker* moniker) override;
    STDMETHOD(GetMoniker)(DWORD assign, DWORD whichMoniker, IMoniker** moniker) override;
    STDMETHOD(InitFromData)(IDataObject* dataObject, BOOL creation, DWORD reserved) override;
    STDMETHOD(GetClipboardData)(DWORD reserved, IDataObject** dataObject) override;
    STDMETHOD(DoVerb)(LONG verb, LPMSG message, IOleClientSite* activeSite, LONG index, HWND parentWindow, LPCRECT positionRect) override;
    STDMETHOD(EnumVerbs)(IEnumOLEVERB** enumOleVerb) override;
    STDMETHOD(Update)() override;
    STDMETHOD(IsUpToDate)() override;
    STDMETHOD(GetUserClassID)(CLSID* classId) override;
    STDMETHOD(GetUserType)(DWORD formOfType, LPOLESTR* userType) override;
    STDMETHOD(SetExtent)(DWORD drawAspect, SIZEL* size) override;
    STDMETHOD(GetExtent)(DWORD drawAspect, SIZEL* size) override;
    STDMETHOD(Advise)(IAdviseSink* adviseSink, DWORD* connection) override;
    STDMETHOD(Unadvise)(DWORD connection) override;
    STDMETHOD(EnumAdvise)(IEnumSTATDATA** enumAdvise) override;
    STDMETHOD(GetMiscStatus)(DWORD aspect, DWORD* status) override;
    STDMETHOD(SetColorScheme)(LOGPALETTE* logPalette) override;

    STDMETHOD(GetData)(FORMATETC* format, STGMEDIUM* medium) override;
    STDMETHOD(GetDataHere)(FORMATETC* format, STGMEDIUM* medium) override;
    STDMETHOD(QueryGetData)(FORMATETC* format) override;
    STDMETHOD(GetCanonicalFormatEtc)(FORMATETC* input, FORMATETC* output) override;
    STDMETHOD(SetData)(FORMATETC* format, STGMEDIUM* medium, BOOL release) override;
    STDMETHOD(EnumFormatEtc)(DWORD direction, IEnumFORMATETC** enumFormatEtc) override;
    STDMETHOD(DAdvise)(FORMATETC* format, DWORD advf, IAdviseSink* adviseSink, DWORD* connection) override;
    STDMETHOD(DUnadvise)(DWORD connection) override;
    STDMETHOD(EnumDAdvise)(IEnumSTATDATA** enumAdvise) override;

    STDMETHOD(Draw)(DWORD drawAspect, LONG index, void* aspect, DVTARGETDEVICE* targetDevice, HDC targetDeviceContext, HDC drawContext, LPCRECTL bounds, LPCRECTL windowBounds, BOOL(__stdcall* continueCallback)(ULONG_PTR), ULONG_PTR continueContext) override;
    STDMETHOD(GetColorSet)(DWORD drawAspect, LONG index, void* aspect, DVTARGETDEVICE* targetDevice, HDC targetDeviceContext, LOGPALETTE** colorSet) override;
    STDMETHOD(Freeze)(DWORD drawAspect, LONG index, void* aspect, DWORD* freeze) override;
    STDMETHOD(Unfreeze)(DWORD freeze) override;
    STDMETHOD(SetAdvise)(DWORD aspects, DWORD advf, IAdviseSink* adviseSink) override;
    STDMETHOD(GetAdvise)(DWORD* aspects, DWORD* advf, IAdviseSink** adviseSink) override;
    STDMETHOD(GetExtent)(DWORD drawAspect, LONG index, DVTARGETDEVICE* targetDevice, SIZEL* size) override;

    STDMETHOD(GetRunningClass)(LPCLSID classId) override;
    STDMETHOD(Run)(LPBINDCTX bindContext) override;
    STDMETHOD_(BOOL, IsRunning)() override;
    STDMETHOD(LockRunning)(BOOL lock, BOOL lastUnlockCloses) override;
    STDMETHOD(SetContainedObject)(BOOL contained) override;

    STDMETHOD(Cache)(FORMATETC* format, DWORD adviseFlags, DWORD* connection) override;
    STDMETHOD(Uncache)(DWORD connection) override;
    STDMETHOD(EnumCache)(IEnumSTATDATA** enumStatData) override;
    STDMETHOD(InitCache)(IDataObject* dataObject) override;

    STDMETHOD_(DWORD, AddConnection)(DWORD extension, DWORD reserved) override;
    STDMETHOD_(DWORD, ReleaseConnection)(DWORD extension, DWORD reserved, BOOL lastReleaseCloses) override;

    STDMETHOD(GetClassID)(CLSID* classId) override;
    STDMETHOD(IsDirty)() override;
    STDMETHOD(InitNew)(IStorage* storage) override;
    STDMETHOD(Load)(IStorage* storage) override;
    STDMETHOD(Save)(IStorage* storage, BOOL sameAsLoad) override;
    STDMETHOD(SaveCompleted)(IStorage* storage) override;
    STDMETHOD(HandsOffStorage)() override;

private:
    void NotifyPresentationChanged();

    volatile LONG refCount_ = 1;
    ATL::CComPtr<IOleClientSite> clientSite_;
    ATL::CComPtr<IStorage> storage_;
    ATL::CComPtr<IAdviseSink> objectAdviseSink_;
    ATL::CComPtr<IAdviseSink> viewAdviseSink_;
    ATL::CComPtr<IAdviseSink> dataAdviseSink_;
    DWORD viewAdviseAspects_ = 0;
    DWORD viewAdviseFlags_ = 0;
    FORMATETC dataAdviseFormat_{};
    DWORD dataAdviseFlags_ = 0;
    DWORD cacheConnection_ = 1;
    FormulaPresentation presentation_;
    bool dirty_ = false;
};

class FormulaClassFactory final : public IClassFactory
{
public:
    STDMETHOD(QueryInterface)(REFIID iid, void** object) override;
    STDMETHOD_(ULONG, AddRef)() override;
    STDMETHOD_(ULONG, Release)() override;
    STDMETHOD(CreateInstance)(IUnknown* outer, REFIID iid, void** object) override;
    STDMETHOD(LockServer)(BOOL lock) override;

private:
    volatile LONG refCount_ = 1;
};
