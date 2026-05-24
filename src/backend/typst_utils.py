# -*- coding: utf-8 -*-
"""Shared Typst utility functions for pandoc conversion cleanup.

These are imported by latex_renderer, mathcraft_document_engine, and
formula_export to avoid duplicated (and diverging) implementations.

The pipeline for LaTeX->Typst conversion is:

    1. preprocess_latex_for_typst()   - fix known-broken LaTeX before pandoc
    2. pypandoc.convert_text()        - actual conversion
    3. clean_pandoc_typst_artifacts() - fix pandoc artifacts in Typst output
    4. ensure_typst_math_grouping()   - add {} around big-operator bodies
"""

import re


# ---------------------------------------------------------------------------
# Pre-processing: fix LaTeX that pandoc can't handle before conversion
# ---------------------------------------------------------------------------

# LaTeX commands that pandoc leaves as raw TeX in Typst output.
# Map: latex_command -> replacement (or None to just strip the command).
_PANDOC_UNSUPPORTED_PATTERNS = [
    # \cfrac{num}{den} -> \frac{num}{den}  (degrade to regular fraction)
    (r'\\cfrac', r'\\frac'),
    # \sideset{pre}{post}\sum -> \sum_{pre}^{post}  (simplify)
    (r'\\sideset\{([^}]*)\}\{([^}]*)\}', r''),
    # \varnothing -> \emptyset  (pandoc knows \emptyset)
    (r'\\varnothing\b', r'\\emptyset'),
]

# Patterns that need content-aware replacement (handled by callback).
# These are more complex than simple regex substitution.


def _is_text_like_content(content: str) -> bool:
    """Return True if *content* looks like prose rather than math notation.

    Used to decide whether \\textcolor-wrapped content should go through
    \\text{} (for text) or be extracted as raw math (for formulas).
    """
    c = content.strip()
    if not c:
        return True
    # If it contains LaTeX commands, subscripts, superscripts, or operators
    # it is math content.
    if re.search(r'\\[a-zA-Z]', c):
        return False
    if re.search(r'[\^_]', c):
        return False
    if re.search(r'[+\-*/=<>]', c):
        return False
    if re.search(r'\d', c):
        return False
    # Single short word like "important" or "def" is text
    return True


def preprocess_latex_for_typst(latex: str) -> str:
    r"""Pre-process LaTeX math to avoid known pandoc conversion losses.

    Fixes applied before pandoc:

    - ``\\textcolor{color}{content}`` -> content extracted (color info lost,
      but math/text preserved instead of raw-TeX passthrough)
    - ``\\color{color}`` -> stripped (stateful color lost)
    - ``\\stackrel{text}{sym}`` -> ``\\stackrel{\\text{text}}{sym}``
    - ``\\cfrac`` -> ``\\frac`` (degraded)
    - ``\\varnothing`` -> ``\\emptyset``
    - ``\\sideset{pre}{post}\\sum`` -> ``\\sum`` (simplified)

    >>> preprocess_latex_for_typst(r'\textcolor{red}{x^2} + \textcolor{blue}{text}')
    '{x^2} + \\text{text}'
    """
    text = str(latex or "")

    # 1. \textcolor{color}{content} - extract content, preserving math/text
    def _fix_textcolor(m: re.Match) -> str:
        content = m.group(2)
        if _is_text_like_content(content):
            return r'\text{' + content + '}'
        return '{' + content + '}'

    text = re.sub(
        r'\\textcolor\s*\{([^}]*)\}\{([^}]*)\}',
        _fix_textcolor,
        text,
    )

    # 2. \color{color} - strip the stateful command (can't preserve color)
    text = re.sub(r'\\color\s*\{[^}]*\}\s*', '', text)

    # 3. \stackrel{text}{sym} - wrap text in \text{} so pandoc handles it
    def _fix_stackrel(m: re.Match) -> str:
        above = m.group(1)
        below = m.group(2)
        if _is_text_like_content(above) and not above.startswith('\\'):
            above = r'\text{' + above + '}'
        return r'\stackrel{' + above + '}{' + below + '}'

    text = re.sub(
        r'\\stackrel\s*\{([^}]*)\}\{([^}]*)\}',
        _fix_stackrel,
        text,
    )

    # Replace \displaylines{...} content with simple \\-separated form
    # so pandoc can convert the individual lines to Typst.
    _RE_DISPLAYLINES = re.compile(r'\\displaylines\s*\{')

    def _fix_displaylines(text: str) -> str:
        result = []
        pos = 0
        while True:
            m = _RE_DISPLAYLINES.search(text, pos)
            if not m:
                result.append(text[pos:])
                break
            result.append(text[pos:m.start()])
            # Brace-count to find the matching closing }
            brace_start = m.end() - 1  # position of the opening {
            depth = 1
            i = m.end()
            while i < len(text) and depth > 0:
                if text[i] == '{':
                    depth += 1
                elif text[i] == '}':
                    depth -= 1
                i += 1
            if depth != 0:
                # Unmatched brace, keep original
                result.append(text[m.start():])
                pos = len(text)
                break
            inner = text[m.end():i - 1]
            lines = [line.strip() for line in inner.split(r'\\') if line.strip()]
            result.append(r' \\ '.join(lines))
            pos = i
        return ''.join(result)

    text = _fix_displaylines(text)

    # 4. Replace snippet placeholders #? with \Box so pandoc can handle them.
    # \Box renders as a visible placeholder (square.stroked in Typst).
    text = text.replace('#?', r'\Box')

    # 5. Simple pattern replacements
    for pattern, replacement in _PANDOC_UNSUPPORTED_PATTERNS:
        text = re.sub(pattern, replacement, text)

    return text


# ---------------------------------------------------------------------------
# Post-processing: fix pandoc artifacts in Typst output
# ---------------------------------------------------------------------------

def clean_pandoc_typst_artifacts(typst: str) -> str:
    r"""Clean up pandoc conversion artifacts in Typst math output.

    Pandoc may produce malformed patterns like ``{= 1)`` when converting
    LaTeX subscripts such as ``_{n=1}``.  These unbalanced braces break
    Typst parsing and must be repaired.

    Also fixes semantic errors in pandoc's Typst output:
    - ``compose`` -> ``circle`` (pandoc maps \\circ incorrectly)
    - ``^compose`` -> ``^degree`` (superscript \\circ means degrees)
    - ``diameter`` -> ``emptyset`` (pandoc maps \\varnothing incorrectly)

    >>> clean_pandoc_typst_artifacts('sum_(n {= 1)^oo 1 / n^2')
    'sum_(n = 1)^infinity 1 / n^2'
    """
    text = str(typst or "")
    # Fix pandoc artifact: {= X)  ->  = X)
    # The closing ) is preserved so it acts as the limit-group close.
    text = re.sub(r'\{=\s*([^}{)]*)\)', r'= \1)', text)
    # Fix pandoc converting \infty to "oo" (should be "infinity" in Typst).
    # Use word-boundary match so we don't touch "oo" inside identifiers.
    text = re.sub(r'\boo\b', 'infinity', text)
    # Fix pandoc escaping \(, \), \/ in Typst output
    text = text.replace(r'\(', '(')
    text = text.replace(r'\)', ')')
    text = text.replace(r'\/', '/')
    # Fix pandoc escaping | to \| in Typst (| is a math fence in Typst,
    # no escaping needed; \| would render as a literal backslash+pipe).
    text = text.replace(r'\|', '|')
    # Fix pandoc mapping: \circ -> compose (should be circle in Typst)
    # But ^compose (degree symbol) should become ^degree
    text = re.sub(r'\^compose\b', '^degree', text)
    text = re.sub(r'\bcompose\b', 'circle', text)
    # Fix pandoc mapping: \varnothing -> diameter (should be emptyset)
    text = re.sub(r'\bdiameter\b', 'emptyset', text)
    # Strip orphaned trailing } left over from pandoc conversion
    # (e.g. pandoc may wrap fraction bodies producing an extra }).
    while text.endswith('}') and text.count('{') < text.count('}'):
        text = text[:-1]
    return text


def has_top_level_binary_op(body: str) -> bool:
    r"""Check whether *body* contains + - * / at the top level.

    Operators nested inside ``()`` or ``{}`` are ignored because the
    surrounding delimiters already provide correct grouping for Typst.

    >>> has_top_level_binary_op('x + y')
    True
    >>> has_top_level_binary_op('(1 / 2)^n')
    False
    >>> has_top_level_binary_op('a / b')
    True
    """
    depth = 0
    for ch in body:
        if ch in '({':
            depth += 1
        elif ch in ')}':
            depth -= 1
        elif depth == 0 and ch in '+-*/':
            return True
    return False


def ensure_typst_math_grouping(typst: str) -> str:
    r"""Wrap compound bodies of Typst big-operators in {} for correct grouping.

    Typst functions like integral, sum, prod, lim need their body
    wrapped in ``{}`` when the body contains binary operators (+, -, *, /).
    Otherwise only the first term is treated as the body.

    >>> ensure_typst_math_grouping('integral_a^b x+2 dif x')
    'integral_a^b {x+2} dif x'
    """
    text = clean_pandoc_typst_artifacts(typst.strip())
    # Match limit attachments that may include parenthesised content
    # like _(n = 1) or ^(k + 1).  Also match plain limits like _n or ^oo.
    _LIMIT_ATOM = r'(?:[^\s{}()]+|\([^)]*\))'
    _LIMITS = rf'(?:_{_LIMIT_ATOM})?(?:\^{_LIMIT_ATOM})?'
    _OP = r'(?:integral|sum|prod|lim)'
    _BODY = r'([^}]+?)'
    _SENTINEL = r'(dif\s+\S+)'

    def _maybe_wrap(m: re.Match) -> str:
        body = (m.group('body') or '').strip()
        if not body or not has_top_level_binary_op(body):
            return m.group(0)
        # Skip wrapping only when the body is already properly wrapped
        # in a balanced {} pair (the closing } is consumed by the lookahead).
        if body.startswith('{'):
            return m.group(0)
        prefix = m.group(0)[:m.start('body') - m.start(0)]
        suffix = m.group(0)[m.end('body') - m.start(0):]
        return f'{prefix}{{{body}}}{suffix}'

    text = re.sub(
        rf'\b({_OP})({_LIMITS})\s+(?P<body>{_BODY})\s+{_SENTINEL}',
        _maybe_wrap,
        text,
    )
    text = re.sub(
        rf'\b({_OP})({_LIMITS})\s+(?P<body>{_BODY})(?=\s*$|\s*\}})',
        _maybe_wrap,
        text,
    )
    return text


def looks_like_latex_math(text: str) -> bool:
    """Return True if *text* contains LaTeX backslash commands."""
    return bool(text and re.search(r'\\[a-zA-Z]', text))


def clean_pandoc_typst_output(typst: str) -> str:
    r"""Clean up pandoc conversion artifacts in Typst math output.

    Variant for formula_export that additionally strips $ math delimiters
    that pandoc may add around the output.

    >>> clean_pandoc_typst_output('$ sum_(n {= 1)^oo 1 / n^2 $')
    'sum_(n = 1)^infinity 1 / n^2'
    """
    text = (typst or "").strip()
    text = text.replace('$', '')
    return clean_pandoc_typst_artifacts(text)


# ---------------------------------------------------------------------------
# Reverse conversion: Typst -> LaTeX cleanup
# ---------------------------------------------------------------------------

def _strip_typst_grouping_for_reverse(typst: str) -> str:
    r"""Remove {} grouping added by ensure_typst_math_grouping before reverse.

    Pandoc's Typst reader cannot parse ``{body}`` groups attached to
    big-operators when they appear inside function arguments like
    ``sqrt(sum_(...)^(...) {body})``.  LaTeX doesn't need the grouping
    (its \sum naturally takes everything), so stripping the braces
    before reverse conversion is safe.

    >>> _strip_typst_grouping_for_reverse('sum_(n=1)^infinity {1 / n^2}')
    'sum_(n=1)^infinity 1 / n^2'
    """
    text = str(typst or "")
    _OP = r'(?:integral|sum|prod|lim)'
    # Limit atom: either (parenthesised) or a simple token (no spaces/braces).
    _ATOM = r'(?:\([^)]*\)|[^\s^{}]+)'
    _LIMITS = rf'(?:_{_ATOM})?(?:\^{_ATOM})?'
    # Match {body} after a big-operator with optional limits.
    # Body may contain nested braces (e.g. \frac-like expressions).
    text = re.sub(
        rf'\b({_OP})({_LIMITS})\s+\{{([^{{}}]*(?:\{{[^{{}}]*\}}[^{{}}]*)*)\}}',
        r'\1\2 \3',
        text,
    )
    return text


def clean_typst_to_latex_output(latex: str) -> str:
    r"""Clean up pandoc artifacts in Typst->LaTeX reverse conversion.

    Pandoc converts Typst row separator ``med`` to ``\:`` (a LaTeX spacing
    command) instead of ``\\`` (a newline).  Inside ``\begin{...}`` /
    ``\end{...}`` environments this must be ``\\`` to separate rows.

    Also strips ``\[...\]`` display-math wrappers and ``\[\]`` artifacts
    left over from ``$$`` delimiters in the Typst input.

    >>> clean_typst_to_latex_output(r'\[\begin{pmatrix} a & b\: c & d \end{pmatrix}\]')
    '\\begin{pmatrix} a & b\\\\ c & d \\end{pmatrix}'
    """
    text = str(latex or "").strip()

    # Strip pandoc's \[...\] display-math wrapping.
    text = re.sub(r'^\\\[\s*', '', text)
    text = re.sub(r'\s*\\\]\s*$', '', text)
    # Strip orphaned \[\] artifacts from $$ in Typst input.
    text = re.sub(r'\\\[\]', '', text)
    text = text.strip()

    # Pandoc converts Typst "med" (row separator) -> "\:" (LaTeX spacing).
    # Inside matrix/array/cases environments this is always a row break.
    # \: is extremely rare in real LaTeX output from Typst conversion,
    # so a targeted fix inside \begin..\end blocks is safe.
    def _fix_row_sep_in_env(m: re.Match) -> str:
        return m.group(0).replace(r'\:', r'\\')

    text = re.sub(
        r'\\begin\{[^}]*\}.*?\\end\{[^}]*\}',
        _fix_row_sep_in_env,
        text,
        flags=re.DOTALL,
    )

    # Remove any $ delimiters pandoc may have added.
    text = text.replace('$', '')

    return text.strip()
