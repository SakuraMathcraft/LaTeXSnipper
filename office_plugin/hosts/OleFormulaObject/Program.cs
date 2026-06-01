using System;
using System.Text;
using System.Reflection;
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
            if (HasSwitch(args, "/RegServer"))
            {
                OleServerRegistration.RegisterCurrentUser(Assembly.GetExecutingAssembly().Location);
                return 0;
            }

            if (HasSwitch(args, "/UnregServer"))
            {
                OleServerRegistration.UnregisterCurrentUser();
                return 0;
            }

            if (HasSwitch(args, "/RegServerMachine"))
            {
                OleServerRegistration.RegisterLocalMachine(Assembly.GetExecutingAssembly().Location);
                return 0;
            }

            if (HasSwitch(args, "/UnregServerMachine"))
            {
                OleServerRegistration.UnregisterLocalMachine();
                return 0;
            }

            if (HasSwitch(args, "/Embedding"))
            {
                return RunEmbeddingServer();
            }

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

            Console.WriteLine(OleFormulaObjectIds.FriendlyName + " OLE local server");
            Console.WriteLine("Use /RegServer, /UnregServer, /RegServerMachine, /UnregServerMachine, /RenderSvg <latex>, or /RenderEmf <latex> /Output <path>.");
            return 0;
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine(ex.Message);
            return 1;
        }
    }

    private static int RunEmbeddingServer()
    {
        using var server = new OleEmbeddingServer();
        return server.Run();
    }

    private static async System.Threading.Tasks.Task<int> RenderSvgAsync(string latex)
    {
        Console.OutputEncoding = Encoding.UTF8;
        using var runtime = new WebView2MathJaxJavaScriptRuntime();
        var renderer = new MathJaxSvgRenderer(runtime);
        var request = new RenderRequest(latex, FormulaDisplayMode.Display, RenderEngineKind.MathJaxSvg);
        RenderResult result = await renderer.RenderAsync(request, CancellationToken.None).ConfigureAwait(true);
        Console.WriteLine("renderer=" + result.RendererVersion);
        Console.WriteLine("widthPoints=" + result.WidthPoints.ToString(System.Globalization.CultureInfo.InvariantCulture));
        Console.WriteLine("heightPoints=" + result.HeightPoints.ToString(System.Globalization.CultureInfo.InvariantCulture));
        Console.WriteLine("baselinePoints=" + result.BaselinePoints.ToString(System.Globalization.CultureInfo.InvariantCulture));
        Console.WriteLine(Encoding.UTF8.GetString(result.Payload));
        return 0;
    }

    private static async System.Threading.Tasks.Task<int> RenderEmfAsync(string latex, string outputPath)
    {
        Console.OutputEncoding = Encoding.UTF8;
        using var runtime = new WebView2MathJaxJavaScriptRuntime();
        var renderer = new MathJaxSvgRenderer(runtime);
        var request = new RenderRequest(latex, FormulaDisplayMode.Display, RenderEngineKind.MathJaxSvg);
        RenderResult intermediate = await renderer.RenderAsync(request, CancellationToken.None).ConfigureAwait(true);
        var presentationRenderer = new EnhancedMetafilePresentationRenderer();
        OlePresentationResult presentation = await presentationRenderer.RenderPresentationAsync(
            new OlePresentationRequest(intermediate, OlePresentationKind.EnhancedMetafile),
            CancellationToken.None).ConfigureAwait(false);
        string fullPath = System.IO.Path.GetFullPath(outputPath);
        System.IO.File.WriteAllBytes(fullPath, presentation.Payload);
        Console.WriteLine("renderer=" + intermediate.RendererVersion);
        Console.WriteLine("presentation=" + presentation.PresentationKind);
        Console.WriteLine("bytes=" + presentation.Payload.Length.ToString(System.Globalization.CultureInfo.InvariantCulture));
        Console.WriteLine("output=" + fullPath);
        return 0;
    }

    private static bool HasSwitch(string[] args, string switchName)
    {
        foreach (string arg in args)
        {
            if (string.Equals(arg, switchName, StringComparison.OrdinalIgnoreCase))
            {
                return true;
            }
        }

        return false;
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
