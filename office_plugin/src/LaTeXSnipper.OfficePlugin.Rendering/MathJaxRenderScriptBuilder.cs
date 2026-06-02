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
    const source = input.latex || '';
    const display = input.displayMode !== 'Inline';
    const scale = Number(input.fontScale) > 0 ? Number(input.fontScale) : 1;
    const trimmed = source.trim();
    const isMathMl = /^<math(\s|>|:)/i.test(trimmed);
    const container = isMathMl && MathJax.mathml2svg
      ? MathJax.mathml2svg(trimmed, { display: display })
      : MathJax.tex2svg(source, { display: display });
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
      scale: scale,
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
