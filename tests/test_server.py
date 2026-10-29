import os
import tempfile
from pathlib import Path
from urllib.parse import urlparse

os.environ["KITCHEN_TOKEN"] = "t" * 40
os.environ["KITCHEN_PUBLIC_URL"] = "http://testserver"

from fastapi.testclient import TestClient

from core import db
from server.app import app

BEARER = {"Authorization": "Bearer " + "t" * 40}


def test_token_required():
    db.DB_PATH = Path(tempfile.mkdtemp()) / "test.db"
    client = TestClient(app)
    assert client.get("/api/grocery").status_code == 401
    assert client.get("/api/grocery", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.post("/mcp", json={}).status_code == 401
    assert client.get("/api/grocery", headers=BEARER).json() == []
    assert client.post("/api/grocery/1/check", headers=BEARER).status_code == 400
    assert client.get("/docs").status_code == 200


def test_phone_pairing():
    db.DB_PATH = Path(tempfile.mkdtemp()) / "test.db"
    kitchen, phone, stranger = TestClient(app), TestClient(app), TestClient(app)

    assert kitchen.post("/api/pair").status_code == 401
    pair_url = urlparse(kitchen.post("/api/pair", headers=BEARER).json()["url"])
    pair_path = f"{pair_url.path}?{pair_url.query}"

    assert phone.get("/m").status_code == 401
    assert phone.get("/pair?code=guess").status_code == 400
    paired = phone.get(pair_path, follow_redirects=False)
    assert paired.status_code == 303 and "httponly" in paired.headers["set-cookie"].lower()
    assert phone.get("/m").status_code == 200
    assert stranger.get(pair_path, follow_redirects=False).status_code == 400

    assert phone.post("/api/grocery", json=[{"name": "Milk"}]).json() == [1]
    assert phone.get("/api/grocery").json()[0]["name"] == "Milk"
    assert phone.post("/mcp", json={}).status_code == 401
    assert phone.post("/api/pair").status_code == 401
    assert phone.post("/api/phones/revoke-all").status_code == 401

    assert kitchen.post("/api/phones/revoke-all", headers=BEARER).json() == {"revoked": 1}
    assert phone.get("/api/grocery").status_code == 401


if __name__ == "__main__":
    for test in (test_token_required, test_phone_pairing):
        test()
        print(f"{test.__name__} ok")
