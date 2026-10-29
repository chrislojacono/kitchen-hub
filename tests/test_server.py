import os
import tempfile
from pathlib import Path

os.environ["KITCHEN_TOKEN"] = "t" * 40

from fastapi.testclient import TestClient

from core import db
from server.app import app


def test_token_required():
    db.DB_PATH = Path(tempfile.mkdtemp()) / "test.db"
    with TestClient(app) as client:
        good = {"Authorization": "Bearer " + "t" * 40}
        assert client.get("/api/grocery").status_code == 401
        assert client.get("/api/grocery", headers={"Authorization": "Bearer wrong"}).status_code == 401
        assert client.post("/mcp", json={}).status_code == 401
        assert client.get("/api/grocery", headers=good).json() == []
        assert client.post("/api/grocery/1/check", headers=good).status_code == 400
        assert client.get("/docs").status_code == 200


if __name__ == "__main__":
    test_token_required()
    print("test_token_required ok")
