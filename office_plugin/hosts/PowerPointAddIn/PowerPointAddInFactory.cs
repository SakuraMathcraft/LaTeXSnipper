using System;
using System.Threading;
using LaTeXSnipper.OfficePlugin.Abstractions;
using LaTeXSnipper.OfficePlugin.Bridge;
using LaTeXSnipper.OfficePlugin.Editor;

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
        var editor = new PowerPointFormulaEditor();
        var editorSession = new FormulaEditorSession(editor);
        var bridgeClient = new BridgeClient(CreateBridgeOptions());
        var adapter = new DynamicPowerPointApplicationAdapter(powerPointApplication);
        var controller = new PowerPointPluginController(editorSession, bridgeClient, adapter, statusSink, optionsProvider);
        editor.FormulaAccepted += async (_, accepted) =>
        {
            try
            {
                using var timeout = OfficeCommandTimeouts.CreateStandardCommandTokenSource();
                await controller.AcceptEditorFormulaAsync(accepted, timeout.Token);
            }
            catch (OperationCanceledException)
            {
                statusSink.Post(PowerPointStatusKind.Error, PowerPointAddInText.Get("CommandTimeoutStatus"));
            }
            catch (Exception exc)
            {
                statusSink.Post(PowerPointStatusKind.Error, exc.Message);
            }
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
}
