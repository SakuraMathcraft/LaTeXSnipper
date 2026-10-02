using System;
using System.Reflection;
using System.Runtime.Remoting.Messaging;
using System.Runtime.Remoting.Proxies;
using LaTeXSnipper.OfficePlugin.WordAddIn;

namespace LaTeXSnipper.OfficePlugin.WordParsingE2E;

internal sealed class FailingWordAdapter : RealProxy
{
    private readonly IWordApplicationAdapter _inner;
    private readonly string _equationId;

    private FailingWordAdapter(IWordApplicationAdapter inner, string equationId)
        : base(typeof(IWordApplicationAdapter))
    {
        _inner = inner;
        _equationId = equationId;
    }

    public static IWordApplicationAdapter Wrap(IWordApplicationAdapter inner, string equationId)
    {
        return (IWordApplicationAdapter)new FailingWordAdapter(inner, equationId).GetTransparentProxy();
    }

    public override IMessage Invoke(IMessage message)
    {
        var call = (IMethodCallMessage)message;
        var method = (MethodInfo)call.MethodBase;
        try
        {
            if ((method.Name == nameof(IWordApplicationAdapter.UpdateFormulaAsync)
                || method.Name == nameof(IWordApplicationAdapter.ResetOleFormulaObjectAsync))
                && call.Args.Length > 0
                && string.Equals(call.Args[0] as string, _equationId, StringComparison.Ordinal))
            {
                throw new InvalidOperationException("Injected formula update failure");
            }

            if (method.Name == nameof(IWordApplicationAdapter.ReplaceWithMathTypeAsync)
                && call.Args[0] is WordFormulaEditTarget target && target.Metadata.Identity.EquationId == _equationId)
                throw new InvalidOperationException("Injected MathType conversion failure");

            if (method.Name == nameof(IWordApplicationAdapter.ReadMathTypeMathMlAsync)
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
