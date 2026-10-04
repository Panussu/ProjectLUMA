# ทดสอบระบบ Bookmark / Favorite Prompts ของผู้ใช้
from __future__ import annotations


def test_favorite_prompts_crud_and_isolation(backend_client, registered_user):
    headers = {"Authorization": f"Bearer {registered_user['token']}"}

    # 1. Unauthenticated access must fail
    res = backend_client.get("/api/v1/prompts/favorites")
    assert res.status_code == 401

    res = backend_client.post("/api/v1/prompts/favorites", json={"title": "Test", "prompt": "anime girl"})
    assert res.status_code == 401

    # 2. Validation errors
    # Missing title
    res = backend_client.post("/api/v1/prompts/favorites", headers=headers, json={"prompt": "valid prompt"})
    assert res.status_code == 400
    assert res.get_json()["error"]["code"] == "validation_error"

    # Empty prompt
    res = backend_client.post("/api/v1/prompts/favorites", headers=headers, json={"title": "My Title", "prompt": ""})
    assert res.status_code == 400

    # Title too long (> 100 chars)
    res = backend_client.post(
        "/api/v1/prompts/favorites",
        headers=headers,
        json={"title": "x" * 101, "prompt": "valid prompt"},
    )
    assert res.status_code == 400

    # 3. Create valid favorites
    fav1_payload = {
        "title": "Anime Cyberpunk",
        "prompt": "1girl, cyberpunk city, neon lights, rainy reflection, masterpiece",
        "negative_prompt": "low quality, blurry, text",
        "tags": ["anime", "cyberpunk", "scifi"],
    }
    res = backend_client.post("/api/v1/prompts/favorites", headers=headers, json=fav1_payload)
    assert res.status_code == 201
    fav1 = res.get_json()["favorite"]
    assert fav1["title"] == fav1_payload["title"]
    assert fav1["prompt"] == fav1_payload["prompt"]
    assert fav1["negative_prompt"] == fav1_payload["negative_prompt"]
    assert fav1["tags"] == fav1_payload["tags"]
    assert fav1["user_id"] == registered_user["user"]["id"]
    fav1_id = fav1["id"]

    fav2_payload = {
        "title": "Ghibli Meadow",
        "prompt": "lush green hills, blue sky, floating clouds, ghibli style",
        "tags": ["landscape", "ghibli"],
    }
    res = backend_client.post("/api/v1/prompts/favorites", headers=headers, json=fav2_payload)
    assert res.status_code == 201
    fav2_id = res.get_json()["favorite"]["id"]

    # 4. List favorites
    res = backend_client.get("/api/v1/prompts/favorites", headers=headers)
    assert res.status_code == 200
    data = res.get_json()
    assert data["count"] == 2
    # Sorted by created_at desc (fav2 was created after fav1)
    assert data["favorites"][0]["id"] == fav2_id
    assert data["favorites"][1]["id"] == fav1_id

    # 5. Get single favorite
    res = backend_client.get(f"/api/v1/prompts/favorites/{fav1_id}", headers=headers)
    assert res.status_code == 200
    assert res.get_json()["favorite"]["id"] == fav1_id

    # Non-existent favorite
    res = backend_client.get("/api/v1/prompts/favorites/99999", headers=headers)
    assert res.status_code == 404

    # 6. User Isolation: Second user cannot see or delete first user's favorite
    u2_res = backend_client.post(
        "/api/v1/auth/register",
        json={"username": "user2.favorite", "password": "secure-password-123"},
    )
    assert u2_res.status_code == 201
    u2_token = u2_res.get_json()["access_token"]
    u2_headers = {"Authorization": f"Bearer {u2_token}"}

    # User 2 list must be empty
    res = backend_client.get("/api/v1/prompts/favorites", headers=u2_headers)
    assert res.status_code == 200
    assert res.get_json()["count"] == 0

    # User 2 cannot get user 1's favorite
    res = backend_client.get(f"/api/v1/prompts/favorites/{fav1_id}", headers=u2_headers)
    assert res.status_code == 404

    # User 2 cannot delete user 1's favorite
    res = backend_client.delete(f"/api/v1/prompts/favorites/{fav1_id}", headers=u2_headers)
    assert res.status_code == 404

    # 7. User 1 can delete their own favorite
    res = backend_client.delete(f"/api/v1/prompts/favorites/{fav1_id}", headers=headers)
    assert res.status_code == 200
    assert res.get_json()["id"] == fav1_id

    # Deleted item is no longer accessible
    res = backend_client.get(f"/api/v1/prompts/favorites/{fav1_id}", headers=headers)
    assert res.status_code == 404

    # List count reduced to 1
    res = backend_client.get("/api/v1/prompts/favorites", headers=headers)
    assert res.status_code == 200
    assert res.get_json()["count"] == 1
    assert res.get_json()["favorites"][0]["id"] == fav2_id
