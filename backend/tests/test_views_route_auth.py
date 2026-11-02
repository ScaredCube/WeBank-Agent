def test_view_endpoints_require_authentication_before_resource_lookup(client):
    get_response = client.get("/api/views/missing-view-id")
    post_response = client.post(
        "/api/views/missing-view-id/interactions",
        json={
            "event_id": "unauthenticated-event",
            "base_revision": 1,
            "action": "set_sort",
            "value": "amount_desc",
        },
    )

    assert get_response.status_code == 401
    assert post_response.status_code == 401
