# File: tools/health_check.py
"""Tiny health check client for local dev (PEP8-compliant)."""
from __future__ import annotations
import json
import sys
from urllib.request import urlopen, Request

def main() -> int:
    url = "http://localhost:8080/healthz"
    try:
        req = Request(url, headers={"User-Agent": "health-check/1.0"})
        with urlopen(req, timeout=3) as resp:  # nosec - dev only
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("ok"):
                print("OK", data)
                return 0
            print("Bad response:", data, file=sys.stderr)
            return 2
    except Exception as exc:  # pylint: disable=broad-except
        print("ERROR:", exc, file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
