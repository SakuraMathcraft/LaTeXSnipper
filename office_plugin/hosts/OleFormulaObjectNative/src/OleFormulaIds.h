#pragma once

#include <guiddef.h>

inline constexpr wchar_t kFormulaProgId[] = L"LaTeXSnipper.Formula";
inline constexpr wchar_t kFormulaVersionedProgId[] = L"LaTeXSnipper.Formula.1";
inline constexpr wchar_t kFormulaFriendlyName[] = L"LaTeXSnipper Formula";
inline constexpr wchar_t kFormulaDefaultLatex[] = L"e^{i\\pi}+1=0";

// B7F5B4AB-5F94-4D87-A29F-9A41D41B3B9F
inline constexpr GUID CLSID_LaTeXSnipperFormula = {
    0xb7f5b4ab,
    0x5f94,
    0x4d87,
    {0xa2, 0x9f, 0x9a, 0x41, 0xd4, 0x1b, 0x3b, 0x9f}};
