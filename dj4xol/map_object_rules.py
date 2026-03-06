"""Pure helpers for map-object labels and locate-link formatting."""

from html import escape
from urllib.parse import urlencode


def format_space_label(x, y):
    return "Empty Space (%s, %s)" % (x, y)


def format_salvage_label(x, y):
    return "Salvage (%s, %s)" % (x, y)


def build_map_href(base_url, x, y, short_id=None, locate=True):
    params = [('x', int(x)), ('y', int(y))]
    if short_id:
        params.append(('sel', short_id))
    if locate:
        params.append(('locate', 1))
    return '%s?%s' % (base_url, urlencode(params))


def format_map_link(base_url, x, y, label, short_id=None, locate=True):
    href = build_map_href(base_url, x, y, short_id=short_id, locate=locate)
    return '<a href="%s">%s</a>' % (href, escape(label))
