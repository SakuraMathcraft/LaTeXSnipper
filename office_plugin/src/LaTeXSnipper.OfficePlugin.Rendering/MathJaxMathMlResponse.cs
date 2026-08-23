using System;
#if NET48
using System.Collections.Generic;
using System.Web.Script.Serialization;
#else
using System.Text.Json;
#endif

namespace LaTeXSnipper.OfficePlugin.Rendering;

internal sealed class MathJaxMathMlResponse
{
    private MathJaxMathMlResponse(string mathMl, string rendererVersion)
    {
        MathMl = mathMl;
        RendererVersion = rendererVersion;
    }

    public string MathMl { get; }

    public string RendererVersion { get; }

    public static MathJaxMathMlResponse Parse(string responseJson)
    {
#if NET48
        var serializer = new JavaScriptSerializer();
        string decoded = serializer.Deserialize<string>(responseJson) ?? string.Empty;
        var response = serializer.Deserialize<Dictionary<string, object>>(decoded)
            ?? throw new InvalidOperationException("MathJax 返回了无效的 MathML 数据。");
        string error = ReadString(response, "error");
        if (!string.IsNullOrWhiteSpace(error))
        {
            throw new InvalidOperationException("MathJax MathML 转换失败，请检查公式内容后重试。");
        }

        string mathMl = ReadString(response, "mathml");
        if (string.IsNullOrWhiteSpace(mathMl))
        {
            throw new InvalidOperationException("MathJax 未返回 MathML 内容。");
        }

        return new MathJaxMathMlResponse(mathMl, ReadString(response, "version"));
#else
        string decoded = JsonSerializer.Deserialize<string>(responseJson) ?? string.Empty;
        using JsonDocument document = JsonDocument.Parse(decoded);
        JsonElement root = document.RootElement;
        string error = root.TryGetProperty("error", out JsonElement errorElement)
            ? errorElement.GetString() ?? string.Empty
            : string.Empty;
        if (!string.IsNullOrWhiteSpace(error))
        {
            throw new InvalidOperationException("MathJax MathML 转换失败，请检查公式内容后重试。");
        }

        string mathMl = root.TryGetProperty("mathml", out JsonElement mathMlElement)
            ? mathMlElement.GetString() ?? string.Empty
            : string.Empty;
        if (string.IsNullOrWhiteSpace(mathMl))
        {
            throw new InvalidOperationException("MathJax 未返回 MathML 内容。");
        }

        string version = root.TryGetProperty("version", out JsonElement versionElement)
            ? versionElement.GetString() ?? string.Empty
            : string.Empty;
        return new MathJaxMathMlResponse(mathMl, version);
#endif
    }

#if NET48
    private static string ReadString(IReadOnlyDictionary<string, object> values, string key)
    {
        return values.TryGetValue(key, out object? value) ? Convert.ToString(value) ?? string.Empty : string.Empty;
    }
#endif
}
