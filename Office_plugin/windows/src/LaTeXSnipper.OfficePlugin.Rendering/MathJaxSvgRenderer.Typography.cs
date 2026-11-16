using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Abstractions;
#if NET48
using System.Web.Script.Serialization;
#endif

namespace LaTeXSnipper.OfficePlugin.Rendering;

public sealed partial class MathJaxSvgRenderer
{
    private readonly SemaphoreSlim _typographyLock = new SemaphoreSlim(1, 1);
#if NET48
    private readonly Dictionary<string, RenderResult> _typographyCache = new Dictionary<string, RenderResult>();
    private readonly SystemFontOutlineService _fontOutlines = new SystemFontOutlineService();
    private bool _typographyInitialized;
#endif

    /// <summary>Renders source and a complete typography snapshot at its natural physical size.</summary>
    public async Task<RenderResult> RenderTypographyAsync(string latex, FormulaDisplayMode displayMode,
        FormulaTypography typography, CancellationToken cancellationToken)
    {
        ThrowIfDisposed();
        if (string.IsNullOrWhiteSpace(latex)) throw new ArgumentException("公式源码不能为空。", nameof(latex));
        if (typography == null) throw new ArgumentNullException(nameof(typography));
#if NET48
        using var timeout = new CancellationTokenSource(OfficeCommandTimeouts.Render);
        using var linked = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken, timeout.Token);
        CancellationToken token = linked.Token;
        await EnsureInitializedAsync(token).ConfigureAwait(false);
        await _typographyLock.WaitAsync(token).ConfigureAwait(false);
        try
        {
            await InitializeTypographyAsync(token).ConfigureAwait(false);
            var serializer = new JavaScriptSerializer { MaxJsonLength = 16 * 1024 * 1024 };
            string input = SerializeTypographyInput(serializer, latex, displayMode, typography);
            Dictionary<string, object> plan = ParseTypographyResponse(serializer,
                await _runtime.EvaluateAsync("LaTeXSnipperOfficeTypography.prepare(" + input + ")", token).ConfigureAwait(false));
            var outlines = new Dictionary<string, FontRunOutline>();
            var warnings = new HashSet<string>(ReadTypographyWarnings(plan), StringComparer.Ordinal);
            foreach (Dictionary<string, object> run in (object[])plan["runs"])
            {
                token.ThrowIfCancellationRequested();
                string family = (string)run["family"];
                var style = (FontRunStyle)Convert.ToInt32(run["style"], CultureInfo.InvariantCulture);
                FontRunOutline outline = _fontOutlines.Shape((string)run["text"], family, style,
                    new[] { "Times New Roman", "Microsoft YaHei", "SimSun", "Segoe UI Symbol" });
                outlines.Add((string)run["key"], outline);
                if (outline.Warning != null) warnings.Add(outline.Warning);
            }
            string fontData = serializer.Serialize(outlines);
            // Identity includes the actual measured font output. Font replacement cannot reuse stale geometry.
            string key;
            using (var sha = SHA256.Create()) key = Convert.ToBase64String(sha.ComputeHash(
                Encoding.UTF8.GetBytes(_assetResolver.Version + "\n" + input + "\n" + fontData)));
            if (_typographyCache.TryGetValue(key, out RenderResult? cached)) return cached;
            Dictionary<string, object> result = ParseTypographyResponse(serializer,
                await _runtime.EvaluateAsync("LaTeXSnipperOfficeTypography.render(" + input + "," + fontData + ")", token)
                    .ConfigureAwait(false));
            foreach (string warning in ReadTypographyWarnings(result)) warnings.Add(warning);
            double width = Convert.ToDouble(result["widthPoints"], CultureInfo.InvariantCulture);
            double height = Convert.ToDouble(result["heightPoints"], CultureInfo.InvariantCulture);
            double baseline = Convert.ToDouble(result["baselinePoints"], CultureInfo.InvariantCulture);
            if (!(width > 0) || !(height > 0) || double.IsInfinity(width) || double.IsInfinity(height)
                || double.IsNaN(baseline) || double.IsInfinity(baseline))
                throw new InvalidOperationException("字体渲染返回了无效的自然尺寸。");
            var rendered = new RenderResult(RenderEngineKind.MathJaxSvg, SvgMimeType,
                Encoding.UTF8.GetBytes((string)result["svg"]), width, height, baseline, (string)result["version"], warnings.ToArray());
            if (_typographyCache.Count >= 128) _typographyCache.Clear();
            _typographyCache.Add(key, rendered);
            return rendered;
        }
        finally { _typographyLock.Release(); }
#else
        await Task.CompletedTask;
        throw new PlatformNotSupportedException("字体渲染需要 Windows .NET Framework Office 宿主。");
#endif
    }

    /// <summary>Produces semantic MathML with the same source-local/default style cascade, without SVG outlines.</summary>
    public async Task<string> ConvertTypographyToMathMlAsync(string latex, FormulaDisplayMode displayMode,
        FormulaTypography typography, CancellationToken cancellationToken)
    {
        ThrowIfDisposed();
        if (string.IsNullOrWhiteSpace(latex)) throw new ArgumentException("公式源码不能为空。", nameof(latex));
        if (typography == null) throw new ArgumentNullException(nameof(typography));
#if NET48
        using var timeout = new CancellationTokenSource(OfficeCommandTimeouts.Render);
        using var linked = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken, timeout.Token);
        await EnsureInitializedAsync(linked.Token).ConfigureAwait(false);
        await _typographyLock.WaitAsync(linked.Token).ConfigureAwait(false);
        try
        {
            await InitializeTypographyAsync(linked.Token).ConfigureAwait(false);
            var serializer = new JavaScriptSerializer { MaxJsonLength = 16 * 1024 * 1024 };
            string input = SerializeTypographyInput(serializer, latex, displayMode, typography);
            Dictionary<string, object> result = ParseTypographyResponse(serializer,
                await _runtime.EvaluateAsync("LaTeXSnipperOfficeTypography.prepare(" + input + ")", linked.Token).ConfigureAwait(false));
            return (string)result["mathml"];
        }
        finally { _typographyLock.Release(); }
#else
        await Task.CompletedTask;
        throw new PlatformNotSupportedException("字体渲染需要 Windows .NET Framework Office 宿主。");
#endif
    }

#if NET48
    private async Task InitializeTypographyAsync(CancellationToken token)
    {
        if (_typographyInitialized) return;
        using Stream stream = Assembly.GetExecutingAssembly().GetManifestResourceStream(
            "LaTeXSnipper.OfficePlugin.Rendering.MathJaxTypographyAdapter.js")
            ?? throw new InvalidOperationException("字体适配器资源缺失。");
        using var reader = new StreamReader(stream, Encoding.UTF8);
        var serializer = new JavaScriptSerializer();
        ParseTypographyResponse(serializer, await _runtime.EvaluateAsync(reader.ReadToEnd(), token).ConfigureAwait(false));
        _typographyInitialized = true;
    }

    private static string SerializeTypographyInput(JavaScriptSerializer serializer, string latex,
        FormulaDisplayMode displayMode, FormulaTypography typography) => serializer.Serialize(new
        {
            latex, displayMode = displayMode.ToString(),
            typography = new { typography.SymbolFontId, typography.NumberFontFamily, typography.CjkFontFamily,
                DefaultMathStyle = typography.DefaultMathStyle.ToString(), typography.FontSizePoints,
                typography.Color, typography.TypographyVersion }
        });

    private static Dictionary<string, object> ParseTypographyResponse(JavaScriptSerializer serializer, string json)
    {
        if (serializer.DeserializeObject(json) is not Dictionary<string, object> result)
            throw new InvalidOperationException("字体适配器返回了无效数据。");
        if (result.TryGetValue("error", out object error)) throw new InvalidOperationException(Convert.ToString(error));
        return result;
    }

    private static IEnumerable<string> ReadTypographyWarnings(Dictionary<string, object> result) =>
        result.TryGetValue("warnings", out object warnings) ? ((object[])warnings).Cast<string>() : Array.Empty<string>();
#endif
}
