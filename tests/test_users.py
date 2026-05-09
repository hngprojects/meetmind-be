import pytest
from httpx import AsyncClient

from app.models.user import User
from app.services.auth import AuthService

ME_URL = "/api/v1/users/me"


async def test_get_me_returns_200_with_valid_bearer_token(client: AsyncClient, db_session):
    user = User(
        email="me@example.com",
        name="Test User",
        is_verified=True,
    )
    db_session.add(user)
    await db_session.commit()

    token = await AuthService.create_access_token(user)

    response = await client.get(ME_URL, headers={"Authorization": f"Bearer {token}"})

    body = response.json()
    assert response.status_code == 200
    assert body["success"] is True
    assert body["data"]["email"] == "me@example.com"
    assert body["data"]["name"] == "Test User"
    assert "id" in body["data"]


async def test_get_me_returns_401_with_no_token(client: AsyncClient):
    response = await client.get(ME_URL)

    body = response.json()
    assert response.status_code == 401
    assert body["success"] is False
