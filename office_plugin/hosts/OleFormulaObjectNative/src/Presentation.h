#pragma once

#include <windows.h>
#include <string>
#include <vector>

struct FormulaPresentation
{
    std::wstring latex;
    std::wstring payloadJson;
    SIZE himetricSize;
    std::vector<BYTE> enhancedMetafile;
};

FormulaPresentation CreatePlaceholderPresentation(const std::wstring& latex);
FormulaPresentation CreatePresentationFromPayloadWithoutRendering(const std::wstring& payloadJson);
FormulaPresentation CreatePresentationFromPayload(const std::wstring& payloadJson);
HENHMETAFILE CopyEnhMetaFileFromBytes(const std::vector<BYTE>& bytes);
