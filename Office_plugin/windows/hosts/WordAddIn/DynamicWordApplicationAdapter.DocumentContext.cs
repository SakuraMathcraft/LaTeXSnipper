using System;
using System.Threading;

namespace LaTeXSnipper.OfficePlugin.WordAddIn;

public sealed partial class DynamicWordApplicationAdapter
{
    private readonly AsyncLocal<object?> _documentContext = new();

    private dynamic CurrentDocument => _documentContext.Value ?? _wordApplication.ActiveDocument;

    private IDisposable UseDocument(object document)
    {
        if (document == null)
        {
            throw new ArgumentNullException(nameof(document));
        }

        return new DocumentContextScope(this, document);
    }

    private sealed class DocumentContextScope : IDisposable
    {
        private readonly DynamicWordApplicationAdapter _owner;
        private readonly object? _previousDocument;
        private bool _disposed;

        public DocumentContextScope(DynamicWordApplicationAdapter owner, object document)
        {
            _owner = owner;
            _previousDocument = owner._documentContext.Value;
            owner._documentContext.Value = document;
        }

        public void Dispose()
        {
            if (_disposed)
            {
                return;
            }

            _disposed = true;
            _owner._documentContext.Value = _previousDocument;
        }
    }
}
