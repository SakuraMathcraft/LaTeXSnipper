using System.Windows.Forms;

namespace LaTeXSnipper.OfficePlugin.PowerPointAddIn;

public sealed class MessageBoxPowerPointStatusSink : IPowerPointStatusSink
{
    public void Post(PowerPointStatusKind kind, string message)
    {
        if (kind != PowerPointStatusKind.Error || string.IsNullOrWhiteSpace(message))
        {
            return;
        }

        MessageBox.Show(message, "LaTeXSnipper", MessageBoxButtons.OK, MessageBoxIcon.Error);
    }

    public void SetBusy(bool busy)
    {
    }

    public void SetOcrActive(bool active)
    {
    }

    public void SetCurrentFormula(string latex, bool updateMode)
    {
    }
}
