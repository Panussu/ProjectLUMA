# ทดสอบระบบ Bookmark / Favorite Prompts ของผู้ใช้
from __future__ import annotations

from luma_backend.extensions import db
from luma_backend.models import Job, JobAIOptions


def test_favorite_prompts_crud_and_isolation(backend_client, registered_user):
    headers = {"Authorization": f"Bearer {registered_user['token']}"}

    # 1. Unauthenticated access must fail
    res = backend_client.get("/api/v1/prompts/favorites")
    assert res.status_code == 401

    res = backend_client.post("/api/v1/prompts/favorites", json={"title": "Test", "prompt": "anime girl"})
    assert res.status_code == 401

    # 2. Validation errors
    res = backend_client.post("/api/v1/prompts/favorites", headers=headers, json={"prompt": "valid prompt"})
    assert res.status_code == 400
    assert res.get_json()["error"]["code"] == "validation_error"

    res = backend_client.post("/api/v1/prompts/favorites", headers=headers, json={"title": "My Title", "prompt": ""})
    assert res.status_code == 400

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

    # 4. List favorites and filtering
    res = backend_client.get("/api/v1/prompts/favorites", headers=headers)
    assert res.status_code == 200
    data = res.get_json()
    assert data["count"] == 2
    assert data["favorites"][0]["id"] == fav2_id
    assert data["favorites"][1]["id"] == fav1_id

    # Filter by query ?q=ghibli
    res_q = backend_client.get("/api/v1/prompts/favorites?q=ghibli", headers=headers)
    assert res_q.status_code == 200
    assert res_q.get_json()["count"] == 1
    assert res_q.get_json()["favorites"][0]["id"] == fav2_id

    # Filter by tag ?tag=scifi
    res_t = backend_client.get("/api/v1/prompts/favorites?tag=scifi", headers=headers)
    assert res_t.status_code == 200
    assert res_t.get_json()["count"] == 1
    assert res_t.get_json()["favorites"][0]["id"] == fav1_id

    # 5. Get and Update single favorite (PUT)
    res = backend_client.get(f"/api/v1/prompts/favorites/{fav1_id}", headers=headers)
    assert res.status_code == 200
    assert res.get_json()["favorite"]["id"] == fav1_id

    res_put = backend_client.put(
        f"/api/v1/prompts/favorites/{fav1_id}",
        headers=headers,
        json={"title": "Updated Cyberpunk Neon", "tags": ["anime", "neon"]},
    )
    assert res_put.status_code == 200
    assert res_put.get_json()["favorite"]["title"] == "Updated Cyberpunk Neon"
    assert res_put.get_json()["favorite"]["tags"] == ["anime", "neon"]

    # 6. User Isolation: Second user cannot see, edit, or delete first user's favorite
    u2_res = backend_client.post(
        "/api/v1/auth/register",
        json={"username": "user2.favorite", "password": "secure-password-123"},
    )
    assert u2_res.status_code == 201
    u2_token = u2_res.get_json()["access_token"]
    u2_headers = {"Authorization": f"Bearer {u2_token}"}

    res = backend_client.get(f"/api/v1/prompts/favorites/{fav1_id}", headers=u2_headers)
    assert res.status_code == 404

    res = backend_client.put(f"/api/v1/prompts/favorites/{fav1_id}", headers=u2_headers, json={"title": "Hacked"})
    assert res.status_code == 404

    res = backend_client.delete(f"/api/v1/prompts/favorites/{fav1_id}", headers=u2_headers)
    assert res.status_code == 404

    # 7. User 1 can delete their own favorite
    res = backend_client.delete(f"/api/v1/prompts/favorites/{fav1_id}", headers=headers)
    assert res.status_code == 200
    assert res.get_json()["id"] == fav1_id

    res = backend_client.get(f"/api/v1/prompts/favorites/{fav1_id}", headers=headers)
    assert res.status_code == 404


def test_bookmark_from_job_id(backend_client, backend_app, registered_user):
    headers = {"Authorization": f"Bearer {registered_user['token']}"}

    # Create a job in database
    with backend_app.app_context():
        job = Job(
            user_id=registered_user["user"]["id"],
            type="generate",
            prompt="mystical forest glowing mushrooms",
            negative_prompt="dark, ugly",
            status="completed",
            ai_options=JobAIOptions(request_options={}),
        )
        db.session.add(job)
        db.session.commit()
        job_id = job.id

    # Bookmark directly from job_id (e.g. Star button on Frontend)
    res = backend_client.post(
        "/api/v1/prompts/favorites",
        headers=headers,
        json={"job_id": job_id, "tags": ["fantasy", "nature"]},
    )
    assert res.status_code == 201
    fav = res.get_json()["favorite"]
    assert fav["prompt"] == "mystical forest glowing mushrooms"
    assert fav["negative_prompt"] == "dark, ugly"
    assert fav["tags"] == ["fantasy", "nature"]
    assert "mystical forest" in fav["title"]
