#include "FormulaOleObject.h"
#include "OleFormulaIds.h"

#include <atlbase.h>
#include <new>

extern LONG GetNativeOleObjectCount();
extern LONG GetNativeOleLockCount();

STDAPI DllCanUnloadNow()
{
    return GetNativeOleObjectCount() == 0 && GetNativeOleLockCount() == 0 ? S_OK : S_FALSE;
}

STDAPI DllGetClassObject(REFCLSID classId, REFIID iid, void** object)
{
    if (object == nullptr)
    {
        return E_POINTER;
    }

    *object = nullptr;
    if (classId != CLSID_LaTeXSnipperFormula)
    {
        return CLASS_E_CLASSNOTAVAILABLE;
    }

    FormulaClassFactory* factory = new (std::nothrow) FormulaClassFactory();
    if (factory == nullptr)
    {
        return E_OUTOFMEMORY;
    }

    HRESULT result = factory->QueryInterface(iid, object);
    factory->Release();
    return result;
}

BOOL WINAPI DllMain(HINSTANCE, DWORD, void*)
{
    return TRUE;
}
