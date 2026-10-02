using System;
using System.Reflection;
using System.Runtime.Remoting.Messaging;
using System.Runtime.Remoting.Proxies;
using LaTeXSnipper.OfficePlugin.PowerPointAddIn;

internal sealed class FailingPowerPointAdapter : RealProxy
{
    private readonly IPowerPointApplicationAdapter _inner;
    private readonly string _equationId;

    private FailingPowerPointAdapter(IPowerPointApplicationAdapter inner, string equationId)
        : base(typeof(IPowerPointApplicationAdapter))
    {
        _inner = inner;
        _equationId = equationId;
    }

    public static IPowerPointApplicationAdapter Wrap(IPowerPointApplicationAdapter inner, string equationId)
    {
        return (IPowerPointApplicationAdapter)new FailingPowerPointAdapter(inner, equationId).GetTransparentProxy();
    }

    public override IMessage Invoke(IMessage message)
    {
        var call = (IMethodCallMessage)message;
        var method = (MethodInfo)call.MethodBase;
        try
        {
            if (method.Name == nameof(IPowerPointApplicationAdapter.ContainsFormula)
                && string.Equals(call.Args[0] as string, _equationId, StringComparison.Ordinal))
            {
                throw new InvalidOperationException("Injected PowerPoint formula failure");
            }

            if (method.Name == nameof(IPowerPointApplicationAdapter.ReplaceWithMathTypeAsync)
                && call.Args[0] is PowerPointFormulaEditTarget target && target.Metadata.Identity.EquationId == _equationId)
                throw new InvalidOperationException("Injected MathType conversion failure");

            if (method.Name == nameof(IPowerPointApplicationAdapter.ReadMathTypeMathMlAsync)
                && call.Args[0] is LaTeXSnipper.OfficePlugin.Abstractions.MathTypeFormulaTarget mathType
                && mathType.Location.ToString() == _equationId)
                throw new InvalidOperationException("Injected MathType import failure");

            return new ReturnMessage(method.Invoke(_inner, call.Args), null, 0, call.LogicalCallContext, call);
        }
        catch (TargetInvocationException exception)
        {
            return new ReturnMessage(exception.InnerException ?? exception, call);
        }
        catch (Exception exception)
        {
            return new ReturnMessage(exception, call);
        }
    }
}

internal sealed class BatchStatusSink : IPowerPointStatusSink
{
    public PowerPointStatusKind Kind { get; private set; }
    public string Message { get; private set; } = string.Empty;

    public void Post(PowerPointStatusKind kind, string message)
    {
        Kind = kind;
        Message = message;
        Console.WriteLine("STATUS|" + kind + "|" + message);
    }

    public void SetBusy(bool busy) { }
    public void SetOcrActive(bool active) { }
    public void SetCurrentFormula(string latex, bool updateMode) { }
}
