

def test_metrics_endpoint(client):
    r = client.get("/metrics")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    
    text = r.text
    # Verify that all key custom metrics are present
    assert "dataforge_jobs_total" in text
    assert "dataforge_recycle_bin_total" in text
    assert "dataforge_backend_collection_ok" in text
    assert "dataforge_queue_collection_ok" in text
    assert "dataforge_metrics_collection_error_total" in text
