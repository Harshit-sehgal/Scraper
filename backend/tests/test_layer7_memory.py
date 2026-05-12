def test_layer7_semantic_memory():
    from app.semantic_pipeline import run_pipeline
    from app.semantic_boundary_engine import get_boundary_engine
    import os
    
    # Run pipeline to generate some memory
    records = [{"company": "Google", "price": "100"}]
    schema = ["company_name", "price"]
    
    os.environ['SEMANTIC_BOUNDARY_CACHE_PATH'] = '/tmp/test_boundary_cache.json'
    if os.path.exists('/tmp/test_boundary_cache.json'):
        os.remove('/tmp/test_boundary_cache.json')
        
    run_pipeline(records, schema)
    
    be = get_boundary_engine()
    assert be.motif_learner.total_records > 0
    assert os.path.exists('/tmp/test_boundary_cache.json')
    
    # Reset engine and load
    be.motif_learner.total_records = 0
    be.motif_learner.motif_counts.clear()
    
    be.load_from_file('/tmp/test_boundary_cache.json')
    assert be.motif_learner.total_records > 0
