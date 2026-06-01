#include "PendingPayload.h"

#include <windows.h>

namespace
{
constexpr wchar_t kPayloadKey[] = L"Software\\LaTeXSnipper\\OfficePlugin\\OleFormulaObject";
constexpr wchar_t kPendingPayloadValue[] = L"PendingPayload";
constexpr wchar_t kEditorPayloadValue[] = L"EditorPayload";
constexpr wchar_t kEditorPayloadResultValue[] = L"EditorPayloadResult";

std::wstring ReadStringValue(HKEY key, const wchar_t* valueName)
{
    DWORD type = 0;
    DWORD byteCount = 0;
    LONG queryResult = RegQueryValueExW(key, valueName, nullptr, &type, nullptr, &byteCount);
    if (queryResult != ERROR_SUCCESS || type != REG_SZ || byteCount < sizeof(wchar_t))
    {
        return L"";
    }

    std::wstring value(byteCount / sizeof(wchar_t), L'\0');
    queryResult = RegQueryValueExW(key, valueName, nullptr, &type, reinterpret_cast<BYTE*>(value.data()), &byteCount);
    if (queryResult != ERROR_SUCCESS)
    {
        return L"";
    }

    while (!value.empty() && value.back() == L'\0')
    {
        value.pop_back();
    }

    return value;
}
}

std::wstring ConsumePendingPayload()
{
    HKEY key = nullptr;
    LONG openResult = RegOpenKeyExW(HKEY_CURRENT_USER, kPayloadKey, 0, KEY_READ | KEY_WRITE, &key);
    if (openResult != ERROR_SUCCESS)
    {
        return L"";
    }

    std::wstring payload = ReadStringValue(key, kPendingPayloadValue);
    RegDeleteValueW(key, kPendingPayloadValue);
    RegCloseKey(key);
    return payload;
}

void StoreEditorPayload(const std::wstring& payloadJson)
{
    HKEY key = nullptr;
    DWORD disposition = 0;
    LONG createResult = RegCreateKeyExW(HKEY_CURRENT_USER, kPayloadKey, 0, nullptr, REG_OPTION_NON_VOLATILE, KEY_WRITE, nullptr, &key, &disposition);
    if (createResult != ERROR_SUCCESS)
    {
        return;
    }

    RegSetValueExW(
        key,
        kEditorPayloadValue,
        0,
        REG_SZ,
        reinterpret_cast<const BYTE*>(payloadJson.c_str()),
        static_cast<DWORD>((payloadJson.size() + 1) * sizeof(wchar_t)));
    RegDeleteValueW(key, kEditorPayloadResultValue);
    RegCloseKey(key);
}

std::wstring ConsumeEditorPayloadResult()
{
    HKEY key = nullptr;
    LONG openResult = RegOpenKeyExW(HKEY_CURRENT_USER, kPayloadKey, 0, KEY_READ | KEY_WRITE, &key);
    if (openResult != ERROR_SUCCESS)
    {
        return L"";
    }

    std::wstring payload = ReadStringValue(key, kEditorPayloadResultValue);
    RegDeleteValueW(key, kEditorPayloadResultValue);
    RegCloseKey(key);
    return payload;
}
