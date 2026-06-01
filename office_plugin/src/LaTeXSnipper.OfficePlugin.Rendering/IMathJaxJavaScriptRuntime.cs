using System.Threading;
using System.Threading.Tasks;

namespace LaTeXSnipper.OfficePlugin.Rendering;

public interface IMathJaxJavaScriptRuntime
{
    Task InitializeAsync(string mathJaxBundlePath, string bootstrapScript, CancellationToken cancellationToken);

    Task<string> EvaluateAsync(string script, CancellationToken cancellationToken);
}
