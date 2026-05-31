using System.Threading;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.PowerPointAddIn;

public interface IPowerPointApplicationAdapter
{
    Task InsertFormulaImageAsync(PowerPointRenderedImage image, FormulaMetadata metadata, CancellationToken cancellationToken);

    Task InsertFormulaImageAtPositionAsync(PowerPointRenderedImage image, FormulaMetadata metadata, float left, float top, CancellationToken cancellationToken);

    Task<FormulaMetadata> LoadSelectedFormulaAsync(CancellationToken cancellationToken);

    Task DeleteSelectedFormulaAsync(CancellationToken cancellationToken);

    Task<int> DeleteSelectedFormulasAsync(CancellationToken cancellationToken);

    (float Left, float Top) GetSelectedShapePosition();
}
