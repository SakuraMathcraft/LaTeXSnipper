using System;
using System.Threading;
using LaTeXSnipper.OfficePlugin.Abstractions;
using LaTeXSnipper.OfficePlugin.Bridge;
using LaTeXSnipper.OfficePlugin.Editor;
using LaTeXSnipper.OfficePlugin.Rendering;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public static class WordAddInFactory
{
    private const string BridgeUrlEnvironmentVariable = "LATEXSNIPPER_OFFICE_BRIDGE_URL";
    private const string BridgeTokenEnvironmentVariable = "LATEXSNIPPER_OFFICE_BRIDGE_TOKEN";
    private const string DefaultBridgeUrl = "http://127.0.0.1:28765/";

    public static WordPluginController CreateController(
        object wordApplication,
        IWordStatusSink? statusSink = null,
        IWordFormulaOptionsProvider? optionsProvider = null)
    {
        statusSink ??= NullWordStatusSink.Instance;
        var editor = new MathLiveFormulaEditor(CreateEditorOptions());
        var editorSession = new FormulaEditorSession(editor);
        var bridgeClient = new BridgeClient(CreateBridgeOptions());
        var wordAdapter = new DynamicWordApplicationAdapter(wordApplication);
        var oleIntermediateRenderer = new MathJaxSvgRenderer(new WebView2MathJaxJavaScriptRuntime("WordAddIn"));
        var olePresentationPipeline = new OlePresentationPipeline(new IOlePresentationRenderer[] { new EnhancedMetafilePresentationRenderer() });
        var controller = new WordPluginController(
            editorSession,
            bridgeClient,
            wordAdapter,
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
        editor.EditorError += (_, message) => statusSink.Post(WordStatusKind.Error, message);
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
            "latexsnipper-word.officeplugin.local",
            "WordEditorWebView2",
            new[] { @"office_plugin\hosts\WordAddIn\EditorAssets" },
            new[]
            {
                @"Software\Microsoft\Office\Word\Addins\LaTeXSnipper.OfficePlugin.WordVstoAddIn",
                @"Software\Microsoft\Office\16.0\Word\Addins\LaTeXSnipper.OfficePlugin.WordVstoAddIn",
                @"Software\Microsoft\Office\ClickToRun\REGISTRY\MACHINE\Software\Microsoft\Office\Word\Addins\LaTeXSnipper.OfficePlugin.WordVstoAddIn",
                @"Software\Microsoft\Office\ClickToRun\REGISTRY\MACHINE\Software\Microsoft\Office\16.0\Word\Addins\LaTeXSnipper.OfficePlugin.WordVstoAddIn",
            })
        {
            Icon = WordPluginIcon.Load()
        };
    }
}
