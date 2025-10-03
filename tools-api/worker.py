"""Simple worker runner for processing queued jobs using RQ.

Run: python worker.py
"""
from rq import Worker, Queue, Connection
from redis import Redis
import os

redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_conn = Redis.from_url(redis_url)

if __name__ == "__main__":
    with Connection(redis_conn):
        qs = [Queue("default")]
        w = Worker(qs)
        print("Worker started, waiting for jobs...")
        w.work()
