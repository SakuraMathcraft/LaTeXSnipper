#include "OleRegistration.h"

#include "OleFormulaIds.h"
#include "Win32Check.h"

#include <shlwapi.h>
#include <iterator>
#include <string>

namespace
{
constexpr REGSAM kWritableAccess = KEY_READ | KEY_WRITE;
constexpr wchar_t kFormulaMiscStatus[] = L"133521";

std::wstring GuidToRegistryString(const GUID& guid)
{
    wchar_t buffer[64]{};
    StringFromGUID2(guid, buffer, static_cast<int>(std::size(buffer)));
    return buffer;
}

std::wstring QuotePathWithEmbedding(const wchar_t* serverPath)
{
    std::wstring value = L"\"";
    value += serverPath;
    value += L"\" /Embedding";
    return value;
}

std::wstring GetHandlerPath(const wchar_t* serverPath)
{
    wchar_t drive[_MAX_DRIVE]{};
    wchar_t directory[_MAX_DIR]{};
    wchar_t fileName[_MAX_FNAME]{};
    wchar_t extension[_MAX_EXT]{};
    _wsplitpath_s(serverPath, drive, std::size(drive), directory, std::size(directory), fileName, std::size(fileName), extension, std::size(extension));

    wchar_t handlerPath[MAX_PATH]{};
    _wmakepath_s(handlerPath, drive, directory, L"LaTeXSnipper.OfficePlugin.OleFormulaObject.Handler", L".dll");
    return handlerPath;
}

HRESULT CreateKey(HKEY root, const std::wstring& path, REGSAM access, HKEY* key)
{
    DWORD disposition = 0;
    LONG result = RegCreateKeyExW(root, path.c_str(), 0, nullptr, REG_OPTION_NON_VOLATILE, access, nullptr, key, &disposition);
    return result == ERROR_SUCCESS ? S_OK : HRESULT_FROM_WIN32(result);
}

HRESULT SetStringValue(HKEY key, const wchar_t* name, const std::wstring& value)
{
    const DWORD byteCount = static_cast<DWORD>((value.size() + 1) * sizeof(wchar_t));
    LONG result = RegSetValueExW(key, name, 0, REG_SZ, reinterpret_cast<const BYTE*>(value.c_str()), byteCount);
    return result == ERROR_SUCCESS ? S_OK : HRESULT_FROM_WIN32(result);
}

HRESULT SetDefaultValue(HKEY key, const std::wstring& value)
{
    return SetStringValue(key, nullptr, value);
}

HRESULT RegisterProgId(HKEY classesRoot, const wchar_t* progId, const std::wstring& classId)
{
    HKEY progKey = nullptr;
    HRESULT result = CreateKey(classesRoot, progId, kWritableAccess, &progKey);
    if (FAILED(result))
    {
        return result;
    }

    result = SetDefaultValue(progKey, kFormulaFriendlyName);
    HKEY clsidKey = nullptr;
    if (SUCCEEDED(result))
    {
        result = CreateKey(progKey, L"CLSID", kWritableAccess, &clsidKey);
    }

    if (SUCCEEDED(result))
    {
        result = SetDefaultValue(clsidKey, classId);
    }

    if (clsidKey != nullptr)
    {
        RegCloseKey(clsidKey);
    }

    RegCloseKey(progKey);
    return result;
}

void DeleteTreeIfExists(HKEY root, const std::wstring& path, REGSAM access);

HRESULT RegisterClass(HKEY classesRoot, REGSAM access, const wchar_t* serverPath)
{
    const std::wstring classId = GuidToRegistryString(CLSID_LaTeXSnipperFormula);
    const std::wstring classPath = L"CLSID\\" + classId;
    HKEY classKey = nullptr;
    HRESULT result = CreateKey(classesRoot, classPath, access, &classKey);
    if (FAILED(result))
    {
        return result;
    }

    result = SetDefaultValue(classKey, kFormulaFriendlyName);
    if (SUCCEEDED(result))
    {
        result = SetStringValue(classKey, L"AppID", classId);
    }

    const std::wstring handlerPath = GetHandlerPath(serverPath);
    const bool hasHandler = GetFileAttributesW(handlerPath.c_str()) != INVALID_FILE_ATTRIBUTES;

    const struct ChildValue
    {
        const wchar_t* path;
        std::wstring value;
    } childValues[] = {
        {L"ProgID", kFormulaVersionedProgId},
        {L"VersionIndependentProgID", kFormulaProgId},
        {L"LocalServer32", QuotePathWithEmbedding(serverPath)},
        {L"DefaultIcon", std::wstring(L"\"") + serverPath + L"\",0"},
        {L"Insertable", L""},
        {L"MiscStatus", kFormulaMiscStatus},
        {L"MiscStatus\\1", kFormulaMiscStatus},
        {L"Verb\\0", L"&Edit,0,0"},
    };

    for (const ChildValue& child : childValues)
    {
        if (FAILED(result))
        {
            break;
        }

        HKEY childKey = nullptr;
        result = CreateKey(classKey, child.path, access, &childKey);
        if (SUCCEEDED(result))
        {
            result = SetDefaultValue(childKey, child.value);
            RegCloseKey(childKey);
        }
    }

    if (SUCCEEDED(result) && hasHandler)
    {
        HKEY handlerKey = nullptr;
        result = CreateKey(classKey, L"InprocServer32", access, &handlerKey);
        if (SUCCEEDED(result))
        {
            result = SetDefaultValue(handlerKey, handlerPath);
        }

        if (SUCCEEDED(result))
        {
            result = SetStringValue(handlerKey, L"ThreadingModel", L"Apartment");
        }

        if (handlerKey != nullptr)
        {
            RegCloseKey(handlerKey);
        }
    }

    if (SUCCEEDED(result))
    {
        DeleteTreeIfExists(classKey, L"InprocHandler32", access);
    }

    RegCloseKey(classKey);
    return result;
}

HRESULT RegisterInRoot(HKEY root, REGSAM access, const wchar_t* serverPath)
{
    HKEY classesRoot = nullptr;
    HRESULT result = CreateKey(root, L"Software\\Classes", access, &classesRoot);
    if (FAILED(result))
    {
        return result;
    }

    const std::wstring classId = GuidToRegistryString(CLSID_LaTeXSnipperFormula);
    result = RegisterProgId(classesRoot, kFormulaProgId, classId);
    if (SUCCEEDED(result))
    {
        result = RegisterProgId(classesRoot, kFormulaVersionedProgId, classId);
    }

    if (SUCCEEDED(result))
    {
        result = RegisterClass(classesRoot, access, serverPath);
    }

    RegCloseKey(classesRoot);
    return result;
}

void DeleteTreeIfExists(HKEY root, const std::wstring& path, REGSAM access)
{
    HKEY key = nullptr;
    LONG openResult = RegOpenKeyExW(root, path.c_str(), 0, access, &key);
    if (openResult == ERROR_SUCCESS)
    {
        RegCloseKey(key);
        SHDeleteKeyW(root, path.c_str());
    }
}

HRESULT UnregisterInRoot(HKEY root, REGSAM access)
{
    HKEY classesRoot = nullptr;
    HRESULT result = CreateKey(root, L"Software\\Classes", access, &classesRoot);
    if (FAILED(result))
    {
        return result;
    }

    DeleteTreeIfExists(classesRoot, kFormulaProgId, access);
    DeleteTreeIfExists(classesRoot, kFormulaVersionedProgId, access);
    DeleteTreeIfExists(classesRoot, L"CLSID\\" + GuidToRegistryString(CLSID_LaTeXSnipperFormula), access);
    RegCloseKey(classesRoot);
    return S_OK;
}
}

HRESULT RegisterOleFormulaServer(bool machineWide, const wchar_t* serverPath)
{
    if (serverPath == nullptr || serverPath[0] == L'\0')
    {
        return E_INVALIDARG;
    }

    wchar_t fullPath[MAX_PATH]{};
    if (GetFullPathNameW(serverPath, MAX_PATH, fullPath, nullptr) == 0)
    {
        return HResultFromWin32LastError();
    }

    if (GetFileAttributesW(fullPath) == INVALID_FILE_ATTRIBUTES)
    {
        return HRESULT_FROM_WIN32(ERROR_FILE_NOT_FOUND);
    }

    if (!machineWide)
    {
        return RegisterInRoot(HKEY_CURRENT_USER, kWritableAccess, fullPath);
    }

#if defined(_WIN64)
    return RegisterInRoot(HKEY_LOCAL_MACHINE, kWritableAccess | KEY_WOW64_64KEY, fullPath);
#else
    return RegisterInRoot(HKEY_LOCAL_MACHINE, kWritableAccess | KEY_WOW64_32KEY, fullPath);
#endif
}

HRESULT UnregisterOleFormulaServer(bool machineWide)
{
    if (!machineWide)
    {
        return UnregisterInRoot(HKEY_CURRENT_USER, kWritableAccess);
    }

#if defined(_WIN64)
    return UnregisterInRoot(HKEY_LOCAL_MACHINE, kWritableAccess | KEY_WOW64_64KEY);
#else
    return UnregisterInRoot(HKEY_LOCAL_MACHINE, kWritableAccess | KEY_WOW64_32KEY);
#endif
}
