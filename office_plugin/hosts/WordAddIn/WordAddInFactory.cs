using System;
using System.Threading;
using LaTeXSnipper.OfficePlugin.Abstractions;
using LaTeXSnipper.OfficePlugin.Automation;
using LaTeXSnipper.OfficePlugin.Editor;
using LaTeXSnipper.OfficePlugin.Rendering;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public static class WordAddInFactory
{
    public static WordPluginController CreateController(
        object wordApplication,
        IWordStatusSink? statusSink = null,
        IWordFormulaOptionsProvider? optionsProvider = null,
        Func<WordPluginSettings>? settingsLoader = null,
        string? mathJaxHostName = null)
    {
        statusSink ??= NullWordStatusSink.Instance;
        var editor = new MathLiveFormulaEditor(CreateEditorOptions());
        var editorSession = new FormulaEditorSession(editor);
        var automationClient = new AutomationApiClient(new AutomationApiOptions());
        var wordAdapter = new DynamicWordApplicationAdapter(wordApplication);
        var oleIntermediateRenderer = new MathJaxSvgRenderer(
            new WebView2MathJaxJavaScriptRuntime(mathJaxHostName ?? "WordAddIn"));
        var olePresentationPipeline = new OlePresentationPipeline(new IOlePresentationRenderer[] { new EnhancedMetafilePresentationRenderer() });
        var controller = new WordPluginController(
            editorSession,
            automationClient,
            wordAdapter,
            oleIntermediateRenderer,
            olePresentationPipeline,
            statusSink,
            optionsProvider,
            settingsLoader: settingsLoader);
        editor.FormulaSubmitting += async accepted =>
        {
            using var timeout = OfficeCommandTimeouts.CreateStandardCommandTokenSource();
            return await controller.TryAcceptEditorFormulaAsync(accepted, timeout.Token).ConfigureAwait(true);
        };
        editor.EditorCancelled += (_, cancelled) => controller.CancelEditorFormula(cancelled.SessionGeneration);
        editor.EditorError += (_, message) => statusSink.Post(WordStatusKind.Error, message);
        return controller;
    }

    private static MathLiveFormulaEditorOptions CreateEditorOptions()
    {
        return new MathLiveFormulaEditorOptions(
            "latexsnipper-word.officeplugin.local",
            "latexsnipper-editor-shared.officeplugin.local",
            "WordEditorWebView2",
            new[] { @"office_plugin\hosts\WordAddIn\EditorAssets" },
            new[] { @"office_plugin\src\LaTeXSnipper.OfficePlugin.Editor\EditorAssets" },
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
