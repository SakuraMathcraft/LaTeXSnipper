using System.Windows.Forms;

namespace LaTeXSnipper.OfficePlugin.OleFormulaObject;

internal static class ApplicationBootstrap
{
    public static void Initialize()
    {
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
    }
}
