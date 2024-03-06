# Description: Test the web application

from fastapi.testclient import TestClient
from espp2.web.main import app

client = TestClient(app)


def test_read_main():
    response = client.get("/")
    assert response.status_code == 200
