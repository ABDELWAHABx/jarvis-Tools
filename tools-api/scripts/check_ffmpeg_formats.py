import sys
from pathlib import Path

# Ensure the repository root is on sys.path so 'app' can be imported when running
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)
resp = client.get('/media/ffmpeg/formats')
print('STATUS:', resp.status_code)
print('HEADERS:', dict(resp.headers))
try:
    print('JSON:', resp.json())
except Exception:
    print('TEXT:', resp.text[:1000])
