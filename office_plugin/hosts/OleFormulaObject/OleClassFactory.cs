using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;

namespace LaTeXSnipper.OfficePlugin.OleFormulaObject;

internal sealed class OleClassFactory : IClassFactory
{
    private readonly List<FormulaOleObject> _objects = new List<FormulaOleObject>();
    private int _serverLocks;

    public int CreateInstance(IntPtr pUnkOuter, ref Guid riid, out IntPtr ppvObject)
    {
        OleServerLog.Write("CreateInstance riid=" + riid.ToString("D"));
        ppvObject = IntPtr.Zero;
        if (pUnkOuter != IntPtr.Zero)
        {
            OleServerLog.Write("CreateInstance rejected aggregation.");
            return ComConstants.ClassENoAggregation;
        }

        try
        {
            var formulaObject = new FormulaOleObject();
            IntPtr pointer = formulaObject.QueryInterface(riid);
            if (pointer == IntPtr.Zero)
            {
                OleServerLog.Write("CreateInstance no interface.");
                return ComConstants.ENoInterface;
            }

            _objects.Add(formulaObject);
            ppvObject = pointer;
            OleServerLog.Write("CreateInstance ok.");
            return ComConstants.SOk;
        }
        catch
        {
            OleServerLog.Write("CreateInstance failed.");
            return ComConstants.EFail;
        }
    }

    public int LockServer(bool fLock)
    {
        _serverLocks += fLock ? 1 : -1;
        if (_serverLocks < 0)
        {
            _serverLocks = 0;
        }

        return ComConstants.SOk;
    }
}
