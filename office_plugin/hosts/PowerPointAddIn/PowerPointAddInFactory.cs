using System;
using System.Threading;
using LaTeXSnipper.OfficePlugin.Abstractions;
using LaTeXSnipper.OfficePlugin.Automation;
using LaTeXSnipper.OfficePlugin.Editor;
using LaTeXSnipper.OfficePlugin.Rendering;

namespace LaTeXSnipper.OfficePlugin.PowerPointAddIn;

public static class PowerPointAddInFactory
{
    public static PowerPointPluginController CreateController(
        object powerPointApplication,
        IPowerPointStatusSink? statusSink = null,
        IPowerPointFormulaOptionsProvider? optionsProvider = null)
    {
        statusSink ??= NullPowerPointStatusSink.Instance;
        var editor = new MathLiveFormulaEditor(CreateEditorOptions());
        var editorSession = new FormulaEditorSession(editor);
        var automationClient = new AutomationApiClient(new AutomationApiOptions());
        var adapter = new DynamicPowerPointApplicationAdapter(powerPointApplication);
        var oleIntermediateRenderer = new MathJaxSvgRenderer(new WebView2MathJaxJavaScriptRuntime("PowerPointAddIn"));
        var olePresentationPipeline = new OlePresentationPipeline(new IOlePresentationRenderer[] { new EnhancedMetafilePresentationRenderer() });
        var controller = new PowerPointPluginController(
            editorSession,
            automationClient,
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
        editor.EditorCancelled += (_, cancelled) => controller.CancelEditorFormula(cancelled.SessionGeneration);
        editor.EditorError += (_, message) => statusSink.Post(PowerPointStatusKind.Error, message);
        return controller;
    }

    private static MathLiveFormulaEditorOptions CreateEditorOptions()
    {
        return new MathLiveFormulaEditorOptions(
            "latexsnipper-powerpoint.officeplugin.local",
            "latexsnipper-editor-shared.officeplugin.local",
            "PowerPointEditorWebView2",
            new[] { @"office_plugin\hosts\PowerPointAddIn\EditorAssets" },
            new[] { @"office_plugin\src\LaTeXSnipper.OfficePlugin.Editor\EditorAssets" },
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
