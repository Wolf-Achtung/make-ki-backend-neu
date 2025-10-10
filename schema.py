# filename: schema.py
# -*- coding: utf-8 -*-
"""
Schema endpoint & helpers for Frontend/Backend synchronisation.

- Serves a canonical `report_schema.json`
- Adds weak ETag and caching headers
- Provides helpers to resolve labels and validate codes

Env:
  SCHEMA_FILE : path to schema JSON (default: ./shared/report_schema.json)
"""

from __future__ import annotations

import hashlib
import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse

DEFAULT_SCHEMA_PATH = Path(os.getenv("SCHEMA_FILE", "./shared/report_schema.json")).resolve()


@lru_cache(maxsize=1)
def _load_schema() -> Dict[str, Any]:
    if not DEFAULT_SCHEMA_PATH.exists():
        raise FileNotFoundError(f"Schema file not found: {DEFAULT_SCHEMA_PATH}")
    with DEFAULT_SCHEMA_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def _etag(payload: bytes) -> str:
    return hashlib.sha1(payload).hexdigest()


def get_router() -> APIRouter:
    router = APIRouter()

    @router.get("/schema")
    def schema_root(request: Request) -> Response:
        try:
            obj = _load_schema()
            payload = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            etag = _etag(payload)
            inm = request.headers.get("if-none-match")
            if inm and inm == etag:
                return Response(status_code=304)
            resp = JSONResponse(content=obj)
            resp.headers["ETag"] = etag
            resp.headers["Cache-Control"] = "public, max-age=300"
            return resp
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to load schema: {exc}") from exc

    @router.get("/schema/enum/{field_key}")
    def schema_enum(field_key: str) -> Dict[str, Any]:
        obj = _load_schema()
        field = (obj.get("fields") or {}).get(field_key)
        if not field:
            raise HTTPException(status_code=404, detail=f"Unknown field: {field_key}")
        return field

    return router


def resolve_label(field_key: str, value: str, lang: str = "de") -> Optional[str]:
    try:
        fld = _load_schema().get("fields", {}).get(field_key, {})
        for item in fld.get("enum", []):
            if item.get("value") == value:
                lbl = item.get("label")
                if isinstance(lbl, dict):
                    return lbl.get(lang) or lbl.get("de") or lbl.get("en")
                return str(lbl)
    except Exception:
        return None
    return None


def validate_enum(field_key: str, value: str) -> bool:
    try:
        fld = _load_schema().get("fields", {}).get(field_key, {})
        vals = {item.get("value") for item in fld.get("enum", [])}
        return value in vals
    except Exception:
        return False



def get_schema_info() -> Dict[str, Any]:
    """Return minimal schema info for health endpoints (version/hash, field count)."""
    try:
        obj = _load_schema()
        payload = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return {
            "etag": _etag(payload),
            "fields": len((obj or {}).get("fields", {})),
            "version": (obj or {}).get("version") or None,
        }
    except Exception:
        return {"etag": None, "fields": 0, "version": None}
