def test_layer7_semantic_memory() -> None:
    import os

    from app.semantic_boundary_engine import get_boundary_engine
    from app.semantic_pipeline import run_pipeline

    # Run pipeline to generate some memory
    records = [{"company": "Google", "price": "100"}]
    schema = ["company_name", "price"]

    os.environ["SEMANTIC_STATE_PATH"] = "/tmp/test_semantic_state.json"
    if os.path.exists("/tmp/test_semantic_state.json"):
        os.remove("/tmp/test_semantic_state.json")

    run_pipeline(records, schema)

    be = get_boundary_engine()
    assert be.motif_learner.total_records > 0

    # State is now saved at job level; explicitly save for this test
    from app.semantic_persistence import clear_semantic_state, load_semantic_state, save_semantic_state

    save_semantic_state()

    assert os.path.exists("/tmp/test_semantic_state.json")

    # Reset engine and load
    clear_semantic_state(clear_file=False)

    load_semantic_state()
    assert be.motif_learner.total_records > 0
