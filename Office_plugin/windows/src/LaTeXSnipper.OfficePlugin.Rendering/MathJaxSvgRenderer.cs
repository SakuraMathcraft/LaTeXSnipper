using System;
using System.Threading;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.Rendering;

public sealed partial class MathJaxSvgRenderer : IFormulaRenderer, IDisposable
{
    public const string SvgMimeType = "image/svg+xml";

    private readonly IMathJaxJavaScriptRuntime _runtime;
    private readonly MathJaxAssetResolver _assetResolver;
    private readonly SemaphoreSlim _initializeLock = new SemaphoreSlim(1, 1);
    private bool _initialized;
    private bool _disposed;

    public MathJaxSvgRenderer(IMathJaxJavaScriptRuntime runtime, MathJaxAssetResolver? assetResolver = null)
    {
        _runtime = runtime ?? throw new ArgumentNullException(nameof(runtime));
        _assetResolver = assetResolver ?? new MathJaxAssetResolver();
    }

    public RenderEngineKind Engine => RenderEngineKind.MathJaxSvg;

    public Task WarmUpAsync(CancellationToken cancellationToken)
    {
        return EnsureInitializedAsync(cancellationToken);
    }

    public async Task<RenderResult> RenderAsync(RenderRequest request, CancellationToken cancellationToken)
    {
        ThrowIfDisposed();
        if (request == null)
        {
            throw new ArgumentNullException(nameof(request));
        }

        if (request.Engine != RenderEngineKind.MathJaxSvg)
        {
            throw new ArgumentException("当前渲染器只能处理 MathJax SVG 请求。", nameof(request));
        }

        using CancellationTokenSource timeout = CreateTimeoutTokenSource(request);
        using CancellationTokenSource linked = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken, timeout.Token);
        CancellationToken token = linked.Token;

        return await RenderTypographyAsync(request.Latex, request.DisplayMode, request.Typography, token).ConfigureAwait(false);
    }

    private async Task EnsureInitializedAsync(CancellationToken cancellationToken)
    {
        ThrowIfDisposed();
        if (_initialized)
        {
            return;
        }

        await _initializeLock.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            if (_initialized)
            {
                return;
            }

            string bundle = _assetResolver.ResolveStartupScript();
            await _runtime.InitializeAsync(
                bundle,
                cancellationToken).ConfigureAwait(false);
            _initialized = true;
        }
        finally
        {
            _initializeLock.Release();
        }
    }

    private static CancellationTokenSource CreateTimeoutTokenSource(RenderRequest request)
    {
        TimeSpan timeout = request.Timeout <= TimeSpan.Zero ? OfficeCommandTimeouts.Render : request.Timeout;
        return new CancellationTokenSource(timeout);
    }

    public void Dispose()
    {
        if (_disposed)
        {
            return;
        }

        _disposed = true;
        _initializeLock.Dispose();
        _typographyLock.Dispose();
        if (_runtime is IDisposable disposableRuntime)
        {
            disposableRuntime.Dispose();
        }
    }

    private void ThrowIfDisposed()
    {
        if (_disposed)
        {
            throw new ObjectDisposedException(nameof(MathJaxSvgRenderer));
        }
    }
}
