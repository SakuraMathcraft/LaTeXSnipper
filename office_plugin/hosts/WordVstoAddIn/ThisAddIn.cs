using System;
using Microsoft.Office.Core;
using LaTeXSnipper.OfficePlugin.WordAddIn;

namespace LaTeXSnipper.OfficePlugin.WordVstoAddIn
{
    public sealed partial class ThisAddIn
    {
        private WordRibbonExtensibility? ribbonExtensibility;
        private WordPluginController? controller;
        private WordRibbonCallbacks? ribbonCallbacks;
        private WordStatusTaskPaneControl? statusPaneControl;
        private Microsoft.Office.Tools.CustomTaskPane? statusTaskPane;

        protected override IRibbonExtensibility CreateRibbonExtensibilityObject()
        {
            ribbonExtensibility ??= new WordRibbonExtensibility();
            if (ribbonCallbacks != null)
            {
                ribbonExtensibility.AttachCallbacks(ribbonCallbacks);
            }

            return ribbonExtensibility;
        }

        private void ThisAddIn_Startup(object sender, EventArgs e)
        {
            if (controller == null)
            {
                statusPaneControl = new WordStatusTaskPaneControl();
                statusTaskPane = CustomTaskPanes.Add(statusPaneControl, WordAddInText.Get("TaskPaneTitle"));
                statusTaskPane.Width = 480;
                statusTaskPane.Visible = false;

                var visibleStatusSink = new VisibleWordStatusSink(statusPaneControl, ShowStatusPane);
                controller = WordAddInFactory.CreateController(Application, visibleStatusSink, statusPaneControl);
                ribbonCallbacks = new WordRibbonCallbacks(controller, visibleStatusSink, ShowStatusPane);
                AttachTaskPaneCommands(statusPaneControl, ribbonCallbacks);
                ribbonExtensibility?.AttachCallbacks(ribbonCallbacks);
                _ = WarmUpControllerAsync(controller, statusPaneControl);
            }
        }

        private void ThisAddIn_Shutdown(object sender, EventArgs e)
        {
            controller?.Dispose();
            controller = null;
        }

        private static async System.Threading.Tasks.Task WarmUpControllerAsync(
            WordPluginController controller,
            IWordStatusSink statusSink)
        {
            try
            {
                using var timeout = new System.Threading.CancellationTokenSource(System.TimeSpan.FromSeconds(20));
                await controller.WarmUpAsync(timeout.Token);
            }
            catch (OperationCanceledException)
            {
                statusSink.Post(WordStatusKind.Error, WordAddInText.Get("CommandTimeoutStatus"));
            }
            catch (Exception exc)
            {
                statusSink.Post(WordStatusKind.Error, exc.Message);
            }
        }

        private void ShowStatusPane()
        {
            if (statusTaskPane != null)
            {
                statusTaskPane.Visible = true;
            }
        }

        private static void AttachTaskPaneCommands(WordStatusTaskPaneControl pane, WordRibbonCallbacks callbacks)
        {
            pane.ConnectRequested += (_, _) => callbacks.OnConnect(pane);
            pane.InsertRequested += (_, _) => callbacks.OnInsertFromTaskPane(pane);
            pane.ScreenshotOcrRequested += (_, _) => callbacks.OnScreenshotOcr(pane);
            pane.RenumberRequested += (_, _) => callbacks.OnRenumberAll(pane);
        }

        private void InternalStartup()
        {
            Startup += ThisAddIn_Startup;
            Shutdown += ThisAddIn_Shutdown;
        }
    }
}
