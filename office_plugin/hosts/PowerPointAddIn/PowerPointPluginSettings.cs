using System;
using LaTeXSnipper.OfficePlugin.Abstractions;
using Microsoft.Win32;

namespace LaTeXSnipper.OfficePlugin.PowerPointAddIn;

public sealed class PowerPointPluginSettings
{
    private const string RegistryPath = @"Software\LaTeXSnipper\OfficePlugin";
    private const string InsertionBackendValue = "PowerPointInsertionBackend";

    public PowerPointPluginSettings(FormulaInsertionBackend insertionBackend)
    {
        InsertionBackend = insertionBackend;
    }

    public FormulaInsertionBackend InsertionBackend { get; }

    public static PowerPointPluginSettings Load()
    {
        using RegistryKey? key = Registry.CurrentUser.OpenSubKey(RegistryPath);
        string raw = key?.GetValue(InsertionBackendValue) as string ?? string.Empty;
        FormulaInsertionBackend backend = raw == FormulaInsertionBackend.PowerPointCompatibility.ToString()
            ? FormulaInsertionBackend.PowerPointCompatibility
            : FormulaInsertionBackend.Ole;
        return new PowerPointPluginSettings(backend);
    }

    public void Save()
    {
        using RegistryKey key = Registry.CurrentUser.CreateSubKey(RegistryPath)
            ?? throw new InvalidOperationException("Unable to open LaTeXSnipper Office plugin settings.");
        key.SetValue(InsertionBackendValue, InsertionBackend.ToString(), RegistryValueKind.String);
    }
}
