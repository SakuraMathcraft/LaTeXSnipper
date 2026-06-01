#pragma once

#include <windows.h>

HRESULT RegisterOleFormulaServer(bool machineWide, const wchar_t* serverPath);
HRESULT UnregisterOleFormulaServer(bool machineWide);
