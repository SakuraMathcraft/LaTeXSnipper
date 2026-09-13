using LaTeXSnipper.OfficePlugin.Abstractions;
#if NET48
using System.Web.Script.Serialization;
#else
using System.Text.Json;
#endif

namespace LaTeXSnipper.OfficePlugin.Rendering;

internal static class MathJaxRenderScriptBuilder
{
    public static string BuildRenderScript(RenderRequest request)
    {
        var payload = new
        {
            latex = request.Latex,
            outputs = new[] { "svg" },
            displayMode = request.DisplayMode.ToString(),
            fontScale = request.FontScale
        };
#if NET48
        string json = new JavaScriptSerializer().Serialize(payload);
#else
        string json = JsonSerializer.Serialize(payload);
#endif
        return "window.LaTeXSnipperOfficeMath.convert(" + json + ")";
    }

    public static string BuildMathMlScript(string latex, FormulaDisplayMode displayMode)
    {
        var payload = new
        {
            latex,
            outputs = new[] { "mathml" },
            displayMode = displayMode.ToString()
        };
#if NET48
        string json = new JavaScriptSerializer().Serialize(payload);
#else
        string json = JsonSerializer.Serialize(payload);
#endif
        return "window.LaTeXSnipperOfficeMath.convert(" + json + ")";
    }
}
