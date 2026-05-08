import typing
from . import exceptions

__all__ = ["raise_for_status", "get_status_from_response"]

def raise_for_status(status: int) -> typing.NoReturn:
    if status == 502:
        raise exceptions.TokenException()
    elif status == 429:
        raise exceptions.HHavenRateLimited()
    elif status == 404:
        raise exceptions.HHavenNotFound()
    else:
        raise exceptions.HHavenException("Something went wrong.", status)

def get_status_from_response(response: typing.Mapping[str, typing.Any]) -> int | None:
    data = response.get("data", None)
    if data and type(data) is str:
        if data[:3].isdigit(): 
            return int(data[:3])
    return None