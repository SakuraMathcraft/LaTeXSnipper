using System;
using System.Collections.Concurrent;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using LaTeXSnipper.OfficePlugin.Abstractions;

namespace LaTeXSnipper.OfficePlugin.Rendering;

public sealed class MathJaxSvgRenderer : IFormulaRenderer, IDisposable
{
    public const string SvgMimeType = "image/svg+xml";

    private readonly IMathJaxJavaScriptRuntime _runtime;
    private readonly MathJaxAssetResolver _assetResolver;
    private readonly ConcurrentDictionary<MathJaxRenderCacheKey, RenderResult> _cache = new ConcurrentDictionary<MathJaxRenderCacheKey, RenderResult>();
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
            throw new ArgumentException("MathJaxSvgRenderer can only render MathJaxSvg requests.", nameof(request));
        }

        using CancellationTokenSource timeout = CreateTimeoutTokenSource(request);
        using CancellationTokenSource linked = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken, timeout.Token);
        CancellationToken token = linked.Token;

        await EnsureInitializedAsync(token).ConfigureAwait(false);

        var key = new MathJaxRenderCacheKey(request, "3.2.2");
        if (_cache.TryGetValue(key, out RenderResult? cached))
        {
            return cached;
        }

        string script = MathJaxRenderScriptBuilder.BuildRenderScript(request);
        string responseJson = await _runtime.EvaluateAsync(script, token).ConfigureAwait(false);
        MathJaxSvgRenderResponse response = MathJaxSvgRenderResponse.Parse(responseJson);
        var result = new RenderResult(
            RenderEngineKind.MathJaxSvg,
            SvgMimeType,
            Encoding.UTF8.GetBytes(response.Svg),
            response.WidthPoints,
            response.HeightPoints,
            response.BaselinePoints,
            response.RendererVersion,
            response.Warnings);

        return _cache.GetOrAdd(new MathJaxRenderCacheKey(request, result.RendererVersion), result);
    }

    public async Task<string> ConvertToMathMlAsync(
        string latex,
        FormulaDisplayMode displayMode,
        CancellationToken cancellationToken)
    {
        ThrowIfDisposed();
        if (string.IsNullOrWhiteSpace(latex))
        {
            throw new ArgumentException("LaTeX is required.", nameof(latex));
        }

        using var timeout = new CancellationTokenSource(OfficeCommandTimeouts.Render);
        using var linked = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken, timeout.Token);
        await EnsureInitializedAsync(linked.Token).ConfigureAwait(false);
        string script = MathJaxRenderScriptBuilder.BuildMathMlScript(latex, displayMode);
        string responseJson = await _runtime.EvaluateAsync(script, linked.Token).ConfigureAwait(false);
        return MathJaxMathMlResponse.Parse(responseJson).MathMl;
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

            string bundle = _assetResolver.ResolveTexSvgBundle();
            await _runtime.InitializeAsync(
                bundle,
                MathJaxRenderScriptBuilder.BuildConfigurationScript(),
                MathJaxRenderScriptBuilder.BuildBootstrapScript(),
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
