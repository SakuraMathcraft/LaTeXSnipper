using System;
using System.Threading;
using LaTeXSnipper.OfficePlugin.Abstractions;
using LaTeXSnipper.OfficePlugin.Bridge;
using LaTeXSnipper.OfficePlugin.Editor;
using LaTeXSnipper.OfficePlugin.Rendering;

namespace LaTeXSnipper.OfficePlugin.PowerPointAddIn;

public static class PowerPointAddInFactory
{
    private const string BridgeUrlEnvironmentVariable = "LATEXSNIPPER_OFFICE_BRIDGE_URL";
    private const string BridgeTokenEnvironmentVariable = "LATEXSNIPPER_OFFICE_BRIDGE_TOKEN";
    private const string DefaultBridgeUrl = "http://127.0.0.1:28765/";

    public static PowerPointPluginController CreateController(
        object powerPointApplication,
        IPowerPointStatusSink? statusSink = null,
        IPowerPointFormulaOptionsProvider? optionsProvider = null)
    {
        statusSink ??= NullPowerPointStatusSink.Instance;
        var editor = new MathLiveFormulaEditor(CreateEditorOptions());
        var editorSession = new FormulaEditorSession(editor);
        var bridgeClient = new BridgeClient(CreateBridgeOptions());
        var adapter = new DynamicPowerPointApplicationAdapter(powerPointApplication);
        var oleIntermediateRenderer = new MathJaxSvgRenderer(new WebView2MathJaxJavaScriptRuntime("PowerPointAddIn"));
        var olePresentationPipeline = new OlePresentationPipeline(new IOlePresentationRenderer[] { new EnhancedMetafilePresentationRenderer() });
        var controller = new PowerPointPluginController(
            editorSession,
            bridgeClient,
            adapter,
            oleIntermediateRenderer,
            olePresentationPipeline,
            statusSink,
            optionsProvider);
        editor.FormulaSubmitting += async accepted =>
        {
            using var timeout = OfficeCommandTimeouts.CreateStandardCommandTokenSource();
            return await controller.TryAcceptEditorFormulaAsync(accepted, timeout.Token).ConfigureAwait(true);
        };
        editor.EditorCancelled += (_, _) => optionsProvider?.ResetFormulaDraft();
        editor.EditorError += (_, message) => statusSink.Post(PowerPointStatusKind.Error, message);
        return controller;
    }

    private static BridgeOptions CreateBridgeOptions()
    {
        string value = Environment.GetEnvironmentVariable(BridgeUrlEnvironmentVariable) ?? DefaultBridgeUrl;
        string normalized = value.EndsWith("/", StringComparison.Ordinal) ? value : value + "/";
        return new BridgeOptions(new Uri(normalized))
        {
            Token = Environment.GetEnvironmentVariable(BridgeTokenEnvironmentVariable) ?? string.Empty,
        };
    }

    private static MathLiveFormulaEditorOptions CreateEditorOptions()
    {
        return new MathLiveFormulaEditorOptions(
            "latexsnipper-powerpoint.officeplugin.local",
            "PowerPointEditorWebView2",
            new[] { @"office_plugin\hosts\PowerPointAddIn\EditorAssets" },
            new[]
            {
                @"Software\Microsoft\Office\PowerPoint\Addins\LaTeXSnipper.OfficePlugin.PowerPointVstoAddIn",
                @"Software\Microsoft\Office\16.0\PowerPoint\Addins\LaTeXSnipper.OfficePlugin.PowerPointVstoAddIn",
                @"Software\Microsoft\Office\ClickToRun\REGISTRY\MACHINE\Software\Microsoft\Office\PowerPoint\Addins\LaTeXSnipper.OfficePlugin.PowerPointVstoAddIn",
                @"Software\Microsoft\Office\ClickToRun\REGISTRY\MACHINE\Software\Microsoft\Office\16.0\PowerPoint\Addins\LaTeXSnipper.OfficePlugin.PowerPointVstoAddIn",
            })
        {
            Icon = PowerPointPluginIcon.Load(),
            ForceDisplayMode = true
        };
    }
}
