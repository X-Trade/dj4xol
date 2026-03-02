import re

from django import template
from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe

register = template.Library()

_LINK_PATTERN = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_ALLOWED_LINK_PREFIXES = ("http://", "https://", "mailto:", "/")


def _replace_markdown_link(match):
    label = escape(match.group(1).strip())
    href = match.group(2).strip()
    if not href.startswith(_ALLOWED_LINK_PREFIXES):
        return label
    return format_html('<a href="{}">{}</a>', href, label)


@register.filter
def render_fixture_text(value):
    """Render safe server/admin fixture text with basic markdown links.

    Supported syntax:
    - [Label](https://example.com)
    - [Label](/relative/path/)
    """
    if value is None:
        return ""

    text = str(value)
    result = []
    last = 0
    for match in _LINK_PATTERN.finditer(text):
        result.append(escape(text[last:match.start()]))
        result.append(_replace_markdown_link(match))
        last = match.end()
    result.append(escape(text[last:]))
    return mark_safe("".join(str(part) for part in result))
