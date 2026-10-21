"""Normalize language without corrupting existing query strings or fragments."""
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def english_maps_url(url):
    if not isinstance(url, str) or not url.strip():
        raise ValueError('Google Maps URL 必须是非空字符串')
    parts = urlsplit(url.strip())
    if parts.scheme not in ('http', 'https') or not parts.netloc:
        raise ValueError('Google Maps URL 必须使用 http 或 https')
    query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
             if key.lower() != 'hl']
    query.append(('hl', 'en'))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
