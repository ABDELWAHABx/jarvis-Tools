"""Simple config helper that reads environment variables.

This avoids relying on pydantic so the runner script remains simple and
workable in environments with different pydantic versions.
"""
import os


class Settings:
    API_KEY: str
    GOOGLE_DOCS_API_URL: str
    DEBUG: bool
    COBALT_API_BASE_URL: str
    COBALT_API_AUTH_SCHEME: str
    COBALT_API_AUTH_TOKEN: str
    COBALT_API_TIMEOUT: float

    def __init__(self):
        self.API_KEY = os.getenv("API_KEY", "")
        self.GOOGLE_DOCS_API_URL = os.getenv("GOOGLE_DOCS_API_URL", "")
        self.DEBUG = os.getenv("DEBUG", "True").lower() in ("1", "true", "yes")
        self.COBALT_API_BASE_URL = os.getenv("COBALT_API_BASE_URL", "")
        self.COBALT_API_AUTH_SCHEME = os.getenv("COBALT_API_AUTH_SCHEME", "")
        self.COBALT_API_AUTH_TOKEN = os.getenv("COBALT_API_AUTH_TOKEN", "")
        self.COBALT_API_TIMEOUT = float(os.getenv("COBALT_API_TIMEOUT", "60"))


settings = Settings()
