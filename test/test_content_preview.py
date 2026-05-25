from preview.content_preview import build_mixed_content_html
from preview.math_preview import MATHJAX_CDN_URL, MATHJAX_CDN_URL_BACKUP
from preview.smart_preview import build_smart_preview_html


def test_mixed_content_escapes_text_and_preserves_formulas():
    html = build_mixed_content_html("<b>x</b>\n$y=1$\n$$z=2$$")

    assert "&lt;b&gt;x&lt;/b&gt;<br>" in html
    assert "$y=1$" in html
    assert "$$z=2$$" in html


def test_mixed_content_mathjax_loader_falls_back_to_backup_cdn():
    html = build_mixed_content_html("$x$")

    assert "var localScript = 'tex-mml-chtml.js';" in html
    assert "script.src = localScript;" in html
    assert MATHJAX_CDN_URL in html
    assert MATHJAX_CDN_URL_BACKUP in html
    assert "cdnScript.onerror" in html
    assert "backupScript.src = cdnUrls[1];" in html
    assert "document.body || document.head || document.documentElement" in html


def test_smart_preview_uses_shared_mathjax_fallback_loader():
    html = build_smart_preview_html(
        [("$x$", "Formula", "mathcraft")],
        lambda content: f'<div class="formula-content">$${content}$$</div>',
    )

    assert MATHJAX_CDN_URL in html
    assert MATHJAX_CDN_URL_BACKUP in html
    assert "backupScript.src = cdnUrls[1];" in html
    assert "appendScript(script);" in html
