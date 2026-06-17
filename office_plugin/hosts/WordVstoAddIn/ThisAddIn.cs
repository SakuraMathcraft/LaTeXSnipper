using System;
using System.Collections.Generic;
using Microsoft.Office.Core;
using LaTeXSnipper.OfficePlugin.WordAddIn;

namespace LaTeXSnipper.OfficePlugin.WordVstoAddIn
{
    public sealed partial class ThisAddIn
    {
        private WordRibbonExtensibility? ribbonExtensibility;
        private WordPluginController? controller;
        private WordRibbonCallbacks? ribbonCallbacks;
        private ActiveWindowStatusPaneHost? statusPaneHost;

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
                statusPaneHost = new ActiveWindowStatusPaneHost(this);
                var visibleStatusSink = new VisibleWordStatusSink(statusPaneHost, ShowStatusPane);
                controller = WordAddInFactory.CreateController(Application, visibleStatusSink, statusPaneHost);
                ribbonCallbacks = new WordRibbonCallbacks(controller, visibleStatusSink, ShowStatusPane);
                statusPaneHost.AttachCallbacks(ribbonCallbacks);
                ribbonExtensibility?.AttachCallbacks(ribbonCallbacks);
                Application.WindowSelectionChange += OnWindowSelectionChange;
                _ = WarmUpControllerAsync(controller, statusPaneHost);
            }
        }

        private void ThisAddIn_Shutdown(object sender, EventArgs e)
        {
            Application.WindowSelectionChange -= OnWindowSelectionChange;
            controller?.Dispose();
            controller = null;
            statusPaneHost?.Dispose();
            statusPaneHost = null;
        }

        private void OnWindowSelectionChange(Microsoft.Office.Interop.Word.Selection selection)
        {
            ribbonCallbacks?.OnSelectionChanged();
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
            statusPaneHost?.ShowActivePane();
        }

        private static void AttachTaskPaneCommands(WordStatusTaskPaneControl pane, WordRibbonCallbacks callbacks)
        {
            pane.ConnectRequested += (_, _) => callbacks.OnConnect(pane);
            pane.InsertRequested += (_, _) => callbacks.OnInsertFromTaskPane(pane);
            pane.ScreenshotOcrRequested += (_, _) => callbacks.OnScreenshotOcr(pane);
            pane.RenumberRequested += (_, _) => callbacks.OnRenumberAll(pane);
        }

        private sealed class ActiveWindowStatusPaneHost : IWordStatusSink, IWordFormulaOptionsProvider, IDisposable
        {
            private readonly ThisAddIn addIn;
            private readonly Dictionary<int, PaneEntry> panes = new();
            private WordRibbonCallbacks? callbacks;

            public ActiveWindowStatusPaneHost(ThisAddIn addIn)
            {
                this.addIn = addIn;
            }

            public string CurrentLatex => GetActivePane().Control.CurrentLatex;

            public void AttachCallbacks(WordRibbonCallbacks callbacks)
            {
                this.callbacks = callbacks;
            }

            public WordFormulaOptions GetFormulaOptions()
            {
                return GetActivePane().Control.GetFormulaOptions();
            }

            public void ApplyFormulaMetadata(LaTeXSnipper.OfficePlugin.Abstractions.FormulaMetadata metadata, bool updateMode)
            {
                GetActivePane().Control.ApplyFormulaMetadata(metadata, updateMode);
            }

            public void ResetFormulaDraft()
            {
                GetActivePane().Control.ResetFormulaDraft();
            }

            public void Post(WordStatusKind kind, string message)
            {
                GetActivePane().Control.Post(kind, message);
            }

            public void SetBusy(bool busy)
            {
                GetActivePane().Control.SetBusy(busy);
            }

            public void SetOcrActive(bool active)
            {
                GetActivePane().Control.SetOcrActive(active);
            }

            public void SetCurrentFormula(string latex, bool updateMode)
            {
                GetActivePane().Control.SetCurrentFormula(latex, updateMode);
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

            private PaneEntry GetActivePane()
            {
                dynamic window = addIn.Application.ActiveWindow;
                int key = Convert.ToInt32(window.Hwnd);
                if (panes.TryGetValue(key, out PaneEntry entry))
                {
                    return entry;
                }

                var control = new WordStatusTaskPaneControl();
                Microsoft.Office.Tools.CustomTaskPane taskPane =
                    addIn.CustomTaskPanes.Add(control, WordAddInText.Get("TaskPaneTitle"), window);
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
                public PaneEntry(WordStatusTaskPaneControl control, Microsoft.Office.Tools.CustomTaskPane taskPane)
                {
                    Control = control;
                    TaskPane = taskPane;
                }

                public WordStatusTaskPaneControl Control { get; }

                public Microsoft.Office.Tools.CustomTaskPane TaskPane { get; }
            }
        }

        private void InternalStartup()
        {
            Startup += ThisAddIn_Startup;
            Shutdown += ThisAddIn_Shutdown;
        }
    }
}
