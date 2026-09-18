"""Tests for FastAPI endpoints and query caching."""

import pytest
from fastapi.testclient import TestClient

from mindthespot.api.app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health_endpoint(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["version"] == "0.1.0"
    assert "timestamp" in data


def test_list_anomalies(client):
    response = client.get("/api/v1/anomalies")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1

    first = data[0]
    assert "pool_key" in first
    assert "z_score" in first
    assert "severity" in first
    assert "pivot_count" in first
    assert first["severity"] in ["CRITICAL", "ELEVATED"]


def test_filter_anomalies_by_severity(client):
    response = client.get("/api/v1/anomalies?severity=CRITICAL")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    for item in data:
        assert item["severity"] == "CRITICAL"


def test_list_pools_and_search(client):
    response = client.get("/api/v1/pools")
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 10

    # Search for c4d
    response_search = client.get("/api/v1/pools?search=c4d")
    assert response_search.status_code == 200
    data_search = response_search.json()
    for item in data_search:
        assert "c4d" in item["machine_type"] or "c4d" in item["family"]


def test_get_pool_history(client):
    # Retrieve a valid pool from list
    pools_res = client.get("/api/v1/pools")
    pool = pools_res.json()[0]

    url = f"/api/v1/pools/{pool['region']}/{pool['zone']}/{pool['machine_type']}/history"
    res = client.get(url)
    assert res.status_code == 200
    data = res.json()
    assert data["pool_key"] == pool["pool_key"]
    assert len(data["rates"]) == 30
    assert len(data["intervals"]) >= 1
    assert "z_score" in data


def test_get_pool_history_not_found(client):
    res = client.get("/api/v1/pools/non-existent-region/zone-x/custom-8/history")
    assert res.status_code == 404


def test_get_pool_pivots(client):
    # Lookup pivots for a congested pool (e.g. europe-west4 / europe-west4-a / c4d-standard-16)
    url = "/api/v1/pivots/europe-west4/europe-west4-a/c4d-standard-16"
    res = client.get(url)
    assert res.status_code == 200
    data = res.json()
    assert "pivots" in data
    assert len(data["pivots"]) >= 1

    first_pivot = data["pivots"][0]
    assert first_pivot["preemption_savings"] > 0
    assert first_pivot["pivot_type"] in ["SAME_ZONE_PIVOT", "ZONE_PIVOT", "FAMILY_PIVOT"]
    assert "cost_savings_pct" in first_pivot
    assert "priority_rank" in first_pivot


def test_watchlist_workflow(client):
    # 1. Get existing watchlist
    get_res = client.get("/api/v1/watchlist")
    assert get_res.status_code == 200
    initial_watchlist = get_res.json()
    initial_count = len(initial_watchlist)

    # 2. Add custom entry
    payload = {
        "name": "New Team Custom Target",
        "region": "us-east4",
        "zones": ["us-east4-a"],
        "machine_types": ["c4a-standard-16"],
        "alert_threshold_z": 2.0,
    }
    post_res = client.post("/api/v1/watchlist", json=payload)
    assert post_res.status_code == 200
    assert post_res.json()["status"] == "success"

    # 3. Verify watchlist updated
    get_res2 = client.get("/api/v1/watchlist")
    assert len(get_res2.json()) == initial_count + 1

    # 4. Toggle watchlist pool
    toggle_res = client.post(
        "/api/v1/watchlist/toggle",
        json={
            "region": "us-east4",
            "zone": "us-east4-a",
            "machine_type": "c4a-standard-16",
            "is_watchlist": True,
            "custom_label": "Starred Test",
        },
    )
    assert toggle_res.status_code == 200
    assert toggle_res.json()["is_watchlist"] is True

    # 5. Remove watchlist pool via DELETE
    del_res = client.delete("/api/v1/watchlist/us-east4/us-east4-a/c4a-standard-16")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "success"

    # 6. Remove entire target via DELETE /api/v1/watchlist
    del_target_res = client.delete(
        "/api/v1/watchlist?region=us-east4&name=New+Team+Custom+Target"
    )
    assert del_target_res.status_code == 200
    assert del_target_res.json()["status"] == "success"

    # 7. Verify watchlist count returned to initial
    get_res3 = client.get("/api/v1/watchlist")
    assert len(get_res3.json()) == initial_count


def test_anomalies_price_filter(client):
    # Test anomalies with price_filter
    hike_res = client.get("/api/v1/anomalies?price_filter=HIKE")
    assert hike_res.status_code == 200
    hikes = hike_res.json()
    for h in hikes:
        assert h["price_hike_detected"] is True

    drop_res = client.get("/api/v1/anomalies?price_filter=DROP")
    assert drop_res.status_code == 200
    drops = drop_res.json()
    for d in drops:
        assert d["price_drop_detected"] is True


def test_spa_serving(tmp_path, monkeypatch):
    import mindthespot.api.app as app_module
    from mindthespot.api.app import create_app

    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    index_file = dist_dir / "index.html"
    index_file.write_text("<!doctype html><html><body>MindTheSpot Mock SPA</body></html>")

    monkeypatch.setattr(app_module, "FRONTEND_DIST_DIR", dist_dir)
    new_app = create_app()

    with TestClient(new_app) as fresh_client:
        res = fresh_client.get("/")
        assert res.status_code == 200
        assert "<!doctype html>" in res.text
        assert "MindTheSpot Mock SPA" in res.text

        # Test SPA route fallback
        spa_route_res = fresh_client.get("/explorer")
        assert spa_route_res.status_code == 200
        assert "MindTheSpot Mock SPA" in spa_route_res.text


def test_auth_me_default_dev_mode(client):
    res = client.get("/api/v1/auth/me")
    assert res.status_code == 200
    data = res.json()
    assert data["email"] == "dev@mindthespot.internal"
    assert data["is_authenticated"] is False


def test_auth_me_with_iap_headers(client):
    headers = {
        "x-goog-authenticated-user-email": "accounts.google.com:sre@jcfesantieu.altostrat.com",
        "x-goog-authenticated-user-id": "123456789",
    }
    res = client.get("/api/v1/auth/me", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["email"] == "sre@jcfesantieu.altostrat.com"
    assert data["user_id"] == "123456789"
    assert data["is_authenticated"] is True
