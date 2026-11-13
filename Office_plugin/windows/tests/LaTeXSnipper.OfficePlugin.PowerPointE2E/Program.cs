using System;
using System.IO;
using System.Linq;
using System.Windows.Forms;

internal static class Program
{
    [STAThread]
    private static int Main(string[] args)
    {
        string mode = args.Length >= 2 ? args[1] : "--ole";
        bool includeMathType = mode == "--mathtype-only" || args.Skip(2).Contains("--mathtype");
        bool nativeEdit = args.Skip(2).Contains("--mathtype-native-edit");
        if (args.Length < 1 || args.Length > 4 || !new[] { "--ole", "--batch", "--copy", "--gesture", "--mathtype-only" }.Contains(mode)
            || args.Skip(2).Any(a => a != "--mathtype" && a != "--mathtype-native-edit")
            || args.Skip(2).Distinct().Count() != args.Skip(2).Count()
            || includeMathType && mode != "--ole" && mode != "--copy" && mode != "--mathtype-only"
            || nativeEdit && !includeMathType)
        { Console.Error.WriteLine("Usage: PowerPointE2E <output.pptx> [--ole|--batch|--copy|--gesture|--mathtype-only] [--mathtype] [--mathtype-native-edit]"); return 2; }
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
                    mode == "--ole", mode == "--batch", includeMathType,
                    mode == "--copy", mode == "--gesture", nativeEdit, mode == "--mathtype-only");
                exitCode = 0;
            }
            catch (Exception error) { Console.Error.WriteLine(error); }
            finally { host.Close(); }
        };
        Application.Run(host);
        return exitCode;
    }
}
