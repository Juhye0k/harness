"""ASGI guard keeps resource usage until the final response body is delivered."""

import hmac
from http.cookies import SimpleCookie
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse

from app.api.auth import COOKIE, csrf, session_user
from app.config import get_settings
from app.domain.jobs import JobError
from app.services.access import acquire, current_user, release


class AuthMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        settings = get_settings()
        if (
            settings.enable_auth
            and settings.app_env not in {"development", "test"}
            and not settings.auth_origin.startswith("https://")
        ):
            return await JSONResponse({"error": {"code": "HTTPS_REQUIRED"}}, 503)(
                scope, receive, send
            )
        if not settings.enable_auth:
            if settings.app_env not in {"development", "test"}:
                return await JSONResponse({"error": {"code": "AUTH_REQUIRED"}}, 503)(
                    scope, receive, send
                )
            return await self.app(scope, receive, send)
        request = Request(scope, receive)
        path = request.url.path
        public = path in {
            "/login",
            "/health/live",
            "/health/ready",
            "/auth/google/start",
            "/auth/google/callback",
        } or path.startswith(("/static/", "/deletion-status/"))
        if public:
            return await self.app(scope, receive, send)
        uses, context_token = [], None
        try:
            cookies = SimpleCookie(request.headers.get("cookie", ""))
            token = cookies[COOKIE].value if COOKIE in cookies else ""
            user, _ = await run_in_threadpool(
                session_user,
                token,
                request.method not in {"GET", "HEAD"}
                or request.headers.get("x-user-activity") == "1",
            )
            if request.method not in {"GET", "HEAD", "OPTIONS"}:
                if request.headers.get("origin") != settings.auth_origin or not hmac.compare_digest(
                    request.headers.get("x-csrf-token", ""), csrf(token)
                ):
                    raise JobError("CSRF_DENIED", "앱 화면에서 다시 요청하세요.", 403)
            parts = path.strip("/").split("/")
            resources = []
            if len(parts) > 1 and parts[0] in {"analyses", "jobs", "assets"}:
                try:
                    resource = UUID(parts[1])
                except ValueError:
                    resource = None
                if resource:
                    resources.append(
                        (
                            {"analyses": "analysis", "jobs": "job", "assets": "asset"}[parts[0]],
                            resource,
                        )
                    )
            # Parent references in create requests also need a usage claim.
            upload_stream = (
                request.method == "PUT"
                and len(parts) == 3
                and parts[0] == "assets"
                and parts[2] == "content"
            )
            body = b""
            if not upload_stream:
                chunks, size = [], 0
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > 65536:
                        raise JobError("INPUT_TOO_LARGE", "입력 크기 제한을 초과했습니다.", 413)
                    chunks.append(chunk)
                body = b"".join(chunks)
            if body and request.method in {"POST", "PUT"}:
                try:
                    import json

                    data = json.loads(body)
                    for key, kind in (("asset_id", "asset"), ("job_id", "job")):
                        if isinstance(data, dict) and data.get(key):
                            resources.append((kind, UUID(data[key])))
                except (ValueError, TypeError):
                    pass  # Endpoint validation supplies the ordinary invalid-input response.
            # Deletion must not block on its own request claim.
            if request.method == "DELETE" or "deletion-preview" in parts:
                resources = []
            if request.method != "DELETE":
                uses = await run_in_threadpool(acquire, user, resources)
            context_token = current_user.set(user)
            sent = False

            async def replay():
                nonlocal sent
                if not sent:
                    sent = True
                    return {"type": "http.request", "body": body, "more_body": False}
                return await receive()

            async def private_send(message):
                if message["type"] == "http.response.start":
                    if "/verification/assets/" in path and path.endswith(".html"):
                        message["headers"] = list(message.get("headers", [])) + [
                            (b"content-disposition", b"attachment"),
                            (b"content-security-policy", b"sandbox; default-src 'none'"),
                            (b"x-content-type-options", b"nosniff"),
                        ]
                    message["headers"] = list(message.get("headers", [])) + [
                        (b"cache-control", b"no-store"),
                        (b"referrer-policy", b"no-referrer"),
                    ]
                await send(message)

            await self.app(scope, receive if upload_stream else replay, private_send)
        except JobError as exc:
            if exc.status_code == 401 and "text/html" in request.headers.get("accept", ""):
                return await RedirectResponse("/login", status_code=303)(scope, receive, send)
            await JSONResponse({"error": {"code": exc.code, "message": str(exc)}}, exc.status_code)(
                scope, receive, send
            )
        except SQLAlchemyError:
            await JSONResponse({"error": {"code": "AUTH_STORE_UNAVAILABLE"}}, 503)(
                scope, receive, send
            )
        finally:
            if context_token is not None:
                current_user.reset(context_token)
            await run_in_threadpool(release, uses)
