#include "NativeLog.h"

#include <shlobj.h>
#include <strsafe.h>
#include <iterator>

namespace
{
constexpr DWORD kMaxLogBytes = 1024 * 1024;

void RotateLogIfNeeded(const wchar_t* path)
{
    WIN32_FILE_ATTRIBUTE_DATA attributes{};
    if (!GetFileAttributesExW(path, GetFileExInfoStandard, &attributes))
    {
        return;
    }

    LARGE_INTEGER size{};
    size.HighPart = static_cast<LONG>(attributes.nFileSizeHigh);
    size.LowPart = attributes.nFileSizeLow;
    if (size.QuadPart < kMaxLogBytes)
    {
        return;
    }

    wchar_t rotatedPath[MAX_PATH]{};
    if (FAILED(StringCchPrintfW(rotatedPath, MAX_PATH, L"%s.old", path)))
    {
        return;
    }

    DeleteFileW(rotatedPath);
    MoveFileExW(path, rotatedPath, MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH);
}
}

void WriteNativeOleLog(const wchar_t* message)
{
    wchar_t enabled[8]{};
    if (GetEnvironmentVariableW(L"LATEXSNIPPER_OLE_LOG", enabled, static_cast<DWORD>(std::size(enabled))) == 0)
    {
        return;
    }

    wchar_t localAppData[MAX_PATH]{};
    if (FAILED(SHGetFolderPathW(nullptr, CSIDL_LOCAL_APPDATA, nullptr, SHGFP_TYPE_CURRENT, localAppData)))
    {
        return;
    }

    wchar_t directory[MAX_PATH]{};
    if (FAILED(StringCchPrintfW(directory, MAX_PATH, L"%s\\LaTeXSnipper\\OfficePlugin\\OleFormulaObjectNative", localAppData)))
    {
        return;
    }

    SHCreateDirectoryExW(nullptr, directory, nullptr);

    wchar_t path[MAX_PATH]{};
    if (FAILED(StringCchPrintfW(path, MAX_PATH, L"%s\\ole-native.log", directory)))
    {
        return;
    }

    RotateLogIfNeeded(path);

    HANDLE file = CreateFileW(path, FILE_APPEND_DATA, FILE_SHARE_READ | FILE_SHARE_WRITE, nullptr, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (file == INVALID_HANDLE_VALUE)
    {
        return;
    }

    SYSTEMTIME now{};
    GetLocalTime(&now);

    wchar_t line[1024]{};
    if (SUCCEEDED(StringCchPrintfW(
            line,
            1024,
            L"%04u-%02u-%02uT%02u:%02u:%02u.%03u %s\r\n",
            now.wYear,
            now.wMonth,
            now.wDay,
            now.wHour,
            now.wMinute,
            now.wSecond,
            now.wMilliseconds,
            message)))
    {
        DWORD bytesWritten = 0;
        WriteFile(file, line, static_cast<DWORD>(wcslen(line) * sizeof(wchar_t)), &bytesWritten, nullptr);
    }

    CloseHandle(file);
}
