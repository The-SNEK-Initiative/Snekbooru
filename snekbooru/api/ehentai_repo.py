import os
import re
import cloudscraper
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from typing import Any, List, Optional, Union
from urllib.parse import urljoin, quote_plus

from enma.application.core.interfaces.manga_repository import IMangaRepository
from enma.domain.entities.manga import (MIME, Chapter, Genre, Author, Image, Manga, SymbolicLink,
                                        Title, Tag as EnmaTag)
from enma.domain.entities.search_result import Pagination, SearchResult, Thumb
from enma.domain.utils import mime
from snekbooru.common.constants import USER_AGENT, EHENTAI_API
from snekbooru.api.ehentai_utils import fetch_gallery_metadata, parse_gallery_id_token

class EHentaiRepo(IMangaRepository):
    def __init__(self):
        self._base_url = "https://e-hentai.org/"
        self._scraper = cloudscraper.create_scraper()

    def set_config(self, config: Any) -> None:
        pass

    def get(self, identifier: str, with_symbolic_links: bool = False, **kwargs) -> Union[Manga, None]:
        if "/" in identifier:
            gid, token = identifier.split("/")[:2]
        else:
            gid = identifier
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

            manga = Manga(
                title=Title(
                    english=meta.get("title"),
                    japanese=meta.get("title_jpn"),
                    other=meta.get("title")
                ),
                id=str(meta.get("gid")),
                created_at=datetime.fromtimestamp(int(meta.get("posted")), tz=timezone.utc),
                updated_at=datetime.fromtimestamp(int(meta.get("posted")), tz=timezone.utc),
                status='completed',
                url=f"https://e-hentai.org/g/{meta.get('gid')}/{meta.get('token')}/",
                language=None,
                authors=authors,
                genres=genres,
                thumbnail=Image(uri=meta.get("thumb"), mime=MIME.J, width=250, height=350),
                tags=tags,
                cover=Image(uri=meta.get("thumb"), mime=MIME.J, width=250, height=350),
                chapters=[]
            )
            return manga
        except Exception as e:
            print(f"Error fetching e-hentai metadata: {e}")
            return None

    def search(self, query: str, page: int, **kwargs) -> SearchResult:
        encoded_query = quote_plus(query)
        search_url = f"{self._base_url}?f_search={encoded_query}&page={page-1}"
        r = self._scraper.get(search_url, headers={"User-Agent": USER_AGENT})
        r.raise_for_status()
        
        soup = BeautifulSoup(r.text, 'html.parser')
        
        results = []
        
        items = soup.select("table.itg tr")
        if not items:
             items = soup.select("div.gl1t")

        gids_tokens = []
        for item in items:
            link = item.find("a", href=re.compile(r"/g/\d+/[a-f0-9]+/"))
            if link:
                url = link['href']
                gid, token = parse_gallery_id_token(url)
                if gid and token:
                    title = ""
                    title_elem = item.select_one(".glink") or item.select_one(".gl3t")
                    if title_elem: title = title_elem.get_text(strip=True)
                    
                    thumb_url = ""
                    thumb_elem = item.find("img")
                    if thumb_elem:
                        thumb_url = thumb_elem.get("src") or thumb_elem.get("data-src") or ""

                    gids_tokens.append((gid, token))
                    
                    results.append(Thumb(
                        id=f"{gid}/{token}",
                        url=url,
                        cover=Image(uri=thumb_url, mime=MIME.J, width=200, height=280),
                        title=title
                    ))

        total_pages = 1
        ptb = soup.select_one("table.ptt")
        if ptb:
            last_page_elem = ptb.select("td")[-2]
            if last_page_elem:
                try:
                    total_pages = int(last_page_elem.get_text(strip=True))
                except:
                    pass

        return SearchResult(
            query=query,
            total_pages=total_pages,
            page=page,
            total_results=len(results) * total_pages,
            results=results
        )

    def paginate(self, page: int) -> Pagination:
        res = self.search(query="", page=page)
        return Pagination(
            page=page,
            total_pages=res.total_pages,
            results=res.results
        )

    def random(self) -> Manga:
        raise NotImplementedError("Random not implemented for e-hentai")

    def author_page(self, author: str, page: int) -> Any:
        return self.search(query=f"artist:{author}", page=page)

    def fetch_chapter_by_symbolic_link(self, link: SymbolicLink) -> Chapter:
        raise NotImplementedError("fetch_chapter_by_symbolic_link not implemented for e-hentai")
