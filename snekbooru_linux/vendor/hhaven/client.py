import aiohttp
import json
import logging
import typing
import aiocache  # type: ignore[reportMissingTypeStubs]
from . import exceptions, utility, models
from .decorators import requires_build, requires_token, cached

__all__ = ["Client"]

class Client:
    cache: aiocache.Cache | None  # type: ignore[reportUnknownMemberType]
    cache_ttl: int
    proxy: str | None
    proxy_auth: aiohttp.BasicAuth | None
    _built = False
    _session: aiohttp.ClientSession | None = None
    _BASE_API_URL = "https://api.hentaihaven.app/v1/"
    _logger: logging.Logger = logging.getLogger(__name__)
    _default_headers: typing.Dict[str, str] = {
        "content-type": "application/x-www-form-urlencoded; charset=utf-8",
        "user-agent": "HH_xxx_APP",
        "warden": ""
    }
    _default_warden_body: typing.Mapping[str, typing.Any] = {
        "sdkInt": 33,
        "board": "goldfish_x86_64",
        "brand": "google",
        "display": "sdk_gphone_x86_64-userdebug 13 TE1A.220922.028 10190541 dev-keys",
        "fingerprint": "google/sdk_gphone_x86_64/emu64xa:13/TE1A.220922.028/10190541:userdebug/dev-keys",
        "manufacturer": "Google",
        "model": "sdk_gphone_x86_64"
    }

    def __init__(
        self, 
        token: str | None = None,
        *,
        cache: aiocache.Cache | None = None,
        cache_ttl: int = 1800,
        debug: bool = False,
        warden_body: typing.Mapping[str, typing.Any] = _default_warden_body,
        proxy: str | None = None,
        proxy_auth: aiohttp.BasicAuth | None = None
    ) -> None:
        self.cache = cache
        self.debug = debug
        self.cache_ttl = cache_ttl
        self._default_warden_body = warden_body
        self.proxy = proxy
        self.proxy_auth = proxy_auth
        if token:
            self.token = token
    
    @property
    def token(self) -> str | None:
        return self._default_headers["warden"]

    @token.setter
    def token(self, token: str) -> None:
        self._default_headers["warden"] = token
    
    @property
    def debug(self) -> bool:
        return logging.getLogger("hhaven").level == logging.DEBUG
    
    @debug.setter
    def debug(self, debug: bool) -> None:
        logging.basicConfig()
        level = logging.DEBUG if debug else logging.NOTSET
        logging.getLogger("hhaven").setLevel(level)
    
    async def build(
        self, 
        token: str | None = None,
        *,
        validate_token: bool = True
    ) -> "Client":
        if token:
            self.token = token
            self._default_headers["warden"] = token
        if not self.token:
            await self.get_new_token(apply=True)
        if validate_token:
            await self._request("GET", "hentai/home", disable_logging=True)
        self._built = True
        return self

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
        self._built = False

    async def _request(
        self,
        method: typing.Literal["GET", "POST"],
        path: str,
        headers: typing.Mapping[str, str] = _default_headers,
        data: typing.Mapping[str, typing.Any] = {},
        disable_logging: bool = False
    ) -> typing.Mapping[str, typing.Any]:
        current_warden = self._session.headers.get("warden") if self._session else None
        if not self._session or self._session.closed or current_warden != self.token:
            if self._session and not self._session.closed:
                await self._session.close()
            self._session = aiohttp.ClientSession(headers=self._default_headers.copy(),
                                                  proxy=self.proxy,
                                                  auth=self.proxy_auth)
        async with self._session.request(
            method=method,
            url=self._BASE_API_URL + path,
            data=data,
        ) as r:
            response = await r.json(content_type=None)
            status = utility.get_status_from_response(response) or r.status
            if not disable_logging:
                self._logger.debug("%s %s\n%s\n%s", method, r.url, json.dumps(data, separators=(",", ":")), response)
            if not str(status).startswith("2"):
                utility.raise_for_status(status)
            return response

    @requires_build
    @requires_token
    @cached
    async def home(self) -> models.HomePage:
        data = await self._request("GET", "hentai/home")
        return models.HomePage(client=self, **data["data"])

    @requires_build
    @requires_token
    @cached
    async def search(self, query: str) -> list[models.PartialHentai]:
        data = await self._request("GET", f"search?q={query}")
        if type(data["data"]) is str:
            return []
        return [models.PartialHentai(client=self, **post) for post in data["data"]]

    @requires_build
    @requires_token
    @cached
    async def get_hentai(self, id: int) -> models.Hentai:
        data = await self._request("GET", f"hentai/{id}")
        if type(data["data"]) is str:
            raise exceptions.HentaiNotFound()
        return models.Hentai(client=self, **data["data"])

    @requires_build
    @requires_token
    @cached
    async def get_episode(self, id: int, hentai_id: int) -> models.HentaiEpisode:
        data = await self._request("GET", f"hentai/{hentai_id}/episode/{id}")
        if type(data["data"]) is str:
            raise exceptions.HentaiEpisodeNotFound()
        return models.HentaiEpisode(**data["data"])

    @requires_build
    @requires_token
    @cached
    async def get_all_genres(self) -> typing.List[models.HentaiGenre]:
        data = await self._request("GET", "genre/all")
        return [models.HentaiGenre(client=self, **genre) for genre in data["data"]]

    @requires_build
    @requires_token
    @cached
    async def get_genre_page(self, id: int, page: int = 1) -> models.GenrePage:
        data = await self._request("GET", f"genre/{id}?p={page}")
        if type(data["data"]) is str:
            raise exceptions.GenrePageNotFound()
        return models.GenrePage(client=self, **data["data"])

    @requires_build
    @requires_token
    @cached
    async def get_all_hentai(self, page: int = 1) -> models.HentaiPage:
        data = await self._request("GET", f"hentai/all?p={page}")
        if type(data["data"]) is str:
            raise exceptions.HentaiPageNotFound()
        return models.HentaiPage(client=self, **data["data"])

    async def get_new_token(
        self, 
        apply: bool = True,
        *,
        body: typing.Mapping[str, typing.Any] = _default_warden_body,
        headers: typing.Mapping[str, str] = _default_headers
    ) -> str:
        response = await self._request("POST", "warden", headers, body)
        token = response["data"]["token"]
        if apply:
            self.token = token
            if self._session and not self._session.closed:
                await self._session.close()
        return token
