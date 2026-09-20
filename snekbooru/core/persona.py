import time
from urllib.parse import urlparse

from snekbooru.core.config import load_browsing_profile, save_browsing_profile

PROFILE_VERSION = 1
MAX_RECENT_OPENS = 300
HENTAI_META = {"rating:"}
META_PREFIXES = ("rating:", "score:", "width:", "height:", "filetype:")


def empty_profile():
    return {
        "version": PROFILE_VERSION,
        "created": time.time(),
        "last_active": time.time(),
        "total_opens": 0,
        "total_dwell_seconds": 0.0,
        "context_opens": {},
        "category_stats": {},
        "tag_affinity": {},
        "rating_affinity": {},
        "source_affinity": {},
        "hentai": {
            "opens": 0,
            "dwell_seconds": 0.0,
            "series": {},
            "genres": {},
            "sources": {},
        },
        "manga": {
            "opens": 0,
            "dwell_seconds": 0.0,
            "series": {},
            "sources": {},
        },
        "searches": {},
        "downloads": {},
        "active_hours": {},
        "recent_opens": [],
    }


def load_profile():
    profile = load_browsing_profile()
    base = empty_profile()
    if not isinstance(profile, dict):
        return base
    base.update(profile)
    base.setdefault("version", PROFILE_VERSION)
    base.setdefault("hentai", {})
    base.setdefault("manga", {})
    return base


def save_profile(profile):
    profile["last_active"] = time.time()
    save_browsing_profile(profile)


def _bump(counter, key, amount=1):
    if not key:
        return
    counter[key] = counter.get(key, 0) + amount


def _clean_tags(tags_str):
    if tags_str is None:
        return []
    tokens = tags_str.replace(",", " ").split()
    cleaned = []
    for tok in tokens:
        t = str(tok).strip().lower()
        if not t or t == "none" or t == "unknown":
            continue
        if t.startswith(META_PREFIXES):
            continue
        cleaned.append(t)
    return cleaned


def _derive_source(post):
    post_src = post.get("source_post_url") or post.get("file_url") or post.get("preview_url") or ""
    try:
        host = urlparse(post_src).netloc.lower()
    except Exception:
        host = ""
    if not host:
        return "Unknown"
    return host.replace("www.", "")


def record_post_open(profile, post, context="browser", category=None, dwell=0.0):
    now = time.time()
    profile["total_opens"] = profile.get("total_opens", 0) + 1
    dwell = max(0.0, float(dwell))
    profile["total_dwell_seconds"] = profile.get("total_dwell_seconds", 0.0) + dwell

    ctx = context or "browser"
    _bump(profile["context_opens"], ctx)

    if category:
        cat = profile["category_stats"].setdefault(str(category), {"opens": 0, "dwell_seconds": 0.0})
        cat["opens"] += 1
        cat["dwell_seconds"] += dwell

    weight = 1.0 + min(dwell, 300.0) / 60.0
    tags = _clean_tags(post.get("tags") or "")
    for tag in tags[:60]:
        profile["tag_affinity"][tag] = profile["tag_affinity"].get(tag, 0) + weight

    rating = str(post.get("rating", "unknown")).lower()
    _bump(profile["rating_affinity"], rating)

    source = _derive_source(post)
    _bump(profile["source_affinity"], source)

    hour = time.localtime(now).tm_hour
    _bump(profile["active_hours"], str(hour))

    recent = profile["recent_opens"]
    recent.append({
        "ts": now,
        "id": post.get("id"),
        "rating": rating,
        "category": category,
        "context": ctx,
        "dwell": round(dwell, 1),
    })
    if len(recent) > MAX_RECENT_OPENS:
        profile["recent_opens"] = recent[-MAX_RECENT_OPENS:]

    profile["last_active"] = now


def record_hentai_open(profile, post, dwell=0.0):
    now = time.time()
    dwell = max(0.0, float(dwell))
    hentai = profile["hentai"]
    hentai["opens"] = hentai.get("opens", 0) + 1
    hentai["dwell_seconds"] = hentai.get("dwell_seconds", 0.0) + dwell

    slug = post.get("hentai_slug") or post.get("id") or ""
    title = post.get("hentai_title") or post.get("title") or ""
    if slug:
        series = hentai["series"].setdefault(str(slug), {"title": title or str(slug), "opens": 0, "dwell_seconds": 0.0})
        series["title"] = title or series.get("title") or str(slug)
        series["opens"] += 1
        series["dwell_seconds"] += dwell

    for genre in post.get("hentai_genres") or []:
        _bump(hentai["genres"], str(genre).strip())

    for tag in _clean_tags(post.get("tags") or ""):
        _bump(hentai["genres"], tag)

    _bump(hentai["sources"], _derive_source(post))
    profile["last_active"] = now


def record_manga_open(profile, entry, source="Unknown", dwell=0.0):
    now = time.time()
    dwell = max(0.0, float(dwell))
    manga = profile["manga"]
    manga["opens"] = manga.get("opens", 0) + 1
    manga["dwell_seconds"] = manga.get("dwell_seconds", 0.0) + dwell

    title = entry.get("title") or entry.get("name") or str(entry.get("url") or "Unknown")
    series = manga["series"].setdefault(str(title), {"opens": 0, "dwell_seconds": 0.0})
    series["opens"] += 1
    series["dwell_seconds"] += dwell

    _bump(manga["sources"], source)
    profile["last_active"] = now


def record_search(profile, text):
    if not text:
        return
    terms = _clean_tags(text)
    for term in terms:
        _bump(profile["searches"], term, 1)


def record_download(profile, post, source="Unknown"):
    _bump(profile["downloads"], source)


def _weighted_top(counter, limit, exclude=()):
    exclude = set(exclude or ())
    scored = [(tag, weight) for tag, weight in counter.items() if tag not in exclude]
    scored.sort(key=lambda item: item[1], reverse=True)
    return scored[:limit]


def top_affinity_tags(profile, limit=25, exclude=()):
    return [tag for tag, _weight in _weighted_top(profile.get("tag_affinity", {}), limit, exclude)]


def compute_personality(profile):
    boring = [
        "rating", "safe", "questionable", "explicit", "general", "sensitive",
        "1girl", "single", "solo", "long hair",
    ]
    overview = {
        "total_opens": profile.get("total_opens", 0),
        "total_dwell_seconds": round(profile.get("total_dwell_seconds", 0.0), 1),
        "context_opens": dict(profile.get("context_opens", {})),
        "top_tags": _weighted_top(profile.get("tag_affinity", {}), 25, boring),
        "top_ratings": _weighted_top(profile.get("rating_affinity", {}), 5),
        "top_sources": _weighted_top(profile.get("source_affinity", {}), 5),
        "category_stats": dict(profile.get("category_stats", {})),
        "active_hours": _weighted_top(profile.get("active_hours", {}), 3),
        "hentai": {
            "opens": profile.get("hentai", {}).get("opens", 0),
            "dwell_seconds": round(profile.get("hentai", {}).get("dwell_seconds", 0.0), 1),
            "top_series": _weighted_top(profile.get("hentai", {}).get("series", {}), 10),
            "top_genres": _weighted_top(profile.get("hentai", {}).get("genres", {}), 15),
            "top_sources": _weighted_top(profile.get("hentai", {}).get("sources", {}), 5),
        },
        "manga": {
            "opens": profile.get("manga", {}).get("opens", 0),
            "dwell_seconds": round(profile.get("manga", {}).get("dwell_seconds", 0.0), 1),
            "top_series": _weighted_top(profile.get("manga", {}).get("series", {}), 10),
            "top_sources": _weighted_top(profile.get("manga", {}).get("sources", {}), 5),
        },
        "top_searches": _weighted_top(profile.get("searches", {}), 10),
        "top_download_sources": _weighted_top(profile.get("downloads", {}), 5),
    }
    return overview


def personality_summary_text(overview):
    lines = []
    if overview["total_opens"]:
        avg = overview["total_dwell_seconds"] / overview["total_opens"]
        lines.append(f"Viewed {overview['total_opens']} posts, ~{avg:.0f}s avg per post.")
    if overview["top_tags"]:
        lines.append("Top affinity tags: " + ", ".join(t.capitalize() for t, w in overview["top_tags"][:15]))
    if overview["top_ratings"]:
        lines.append("Rating preference: " + ", ".join(f"{r} ({int(w)})" for r, w in overview["top_ratings"]))
    cats = [c for c, s in overview["category_stats"].items() if s.get("opens", 0) > 0]
    if cats:
        cat_lines = []
        for c in cats:
            s = overview["category_stats"][c]
            avg = s["dwell_seconds"] / s["opens"] if s["opens"] else 0
            cat_lines.append(f"'{c}': {s['opens']} opens, ~{avg:.0f}s avg")
        lines.append("Liked categories: " + "; ".join(cat_lines))
    h = overview["hentai"]
    if h["opens"]:
        lines.append(f"Watched {h['opens']} hentai series (~{h['dwell_seconds']:.0f}s).")
        if h["top_series"]:
            names = [t.capitalize() for t, w in h["top_series"][:5] if t]
            lines.append("Top hentai: " + ", ".join(names))
        if h["top_genres"]:
            lines.append("Preferred hentai genres: " + ", ".join(g.capitalize() for g, w in h["top_genres"][:8]))
    m = overview["manga"]
    if m["opens"]:
        lines.append(f"Explored {m['opens']} manga series (~{m['dwell_seconds']:.0f}s).")
        if m["top_series"]:
            names = [t.capitalize() for t, w in m["top_series"][:5] if t]
            lines.append("Top manga: " + ", ".join(names))
    if overview["top_searches"]:
        lines.append("Top searches: " + ", ".join(t for t, w in overview["top_searches"][:8]))
    return " ".join(lines)