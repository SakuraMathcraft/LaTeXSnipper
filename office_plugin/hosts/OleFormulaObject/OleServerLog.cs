using System;
using System.IO;

namespace LaTeXSnipper.OfficePlugin.OleFormulaObject;

internal static class OleServerLog
{
    public static void Write(string message)
    {
        try
        {
            string directory = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "LaTeXSnipper",
                "OfficePlugin",
                "OleFormulaObject");
            Directory.CreateDirectory(directory);
            string path = Path.Combine(directory, "ole-server.log");
            File.AppendAllText(path, DateTimeOffset.Now.ToString("O") + " " + message + Environment.NewLine);
        }
        catch
        {
        }
    }
}
