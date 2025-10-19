# -*- coding: utf-8 -*-
from __future__ import annotations
import os, sys, time
try:
    import redis
    from rq import Worker, Queue, Connection
except Exception as e:
    print("RQ/Redis not installed:", e, file=sys.stderr)
    sys.exit(1)

redis_url = os.environ.get("REDIS_URL")
if not redis_url:
    print("REDIS_URL not set; worker cannot start.", file=sys.stderr)
    sys.exit(2)

conn = redis.from_url(redis_url, decode_responses=False)
listen = ["reports"]

if __name__ == "__main__":
    with Connection(conn):
        worker = Worker(map(Queue, listen))
        print("RQ worker connected. Queues:", listen, "Redis:", redis_url)
        worker.work(with_scheduler=True)
