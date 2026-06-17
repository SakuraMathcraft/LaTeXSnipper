using System;
using System.Collections.Generic;
using Microsoft.Office.Core;
using LaTeXSnipper.OfficePlugin.PowerPointAddIn;
using PowerPoint = Microsoft.Office.Interop.PowerPoint;

namespace LaTeXSnipper.OfficePlugin.PowerPointVstoAddIn
{
    public sealed partial class ThisAddIn
    {
        private PowerPointRibbonExtensibility? ribbonExtensibility;
        private PowerPointPluginController? controller;
        private PowerPointRibbonCallbacks? ribbonCallbacks;
        private ActiveWindowStatusPaneHost? statusPaneHost;

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
                statusPaneHost = new ActiveWindowStatusPaneHost(this);
                var visibleStatusSink = new VisiblePowerPointStatusSink(statusPaneHost, ShowStatusPane);
                controller = PowerPointAddInFactory.CreateController(Application, visibleStatusSink, statusPaneHost);
                ribbonCallbacks = new PowerPointRibbonCallbacks(controller, visibleStatusSink, ShowStatusPane);
                statusPaneHost.AttachCallbacks(ribbonCallbacks);
                ribbonExtensibility?.AttachCallbacks(ribbonCallbacks);
                Application.WindowActivate += OnWindowActivate;
                InitializeActiveStatusPane();
                _ = WarmUpControllerAsync(controller, statusPaneHost);
            }
        }

        private void ThisAddIn_Shutdown(object sender, EventArgs e)
        {
            Application.WindowActivate -= OnWindowActivate;
            controller?.Dispose();
            controller = null;
            statusPaneHost?.Dispose();
            statusPaneHost = null;
        }

        private void OnWindowActivate(PowerPoint.Presentation presentation, PowerPoint.DocumentWindow window)
        {
            statusPaneHost?.EnsurePane(window);
        }

        private void InitializeActiveStatusPane()
        {
            try
            {
                statusPaneHost?.EnsurePane(Application.ActiveWindow);
            }
            catch
            {
            }
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
            statusPaneHost?.ShowActivePane();
        }

        private static void AttachTaskPaneCommands(PowerPointStatusTaskPaneControl pane, PowerPointRibbonCallbacks callbacks)
        {
            pane.ConnectRequested += (_, _) => callbacks.OnConnect(pane);
            pane.InsertRequested += (_, _) => callbacks.OnInsertFromTaskPane(pane);
            pane.ScreenshotOcrRequested += (_, _) => callbacks.OnScreenshotOcr(pane);
        }

        private sealed class ActiveWindowStatusPaneHost : IPowerPointStatusSink, IPowerPointFormulaOptionsProvider, IDisposable
        {
            private readonly ThisAddIn addIn;
            private readonly Dictionary<int, PaneEntry> panes = new();
            private PowerPointRibbonCallbacks? callbacks;

            public ActiveWindowStatusPaneHost(ThisAddIn addIn)
            {
                this.addIn = addIn;
            }

            public string CurrentLatex => TryGetActivePane(out PaneEntry entry)
                ? entry.Control.CurrentLatex
                : "e^{i\\pi}+1=0";

            public void AttachCallbacks(PowerPointRibbonCallbacks callbacks)
            {
                this.callbacks = callbacks;
            }

            public void EnsurePane(PowerPoint.DocumentWindow window)
            {
                _ = GetPane(window);
            }

            public PowerPointFormulaOptions GetFormulaOptions()
            {
                return TryGetActivePane(out PaneEntry entry)
                    ? entry.Control.GetFormulaOptions()
                    : new PowerPointFormulaOptions();
            }

            public void ResetFormulaDraft()
            {
                if (TryGetActivePane(out PaneEntry entry))
                {
                    entry.Control.ResetFormulaDraft();
                }
            }

            public void Post(PowerPointStatusKind kind, string message)
            {
                if (TryGetActivePane(out PaneEntry entry))
                {
                    entry.Control.Post(kind, message);
                }
            }

            public void SetBusy(bool busy)
            {
                if (TryGetActivePane(out PaneEntry entry))
                {
                    entry.Control.SetBusy(busy);
                }
            }

            public void SetOcrActive(bool active)
            {
                if (TryGetActivePane(out PaneEntry entry))
                {
                    entry.Control.SetOcrActive(active);
                }
            }

            public void SetCurrentFormula(string latex, bool updateMode)
            {
                if (TryGetActivePane(out PaneEntry entry))
                {
                    entry.Control.SetCurrentFormula(latex, updateMode);
                }
            }

            public void ShowActivePane()
            {
                GetActivePane().TaskPane.Visible = true;
            }

            public void Dispose()
            {
                foreach (PaneEntry entry in panes.Values)
                {
                    entry.TaskPane.Visible = false;
                }

                panes.Clear();
            }

            private bool TryGetActivePane(out PaneEntry entry)
            {
                try
                {
                    entry = GetActivePane();
                    return true;
                }
                catch
                {
                    entry = null!;
                    return false;
                }
            }

            private PaneEntry GetActivePane()
            {
                PowerPoint.DocumentWindow window = addIn.Application.ActiveWindow;
                return GetPane(window);
            }

            private PaneEntry GetPane(PowerPoint.DocumentWindow window)
            {
                int key = Convert.ToInt32(window.HWND);
                if (panes.TryGetValue(key, out PaneEntry entry))
                {
                    return entry;
                }

                var control = new PowerPointStatusTaskPaneControl();
                Microsoft.Office.Tools.CustomTaskPane taskPane =
                    addIn.CustomTaskPanes.Add(control, PowerPointAddInText.Get("TaskPaneTitle"), window);
                taskPane.Width = 480;
                taskPane.Visible = false;
                if (callbacks != null)
                {
                    AttachTaskPaneCommands(control, callbacks);
                }

                entry = new PaneEntry(control, taskPane);
                panes.Add(key, entry);
                return entry;
            }

            private sealed class PaneEntry
            {
                public PaneEntry(PowerPointStatusTaskPaneControl control, Microsoft.Office.Tools.CustomTaskPane taskPane)
                {
                    Control = control;
                    TaskPane = taskPane;
                }

                public PowerPointStatusTaskPaneControl Control { get; }

                public Microsoft.Office.Tools.CustomTaskPane TaskPane { get; }
            }
        }
    }
}
