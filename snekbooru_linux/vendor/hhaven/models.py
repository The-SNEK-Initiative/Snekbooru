"""HHaven models."""
import typing
import pydantic
from datetime import datetime

__all__ = [
    "HentaiRating",
    "HentaiGenre",
    "PartialHentaiGenre",
    "GenrePage",
    "HentaiPage",
    "HentaiTag",
    "HentaiAuthor",
    "HentaiRelease",
    "HentaiEpisode",
    "PartialHentaiEpisode",
    "HomePage",
    "Hentai",
    "PartialHentai"
]

class HentaiRating(pydantic.BaseModel):
    rating: float
    votes: int

class HentaiGenre(pydantic.BaseModel):
    id: int
    name: str
    slug: str
    count: int
    thumbnail: typing.Optional[str] = None
    client: typing.Any
    
    def __init__(self, **data: typing.Any):
        processed = {
            k.lower().replace("term_", ""): v
            for k, v in data.items()
        }
        super().__init__(**processed)
        
    async def page(self, page: int = 1) -> "GenrePage":
        return await self.client.get_genre_page(self.id, page)

class PartialHentaiGenre(pydantic.BaseModel):
    id: int
    name: str
    client: typing.Any
    
    def __init__(self, **data: typing.Any):
        processed = {
            k.lower().replace("term_", ""): v
            for k, v in data.items()
        }
        super().__init__(**processed)
        
    async def full(self) -> typing.List["HentaiGenre"]:
        all_genres = await self.client.get_all_genres()
        return [genre for genre in all_genres if genre.id == self.id]
    
    async def page(self, page: int = 1) -> "GenrePage":
        return await self.client.get_genre_page(self.id, page)

class GenrePage(pydantic.BaseModel):
    genre: HentaiGenre
    hentai: list["PartialHentai"]
    total_results: int
    index: int
    total_pages: int
    client: typing.Any
    
    def __init__(self, **data: typing.Any):
        data["genre"] = data.pop("term")
        data["hentai"] = data.pop("hentais")
        data["index"] = data.pop("current_page")
        for hentai in data["hentai"]:
            hentai["client"] = data.get("client")
        data["genre"]["client"] = data.get("client")
        super().__init__(**data)
        
    async def next(self) -> "GenrePage":
        return await self.client.get_genre_page(self.genre.id, self.index + 1)
    
    async def prev(self) -> "GenrePage":
        return await self.client.get_genre_page(self.genre.id, self.index - 1)

class HentaiPage(pydantic.BaseModel):
    hentai: list["PartialHentai"]
    total_results: int
    index: int
    total_pages: int
    client: typing.Any
    
    def __init__(self, **data: typing.Any):
        data["hentai"] = data.pop("hentais")
        data["index"] = data.pop("current_page")
        for hentai in data["hentai"]:
            hentai["client"] = data.get("client")
        super().__init__(**data)
        
    async def next(self) -> "HentaiPage":
        return await self.client.get_all_hentai(self.index + 1)
    
    async def prev(self) -> "HentaiPage":
        return await self.client.get_all_hentai(self.index - 1)

class HentaiTag(pydantic.BaseModel):
    id: int
    name: str

    def __init__(self, **data: typing.Any):
        processed = {
            k.lower().replace("term_", ""): v
            for k, v in data.items()
        }
        super().__init__(**processed)

class HentaiAuthor(pydantic.BaseModel):
    id: int
    name: str

    def __init__(self, **data: typing.Any):
        processed = {
            k.lower().replace("term_", ""): v
            for k, v in data.items()
        }
        super().__init__(**processed)

class HentaiRelease(pydantic.BaseModel):
    id: int
    name: str

    def __init__(self, **data: typing.Any):
        processed = {
            k.lower().replace("term_", ""): v
            for k, v in data.items()
        }
        super().__init__(**processed)

class HentaiEpisode(pydantic.BaseModel):
    id: int
    name: str
    slug: str
    date: datetime
    content: str
    thumbnail: str
    hentai_id: int
    hentai_name: str
    hentai_title: str
    hentai_views: int
    hentai_thumbnail: str
    hentai_description: str
    hentai_date: datetime
    hentai_rating: HentaiRating
    hentai_tags: list[HentaiTag]
    hentai_title_alternative: str
    hentai_genres: list[PartialHentaiGenre]
    hentai_authors: list[HentaiAuthor]
    hentai_releases: list[HentaiRelease]
    next_episode: typing.Optional["HentaiEpisode"] = None
    prev_episode: typing.Optional["HentaiEpisode"] = None

    def __init__(self, **data: typing.Any):
        processed = {
            k.lower().replace("post_", "hentai_").replace("chapter_", ""): v
            for k, v in data.items()
        }
        processed["hentai_description"] = processed.pop("hentai_content")
        processed["date"] = datetime.strptime(processed["date"], "%Y-%m-%d %H:%M:%S")
        processed["hentai_date"] = datetime.strptime(processed["hentai_date"], "%Y-%m-%d %H:%M:%S")
        if data.get("next_episode") is not None:
            for key, value in data.items():
                if key not in ("id", "name", "thumbnail", "date", "slug"):
                    if key == "next_episode" or key == "prev_episode":
                        data["next_episode"][key] = None
                    else:
                        data["next_episode"][key] = value
        if data.get("prev_episode") is not None:
            for key, value in data.items():
                if key not in ("id", "name", "thumbnail", "date", "slug"):
                    if key == "next_episode" or key == "prev_episode":
                        data["prev_episode"][key] = None
                    else:
                        data["prev_episode"][key] = value
        for genre in processed["hentai_genres"]:
            genre["client"] = data.get("client")
        super().__init__(**processed)
 
class PartialHentaiEpisode(pydantic.BaseModel):
    id: int
    name: str
    slug: str
    date: datetime
    thumbnail: str
    hentai_id: int
    hentai_name: str
    hentai_title: str
    hentai_thumbnail: str
    hentai_description: str
    client: typing.Any

    def __init__(self, **data: typing.Any):
        processed = {
            k.lower().replace("post_", "hentai_").replace("chapter_", ""): v
            for k, v in data.items()
        }
        processed["hentai_description"] = processed.pop("hentai_content")
        processed["date"] = datetime.strptime(processed["date"], "%Y-%m-%d %H:%M:%S")
        super().__init__(**processed)
        
    async def full(self) -> HentaiEpisode:
        return await self.client.get_episode(self.id, self.hentai_id)

class Hentai(pydantic.BaseModel):
    id: int
    name: str
    title: str
    views: int
    thumbnail: str
    date: datetime
    description: str
    rating: HentaiRating
    tags: list[HentaiTag]
    title_alternative: str
    genres: list[PartialHentaiGenre]
    authors: list[HentaiAuthor]
    releases: list[HentaiRelease]
    episodes: list[PartialHentaiEpisode]
    client: typing.Any

    def __init__(self, **data: typing.Any):
        processed = {
            k.lower().replace("post_", ""): v
            for k, v in data.items()
        }
        processed["description"] = processed.pop("content")
        processed["date"] = datetime.strptime(processed["date"], "%Y-%m-%d %H:%M:%S")
        for episode in processed["episodes"]:
            episode["client"] = data.get("client")
            episode["hentai_id"] = processed.get("id")
            episode["hentai_name"] = processed.get("name")
            episode["hentai_title"] = processed.get("title")
            episode["hentai_thumbnail"] = processed.get("thumbnail")
            episode["hentai_content"] = processed.get("description")
        for genre in processed["genres"]:
            genre["client"] = data.get("client")
        super().__init__(**processed)

class PartialHentai(pydantic.BaseModel):
    id: int
    name: str
    title: str
    thumbnail: str
    client: typing.Any

    def __init__(self, **data: typing.Any):
        processed = {
            k.lower().replace("post_", ""): v
            for k, v in data.items()
        }
        super().__init__(**processed)
        
    async def full(self) -> Hentai:
        return await self.client.get_hentai(self.id)

class HomePage(pydantic.BaseModel):
    client: typing.Any
    last: list[PartialHentai]
    yuri: list[PartialHentai]
    ecchi: list[PartialHentai]
    incest: list[PartialHentai]
    tentacle: list[PartialHentai]
    uncensored: list[PartialHentai]
    trending_month: list[PartialHentai]
    last_episodes: list[PartialHentaiEpisode]
    
    def __init__(self, **data: typing.Any):
        for _, value in data.items():
            if isinstance(value, list):
                for item in typing.cast(list[typing.Any], value):
                    item["client"] = data.get("client")
        super().__init__(**data)