"""Simple config helper that reads environment variables.

This avoids relying on pydantic so the runner script remains simple and
workable in environments with different pydantic versions.
"""
import os


class Settings:
    API_KEY: str
    GOOGLE_DOCS_API_URL: str
    DEBUG: bool

    def __init__(self):
        self.API_KEY = os.getenv("API_KEY", "")
        self.GOOGLE_DOCS_API_URL = os.getenv("GOOGLE_DOCS_API_URL", "")
        self.DEBUG = os.getenv("DEBUG", "True").lower() in ("1", "true", "yes")


settings = Settings()
