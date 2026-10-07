from fastapi import Request
from fastapi.responses import JSONResponse

from backend.services.enterprise_service import SESSION_COOKIE, resolve_session


async def require_account_session(request: Request, call_next):
    if not request.url.path.startswith("/api/"):
        return await call_next(request)

    authorization = request.headers.get("authorization", "")
    bearer_token = authorization[7:].strip() if authorization.startswith("Bearer ") else None
    user = resolve_session(request.cookies.get(SESSION_COOKIE) or bearer_token)
    request.state.user = user

    if request.url.path == "/api/health" or request.url.path.startswith("/api/auth/"):
        return await call_next(request)
    if not user:
        return JSONResponse(status_code=401, content={"detail": "Sign in to continue"})
    return await call_next(request)
