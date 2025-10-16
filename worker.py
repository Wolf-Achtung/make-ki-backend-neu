# filename: worker.py
# -*- coding: utf-8 -*-
"""RQ worker entry point.
Railway: start with `python worker.py` in a separate service or proc.
"""
from __future__ import annotations

from rq import Worker, Queue, Connection
from redis import Redis
from settings import settings

def main():
    if not settings.REDIS_URL:
        raise SystemExit("REDIS_URL not configured")
    redis_conn = Redis.from_url(settings.REDIS_URL)
    with Connection(redis_conn):
        worker = Worker([Queue(settings.QUEUE_NAME)])
        worker.work(with_scheduler=False)

if __name__ == "__main__":
    main()
