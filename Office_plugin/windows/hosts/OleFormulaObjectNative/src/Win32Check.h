#pragma once

#include <windows.h>

inline HRESULT HResultFromWin32LastError()
{
    const DWORD error = GetLastError();
    return error == ERROR_SUCCESS ? E_FAIL : HRESULT_FROM_WIN32(error);
}
