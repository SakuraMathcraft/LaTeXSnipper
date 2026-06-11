using LaTeXSnipper.OfficePlugin.Abstractions;
#if NET48
using System.Web.Script.Serialization;
#else
using System.Text.Json;
#endif

namespace LaTeXSnipper.OfficePlugin.Rendering;

internal static class MathJaxRenderScriptBuilder
{
    public static string BuildConfigurationScript()
    {
        return @"
window.LaTeXSnipperMathJaxStartupReady = false;
window.MathJax = {
  loader: {
    load: ['[tex]/bbox', '[tex]/boldsymbol', '[tex]/color', '[tex]/mhchem']
  },
  tex: {
    packages: {
      '[+]': ['bbox', 'boldsymbol', 'color', 'mhchem']
    }
  },
  startup: {
    typeset: false,
    ready: function() {
      MathJax.startup.defaultReady();
      window.LaTeXSnipperMathJaxStartupReady = true;
    }
  }
};";
    }

    public static string BuildBootstrapScript()
    {
        return @"
window.LaTeXSnipperMathJax = {
  version: (window.MathJax && window.MathJax.version) || '3.2.2',
  readGroup: function(source, start) {
    if (source[start] !== '{') {
      return null;
    }
    let depth = 0;
    for (let index = start; index < source.length; index += 1) {
      if (source[index] === '\\') {
        index += 1;
        continue;
      }
      if (source[index] === '{') {
        depth += 1;
      } else if (source[index] === '}') {
        depth -= 1;
        if (depth === 0) {
          return {
            content: source.slice(start + 1, index),
            end: index + 1
          };
        }
      }
    }
    return null;
  },
  normalizeMathLiveLatex: function(source) {
    let normalized = source
      .replace(/(^|[^\\])\$/g, '$1')
      .replace(/\\bm(?=\s*\{)/g, '\\boldsymbol');
    const command = '\\colorbox';
    let result = '';
    let cursor = 0;
    while (cursor < normalized.length) {
      const commandIndex = normalized.indexOf(command, cursor);
      if (commandIndex < 0) {
        result += normalized.slice(cursor);
        break;
      }
      result += normalized.slice(cursor, commandIndex);
      let groupStart = commandIndex + command.length;
      while (/\s/.test(normalized[groupStart] || '')) {
        groupStart += 1;
      }
      const color = this.readGroup(normalized, groupStart);
      if (!color) {
        result += command;
        cursor = commandIndex + command.length;
        continue;
      }
      groupStart = color.end;
      while (/\s/.test(normalized[groupStart] || '')) {
        groupStart += 1;
      }
      const body = this.readGroup(normalized, groupStart);
      if (!body) {
        result += normalized.slice(commandIndex, color.end);
        cursor = color.end;
        continue;
      }
      let bodyContent = body.content.trim();
      if (bodyContent.length >= 2 && bodyContent[0] === '$' && bodyContent[bodyContent.length - 1] === '$') {
        bodyContent = bodyContent.slice(1, -1);
      }
      const bodyLatex = this.normalizeMathLiveLatex(bodyContent);
      result += '\\bbox[' + color.content.trim() + ']{' + bodyLatex + '}';
      cursor = body.end;
    }
    return result;
  },
  render: function(input) {
    try {
      const adaptor = MathJax.startup.adaptor;
      const originalSource = input.latex || '';
      const display = input.displayMode !== 'Inline';
      const scale = Number(input.fontScale) > 0 ? Number(input.fontScale) : 1;
      const weight = [5, 10, 15].includes(Number(input.fontWeightPercent))
        ? Number(input.fontWeightPercent)
        : 0;
      const trimmed = originalSource.trim();
      const isMathMl = /^<math(\s|>|:)/i.test(trimmed);
      const source = isMathMl ? trimmed : this.normalizeMathLiveLatex(originalSource);
      const container = isMathMl && MathJax.mathml2svg
        ? MathJax.mathml2svg(source, { display: display })
        : MathJax.tex2svg(source, { display: display });
      const node = adaptor.firstChild(container);
      adaptor.setAttribute(node, 'data-latexsnipper-weight', String(weight));
      if (weight > 0) {
        const viewBox = String(adaptor.getAttribute(node, 'viewBox') || '').trim().split(/\s+/).map(Number);
        const viewBoxHeight = viewBox.length === 4 && Number.isFinite(viewBox[3]) ? viewBox[3] : 1000;
        const strokeWidth = viewBoxHeight * weight / 1000;
        adaptor.setAttribute(node, 'stroke', 'currentColor');
        adaptor.setAttribute(node, 'stroke-width', String(strokeWidth));
        adaptor.setAttribute(node, 'paint-order', 'stroke fill');
        adaptor.setAttribute(node, 'stroke-linejoin', 'round');
      }
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
    } catch (error) {
      return {
        error: String(error && (error.stack || error.message) || error),
        version: this.version
      };
    }
  },
  toMathMl: function(input) {
    try {
      const originalSource = input.latex || '';
      const display = input.displayMode !== 'Inline';
      const source = this.normalizeMathLiveLatex(originalSource);
      const root = MathJax.startup.document.convert(source, {
        display: display,
        end: 20
      });
      return {
        mathml: MathJax.startup.document.toMML(root),
        version: this.version
      };
    } catch (error) {
      return {
        error: String(error && (error.stack || error.message) || error),
        version: this.version
      };
    }
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
            fontScale = request.FontScale,
            fontWeightPercent = request.FontWeightPercent
        };
#if NET48
        string json = new JavaScriptSerializer().Serialize(payload);
#else
        string json = JsonSerializer.Serialize(payload);
#endif
        return "JSON.stringify(window.LaTeXSnipperMathJax.render(" + json + "));";
    }

    public static string BuildMathMlScript(string latex, FormulaDisplayMode displayMode)
    {
        var payload = new
        {
            latex,
            displayMode = displayMode.ToString()
        };
#if NET48
        string json = new JavaScriptSerializer().Serialize(payload);
#else
        string json = JsonSerializer.Serialize(payload);
#endif
        return "JSON.stringify(window.LaTeXSnipperMathJax.toMathMl(" + json + "));";
    }
}
