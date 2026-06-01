using LaTeXSnipper.OfficePlugin.Abstractions;
#if NET48
using System.Web.Script.Serialization;
#else
using System.Text.Json;
#endif

namespace LaTeXSnipper.OfficePlugin.Rendering;

internal static class MathJaxRenderScriptBuilder
{
    public static string BuildBootstrapScript()
    {
        return @"
window.LaTeXSnipperMathJax = {
  version: (window.MathJax && window.MathJax.version) || '3.2.2',
  render: function(input) {
    const adaptor = MathJax.startup.adaptor;
    const container = MathJax.tex2svg(input.latex || '', { display: input.displayMode !== 'Inline' });
    const node = adaptor.firstChild(container);
    const svg = adaptor.outerHTML(node);
    const width = adaptor.getAttribute(node, 'width') || '0ex';
    const height = adaptor.getAttribute(node, 'height') || '0ex';
    const style = adaptor.getAttribute(node, 'style') || '';
    return {
      svg: svg,
      widthEx: width,
      heightEx: height,
      style: style,
      version: this.version,
      warnings: []
    };
  }
};";
    }

    public static string BuildRenderScript(RenderRequest request)
    {
        var payload = new
        {
            latex = request.Latex,
            displayMode = request.DisplayMode.ToString(),
            targetDpi = request.TargetDpi,
            theme = request.Theme,
            fontScale = request.FontScale
        };
#if NET48
        string json = new JavaScriptSerializer().Serialize(payload);
#else
        string json = JsonSerializer.Serialize(payload);
#endif
        return "JSON.stringify(window.LaTeXSnipperMathJax.render(" + json + "));";
    }
}
