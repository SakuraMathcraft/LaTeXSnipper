using System;
using System.Runtime.InteropServices;
using System.Windows.Forms;

namespace LaTeXSnipper.OfficePlugin.OleFormulaObject;

internal sealed class OleEmbeddingServer : IDisposable
{
    private int _registrationCookie;

    public int Run()
    {
        OleServerLog.Write("Embedding server starting.");
        ApplicationBootstrap.Initialize();
        int oleInitializeResult = NativeMethods.OleInitialize(IntPtr.Zero);
        OleServerLog.Write("OleInitialize result=" + oleInitializeResult.ToString(System.Globalization.CultureInfo.InvariantCulture));
        var registrationServices = new RegistrationServices();
        _registrationCookie = registrationServices.RegisterTypeForComClients(
            typeof(FormulaOleObject),
            RegistrationClassContext.LocalServer,
            RegistrationConnectionType.MultipleUse);
        OleServerLog.Write("RegisterTypeForComClients cookie=" + _registrationCookie.ToString(System.Globalization.CultureInfo.InvariantCulture));

        OleServerLog.Write("Entering message loop.");
        Application.Run(new ApplicationContext());
        OleServerLog.Write("Message loop exited.");
        return ComConstants.SOk;
    }

    public void Dispose()
    {
        if (_registrationCookie != 0)
        {
            NativeMethods.CoRevokeClassObject((uint)_registrationCookie);
            _registrationCookie = 0;
        }

        NativeMethods.OleUninitialize();
    }
}
