import pytest
from fastapi.testclient import TestClient

from synthia.main import app


def test_smoke():
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"status": "OK"}