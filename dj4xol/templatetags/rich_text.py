from django import template
from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe

register = template.Library()

_ALLOWED_LINK_PREFIXES = ("http://", "https://", "mailto:", "/")
_ALLOWED_IMAGE_PREFIXES = ("http://", "https://", "/")


def _extract_markdown_token(text, start, image=False):
    prefix = '![' if image else '['
    if not text.startswith(prefix, start):
        return None

    label_start = start + len(prefix)
    label_end = text.find(']', label_start)
    if label_end == -1 or label_end + 1 >= len(text) or text[label_end + 1] != '(':
        return None

    href_start = label_end + 2
    href_end = text.find(')', href_start)
    if href_end == -1:
        return None

    label = text[label_start:label_end].strip()
    href = text[href_start:href_end].strip()
    return {
        'label': label,
        'href': href,
        'end': href_end + 1,
    }


def _render_markdown_image(label, href):
    if not href.startswith(_ALLOWED_IMAGE_PREFIXES):
        return escape(label)
    return format_html(
        '<img class="rich-text-image" src="{}" alt="{}">',
        href,
        label,
    )


def _render_markdown_link(label, href):
    if not href.startswith(_ALLOWED_LINK_PREFIXES):
        return escape(label)
    return format_html('<a href="{}">{}</a>', href, label)


def _render_inline_markup(text):
    if text is None:
        return ''

    result = []
    cursor = 0
    next_token_chars = ('[', '!')

    while cursor < len(text):
        next_positions = [
            text.find(char, cursor)
            for char in next_token_chars
            if text.find(char, cursor) != -1
        ]
        next_pos = min(next_positions) if next_positions else -1
        if next_pos == -1:
            result.append(escape(text[cursor:]))
            break
        if next_pos > cursor:
            result.append(escape(text[cursor:next_pos]))
            cursor = next_pos

        token = _extract_markdown_token(text, cursor, image=True)
        if token:
            result.append(_render_markdown_image(token['label'], token['href']))
            cursor = token['end']
            continue

        token = _extract_markdown_token(text, cursor, image=False)
        if token:
            result.append(_render_markdown_link(token['label'], token['href']))
            cursor = token['end']
            continue

        result.append(escape(text[cursor]))
        cursor += 1

    return mark_safe(''.join(str(part) for part in result))


def _render_standalone_image(text):
    token = _extract_markdown_token(text, 0, image=True)
    if not token or token['end'] != len(text):
        return None
    if not token['href'].startswith(_ALLOWED_IMAGE_PREFIXES):
        return None
    return format_html(
        '<figure class="rich-text-figure">{}</figure>',
        _render_markdown_image(token['label'], token['href']),
    )


def _flush_paragraph(lines, rendered):
    if not lines:
        return
    rendered.append(format_html(
        '<p>{}</p>',
        mark_safe('<br>'.join(
            str(_render_inline_markup(line)) for line in lines
        )),
    ))
    del lines[:]


def _flush_list(items, rendered):
    if not items:
        return
    rendered.append(format_html(
        '<ul class="rich-text-list">{}</ul>',
        mark_safe(''.join(
            '<li>{}</li>'.format(_render_inline_markup(item))
            for item in items
        )),
    ))
    del items[:]


@register.filter
def render_rich_text(value):
    """Render safe server/admin text with simple markdown-style helpers.

    Supported syntax:
    - [Label](https://example.com)
    - [Label](/relative/path/)
    - ![Alt Text](https://example.com/image.png)
    - bullet lines beginning with "- "
    """
    if value is None:
        return ''

    rendered = []
    paragraph_lines = []
    list_items = []
    for raw_line in str(value).splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()

        if not stripped:
            _flush_paragraph(paragraph_lines, rendered)
            _flush_list(list_items, rendered)
            continue

        image_html = _render_standalone_image(stripped)
        if image_html is not None:
            _flush_paragraph(paragraph_lines, rendered)
            _flush_list(list_items, rendered)
            rendered.append(image_html)
            continue

        if stripped.startswith('- '):
            _flush_paragraph(paragraph_lines, rendered)
            list_items.append(stripped[2:].strip())
            continue

        _flush_list(list_items, rendered)
        paragraph_lines.append(line)

    _flush_paragraph(paragraph_lines, rendered)
    _flush_list(list_items, rendered)
    return mark_safe(''.join(str(part) for part in rendered))


@register.filter
def render_fixture_text(value):
    return render_rich_text(value)
