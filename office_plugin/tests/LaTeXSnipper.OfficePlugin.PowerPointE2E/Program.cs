using System;
using System.IO;
using System.Windows.Forms;

internal static class Program
{
    [STAThread]
    private static int Main(string[] args)
    {
        if (args.Length < 1 || args.Length > 2 || (args.Length == 2 && args[1] != "--ole"))
        { Console.Error.WriteLine("Usage: PowerPointE2E <output.pptx> [--ole]"); return 2; }
        Application.EnableVisualStyles();
        int exitCode = 1;
        using var host = new Form { ShowInTaskbar = false, Opacity = 0, Width = 1, Height = 1 };
        host.Shown += async (_, _) =>
        {
            host.Hide();
            try { await PowerPointRoundTrip.RunAsync(Path.GetFullPath(args[0]), args.Length == 2); exitCode = 0; }
            catch (Exception error) { Console.Error.WriteLine(error); }
            finally { host.Close(); }
        };
        Application.Run(host);
        return exitCode;
    }
}
