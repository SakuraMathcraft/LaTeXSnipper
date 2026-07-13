using System.Threading;
using System.Threading.Tasks;

namespace LaTeXSnipper.OfficePlugin.Abstractions;

public interface IFormulaEditor : System.IDisposable
{
    Task WarmUpAsync(CancellationToken cancellationToken);

    Task OpenAsync(FormulaMetadata? initialFormula, bool updateMode, CancellationToken cancellationToken);

}
