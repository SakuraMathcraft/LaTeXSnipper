using System;
using Microsoft.Office.Core;
using LaTeXSnipper.OfficePlugin.PowerPointAddIn;

namespace LaTeXSnipper.OfficePlugin.PowerPointVstoAddIn
{
    public sealed partial class ThisAddIn
    {
        private PowerPointRibbonExtensibility? ribbonExtensibility;
        private PowerPointPluginController? controller;
        private PowerPointRibbonCallbacks? ribbonCallbacks;
        private PowerPointStatusTaskPaneControl? statusPaneControl;
        private Microsoft.Office.Tools.CustomTaskPane? statusTaskPane;

        protected override IRibbonExtensibility CreateRibbonExtensibilityObject()
        {
            ribbonExtensibility ??= new PowerPointRibbonExtensibility();
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
                statusPaneControl = new PowerPointStatusTaskPaneControl();
                statusTaskPane = CustomTaskPanes.Add(statusPaneControl, PowerPointAddInText.Get("TaskPaneTitle"));
                statusTaskPane.Width = 480;
                statusTaskPane.Visible = false;

                var visibleStatusSink = new VisiblePowerPointStatusSink(statusPaneControl, ShowStatusPane);
                controller = PowerPointAddInFactory.CreateController(Application, visibleStatusSink, statusPaneControl);
                ribbonCallbacks = new PowerPointRibbonCallbacks(controller, visibleStatusSink, ShowStatusPane);
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
            PowerPointPluginController controller,
            IPowerPointStatusSink statusSink)
        {
            try
            {
                using var timeout = new System.Threading.CancellationTokenSource(System.TimeSpan.FromSeconds(20));
                await controller.WarmUpAsync(timeout.Token);
            }
            catch (OperationCanceledException)
            {
                statusSink.Post(PowerPointStatusKind.Error, PowerPointAddInText.Get("CommandTimeoutStatus"));
            }
            catch (Exception exc)
            {
                statusSink.Post(PowerPointStatusKind.Error, exc.Message);
            }
        }

        private void InternalStartup()
        {
            Startup += ThisAddIn_Startup;
            Shutdown += ThisAddIn_Shutdown;
        }

        private void ShowStatusPane()
        {
            if (statusTaskPane != null)
            {
                statusTaskPane.Visible = true;
            }
        }

        private static void AttachTaskPaneCommands(PowerPointStatusTaskPaneControl pane, PowerPointRibbonCallbacks callbacks)
        {
            pane.ConnectRequested += (_, _) => callbacks.OnConnect(pane);
            pane.InsertRequested += (_, _) => callbacks.OnInsertFromTaskPane(pane);
            pane.ScreenshotOcrRequested += (_, _) => callbacks.OnScreenshotOcr(pane);
        }
    }
}
