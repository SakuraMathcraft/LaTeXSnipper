#include <windows.h>
#include <ole2.h>
#include <wincrypt.h>
#include <atlbase.h>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>
#include "../../hosts/OleFormulaObjectNative/src/OleFormulaIds.h"

static void Require(bool value, const char* message)
{
    if (!value) throw std::runtime_error(message);
}

static void Check(HRESULT result)
{
    if (FAILED(result)) { std::cerr << "HRESULT=" << std::hex << result << '\n'; throw std::runtime_error("COM call failed"); }
}

static CComPtr<IStorage> Storage()
{
    CComPtr<ILockBytes> bytes;
    Check(CreateILockBytesOnHGlobal(nullptr, TRUE, &bytes));
    CComPtr<IStorage> storage;
    Check(StgCreateDocfileOnILockBytes(bytes, STGM_CREATE | STGM_READWRITE | STGM_SHARE_EXCLUSIVE, 0, &storage));
    return storage;
}

static void WritePayload(IStorage* storage, const std::wstring& payload)
{
    CComPtr<IStream> stream;
    Check(storage->CreateStream(L"Payload", STGM_CREATE | STGM_READWRITE | STGM_SHARE_EXCLUSIVE, 0, 0, &stream));
    const ULONG size = static_cast<ULONG>((payload.size() + 1) * sizeof(wchar_t));
    ULONG written = 0;
    Check(stream->Write(payload.c_str(), size, &written));
    Require(written == size, "Partial payload write");
}

static std::wstring ReadPayload(IStorage* storage)
{
    CComPtr<IStream> stream;
    Check(storage->OpenStream(L"Payload", nullptr, STGM_READ | STGM_SHARE_EXCLUSIVE, 0, &stream));
    STATSTG stat{};
    Check(stream->Stat(&stat, STATFLAG_NONAME));
    std::wstring payload(static_cast<size_t>(stat.cbSize.QuadPart / sizeof(wchar_t)), L'\0');
    ULONG read = 0;
    Check(stream->Read(payload.data(), static_cast<ULONG>(stat.cbSize.QuadPart), &read));
    Require(read == stat.cbSize.QuadPart && !payload.empty() && payload.back() == L'\0', "Invalid stored payload");
    payload.pop_back();
    return payload;
}

static std::wstring Payload()
{
    HDC dc = CreateEnhMetaFileW(nullptr, nullptr, nullptr, nullptr);
    Require(dc != nullptr, "Cannot create EMF");
    Rectangle(dc, 0, 0, 100, 40);
    HENHMETAFILE emf = CloseEnhMetaFile(dc);
    UINT size = GetEnhMetaFileBits(emf, 0, nullptr);
    std::vector<BYTE> bytes(size);
    GetEnhMetaFileBits(emf, size, bytes.data());
    DeleteEnhMetaFile(emf);
    DWORD length = 0;
    Require(CryptBinaryToStringW(bytes.data(), size, CRYPT_STRING_BASE64 | CRYPT_STRING_NOCRLF, nullptr, &length), "Base64 size");
    std::wstring base64(length, L'\0');
    Require(CryptBinaryToStringW(bytes.data(), size, CRYPT_STRING_BASE64 | CRYPT_STRING_NOCRLF, base64.data(), &length), "Base64 encoding");
    base64.resize(wcslen(base64.c_str()));
    return LR"({"schemaVersion":"3","latex":"\\mathrm{\\delta}+\\text{条件概率}","displayMode":"Display","numberingMode":"None","numberText":"","renderEngine":"MathJaxSvg","rendererVersion":"4.1.3","widthPoints":"72","heightPoints":"36","baselinePoints":"4","presentationKind":"EnhancedMetafile","presentationMimeType":"image/emf","typographyVersion":"1","symbolFontId":"mathjax-stix2","numberFontFamily":"Times New Roman","cjkFontFamily":"宋体","defaultMathStyle":"BoldItalic","fontSizePoints":"15.5","color":"#123ABC","presentationPayloadBase64":")"
        + base64 + L"\"}";
}

static void Run(HMODULE module)
{
    using GetFactory = HRESULT(STDAPICALLTYPE*)(REFCLSID, REFIID, void**);
    auto getFactory = reinterpret_cast<GetFactory>(GetProcAddress(module, "DllGetClassObject"));
    Require(getFactory != nullptr, "Missing class factory");
    CComPtr<IClassFactory> factory;
    Check(getFactory(CLSID_LaTeXSnipperFormula, IID_IClassFactory, reinterpret_cast<void**>(&factory)));
    CComPtr<IPersistStorage> object;
    Check(factory->CreateInstance(nullptr, IID_IPersistStorage, reinterpret_cast<void**>(&object)));
    std::wstring payload = Payload();
    auto input = Storage();
    WritePayload(input, payload);
    Check(object->Load(input));
    CComQIPtr<IOleObject> ole(object);
    SIZEL size{};
    Check(ole->GetExtent(DVASPECT_CONTENT, &size));
    Require(size.cx == 2540 && size.cy == 1270, "Physical dimensions changed");
    CComQIPtr<IDataObject> data(object);
    FORMATETC format{CF_ENHMETAFILE, nullptr, DVASPECT_CONTENT, -1, TYMED_ENHMF};
    STGMEDIUM medium{};
    Check(data->GetData(&format, &medium));
    Require(medium.tymed == TYMED_ENHMF && GetEnhMetaFileBits(medium.hEnhMetaFile, 0, nullptr) > 0, "EMF lost");
    ReleaseStgMedium(&medium);
    auto output = Storage();
    Check(object->Save(output, FALSE));
    Check(object->SaveCompleted(output));
    Require(ReadPayload(output) == payload, "Typography/source changed during native save");
    CComPtr<IPersistStorage> reopened;
    Check(factory->CreateInstance(nullptr, IID_IPersistStorage, reinterpret_cast<void**>(&reopened)));
    Check(reopened->Load(output));
    auto copy = Storage();
    Check(reopened->Save(copy, FALSE));
    Require(ReadPayload(copy) == payload, "Typography/source changed on reopen");
    auto invalid = Storage();
    auto position = payload.find(L"\"fontSizePoints\":\"15.5\"");
    payload.replace(position, wcslen(L"\"fontSizePoints\":\"15.5\""), L"\"fontSizePoints\":\"0\"");
    WritePayload(invalid, payload);
    Require(FAILED(reopened->Load(invalid)), "Invalid point size accepted");
    auto preserved = Storage();
    Check(reopened->Save(preserved, FALSE));
    Require(ReadPayload(preserved) == ReadPayload(output), "Rejected input destroyed the loaded formula");
    std::cout << "PASS|Native factory, load, EMF, dimensions, save, reopen, typography and invalid input\n";
}

int wmain(int argc, wchar_t** argv)
{
    if (argc != 2) { std::cerr << "Usage: NativeOleHandler <handler.dll>\n"; return 2; }
    DWORD pendingBytes = 0;
    const LONG pending = RegGetValueW(HKEY_CURRENT_USER, L"Software\\LaTeXSnipper\\OfficePlugin\\OleFormulaObject",
        L"PendingPayload", RRF_RT_ANY, nullptr, nullptr, &pendingBytes);
    if (pending != ERROR_FILE_NOT_FOUND && pending != ERROR_PATH_NOT_FOUND)
    { std::cerr << "Cannot run while an Office payload is pending or its state is inaccessible.\n"; return 2; }
    HRESULT initialized = OleInitialize(nullptr);
    if (FAILED(initialized)) return 2;
    HMODULE module = LoadLibraryW(argv[1]);
    int result = 1;
    try { Require(module != nullptr, "Cannot load handler DLL"); Run(module); result = 0; }
    catch (const std::exception& error) { std::cerr << error.what() << '\n'; }
    if (module) FreeLibrary(module);
    OleUninitialize();
    return result;
}
