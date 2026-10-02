using System;
using System.IO;
using System.Windows.Forms;

internal static class Program
{
    [STAThread]
    private static int Main(string[] args)
    {
        if (args.Length < 1 || args.Length > 3 || (args.Length >= 2 && args[1] != "--ole" && args[1] != "--batch" && args[1] != "--copy" && args[1] != "--gesture")
            || (args.Length == 3 && ((args[1] != "--ole" && args[1] != "--copy") || args[2] != "--mathtype")))
        { Console.Error.WriteLine("Usage: PowerPointE2E <output.pptx> [--ole [--mathtype]|--batch|--copy [--mathtype]|--gesture]"); return 2; }
        Application.EnableVisualStyles();
        System.Diagnostics.Trace.Listeners.Add(new System.Diagnostics.ConsoleTraceListener());
        int exitCode = 1;
        using var host = new Form { ShowInTaskbar = false, Opacity = 0, Width = 1, Height = 1 };
        host.Shown += async (_, _) =>
        {
            host.Hide();
            try
            {
                await PowerPointRoundTrip.RunAsync(Path.GetFullPath(args[0]),
                    args.Length >= 2 && args[1] == "--ole", args.Length >= 2 && args[1] == "--batch", args.Length == 3,
                    args.Length >= 2 && args[1] == "--copy", args.Length >= 2 && args[1] == "--gesture");
                exitCode = 0;
            }
            catch (Exception error) { Console.Error.WriteLine(error); }
            finally { host.Close(); }
        };
        Application.Run(host);
        return exitCode;
    }
}
