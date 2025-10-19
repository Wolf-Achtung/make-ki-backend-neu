"""
Compatibility shim for legacy clients expecting POST /api/login.
We redirect with HTTP 307 to the canonical /api/auth/login endpoint
so the method and body are preserved.
"""
from fastapi import APIRouter, Request, Response
from starlette.responses import RedirectResponse, JSONResponse

router = APIRouter()

@router.post("/login", include_in_schema=False)
async def login_alias_post(request: Request):
    return RedirectResponse(url="/api/auth/login", status_code=307)

@router.options("/login", include_in_schema=False)
async def login_alias_options() -> Response:
    # Allow CORS preflight to succeed quickly
    return Response(status_code=204)

@router.get("/login", include_in_schema=False)
async def login_alias_get():
    return JSONResponse({"detail": "Use POST /api/login"}, status_code=405)
