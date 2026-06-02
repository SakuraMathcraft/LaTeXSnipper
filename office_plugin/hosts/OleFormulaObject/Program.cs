using System;
using System.Drawing;
using System.IO;
using System.Windows.Forms;
using System.Text;
using System.Threading;
using LaTeXSnipper.OfficePlugin.Abstractions;
using LaTeXSnipper.OfficePlugin.Editor;
using LaTeXSnipper.OfficePlugin.Rendering;

namespace LaTeXSnipper.OfficePlugin.OleFormulaObject;

internal static class Program
{
    [STAThread]
    private static int Main(string[] args)
    {
        try
        {
            if (HasSwitch(args, "/EditPayload"))
            {
                return EditPayload();
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

            TryWriteLine(OleFormulaObjectIds.FriendlyName + " OLE local server");
            TryWriteLine("Use /RenderSvg <latex>, /RenderEmf <latex> /Output <path>, or /EditPayload.");
            return 0;
        }
        catch (Exception ex)
        {
            TryWriteError(ex.Message);
            return 1;
        }
    }

    private static int EditPayload()
    {
        string payloadJson = OlePayloadRegistryStore.ReadEditorPayload();
        string latex = OlePayloadRegistryStore.ReadLatex(payloadJson);
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        var editor = new MathLiveFormulaEditor(CreateEditorOptions());
        FormulaEditorAcceptedEventArgs? accepted = editor.ShowModal(CreateEditorMetadata(latex), updateMode: true);
        if (accepted == null)
        {
            return 2;
        }

        string updatedPayload = RenderPayloadAsync(payloadJson, accepted.Latex).GetAwaiter().GetResult();
        OlePayloadRegistryStore.SaveEditorPayloadResult(updatedPayload);
        return 0;
    }

    private static FormulaMetadata CreateEditorMetadata(string latex)
    {
        return new FormulaMetadata(
            new FormulaIdentity("ole-object", Guid.NewGuid().ToString("N")),
            latex,
            FormulaDisplayMode.Display,
            NumberingMode.None,
            string.Empty,
            RenderEngineKind.MathJaxSvg,
            schemaVersion: 1);
    }

    private static MathLiveFormulaEditorOptions CreateEditorOptions()
    {
        return new MathLiveFormulaEditorOptions(
            "latexsnipper-ole.officeplugin.local",
            "OleFormulaObjectEditorWebView2",
            new[]
            {
                @"office_plugin\hosts\WordAddIn\EditorAssets",
                @"office_plugin\hosts\PowerPointAddIn\EditorAssets",
            },
            Array.Empty<string>())
        {
            ForceDisplayMode = true,
            Icon = LoadIcon()
        };
    }

    private static Icon? LoadIcon()
    {
        string path = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "icon.ico");
        return File.Exists(path) ? new Icon(path) : null;
    }

    private static async System.Threading.Tasks.Task<string> RenderPayloadAsync(string payloadJson, string latex)
    {
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
        return OlePayloadRegistryStore.WithPresentation(payloadJson, latex, intermediate.RendererVersion, presentation);
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
