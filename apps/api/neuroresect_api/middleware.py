"""Bound requests before JSON parsing and record payload-free request telemetry."""

import json
import logging
import time
import uuid

from starlette.responses import JSONResponse

logger = logging.getLogger("neuroresect.requests")


class RequestMiddleware:
    def __init__(self, app, max_request_bytes: int) -> None:
        self.app = app
        self.max_request_bytes = max_request_bytes

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = time.monotonic()
        request_id = uuid.uuid4().hex
        status = 500

        async def send_with_id(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message["headers"] = [
                    *message.get("headers", []),
                    (b"x-request-id", request_id.encode()),
                ]
            await send(message)

        async def reject(status_code: int, code: str, message: str) -> None:
            response = JSONResponse(
                {"error": {"code": code, "message": message, "details": {}}},
                status_code=status_code,
            )
            await response(scope, receive, send_with_id)

        try:
            headers = dict(scope.get("headers", []))
            if b"content-length" in headers:
                try:
                    declared = int(headers[b"content-length"])
                except ValueError:
                    await reject(400, "INVALID_CONTENT_LENGTH", "Invalid Content-Length header.")
                    return
                if declared < 0:
                    await reject(400, "INVALID_CONTENT_LENGTH", "Invalid Content-Length header.")
                    return
                if declared > self.max_request_bytes:
                    await reject(
                        413, "REQUEST_TOO_LARGE", "Request exceeds the configured size limit."
                    )
                    return
            body = bytearray()
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                body.extend(message.get("body", b""))
                if len(body) > self.max_request_bytes:
                    await reject(
                        413, "REQUEST_TOO_LARGE", "Request exceeds the configured size limit."
                    )
                    return
                if not message.get("more_body", False):
                    break
            delivered = False

            async def buffered_receive():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                return await receive()

            await self.app(scope, buffered_receive, send_with_id)
        finally:
            route = scope.get("route")
            logger.info(
                json.dumps(
                    {
                        "event": "http_request",
                        "request_id": request_id,
                        "method": scope["method"],
                        "route": getattr(route, "path", "unmatched"),
                        "status": status,
                        "duration_ms": round((time.monotonic() - started) * 1000, 2),
                    }
                )
            )
