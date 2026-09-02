import httpx

from app.config import settings
from app.exceptions import ApiError


class YouVersionClient:
    """
    Thin wrapper around the YouVersion Platform API.

    Caches per-day passage lookups and per-(version, passage) text lookups
    separately and indefinitely, since the underlying calendar and passage
    text for a given version are static for the lifetime of the process.
    """

    def __init__(self, http_client: httpx.AsyncClient | None = None):
        self._client = http_client or httpx.AsyncClient(
            base_url=settings.youversion_base_url,
            timeout=settings.request_timeout_seconds,
        )
        self._passage_id_cache: dict[int, str] = {}
        self._passage_text_cache: dict[tuple[int, str], dict] = {}

    async def aclose(self) -> None:
        await self._client.aclose()

    def _headers(self) -> dict:
        return {"x-yvp-app-key": settings.youversion_app_key}

    async def _get(self, path: str, params: dict | None = None) -> dict:
        try:
            response = await self._client.get(
                path, params=params, headers=self._headers()
            )
        except httpx.RequestError as exc:
            # Never include the app key (it's only in the request, not the
            # exception text) — safe to reference the upstream path here.
            raise ApiError(
                502, "UPSTREAM_ERROR", f"Could not reach YouVersion ({path}): {exc.__class__.__name__}"
            ) from exc

        if response.status_code >= 400:
            raise ApiError(
                502, "UPSTREAM_ERROR", f"YouVersion returned {response.status_code} for {path}"
            )

        try:
            return response.json()
        except ValueError as exc:
            raise ApiError(
                502, "UPSTREAM_ERROR", f"YouVersion returned invalid JSON for {path}"
            ) from exc

    async def get_passage_id(self, day: int) -> str:
        if day in self._passage_id_cache:
            return self._passage_id_cache[day]

        data = await self._get(f"/v1/verse_of_the_days/{day}")
        try:
            passage_id = data["passage_id"]
        except (KeyError, TypeError) as exc:
            raise ApiError(
                502, "UPSTREAM_ERROR", "YouVersion verse-of-the-day response was missing 'passage_id'"
            ) from exc

        self._passage_id_cache[day] = passage_id
        return passage_id

    async def get_passage_text(self, version_id: int, passage_id: str) -> dict:
        cache_key = (version_id, passage_id)
        if cache_key in self._passage_text_cache:
            return self._passage_text_cache[cache_key]

        data = await self._get(
            f"/v1/bibles/{version_id}/passages/{passage_id}",
            params={"format": "text"},
        )
        try:
            result = {"reference": data["reference"], "text": data["content"]}
        except (KeyError, TypeError) as exc:
            raise ApiError(
                502, "UPSTREAM_ERROR", "YouVersion passage response was missing 'reference' or 'content'"
            ) from exc

        self._passage_text_cache[cache_key] = result
        return result

    async def list_english_versions(self) -> list[dict]:
        data = await self._get("/v1/bibles", params={"language_ranges[]": "en*"})
        try:
            return [
                {"id": item["id"], "abbreviation": item["abbreviation"], "title": item["title"]}
                for item in data["data"]
            ]
        except (KeyError, TypeError) as exc:
            raise ApiError(
                502, "UPSTREAM_ERROR", "YouVersion bibles response was missing expected fields"
            ) from exc
