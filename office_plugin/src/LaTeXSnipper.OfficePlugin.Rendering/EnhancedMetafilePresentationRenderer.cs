using System;
using System.Threading;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.Rendering;

public sealed class EnhancedMetafilePresentationRenderer : IOlePresentationRenderer
{
    public const string EmfMimeType = "application/x-emf";
    private const double HorizontalPaddingPoints = 1.5;
    private const double VerticalPaddingPoints = 0.5;

    public OlePresentationKind PresentationKind => OlePresentationKind.EnhancedMetafile;

    public Task<OlePresentationResult> RenderPresentationAsync(OlePresentationRequest request, CancellationToken cancellationToken)
    {
        if (request == null)
        {
            throw new ArgumentNullException(nameof(request));
        }

        cancellationToken.ThrowIfCancellationRequested();
#if NET48
        byte[] payload = SvgEnhancedMetafileWriter.Write(request.IntermediateRender, cancellationToken);
        var result = new OlePresentationResult(
            OlePresentationKind.EnhancedMetafile,
            EmfMimeType,
            payload,
            request.IntermediateRender.WidthPoints + HorizontalPaddingPoints * 2,
            request.IntermediateRender.HeightPoints + VerticalPaddingPoints * 2,
            request.IntermediateRender.BaselinePoints + VerticalPaddingPoints);
        return Task.FromResult(result);
#else
        throw new PlatformNotSupportedException("Enhanced Metafile rendering is only available in the Windows .NET Framework Office host.");
#endif
    }
}
