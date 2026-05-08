import re


def normalize_http_url(url):
    if not isinstance(url, str):
        return None
    u = url.strip()
    if u.startswith("//"):
        return "https:" + u
    return u


def extract_direct_url(manga_obj):
    if manga_obj is None:
        return None
    if isinstance(manga_obj, dict):
        for k in ("url", "uri", "link", "page", "source_url", "identifier"):
            v = manga_obj.get(k)
            if isinstance(v, str):
                u = normalize_http_url(v)
                if isinstance(u, str) and u.startswith("http"):
                    return u
    for attr in ("url", "uri", "link", "page", "source_url", "identifier"):
        if hasattr(manga_obj, attr):
            try:
                v = getattr(manga_obj, attr)
                u = normalize_http_url(v)
                if isinstance(u, str) and u.startswith("http"):
                    return u
            except Exception:
                pass
    return None


def extract_identifier(manga_obj):
    if manga_obj is None:
        return None
    if isinstance(manga_obj, dict):
        for k in ("identifier", "id", "uuid", "manga_id", "code", "slug"):
            if k in manga_obj:
                v = manga_obj.get(k)
                if isinstance(v, (str, int)):
                    s = str(v).strip()
                    if s:
                        return s
        for k in ("url", "uri", "link", "page", "source_url"):
            v = manga_obj.get(k)
            if isinstance(v, str):
                s = v.strip()
                if s:
                    return s
    for attr in ("identifier", "id", "uuid", "manga_id", "code", "slug"):
        if hasattr(manga_obj, attr):
            try:
                v = getattr(manga_obj, attr)
                if isinstance(v, (str, int)):
                    s = str(v).strip()
                    if s:
                        return s
            except Exception:
                pass
    for attr in ("url", "uri", "link", "page", "source_url"):
        if hasattr(manga_obj, attr):
            try:
                v = getattr(manga_obj, attr)
                if isinstance(v, str):
                    s = v.strip()
                    if s:
                        return s
            except Exception:
                pass
    return None


def resolve_manga_url(manga_obj, *, src=None, source_meta=None):
    direct = extract_direct_url(manga_obj)
    if direct:
        return direct

    identifier = extract_identifier(manga_obj)
    if not identifier:
        return None

    candidate = normalize_http_url(identifier)
    if isinstance(candidate, str) and candidate.startswith("http"):
        return candidate

    name = ""
    if isinstance(source_meta, dict):
        try:
            name = str(source_meta.get("name") or "").lower()
        except Exception:
            name = ""
    if not name and src is not None:
        try:
            name = str(getattr(src, "name", str(src))).lower()
        except Exception:
            name = ""

    base = None
    if isinstance(source_meta, dict):
        for k in ("base_url", "home_url", "site_url", "website", "url"):
            v = source_meta.get(k)
            if isinstance(v, str):
                vv = normalize_http_url(v)
                if isinstance(vv, str) and vv.startswith("http"):
                    base = vv
                    break

    s = str(identifier).strip()
    if s.startswith("//"):
        return "https:" + s
    if s.startswith("/") and base:
        return base.rstrip("/") + s

    if "mangadex" in name:
        match = re.search(r"([0-9a-fA-F-]{36})", s)
        if match:
            return f"https://mangadex.org/title/{match.group(1)}"

    if "nhentai" in name:
        match = re.search(r"(\d{1,10})", s)
        if match:
            return f"https://nhentai.net/g/{match.group(1)}/"

    if base:
        return base.rstrip("/") + "/" + s.lstrip("/")

    return None

