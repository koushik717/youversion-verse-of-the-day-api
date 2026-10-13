import httpx
import pytest

from app.config import settings

FAKE_APP_KEY = "test-app-key-should-never-leak"


def votd_response(day: int, passage_id: str = "REV.3.20") -> httpx.Response:
    return httpx.Response(200, json={"day": day, "passage_id": passage_id})


def passage_response(reference: str, content: str) -> httpx.Response:
    return httpx.Response(200, json={"id": "REV.3.20", "content": content, "reference": reference})


def test_happy_path(make_client, monkeypatch):
    monkeypatch.setattr(settings, "youversion_app_key", FAKE_APP_KEY)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/verse_of_the_days/195":
            return votd_response(195)
        if request.url.path == "/v1/bibles/206/passages/REV.3.20":
            return passage_response(
                "Revelation 3:20",
                "Behold, I stand at the door and knock.",
            )
        raise AssertionError(f"unexpected request: {request.url}")

    client = make_client(handler)
    response = client.get("/votd", params={"day": 195, "version": 206})

    assert response.status_code == 200
    assert response.json() == {
        "day": 195,
        "reference": "Revelation 3:20",
        "text": "Behold, I stand at the door and knock.",
        "version_id": 206,
    }


@pytest.mark.parametrize("bad_day", ["0", "367", "abc", "-1"])
def test_invalid_day_never_calls_upstream(make_client, bad_day):
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("invalid day should be rejected before any upstream call")

    client = make_client(handler)
    response = client.get("/votd", params={"day": bad_day, "version": 206})

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "INVALID_DAY",
            "message": "day must be an integer between 1 and 366",
        }
    }


def test_upstream_500_becomes_502(make_client):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="internal server error")

    client = make_client(handler)
    response = client.get("/votd", params={"day": 195, "version": 206})

    assert response.status_code == 502
    body = response.json()
    assert body["error"]["code"] == "UPSTREAM_ERROR"


def test_upstream_timeout_becomes_502(make_client):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("connection timed out", request=request)

    client = make_client(handler)
    response = client.get("/votd", params={"day": 195, "version": 206})

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "UPSTREAM_ERROR"


def test_repeated_request_hits_upstream_once(make_client):
    call_counts = {"day": 0, "passage": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/verse_of_the_days/195":
            call_counts["day"] += 1
            return votd_response(195)
        if request.url.path == "/v1/bibles/206/passages/REV.3.20":
            call_counts["passage"] += 1
            return passage_response("Revelation 3:20", "Behold, I stand at the door.")
        raise AssertionError(f"unexpected request: {request.url}")

    client = make_client(handler)
    for _ in range(3):
        response = client.get("/votd", params={"day": 195, "version": 206})
        assert response.status_code == 200

    assert call_counts == {"day": 1, "passage": 1}


def test_defaults_when_day_and_version_omitted(make_client):
    seen_paths = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_paths.append(request.url.path)
        if request.url.path.startswith("/v1/verse_of_the_days/"):
            return votd_response(int(request.url.path.rsplit("/", 1)[-1]))
        return passage_response("Revelation 3:20", "Behold, I stand at the door.")

    client = make_client(handler)
    response = client.get("/votd")

    assert response.status_code == 200
    body = response.json()
    assert 1 <= body["day"] <= 366
    assert body["version_id"] == settings.default_version_id


def test_app_key_never_appears_in_a_response(make_client, monkeypatch):
    monkeypatch.setattr(settings, "youversion_app_key", FAKE_APP_KEY)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    client = make_client(handler)
    response = client.get("/votd", params={"day": 195, "version": 206})

    assert FAKE_APP_KEY not in response.text


def test_versions_endpoint(make_client):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/bibles"
        return httpx.Response(
            200,
            json={
                "data": [
                    {"id": 206, "abbreviation": "WEB", "title": "World English Bible", "language_tag": "en"},
                    {"id": 12, "abbreviation": "ASV", "title": "American Standard Version", "language_tag": "en"},
                ]
            },
        )

    client = make_client(handler)
    response = client.get("/versions")

    assert response.status_code == 200
    assert response.json() == [
        {"id": 206, "abbreviation": "WEB", "title": "World English Bible"},
        {"id": 12, "abbreviation": "ASV", "title": "American Standard Version"},
    ]


def test_licensed_version_403_becomes_502(make_client):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/verse_of_the_days/195":
            return votd_response(195)
        if request.url.path == "/v1/bibles/111/passages/REV.3.20":
            return httpx.Response(403, json={"message": "Access denied"})
        raise AssertionError(f"unexpected request: {request.url}")

    client = make_client(handler)
    response = client.get("/votd", params={"day": 195, "version": 111})

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "UPSTREAM_ERROR"


@pytest.mark.parametrize("bad_version", ["-5", "0"])
def test_non_positive_version_never_calls_upstream(make_client, bad_version):
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("non-positive version should be rejected before any upstream call")

    client = make_client(handler)
    response = client.get("/votd", params={"day": 195, "version": bad_version})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_VERSION"
