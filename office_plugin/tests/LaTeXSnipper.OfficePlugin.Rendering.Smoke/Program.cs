using System;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Abstractions;
using LaTeXSnipper.OfficePlugin.Rendering;

internal static class Program
{
    private static int Main(string[] args)
    {
        try
        {
            if (args.Length == 1 && args[0] == "--typography")
                TypographySmoke.RunAsync().GetAwaiter().GetResult();
            else
                RunAsync().GetAwaiter().GetResult();
            return 0;
        }
        catch (Exception error)
        {
            Console.Error.WriteLine(error.GetType().FullName + ": " + error.Message);
            if (error.InnerException != null) Console.Error.WriteLine(error.InnerException.Message);
            return 1;
        }
    }

    private static async Task RunAsync()
    {
        using var runtime = new WebView2MathJaxJavaScriptRuntime("RenderingSmoke-" + Guid.NewGuid().ToString("N"));
        using var renderer = new MathJaxSvgRenderer(runtime);
        var emfRenderer = new EnhancedMetafilePresentationRenderer();
        string[] sources = {
            @"\ce{CO2 + C -> 2 CO}",
            @"\begin{align}&\text{设 }A,B\text{ 为事件}\\&P(A\mid B)=\frac{P(A\cap B)}{P(B)}\end{align}",
            @"\mathrm{\delta}",
            @"\colorbox{red}{$x$}",
            "<math><mfrac><mi>a</mi><mi>b</mi></mfrac></math>"
        };
        foreach (string source in sources)
        {
            var request = new RenderRequest(source, FormulaDisplayMode.Display, RenderEngineKind.MathJaxSvg, FormulaTypography.Default);
            RenderResult svg = await renderer.RenderAsync(request, CancellationToken.None);
            string svgText = Encoding.UTF8.GetString(svg.Payload);
            if (!svgText.StartsWith("<svg", StringComparison.Ordinal) || svgText.Contains("data-mjx-error"))
                throw new InvalidOperationException("Invalid SVG: " + source);
            OlePresentationResult emf = await emfRenderer.RenderPresentationAsync(
                new OlePresentationRequest(svg, OlePresentationKind.EnhancedMetafile), CancellationToken.None);
            if (emf.Payload.Length == 0 || emf.WidthPoints <= 0 || emf.HeightPoints <= 0
                || emf.RendererVersion != svg.RendererVersion)
                throw new InvalidOperationException("Invalid EMF: " + source);
            string mathml = await renderer.ConvertTypographyToMathMlAsync(source, FormulaDisplayMode.Display, FormulaTypography.Default, CancellationToken.None);
            if (!mathml.StartsWith("<math", StringComparison.Ordinal) || mathml.Contains("<merror"))
                throw new InvalidOperationException("Invalid MathML: " + source);
            if (!ReferenceEquals(svg, await renderer.RenderAsync(request, CancellationToken.None)))
                throw new InvalidOperationException("Render cache version mismatch");
            Console.WriteLine($"MathJax {svg.RendererVersion}: SVG {svg.Payload.Length}, EMF {emf.Payload.Length}, MathML {mathml.Length}");
        }
        // The generic bridge must await promises and release abandoned requests.
        string delayed = await runtime.EvaluateAsync("new Promise(resolve => setTimeout(() => resolve({ok:true}), 50))", CancellationToken.None);
        if (delayed != "{\"ok\":true}") throw new InvalidOperationException("Async bridge lost its result");
        using (var cancel = new CancellationTokenSource(30))
        {
            try
            {
                await runtime.EvaluateAsync("new Promise(resolve => setTimeout(resolve, 200))", cancel.Token);
                throw new InvalidOperationException("Cancellation was ignored");
            }
            catch (OperationCanceledException) { }
        }
        Console.WriteLine("Office rendering smoke passed.");
    }
}
