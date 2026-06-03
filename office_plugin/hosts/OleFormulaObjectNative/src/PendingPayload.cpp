#include "PendingPayload.h"

#include <windows.h>

namespace
{
constexpr wchar_t kPayloadKey[] = L"Software\\LaTeXSnipper\\OfficePlugin\\OleFormulaObject";
constexpr wchar_t kPendingPayloadValue[] = L"PendingPayload";

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

