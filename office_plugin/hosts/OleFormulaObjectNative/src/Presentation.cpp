#include "Presentation.h"

#include <cmath>
#include <cstdlib>

namespace
{
constexpr int kDefaultWidthPoints = 180;
constexpr int kDefaultHeightPoints = 42;
constexpr int kPointsPerInch = 72;
constexpr int kHimetricPerInch = 2540;

int PointsToHimetric(int points)
{
    return MulDiv(points, kHimetricPerInch, kPointsPerInch);
}

int PointsToHimetric(double points)
{
    return static_cast<int>(std::lround(points * kHimetricPerInch / kPointsPerInch));
}

std::wstring ExtractJsonString(const std::wstring& json, const std::wstring& propertyName)
{
    const std::wstring marker = L"\"" + propertyName + L"\"";
    size_t property = json.find(marker);
    if (property == std::wstring::npos)
    {
        return L"";
    }

    size_t colon = json.find(L':', property + marker.size());
    if (colon == std::wstring::npos)
    {
        return L"";
    }

    size_t start = json.find(L'"', colon + 1);
    if (start == std::wstring::npos)
    {
        return L"";
    }

    std::wstring value;
    bool escaped = false;
    for (size_t i = start + 1; i < json.size(); ++i)
    {
        wchar_t ch = json[i];
        if (escaped)
        {
            switch (ch)
            {
            case L'"':
            case L'\\':
            case L'/':
                value.push_back(ch);
                break;
            case L'n':
                value.push_back(L'\n');
                break;
            case L'r':
                value.push_back(L'\r');
                break;
            case L't':
                value.push_back(L'\t');
                break;
            default:
                value.push_back(ch);
                break;
            }
            escaped = false;
            continue;
        }

        if (ch == L'\\')
        {
            escaped = true;
            continue;
        }

        if (ch == L'"')
        {
            break;
        }

        value.push_back(ch);
    }

    return value;
}

double ExtractJsonNumber(const std::wstring& json, const std::wstring& propertyName)
{
    std::wstring text = ExtractJsonString(json, propertyName);
    if (text.empty())
    {
        return 0;
    }

    wchar_t* end = nullptr;
    double value = wcstod(text.c_str(), &end);
    return end == text.c_str() ? 0 : value;
}

int DecodeBase64Char(wchar_t ch)
{
    if (ch >= L'A' && ch <= L'Z')
    {
        return static_cast<int>(ch - L'A');
    }

    if (ch >= L'a' && ch <= L'z')
    {
        return static_cast<int>(ch - L'a') + 26;
    }

    if (ch >= L'0' && ch <= L'9')
    {
        return static_cast<int>(ch - L'0') + 52;
    }

    if (ch == L'+')
    {
        return 62;
    }

    if (ch == L'/')
    {
        return 63;
    }

    return -1;
}

std::vector<BYTE> DecodeBase64(const std::wstring& value)
{
    std::vector<BYTE> bytes;
    int buffer = 0;
    int bits = -8;
    for (wchar_t ch : value)
    {
        if (ch == L'=')
        {
            break;
        }

        int decoded = DecodeBase64Char(ch);
        if (decoded < 0)
        {
            continue;
        }

        buffer = (buffer << 6) | decoded;
        bits += 6;
        if (bits >= 0)
        {
            bytes.push_back(static_cast<BYTE>((buffer >> bits) & 0xFF));
            bits -= 8;
        }
    }

    return bytes;
}

bool IsValidBase64(const std::wstring& value)
{
    if (value.empty() || value.size() % 4 != 0)
    {
        return false;
    }

    size_t padding = 0;
    if (value.back() == L'=')
    {
        padding++;
    }
    if (value.size() > 1 && value[value.size() - 2] == L'=')
    {
        padding++;
    }

    for (size_t index = 0; index < value.size() - padding; index++)
    {
        if (DecodeBase64Char(value[index]) < 0)
        {
            return false;
        }
    }

    for (size_t index = value.size() - padding; index < value.size(); index++)
    {
        if (value[index] != L'=')
        {
            return false;
        }
    }

    return true;
}

void ApplyPayloadSize(const std::wstring& payloadJson, FormulaPresentation* presentation)
{
    double widthPoints = ExtractJsonNumber(payloadJson, L"widthPoints");
    double heightPoints = ExtractJsonNumber(payloadJson, L"heightPoints");
    if (widthPoints > 0 && heightPoints > 0)
    {
        presentation->himetricSize = {PointsToHimetric(widthPoints), PointsToHimetric(heightPoints)};
    }
}

}

static bool HasRequiredFormulaPayloadFields(const std::wstring& payloadJson)
{
    std::wstring presentationPayload = ExtractJsonString(payloadJson, L"presentationPayloadBase64");
    return !ExtractJsonString(payloadJson, L"latex").empty()
        && !ExtractJsonString(payloadJson, L"displayMode").empty()
        && !ExtractJsonString(payloadJson, L"numberingMode").empty()
        && !ExtractJsonString(payloadJson, L"fontScale").empty()
        && !ExtractJsonString(payloadJson, L"renderEngine").empty()
        && !ExtractJsonString(payloadJson, L"rendererVersion").empty()
        && ExtractJsonNumber(payloadJson, L"widthPoints") > 0
        && ExtractJsonNumber(payloadJson, L"heightPoints") > 0
        && !ExtractJsonString(payloadJson, L"presentationKind").empty()
        && !ExtractJsonString(payloadJson, L"presentationMimeType").empty()
        && IsValidBase64(presentationPayload);
}

bool IsSupportedFormulaPayload(const std::wstring& payloadJson)
{
    if (!HasRequiredFormulaPayloadFields(payloadJson))
    {
        return false;
    }

    std::wstring schemaVersion = ExtractJsonString(payloadJson, L"schemaVersion");
    if (schemaVersion == L"1")
    {
        return !ExtractJsonString(payloadJson, L"documentId").empty()
            && !ExtractJsonString(payloadJson, L"equationId").empty();
    }

    if (schemaVersion == L"2")
    {
        return payloadJson.find(L"\"documentId\"") == std::wstring::npos
            && payloadJson.find(L"\"equationId\"") == std::wstring::npos;
    }

    return false;
}

FormulaPresentation CreatePresentationFromPayload(const std::wstring& payloadJson)
{
    if (!IsSupportedFormulaPayload(payloadJson))
    {
        return FormulaPresentation{};
    }

    std::wstring latex = ExtractJsonString(payloadJson, L"latex");
    FormulaPresentation presentation{};
    presentation.latex = latex;
    presentation.payloadJson = payloadJson;
    presentation.himetricSize = {PointsToHimetric(kDefaultWidthPoints), PointsToHimetric(kDefaultHeightPoints)};
    ApplyPayloadSize(payloadJson, &presentation);

    std::vector<BYTE> payloadPresentation = DecodeBase64(ExtractJsonString(payloadJson, L"presentationPayloadBase64"));
    presentation.enhancedMetafile = std::move(payloadPresentation);
    return presentation;
}

FormulaPresentation CreatePresentationFromPayloadWithoutRendering(const std::wstring& payloadJson)
{
    if (!IsSupportedFormulaPayload(payloadJson))
    {
        return FormulaPresentation{};
    }

    std::wstring latex = ExtractJsonString(payloadJson, L"latex");
    FormulaPresentation presentation{};
    presentation.latex = latex;
    presentation.payloadJson = payloadJson;
    presentation.himetricSize = {PointsToHimetric(kDefaultWidthPoints), PointsToHimetric(kDefaultHeightPoints)};
    ApplyPayloadSize(payloadJson, &presentation);

    std::vector<BYTE> payloadPresentation = DecodeBase64(ExtractJsonString(payloadJson, L"presentationPayloadBase64"));
    presentation.enhancedMetafile = std::move(payloadPresentation);
    return presentation;
}

HENHMETAFILE CopyEnhMetaFileFromBytes(const std::vector<BYTE>& bytes)
{
    if (bytes.empty())
    {
        return nullptr;
    }

    return SetEnhMetaFileBits(static_cast<UINT>(bytes.size()), bytes.data());
}
