import json
import logging

from httpx import AsyncClient

from app.core.logging import JsonFormatter, request_id_var
from app.core.middleware import REQUEST_ID_HEADER


async def test_liveness(http: AsyncClient) -> None:
    response = await http.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_readiness_checks_database(http: AsyncClient) -> None:
    response = await http.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_request_id_is_generated(http: AsyncClient) -> None:
    response = await http.get("/health")
    assert len(response.headers[REQUEST_ID_HEADER]) == 32


async def test_valid_incoming_request_id_is_kept(http: AsyncClient) -> None:
    response = await http.get("/health", headers={REQUEST_ID_HEADER: "abc-123"})
    assert response.headers[REQUEST_ID_HEADER] == "abc-123"


async def test_invalid_incoming_request_id_is_replaced(http: AsyncClient) -> None:
    response = await http.get("/health", headers={REQUEST_ID_HEADER: "bad id\n" * 20})
    assert response.headers[REQUEST_ID_HEADER] != "bad id\n" * 20
    assert len(response.headers[REQUEST_ID_HEADER]) == 32


def test_json_formatter_includes_request_id_and_extra() -> None:
    record = logging.makeLogRecord(
        {"name": "t", "levelname": "INFO", "msg": "request", "status": 200}
    )
    token = request_id_var.set("rid-1")
    try:
        payload = json.loads(JsonFormatter().format(record))
    finally:
        request_id_var.reset(token)
    assert payload["msg"] == "request"
    assert payload["request_id"] == "rid-1"
    assert payload["status"] == 200
