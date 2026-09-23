#if NET48
using System;
using System.Collections.Generic;
using System.Drawing.Text;
using System.Globalization;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.Editor;

internal sealed partial class MathLiveFormulaEditorForm
{
    private CancellationTokenSource? _previewCancellation;
    private bool _submitting;

    private Dictionary<string, object> CreateTypographyCatalog()
    {
        using var installed = new InstalledFontCollection();
        var families = installed.Families;
        string[] names;
        try { names = families.Select(font => font.Name).Distinct().OrderBy(name => name).ToArray(); }
        finally { foreach (var family in families) family.Dispose(); }
        return new Dictionary<string, object>
        {
            ["symbolFonts"] = _options.SymbolFonts,
            ["systemFonts"] = names,
            ["namedSizes"] = FormulaFontSize.NamedSizes,
            ["minimumPoints"] = FormulaFontSize.MinimumPoints,
            ["maximumPoints"] = FormulaFontSize.MaximumPoints,
            ["mathStyles"] = Enum.GetNames(typeof(FormulaMathStyle)),
        };
    }

    private FormulaTypography ReadTypography(Dictionary<string, object> message)
    {
        if (!message.TryGetValue("typography", out object raw) || raw is not Dictionary<string, object> fields)
            throw new FormatException("Missing editor typography snapshot.");
        FormulaTypography typography = FormulaTypographyFields.Read(fields);
        if (!_options.SymbolFonts.Contains(typography.SymbolFontId))
            throw new FormatException("Unavailable mathematical symbol font: " + typography.SymbolFontId);
        return typography;
    }

    private void CancelPreview()
    {
        // The request owns disposal: cancellation can race a renderer continuation.
        CancellationTokenSource? pending = _previewCancellation;
        _previewCancellation = null;
        pending?.Cancel();
    }

    private async Task RenderPreviewAsync(Dictionary<string, object> message)
    {
        CancelPreview();
        long generation = _currentSessionGeneration;
        long revision = Convert.ToInt64(message["revision"], CultureInfo.InvariantCulture);
        using var cancellation = new CancellationTokenSource();
        _previewCancellation = cancellation;
        var response = new Dictionary<string, object> { ["session"] = generation, ["revision"] = revision };
        try
        {
            FormulaTypography typography = ReadTypography(message);
            string latex = Convert.ToString(message["latex"]) ?? string.Empty;
            bool display = _options.ForceDisplayMode || Convert.ToBoolean(message["display"], CultureInfo.InvariantCulture);
            var request = new RenderRequest(MathLiveLatexStyleNormalizer.NormalizeLatex(latex.Trim()), display ? FormulaDisplayMode.Display : FormulaDisplayMode.Inline,
                RenderEngineKind.MathJaxSvg, typography);
            RenderResult result = await _options.PreviewRenderer.RenderAsync(request, cancellation.Token).ConfigureAwait(true);
            response["image"] = "data:image/svg+xml;base64," + Convert.ToBase64String(result.Payload);
            response["widthPoints"] = result.WidthPoints;
            response["heightPoints"] = result.HeightPoints;
            response["warnings"] = result.Warnings;
        }
        catch (OperationCanceledException) when (cancellation.IsCancellationRequested) { return; }
        catch (Exception error) { response["error"] = error.Message; }
        finally
        {
            if (ReferenceEquals(_previewCancellation, cancellation)) _previewCancellation = null;
        }
        if (cancellation.IsCancellationRequested || generation != _currentSessionGeneration || IsDisposed || _committed) return;
        await ExecuteEditorScriptAsync("window.LaTeXSnipperEditor?.previewResult(" + _serializer.Serialize(response) + ");").ConfigureAwait(true);
    }
}
#endif
