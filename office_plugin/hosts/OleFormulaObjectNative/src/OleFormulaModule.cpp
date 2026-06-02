#include "FormulaOleObject.h"
#include "NativeLog.h"
#include "OleFormulaIds.h"
#include "OleRegistration.h"

#include <atlbase.h>
#include <atlcom.h>
#include <iterator>
#include <new>
#include <shellapi.h>
#include <string>

extern LONG GetNativeOleObjectCount();
extern LONG GetNativeOleLockCount();

namespace
{
bool HasSwitch(int argc, wchar_t** argv, const wchar_t* name)
{
    for (int i = 1; i < argc; ++i)
    {
        if (_wcsicmp(argv[i], name) == 0)
        {
            return true;
        }
    }

    return false;
}

std::wstring GetExecutablePath()
{
    wchar_t buffer[MAX_PATH]{};
    DWORD length = GetModuleFileNameW(nullptr, buffer, static_cast<DWORD>(std::size(buffer)));
    return std::wstring(buffer, length);
}

int ReturnHResult(HRESULT result)
{
    return SUCCEEDED(result) ? 0 : static_cast<int>(result);
}

HRESULT RunEmbeddingServer()
{
    WriteNativeOleLog(L"Embedding server starting.");
    HRESULT initResult = OleInitialize(nullptr);
    if (FAILED(initResult))
    {
        WriteNativeOleLog(L"OleInitialize failed.");
        return initResult;
    }
    WriteNativeOleLog(L"OleInitialize succeeded.");

    FormulaClassFactory* factory = new (std::nothrow) FormulaClassFactory();
    if (factory == nullptr)
    {
        WriteNativeOleLog(L"Class factory allocation failed.");
        OleUninitialize();
        return E_OUTOFMEMORY;
    }

    DWORD registrationCookie = 0;
    HRESULT registerResult = CoRegisterClassObject(
        CLSID_LaTeXSnipperFormula,
        static_cast<IClassFactory*>(factory),
        CLSCTX_LOCAL_SERVER,
        REGCLS_MULTI_SEPARATE,
        &registrationCookie);

    if (FAILED(registerResult))
    {
        WriteNativeOleLog(L"CoRegisterClassObject failed.");
        factory->Release();
        OleUninitialize();
        return registerResult;
    }
    WriteNativeOleLog(L"CoRegisterClassObject succeeded.");

    MSG message{};
    WriteNativeOleLog(L"Entering message loop.");
    while (GetMessageW(&message, nullptr, 0, 0) > 0)
    {
        TranslateMessage(&message);
        DispatchMessageW(&message);
    }

    WriteNativeOleLog(L"Message loop exited.");
    CoRevokeClassObject(registrationCookie);
    factory->Release();
    OleUninitialize();
    return S_OK;
}
}

int WINAPI wWinMain(HINSTANCE, HINSTANCE, PWSTR, int)
{
    int argc = 0;
    wchar_t** argv = CommandLineToArgvW(GetCommandLineW(), &argc);
    if (argv == nullptr)
    {
        return ReturnHResult(HRESULT_FROM_WIN32(GetLastError()));
    }

    HRESULT result = S_OK;
    const std::wstring executablePath = GetExecutablePath();
    if (HasSwitch(argc, argv, L"/RegServer"))
    {
        result = RegisterOleFormulaServer(false, executablePath.c_str());
    }
    else if (HasSwitch(argc, argv, L"/UnregServer"))
    {
        result = UnregisterOleFormulaServer(false);
    }
    else if (HasSwitch(argc, argv, L"/RegServerMachine"))
    {
        result = RegisterOleFormulaServer(true, executablePath.c_str());
    }
    else if (HasSwitch(argc, argv, L"/UnregServerMachine"))
    {
        result = UnregisterOleFormulaServer(true);
    }
    else if (HasSwitch(argc, argv, L"/Embedding") || HasSwitch(argc, argv, L"-Embedding"))
    {
        result = RunEmbeddingServer();
    }

    LocalFree(argv);
    return ReturnHResult(result);
}
