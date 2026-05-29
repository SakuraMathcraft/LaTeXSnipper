using System;
using System.Threading;
using System.Windows.Forms;
using LaTeXSnipper.OfficePlugin.Bridge;
using LaTeXSnipper.OfficePlugin.Editor;

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
        var editor = new MathLiveFormulaEditor();
        var editorSession = new FormulaEditorSession(editor);
        var bridgeClient = new BridgeClient(CreateBridgeOptions());
        var wordAdapter = new DynamicWordApplicationAdapter(wordApplication);
        var controller = new WordPluginController(editorSession, bridgeClient, wordAdapter, statusSink, optionsProvider);
        editor.FormulaAccepted += async (_, accepted) =>
        {
            try
            {
                await controller.AcceptEditorFormulaAsync(accepted, CancellationToken.None);
            }
            catch (Exception exc)
            {
                statusSink.Post(WordStatusKind.Error, exc.Message);
            }
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
}
