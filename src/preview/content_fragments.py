"""Shared HTML fragments for raw formulas and documents containing delimited math."""

from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET


_MATH = r'(?<!\\)(?:\$\$(?:\\.|(?!\$\$)[\s\S])*?\$\$|\$(?:\\.|[^\\$\n])*?\$|\\\[[\s\S]*?\\\]|\\\([\s\S]*?\\\))'
_SVG = r'<svg\b[^>]*>[\s\S]*?</svg\s*>'
_FRAGMENTS = re.compile(f'(?P<math>{_MATH})|(?P<svg>{_SVG})', re.IGNORECASE)
_FENCE = re.compile(r'```(?:latex|tex|math)?\s*(.*?)\s*```', re.IGNORECASE | re.DOTALL)
_SVG_ELEMENTS = set('svg g path rect line circle ellipse polygon polyline text tspan textpath defs use '
                    'clippath mask lineargradient radialgradient stop pattern marker title desc image symbol view style'.split())


def unwrap_math_delimiters(text: str) -> str:
    value = text.strip()
    fence = _FENCE.fullmatch(value)
    if fence:
        value = fence.group(1).strip()
    if re.fullmatch(_MATH, value):
        width = 2 if value.startswith(('$$', r'\[', r'\(')) else 1
        return value[width:-width].strip()
    return value


def _local_svg(source: str) -> str:
    """Preserve static diagrams without executing embedded document content."""
    try:
        root = ET.fromstring(source)
    except ET.ParseError:
        return html.escape(source)
    for element in root.iter():
        element.tag = element.tag.rsplit('}', 1)[-1]
        for child in list(element):
            if child.tag.rsplit('}', 1)[-1].lower() not in _SVG_ELEMENTS:
                element.remove(child)
        for name, value in list(element.attrib.items()):
            attribute = name.rsplit('}', 1)[-1].lower()
            urls = re.findall(r'url\(\s*[\'"]?([^\)\'\"]+)', value, re.IGNORECASE)
            if (attribute.startswith('on') or (attribute in {'href', 'src'} and not value.startswith('#'))
                    or any(not url.startswith('#') for url in urls)
                    or re.search(r'javascript:|@import|expression\s*\(', value, re.IGNORECASE)):
                del element.attrib[name]
        if element.tag.lower() == 'style' and re.search(r'@import|url\s*\(', element.text or '', re.IGNORECASE):
            element.text = ''
    root.set('class', (root.get('class', '') + ' tex2jax_ignore').strip())
    root.set('xmlns', 'http://www.w3.org/2000/svg')
    return ET.tostring(root, encoding='unicode')


def render_mixed_content(content: str) -> str:
    parts = []
    offset = 0
    for match in _FRAGMENTS.finditer(content):
        parts.append(html.escape(content[offset:match.start()]).replace('\n', '<br>'))
        if match.lastgroup == 'svg':
            parts.append(_local_svg(match.group()))
        else:
            parts.append(html.escape(match.group()))
        offset = match.end()
    parts.append(html.escape(content[offset:]).replace('\n', '<br>'))
    return ''.join(parts)


def render_formula_content(content: str) -> str:
    value = content.strip()
    fence = _FENCE.fullmatch(value)
    if fence:
        value = fence.group(1).strip()
    if _FRAGMENTS.search(value) or re.search(r'(?m)^\s{0,3}#{1,6}\s+', value):
        return f'<div class="document-content">{render_mixed_content(value)}</div>'
    return f'<div class="formula-content">$${html.escape(value)}$$</div>'
