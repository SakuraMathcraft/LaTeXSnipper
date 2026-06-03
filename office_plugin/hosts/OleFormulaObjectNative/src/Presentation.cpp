#include "Presentation.h"

#include "OleFormulaIds.h"
#include "Win32Check.h"

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <shlwapi.h>

namespace
{
constexpr int kDefaultWidthPoints = 180;
constexpr int kDefaultHeightPoints = 42;
constexpr int kPointsPerInch = 72;
constexpr int kHimetricPerInch = 2540;
constexpr int kEmfDpi = 144;

int PointsToHimetric(int points)
{
    return MulDiv(points, kHimetricPerInch, kPointsPerInch);
}

int PointsToHimetric(double points)
{
    return static_cast<int>(std::lround(points * kHimetricPerInch / kPointsPerInch));
}

int PointsToPixels(int points)
{
    return (std::max)(1, MulDiv(points, kEmfDpi, kPointsPerInch));
}

RECT BuildFrameRect(int widthPixels, int heightPixels)
{
    RECT rect{};
    rect.left = 0;
    rect.top = 0;
    rect.right = widthPixels;
    rect.bottom = heightPixels;
    return rect;
}

RECT BuildFrameRectHimetric(int widthPoints, int heightPoints)
{
    RECT rect{};
    rect.left = 0;
    rect.top = 0;
    rect.right = PointsToHimetric(widthPoints);
    rect.bottom = PointsToHimetric(heightPoints);
    return rect;
}

void DrawFormulaText(HDC hdc, RECT bounds, const std::wstring& latex)
{
    SetBkMode(hdc, TRANSPARENT);
    SetTextColor(hdc, RGB(0, 0, 0));

    LOGFONTW logFont{};
    logFont.lfHeight = -MulDiv(18, GetDeviceCaps(hdc, LOGPIXELSY), kPointsPerInch);
    logFont.lfWeight = FW_NORMAL;
    wcscpy_s(logFont.lfFaceName, L"Cambria Math");

    HFONT font = CreateFontIndirectW(&logFont);
    HFONT oldFont = font == nullptr ? nullptr : static_cast<HFONT>(SelectObject(hdc, font));

    std::wstring text = latex.empty() ? L"e^{i\\pi}+1=0" : latex;
    DrawTextW(hdc, text.c_str(), static_cast<int>(text.size()), &bounds, DT_CENTER | DT_VCENTER | DT_SINGLELINE | DT_NOPREFIX);

    if (oldFont != nullptr)
    {
        SelectObject(hdc, oldFont);
    }

    if (font != nullptr)
    {
        DeleteObject(font);
    }
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

FormulaPresentation CreatePlaceholderPresentation(const std::wstring& latex)
{
    FormulaPresentation presentation{};
    presentation.latex = latex.empty() ? L"e^{i\\pi}+1=0" : latex;
    presentation.payloadJson = L"";
    presentation.himetricSize = {PointsToHimetric(kDefaultWidthPoints), PointsToHimetric(kDefaultHeightPoints)};

    HDC screen = GetDC(nullptr);
    RECT frameHimetric = BuildFrameRectHimetric(kDefaultWidthPoints, kDefaultHeightPoints);
    HDC metafileDc = CreateEnhMetaFileW(screen, nullptr, &frameHimetric, L"LaTeXSnipper\0Formula\0");
    ReleaseDC(nullptr, screen);
    if (metafileDc == nullptr)
    {
        return presentation;
    }

    RECT bounds = BuildFrameRect(PointsToPixels(kDefaultWidthPoints), PointsToPixels(kDefaultHeightPoints));
    DrawFormulaText(metafileDc, bounds, presentation.latex);

    HENHMETAFILE metafile = CloseEnhMetaFile(metafileDc);
    if (metafile == nullptr)
    {
        return presentation;
    }

    UINT byteCount = GetEnhMetaFileBits(metafile, 0, nullptr);
    if (byteCount > 0)
    {
        presentation.enhancedMetafile.resize(byteCount);
        GetEnhMetaFileBits(metafile, byteCount, presentation.enhancedMetafile.data());
    }

    DeleteEnhMetaFile(metafile);
    return presentation;
}

FormulaPresentation CreatePresentationFromPayload(const std::wstring& payloadJson)
{
    std::wstring latex = ExtractJsonString(payloadJson, L"latex");
    FormulaPresentation presentation{};
    presentation.latex = latex.empty() ? kFormulaDefaultLatex : latex;
    presentation.payloadJson = payloadJson;
    presentation.himetricSize = {PointsToHimetric(kDefaultWidthPoints), PointsToHimetric(kDefaultHeightPoints)};
    ApplyPayloadSize(payloadJson, &presentation);

    std::vector<BYTE> payloadPresentation = DecodeBase64(ExtractJsonString(payloadJson, L"presentationPayloadBase64"));
    if (!payloadPresentation.empty())
    {
        presentation.enhancedMetafile = std::move(payloadPresentation);
        return presentation;
    }

    FormulaPresentation placeholder = CreatePlaceholderPresentation(presentation.latex);
    placeholder.payloadJson = payloadJson;
    return placeholder;
}

FormulaPresentation CreatePresentationFromPayloadWithoutRendering(const std::wstring& payloadJson)
{
    std::wstring latex = ExtractJsonString(payloadJson, L"latex");
    FormulaPresentation presentation{};
    presentation.latex = latex.empty() ? kFormulaDefaultLatex : latex;
    presentation.payloadJson = payloadJson;
    presentation.himetricSize = {PointsToHimetric(kDefaultWidthPoints), PointsToHimetric(kDefaultHeightPoints)};
    ApplyPayloadSize(payloadJson, &presentation);

    std::vector<BYTE> payloadPresentation = DecodeBase64(ExtractJsonString(payloadJson, L"presentationPayloadBase64"));
    if (!payloadPresentation.empty())
    {
        presentation.enhancedMetafile = std::move(payloadPresentation);
        return presentation;
    }

    FormulaPresentation placeholder = CreatePlaceholderPresentation(presentation.latex);
    placeholder.payloadJson = payloadJson;
    return placeholder;
}

HENHMETAFILE CopyEnhMetaFileFromBytes(const std::vector<BYTE>& bytes)
{
    if (bytes.empty())
    {
        return nullptr;
    }

    return SetEnhMetaFileBits(static_cast<UINT>(bytes.size()), bytes.data());
}
