using System;
using System.Text;
using System.Threading;
using LaTeXSnipper.OfficePlugin.Abstractions;
using LaTeXSnipper.OfficePlugin.Rendering;

namespace LaTeXSnipper.OfficePlugin.OleFormulaObject;

internal static class Program
{
    [STAThread]
    private static int Main(string[] args)
    {
        try
        {
            string? renderLatex = GetSwitchValue(args, "/RenderSvg");
            if (renderLatex != null)
            {
                return RenderSvgAsync(renderLatex).GetAwaiter().GetResult();
            }

            string? renderEmfLatex = GetSwitchValue(args, "/RenderEmf");
            if (renderEmfLatex != null)
            {
                string outputPath = GetSwitchValue(args, "/Output") ?? "latexsnipper-formula.emf";
                return RenderEmfAsync(renderEmfLatex, outputPath).GetAwaiter().GetResult();
            }

            TryWriteLine(OleFormulaObjectIds.FriendlyName + " OLE local server");
            TryWriteLine("Use /RenderSvg <latex> or /RenderEmf <latex> /Output <path>.");
            return 0;
        }
        catch (Exception ex)
        {
            TryWriteError(ex.Message);
            return 1;
        }
    }

    private static async System.Threading.Tasks.Task<int> RenderSvgAsync(string latex)
    {
        TrySetConsoleUtf8();
        using var runtime = new WebView2MathJaxJavaScriptRuntime("OleFormulaObject");
        var renderer = new MathJaxSvgRenderer(runtime);
        var request = new RenderRequest(latex, FormulaDisplayMode.Display, RenderEngineKind.MathJaxSvg)
        {
            FontScale = 1.2
        };
        RenderResult result = await renderer.RenderAsync(request, CancellationToken.None).ConfigureAwait(true);
        TryWriteLine("renderer=" + result.RendererVersion);
        TryWriteLine("widthPoints=" + result.WidthPoints.ToString(System.Globalization.CultureInfo.InvariantCulture));
        TryWriteLine("heightPoints=" + result.HeightPoints.ToString(System.Globalization.CultureInfo.InvariantCulture));
        TryWriteLine("baselinePoints=" + result.BaselinePoints.ToString(System.Globalization.CultureInfo.InvariantCulture));
        TryWriteLine(Encoding.UTF8.GetString(result.Payload));
        return 0;
    }

    private static async System.Threading.Tasks.Task<int> RenderEmfAsync(string latex, string outputPath)
    {
        TrySetConsoleUtf8();
        using var runtime = new WebView2MathJaxJavaScriptRuntime("OleFormulaObject");
        var renderer = new MathJaxSvgRenderer(runtime);
        var request = new RenderRequest(latex, FormulaDisplayMode.Display, RenderEngineKind.MathJaxSvg)
        {
            FontScale = 1.2
        };
        RenderResult intermediate = await renderer.RenderAsync(request, CancellationToken.None).ConfigureAwait(true);
        var presentationRenderer = new EnhancedMetafilePresentationRenderer();
        OlePresentationResult presentation = await presentationRenderer.RenderPresentationAsync(
            new OlePresentationRequest(intermediate, OlePresentationKind.EnhancedMetafile),
            CancellationToken.None).ConfigureAwait(false);
        string fullPath = System.IO.Path.GetFullPath(outputPath);
        System.IO.File.WriteAllBytes(fullPath, presentation.Payload);
        TryWriteLine("renderer=" + intermediate.RendererVersion);
        TryWriteLine("presentation=" + presentation.PresentationKind);
        TryWriteLine("bytes=" + presentation.Payload.Length.ToString(System.Globalization.CultureInfo.InvariantCulture));
        TryWriteLine("output=" + fullPath);
        return 0;
    }

    private static void TrySetConsoleUtf8()
    {
        try
        {
            Console.OutputEncoding = Encoding.UTF8;
        }
        catch (Exception)
        {
        }
    }

    private static void TryWriteLine(string message)
    {
        try
        {
            Console.WriteLine(message);
        }
        catch (Exception)
        {
        }
    }

    private static void TryWriteError(string message)
    {
        try
        {
            Console.Error.WriteLine(message);
        }
        catch (Exception)
        {
        }
    }

    private static string? GetSwitchValue(string[] args, string switchName)
    {
        for (int i = 0; i < args.Length - 1; i++)
        {
            if (string.Equals(args[i], switchName, StringComparison.OrdinalIgnoreCase))
            {
                return args[i + 1];
            }
        }

        return null;
    }
}
