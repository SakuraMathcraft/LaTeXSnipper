#if NETFRAMEWORK
using System;
using System.Runtime.InteropServices;

namespace LaTeXSnipper.OfficePlugin.Rendering;

public static class MathTypeOleBridge
{
    public const string ProgId = "Equation.DSMT4";

    public static bool IsEquation(object shape)
    {
        try { return string.Equals(Convert.ToString(((dynamic)shape).OLEFormat.ProgID), ProgId, StringComparison.OrdinalIgnoreCase); }
        catch (COMException) { return false; }
        catch (Microsoft.CSharp.RuntimeBinder.RuntimeBinderException) { return false; }
    }
}
#endif
