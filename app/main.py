from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse

from app.client import YouVersionClient
from app.config import settings
from app.exceptions import ApiError
from app.schemas import BibleVersion, VerseOfTheDay


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.youversion = YouVersionClient()
    yield
    await app.state.youversion.aclose()


app = FastAPI(title="Verse of the Day API", lifespan=lifespan)


@app.exception_handler(ApiError)
async def api_error_handler(request: Request, exc: ApiError):
    return JSONResponse(status_code=exc.status_code, content=exc.to_dict())


def _parse_day(raw_day: str | None) -> int:
    if raw_day is None:
        # "Today" is defined in UTC so the answer doesn't depend on where
        # the server (or the caller) happens to be running.
        return datetime.now(timezone.utc).timetuple().tm_yday

    try:
        day = int(raw_day)
    except ValueError:
        raise ApiError(400, "INVALID_DAY", "day must be an integer between 1 and 366")

    if not 1 <= day <= 366:
        raise ApiError(400, "INVALID_DAY", "day must be an integer between 1 and 366")

    return day


def _parse_version(raw_version: str | None) -> int:
    if raw_version is None:
        # Default to a public-domain version so an unqualified request
        # always succeeds instead of hitting a licensing 403 by chance.
        return settings.default_version_id

    try:
        return int(raw_version)
    except ValueError:
        raise ApiError(400, "INVALID_VERSION", "version must be an integer bible version id")


@app.get("/votd", response_model=VerseOfTheDay)
async def get_verse_of_the_day(
    request: Request,
    day: str | None = Query(default=None),
    version: str | None = Query(default=None),
):
    parsed_day = _parse_day(day)
    parsed_version = _parse_version(version)

    client: YouVersionClient = request.app.state.youversion
    passage_id = await client.get_passage_id(parsed_day)
    passage = await client.get_passage_text(parsed_version, passage_id)

    return VerseOfTheDay(
        day=parsed_day,
        reference=passage["reference"],
        text=passage["text"],
        version_id=parsed_version,
    )


@app.get("/versions", response_model=list[BibleVersion])
async def get_versions(request: Request):
    client: YouVersionClient = request.app.state.youversion
    versions = await client.list_english_versions()
    return [BibleVersion(**v) for v in versions]
