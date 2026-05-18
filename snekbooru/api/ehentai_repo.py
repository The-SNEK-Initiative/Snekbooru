import re
import cloudscraper
from datetime import datetime, timezone
from types import SimpleNamespace
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from snekbooru.common.constants import USER_AGENT
from snekbooru.api.ehentai_utils import fetch_gallery_metadata, parse_gallery_id_token

try:
    from enma.application.core.interfaces.manga_repository import IMangaRepository
    from enma.domain.entities.manga import (MIME, Chapter, Genre, Author, Image, Manga, SymbolicLink,
                                            Title, Tag as EnmaTag)
    from enma.domain.entities.search_result import Pagination, SearchResult, Thumb
    ENMA_TYPES_AVAILABLE = True
except Exception:
    ENMA_TYPES_AVAILABLE = False

    class IMangaRepository:
        pass

    class _MIME:
        J = "image/jpeg"

    MIME = _MIME()
    Chapter = SymbolicLink = object

    def Title(**kwargs): return SimpleNamespace(**kwargs)
    def Genre(**kwargs): return SimpleNamespace(**kwargs)
    def Author(**kwargs): return SimpleNamespace(**kwargs)
    def Image(**kwargs): return SimpleNamespace(**kwargs)
    def Manga(**kwargs): return SimpleNamespace(**kwargs)
    def EnmaTag(**kwargs): return SimpleNamespace(**kwargs)
    def Thumb(**kwargs): return SimpleNamespace(**kwargs)
    def SearchResult(**kwargs): return SimpleNamespace(**kwargs)
    def Pagination(**kwargs): return SimpleNamespace(**kwargs)


class EHentaiRepo(IMangaRepository):
    def __init__(self):
        self._base_url = "https://e-hentai.org/"
        self._scraper = cloudscraper.create_scraper()

    def set_config(self, config):
        pass

    def get(self, identifier, with_symbolic_links=False, **kwargs):
        if "/" in str(identifier):
            gid, token = str(identifier).split("/")[:2]
        else:
            gid = str(identifier)
            token = kwargs.get("token", "")

        try:
            meta = fetch_gallery_metadata(int(gid), token, http_client=self._scraper)
            tags = []
            genres = []
            authors = []
            for t in meta.get("tags", []):
                if ":" in t:
                    ns, name = t.split(":", 1)
                    if ns == "artist":
                        authors.append(Author(id=name, name=name))
                    else:
                        tags.append(EnmaTag(type=ns, name=name, id=t))
                else:
                    genres.append(Genre(id=t, name=t))

            return Manga(
                title=Title(
                    english=meta.get("title"),
                    japanese=meta.get("title_jpn"),
                    other=meta.get("title"),
                ),
                id=str(meta.get("gid")),
                created_at=datetime.fromtimestamp(int(meta.get("posted")), tz=timezone.utc),
                updated_at=datetime.fromtimestamp(int(meta.get("posted")), tz=timezone.utc),
                status="completed",
                url=f"https://e-hentai.org/g/{meta.get('gid')}/{meta.get('token')}/",
                language=None,
                authors=authors,
                genres=genres,
                thumbnail=Image(uri=meta.get("thumb"), mime=MIME.J, width=250, height=350),
                tags=tags,
                cover=Image(uri=meta.get("thumb"), mime=MIME.J, width=250, height=350),
                chapters=[],
            )
        except Exception as e:
            print(f"Error fetching e-hentai metadata: {e}")
            return None

    def search(self, query, page, **kwargs):
        encoded_query = quote_plus(query or "")
        search_url = f"{self._base_url}?f_search={encoded_query}&page={max(0, int(page) - 1)}"
        r = self._scraper.get(search_url, headers={"User-Agent": USER_AGENT}, timeout=30)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        results = []
        items = soup.select("table.itg tr") or soup.select("div.gl1t")
        for item in items:
            link = item.find("a", href=re.compile(r"/g/\d+/[a-f0-9]+/"))
            if not link:
                continue
            url = link.get("href")
            gid, token = parse_gallery_id_token(url)
            title_elem = item.select_one(".glink") or item.select_one(".gl3t")
            title = title_elem.get_text(strip=True) if title_elem else ""
            thumb_elem = item.find("img")
            thumb_url = thumb_elem.get("src") or thumb_elem.get("data-src") or "" if thumb_elem else ""
            results.append(Thumb(
                id=f"{gid}/{token}" if gid and token else (url or ""),
                url=url,
                cover=Image(uri=thumb_url, mime=MIME.J, width=200, height=280),
                title=title,
            ))

        total_pages = 1
        ptb = soup.select_one("table.ptt")
        if ptb:
            tds = ptb.select("td")
            if len(tds) >= 2:
                try:
                    total_pages = int(tds[-2].get_text(strip=True))
                except Exception:
                    pass

        return SearchResult(
            query=query,
            total_pages=total_pages,
            page=page,
            total_results=len(results) * total_pages,
            results=results,
        )

    def paginate(self, page):
        res = self.search(query="", page=page)
        return Pagination(page=page, total_pages=getattr(res, "total_pages", 1), results=getattr(res, "results", []))

    def random(self):
        raise NotImplementedError("Random not implemented for e-hentai")

    def author_page(self, author, page):
        return self.search(query=f"artist:{author}", page=page)

    def fetch_chapter_by_symbolic_link(self, link):
        raise NotImplementedError("fetch_chapter_by_symbolic_link not implemented for e-hentai")
