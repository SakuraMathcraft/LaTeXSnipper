using System;
using System.Threading;
using LaTeXSnipper.OfficePlugin.Abstractions;
using LaTeXSnipper.OfficePlugin.Rendering;

namespace LaTeXSnipper.OfficePlugin.OleFormulaObject;

internal static class OleFormulaPresentationFactory
{
    public const string DefaultLatex = @"e^{i\pi}+1=0";

    public static OleFormulaPresentation CreateDefault()
    {
        using var runtime = new WebView2MathJaxJavaScriptRuntime();
        var renderer = new MathJaxSvgRenderer(runtime);
        var request = new RenderRequest(DefaultLatex, FormulaDisplayMode.Display, RenderEngineKind.MathJaxSvg);
        RenderResult intermediate = renderer.RenderAsync(request, CancellationToken.None).GetAwaiter().GetResult();
        var presentationRenderer = new EnhancedMetafilePresentationRenderer();
        OlePresentationResult presentation = presentationRenderer.RenderPresentationAsync(
            new OlePresentationRequest(intermediate, OlePresentationKind.EnhancedMetafile),
            CancellationToken.None).GetAwaiter().GetResult();
        var identity = new FormulaIdentity("ole-object", Guid.NewGuid().ToString("N"));
        var payload = new OleFormulaPayload(
            identity,
            DefaultLatex,
            FormulaDisplayMode.Display,
            NumberingMode.None,
            string.Empty,
            intermediate.RendererVersion,
            presentation.WidthPoints,
            presentation.HeightPoints,
            presentation.BaselinePoints);
        return new OleFormulaPresentation(payload, presentation.Payload);
    }
}
