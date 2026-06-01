using System;
using System.IO;
using Microsoft.Win32;

namespace LaTeXSnipper.OfficePlugin.OleFormulaObject;

internal static class OleServerRegistration
{
    public static void RegisterCurrentUser(string serverPath)
    {
        if (string.IsNullOrWhiteSpace(serverPath))
        {
            throw new ArgumentException("OLE server path is required.", nameof(serverPath));
        }

        string fullPath = Path.GetFullPath(serverPath);
        if (!File.Exists(fullPath))
        {
            throw new FileNotFoundException("OLE server executable was not found.", fullPath);
        }

        using RegistryKey classes = Registry.CurrentUser.CreateSubKey(@"Software\Classes") ?? throw new InvalidOperationException("Cannot open HKCU Software\\Classes.");
        RegisterProgId(classes, OleFormulaObjectIds.ProgId);
        RegisterProgId(classes, OleFormulaObjectIds.VersionedProgId);
        RegisterClass(classes, fullPath);
    }

    public static void UnregisterCurrentUser()
    {
        using RegistryKey classes = Registry.CurrentUser.CreateSubKey(@"Software\Classes") ?? throw new InvalidOperationException("Cannot open HKCU Software\\Classes.");
        UnregisterClasses(classes);
    }

    public static void RegisterLocalMachine(string serverPath)
    {
        RegisterInMachineView(serverPath, RegistryView.Default);
        if (Environment.Is64BitOperatingSystem)
        {
            RegisterInMachineView(serverPath, RegistryView.Registry64);
            RegisterInMachineView(serverPath, RegistryView.Registry32);
        }
    }

    public static void UnregisterLocalMachine()
    {
        UnregisterInMachineView(RegistryView.Default);
        if (Environment.Is64BitOperatingSystem)
        {
            UnregisterInMachineView(RegistryView.Registry64);
            UnregisterInMachineView(RegistryView.Registry32);
        }
    }

    private static void RegisterInMachineView(string serverPath, RegistryView view)
    {
        using RegistryKey root = RegistryKey.OpenBaseKey(RegistryHive.LocalMachine, view);
        using RegistryKey classes = root.CreateSubKey(@"Software\Classes") ?? throw new InvalidOperationException("Cannot open HKLM Software\\Classes.");
        RegisterClasses(classes, serverPath);
    }

    private static void UnregisterInMachineView(RegistryView view)
    {
        using RegistryKey root = RegistryKey.OpenBaseKey(RegistryHive.LocalMachine, view);
        using RegistryKey classes = root.CreateSubKey(@"Software\Classes") ?? throw new InvalidOperationException("Cannot open HKLM Software\\Classes.");
        UnregisterClasses(classes);
    }

    private static void RegisterClasses(RegistryKey classes, string serverPath)
    {
        string fullPath = Path.GetFullPath(serverPath);
        if (!File.Exists(fullPath))
        {
            throw new FileNotFoundException("OLE server executable was not found.", fullPath);
        }

        RegisterProgId(classes, OleFormulaObjectIds.ProgId);
        RegisterProgId(classes, OleFormulaObjectIds.VersionedProgId);
        RegisterClass(classes, fullPath);
    }

    private static void UnregisterClasses(RegistryKey classes)
    {
        DeleteSubKeyTreeIfExists(classes, OleFormulaObjectIds.ProgId);
        DeleteSubKeyTreeIfExists(classes, OleFormulaObjectIds.VersionedProgId);
        DeleteSubKeyTreeIfExists(classes, @"CLSID\" + OleFormulaObjectIds.ClassId.ToString("B").ToUpperInvariant());
    }

    private static void RegisterProgId(RegistryKey classes, string progId)
    {
        using RegistryKey key = classes.CreateSubKey(progId) ?? throw new InvalidOperationException("Cannot create " + progId + ".");
        key.SetValue(null, OleFormulaObjectIds.FriendlyName);
        using RegistryKey clsid = key.CreateSubKey("CLSID") ?? throw new InvalidOperationException("Cannot create " + progId + " CLSID registration.");
        clsid.SetValue(null, OleFormulaObjectIds.ClassId.ToString("B").ToUpperInvariant());
    }

    private static void RegisterClass(RegistryKey classes, string serverPath)
    {
        string clsidPath = @"CLSID\" + OleFormulaObjectIds.ClassId.ToString("B").ToUpperInvariant();
        using RegistryKey clsid = classes.CreateSubKey(clsidPath) ?? throw new InvalidOperationException("Cannot create OLE CLSID registration.");
        clsid.SetValue(null, OleFormulaObjectIds.FriendlyName);
        clsid.SetValue("AppID", OleFormulaObjectIds.ClassId.ToString("B").ToUpperInvariant());

        using RegistryKey progId = clsid.CreateSubKey("ProgID") ?? throw new InvalidOperationException("Cannot create ProgID registration.");
        progId.SetValue(null, OleFormulaObjectIds.VersionedProgId);

        using RegistryKey versionIndependentProgId = clsid.CreateSubKey("VersionIndependentProgID") ?? throw new InvalidOperationException("Cannot create VersionIndependentProgID registration.");
        versionIndependentProgId.SetValue(null, OleFormulaObjectIds.ProgId);

        using RegistryKey localServer = clsid.CreateSubKey("LocalServer32") ?? throw new InvalidOperationException("Cannot create LocalServer32 registration.");
        localServer.SetValue(null, "\"" + serverPath + "\" /Embedding");

        using RegistryKey inprocHandler = clsid.CreateSubKey("InprocHandler32") ?? throw new InvalidOperationException("Cannot create InprocHandler32 registration.");
        inprocHandler.SetValue(null, "ole32.dll");

        using RegistryKey defaultIcon = clsid.CreateSubKey("DefaultIcon") ?? throw new InvalidOperationException("Cannot create DefaultIcon registration.");
        defaultIcon.SetValue(null, "\"" + serverPath + "\",0");

        using RegistryKey insertable = clsid.CreateSubKey("Insertable") ?? throw new InvalidOperationException("Cannot create Insertable registration.");
        insertable.SetValue(null, string.Empty);

        using RegistryKey verb = clsid.CreateSubKey(@"Verb\0") ?? throw new InvalidOperationException("Cannot create OLE verb registration.");
        verb.SetValue(null, "&Edit,0,2");
    }

    private static void DeleteSubKeyTreeIfExists(RegistryKey root, string subKey)
    {
        if (root.OpenSubKey(subKey) != null)
        {
            root.DeleteSubKeyTree(subKey);
        }
    }
}
