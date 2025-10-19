#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RQ worker entrypoint for Railway.
Start with: python worker.py
Configure with env: REDIS_URL, RQ_QUEUES (comma separated), RQ_JOB_TIMEOUT, RQ_LOG_LEVEL
"""
from __future__ import annotations

import logging
import os

from redis import Redis
from rq import Connection, Worker, Queue

from queue_utils import get_redis_connection, get_queue_names

def main() -> int:
    log_level = os.getenv("RQ_LOG_LEVEL", "INFO").upper()
    logging.basicConfig(level=log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logger = logging.getLogger("rq.worker")

    conn: Redis = get_redis_connection()
    names = get_queue_names()
    queues = [Queue(n, connection=conn) for n in names]
    logger.info("Starting RQ worker. Queues=%s", names)
    with Connection(conn):
        worker = Worker(queues, connection=conn)
        worker.work(with_scheduler=True, logging_level=log_level)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
