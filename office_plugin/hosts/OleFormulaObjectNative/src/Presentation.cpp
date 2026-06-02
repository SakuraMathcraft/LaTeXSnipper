#include "Presentation.h"

#include "Win32Check.h"

#include <algorithm>
#include <fstream>
#include <iterator>
#include <shlwapi.h>
#include <sstream>

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

std::wstring QuoteArgument(const std::wstring& value)
{
    std::wstring quoted = L"\"";
    for (wchar_t ch : value)
    {
        if (ch == L'"')
        {
            quoted += L"\\\"";
        }
        else
        {
            quoted.push_back(ch);
        }
    }

    quoted.push_back(L'"');
    return quoted;
}

std::wstring GetExecutableDirectory()
{
    wchar_t modulePath[MAX_PATH]{};
    DWORD length = GetModuleFileNameW(nullptr, modulePath, MAX_PATH);
    std::wstring directory(modulePath, length);
    size_t slash = directory.find_last_of(L"\\/");
    return slash == std::wstring::npos ? L"." : directory.substr(0, slash);
}

std::vector<BYTE> ReadBinaryFile(const std::wstring& path)
{
    std::ifstream input(path, std::ios::binary);
    if (!input)
    {
        return {};
    }

    return std::vector<BYTE>(std::istreambuf_iterator<char>(input), std::istreambuf_iterator<char>());
}

std::vector<BYTE> TryRenderEmfWithHelper(const std::wstring& latex)
{
    std::wstring renderer = ResolveRendererPath();
    if (renderer.empty())
    {
        return {};
    }

    wchar_t tempDirectory[MAX_PATH]{};
    if (GetTempPathW(MAX_PATH, tempDirectory) == 0)
    {
        return {};
    }

    wchar_t tempFile[MAX_PATH]{};
    if (GetTempFileNameW(tempDirectory, L"lsf", 0, tempFile) == 0)
    {
        return {};
    }

    DeleteFileW(tempFile);
    std::wstring outputPath = std::wstring(tempFile) + L".emf";
    std::wstring commandLine = QuoteArgument(renderer) + L" /RenderEmf " + QuoteArgument(latex) + L" /Output " + QuoteArgument(outputPath);

    STARTUPINFOW startup{};
    startup.cb = sizeof(startup);
    startup.dwFlags = STARTF_USESHOWWINDOW;
    startup.wShowWindow = SW_HIDE;
    PROCESS_INFORMATION process{};
    std::vector<wchar_t> mutableCommand(commandLine.begin(), commandLine.end());
    mutableCommand.push_back(L'\0');
    BOOL created = CreateProcessW(nullptr, mutableCommand.data(), nullptr, nullptr, FALSE, CREATE_NO_WINDOW, nullptr, nullptr, &startup, &process);
    if (!created)
    {
        return {};
    }

    DWORD waitResult = WaitForSingleObject(process.hProcess, 20000);
    DWORD exitCode = 1;
    GetExitCodeProcess(process.hProcess, &exitCode);
    CloseHandle(process.hThread);
    CloseHandle(process.hProcess);
    if (waitResult != WAIT_OBJECT_0 || exitCode != 0)
    {
        DeleteFileW(outputPath.c_str());
        return {};
    }

    std::vector<BYTE> bytes = ReadBinaryFile(outputPath);
    DeleteFileW(outputPath.c_str());
    return bytes;
}
}

std::wstring ResolveRendererPath()
{
    wchar_t configured[MAX_PATH]{};
    DWORD configuredLength = GetEnvironmentVariableW(L"LATEXSNIPPER_OLE_RENDERER", configured, MAX_PATH);
    if (configuredLength > 0 && GetFileAttributesW(configured) != INVALID_FILE_ATTRIBUTES)
    {
        return configured;
    }

    std::wstring installed = GetExecutableDirectory() + L"\\..\\..\\OleFormulaRenderer\\LaTeXSnipper.OfficePlugin.OleFormulaObject.exe";
    wchar_t fullPath[MAX_PATH]{};
    if (GetFullPathNameW(installed.c_str(), MAX_PATH, fullPath, nullptr) > 0 && GetFileAttributesW(fullPath) != INVALID_FILE_ATTRIBUTES)
    {
        return fullPath;
    }

    std::wstring dev = GetExecutableDirectory() + L"\\..\\..\\..\\..\\..\\OleFormulaObject\\bin\\Release\\net48\\LaTeXSnipper.OfficePlugin.OleFormulaObject.exe";
    if (GetFullPathNameW(dev.c_str(), MAX_PATH, fullPath, nullptr) > 0 && GetFileAttributesW(fullPath) != INVALID_FILE_ATTRIBUTES)
    {
        return fullPath;
    }

    return L"";
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
    FormulaPresentation presentation = CreatePlaceholderPresentation(latex);
    presentation.payloadJson = payloadJson;
    std::vector<BYTE> rendered = TryRenderEmfWithHelper(presentation.latex);
    if (!rendered.empty())
    {
        presentation.enhancedMetafile = std::move(rendered);
    }

    return presentation;
}

FormulaPresentation CreatePresentationFromPayloadWithoutRendering(const std::wstring& payloadJson)
{
    std::wstring latex = ExtractJsonString(payloadJson, L"latex");
    FormulaPresentation presentation = CreatePlaceholderPresentation(latex);
    presentation.payloadJson = payloadJson;
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
