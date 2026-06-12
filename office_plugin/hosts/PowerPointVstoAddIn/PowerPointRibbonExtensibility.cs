using System;
using System.Runtime.InteropServices;
using Microsoft.Office.Core;
using LaTeXSnipper.OfficePlugin.PowerPointAddIn;

namespace LaTeXSnipper.OfficePlugin.PowerPointVstoAddIn
{
    [ComVisible(true)]
    [Guid("3A7C0FC3-E9A5-4B62-B53C-7E4DB14F2563")]
    public sealed class PowerPointRibbonExtensibility : IRibbonExtensibility
    {
        private PowerPointRibbonCallbacks? callbacks;

        public void AttachCallbacks(PowerPointRibbonCallbacks attachedCallbacks)
        {
            callbacks = attachedCallbacks ?? throw new ArgumentNullException(nameof(attachedCallbacks));
        }

        public string GetCustomUI(string ribbonId)
        {
            return PowerPointRibbonXml.GetCustomUI();
        }

        public void OnInsertFormula(IRibbonControl control)
        {
            callbacks?.OnInsertFormula(control);
        }

        public void OnScreenshotOcr(IRibbonControl control)
        {
            callbacks?.OnScreenshotOcr(control);
        }

        public void OnLoadSelected(IRibbonControl control)
        {
            callbacks?.OnLoadSelected(control);
        }

        public void OnDeleteSelected(IRibbonControl control)
        {
            callbacks?.OnDeleteSelected(control);
        }

        public void OnConvertSelectedToOle(IRibbonControl control)
        {
            callbacks?.OnConvertSelectedToOle(control);
        }

        public void OnConvertSelectedToPng(IRibbonControl control)
        {
            callbacks?.OnConvertSelectedToPng(control);
        }

        public void OnFormatSelected(IRibbonControl control)
        {
            callbacks?.OnFormatSelected(control);
        }

        public void OnFormatAll(IRibbonControl control)
        {
            callbacks?.OnFormatAll(control);
        }

        public void OnShowTaskPane(IRibbonControl control)
        {
            callbacks?.OnShowTaskPane(control);
        }

        public void OnSettings(IRibbonControl control)
        {
            callbacks?.OnSettings(control);
        }

        public void OnHelp(IRibbonControl control)
        {
            callbacks?.OnHelp(control);
        }
    }
}
