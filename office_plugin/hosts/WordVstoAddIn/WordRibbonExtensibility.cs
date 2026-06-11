using System;
using System.Runtime.InteropServices;
using Microsoft.Office.Core;
using LaTeXSnipper.OfficePlugin.WordAddIn;

namespace LaTeXSnipper.OfficePlugin.WordVstoAddIn
{
    [ComVisible(true)]
    [Guid("AD5C4EEA-516B-4F8A-9C03-EE9EA83F8DBB")]
    public sealed class WordRibbonExtensibility : IRibbonExtensibility
    {
        private WordRibbonCallbacks? callbacks;

        public void AttachCallbacks(WordRibbonCallbacks attachedCallbacks)
        {
            callbacks = attachedCallbacks ?? throw new ArgumentNullException(nameof(attachedCallbacks));
        }

        public string GetCustomUI(string ribbonId)
        {
            return WordRibbonXml.GetCustomUI();
        }

        public void OnInsertOmml(IRibbonControl control)
        {
            callbacks?.OnInsertOmml(control);
        }

        public void OnInsertInline(IRibbonControl control)
        {
            callbacks?.OnInsertInline(control);
        }

        public void OnInsertDisplay(IRibbonControl control)
        {
            callbacks?.OnInsertDisplay(control);
        }

        public void OnInsertNumbered(IRibbonControl control)
        {
            callbacks?.OnInsertNumbered(control);
        }

        public void OnLoadSelected(IRibbonControl control)
        {
            callbacks?.OnLoadSelected(control);
        }

        public void OnScreenshotOcr(IRibbonControl control)
        {
            callbacks?.OnScreenshotOcr(control);
        }

        public void OnDeleteSelected(IRibbonControl control)
        {
            callbacks?.OnDeleteSelected(control);
        }

        public void OnAutoNumberSelected(IRibbonControl control)
        {
            callbacks?.OnAutoNumberSelected(control);
        }

        public void OnRenumberAll(IRibbonControl control)
        {
            callbacks?.OnRenumberAll(control);
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

        public void OnConvertSelectedToOle(IRibbonControl control) => callbacks?.OnConvertSelectedToOle(control);
        public void OnConvertSelectedToOmml(IRibbonControl control) => callbacks?.OnConvertSelectedToOmml(control);
        public void OnConvertAllToOle(IRibbonControl control) => callbacks?.OnConvertAllToOle(control);
        public void OnConvertAllToOmml(IRibbonControl control) => callbacks?.OnConvertAllToOmml(control);
        public void OnInsertReference(IRibbonControl control) => callbacks?.OnInsertReference(control);
        public void OnInsertChapterBoundary(IRibbonControl control) => callbacks?.OnInsertChapterBoundary(control);
        public void OnInsertSectionBoundary(IRibbonControl control) => callbacks?.OnInsertSectionBoundary(control);
        public void OnFormatSelected(IRibbonControl control) => callbacks?.OnFormatSelected(control);
        public void OnFormatAll(IRibbonControl control) => callbacks?.OnFormatAll(control);

    }
}
