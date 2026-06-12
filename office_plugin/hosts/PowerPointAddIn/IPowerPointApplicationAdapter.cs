using System.Threading;
using System.Threading.Tasks;
using System.Collections.Generic;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.PowerPointAddIn;

public interface IPowerPointApplicationAdapter
{
    Task ActivateForEditingAsync(CancellationToken cancellationToken);

    Task InsertFormulaImageAsync(PowerPointRenderedImage image, FormulaMetadata metadata, CancellationToken cancellationToken);

    Task InsertFormulaImageAtPositionAsync(PowerPointRenderedImage image, FormulaMetadata metadata, float left, float top, float scale, CancellationToken cancellationToken);

    Task InsertFormulaImageOnSlideAsync(int slideIndex, PowerPointRenderedImage image, FormulaMetadata metadata, float left, float top, float scale, CancellationToken cancellationToken);

    Task InsertOleFormulaObjectAsync(FormulaMetadata metadata, OlePresentationResult presentation, CancellationToken cancellationToken);

    Task InsertOleFormulaObjectAtPositionAsync(FormulaMetadata metadata, OlePresentationResult presentation, float left, float top, float shapeScale, CancellationToken cancellationToken);

    Task InsertOleFormulaObjectOnSlideAsync(int slideIndex, FormulaMetadata metadata, OlePresentationResult presentation, float left, float top, float shapeScale, CancellationToken cancellationToken);

    Task<FormulaMetadata> LoadSelectedFormulaAsync(CancellationToken cancellationToken);

    Task<IReadOnlyList<PowerPointFormulaEntry>> LoadSelectedFormulaEntriesAsync(CancellationToken cancellationToken);

    Task<int> ResetCustomFormulaSizesAsync(CancellationToken cancellationToken);

    Task DeleteSelectedFormulaAsync(CancellationToken cancellationToken);

    Task DeleteFormulaByIdAsync(string equationId, CancellationToken cancellationToken);

    Task<int> DeleteSelectedFormulasAsync(CancellationToken cancellationToken);

    (float Left, float Top, float ShapeScale) GetSelectedShapeFrame();
}
