from rq import Queue
from redis import Redis
import os

# Simple Redis connection using environment variables or defaults
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_conn = Redis.from_url(redis_url)
queue = Queue("default", connection=redis_conn)

def enqueue(func, *args, **kwargs):
    return queue.enqueue(func, *args, **kwargs)
