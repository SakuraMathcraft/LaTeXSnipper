using System;
using System.Diagnostics;
using System.IO;
using System.Threading.Tasks;
using System.Windows.Forms;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.WordParsingE2E;

internal static class Program
{
    [STAThread]
    private static int Main(string[] args)
    {
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        Trace.Listeners.Add(new ConsoleTraceListener(useErrorStream: true));

        E2EOptions options;
        try
        {
            options = E2EOptions.Parse(args);
        }
        catch (Exception exception)
        {
            Console.Error.WriteLine(exception.Message);
            return 2;
        }

        int exitCode = 1;
        using var messageFilter = WordComMessageFilter.Register();
        using var host = new Form
        {
            ShowInTaskbar = false,
            StartPosition = FormStartPosition.Manual,
            Width = 1,
            Height = 1,
            Opacity = 0,
        };
        host.Shown += async (_, _) =>
        {
            host.Hide();
            try
            {
                await new WordParsingE2ERunner(options).RunAsync().ConfigureAwait(true);
                exitCode = 0;
            }
            catch (Exception exception)
            {
                Console.Error.WriteLine(exception);
            }
            finally
            {
                host.Close();
            }
        };
        Application.Run(host);
        return exitCode;
    }
}

internal sealed class E2EOptions
{
    private E2EOptions(FormulaInsertionBackend backend, string outputPath)
    {
        Backend = backend;
        OutputPath = outputPath;
    }

    public FormulaInsertionBackend Backend { get; }

    public string OutputPath { get; }

    public static E2EOptions Parse(string[] args)
    {
        FormulaInsertionBackend? backend = null;
        string outputPath = string.Empty;
        for (int index = 0; index < args.Length; index++)
        {
            string argument = args[index];
            if (string.Equals(argument, "--backend", StringComparison.OrdinalIgnoreCase))
            {
                backend = ParseBackend(ReadValue(args, ref index, argument));
            }
            else if (string.Equals(argument, "--output", StringComparison.OrdinalIgnoreCase))
            {
                outputPath = Path.GetFullPath(ReadValue(args, ref index, argument));
            }
            else
            {
                throw new ArgumentException("Unknown argument: " + argument);
            }
        }

        if (!backend.HasValue)
        {
            throw new ArgumentException("--backend must be either omml or ole.");
        }

        if (string.IsNullOrWhiteSpace(outputPath))
        {
            throw new ArgumentException("--output is required.");
        }

        return new E2EOptions(backend.Value, outputPath);
    }

    private static FormulaInsertionBackend ParseBackend(string value)
    {
        if (string.Equals(value, "omml", StringComparison.OrdinalIgnoreCase))
        {
            return FormulaInsertionBackend.WordOmml;
        }

        if (string.Equals(value, "ole", StringComparison.OrdinalIgnoreCase))
        {
            return FormulaInsertionBackend.Ole;
        }

        throw new ArgumentException("Unsupported backend: " + value);
    }

    private static string ReadValue(string[] args, ref int index, string argument)
    {
        index++;
        if (index >= args.Length || string.IsNullOrWhiteSpace(args[index]))
        {
            throw new ArgumentException(argument + " requires a value.");
        }

        return args[index];
    }
}
