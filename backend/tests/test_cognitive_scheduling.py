import time
from app.semantic_world_state import get_world_state
from app.semantic_os import get_semantic_os

def test_priority_ordering():
    sos = get_semantic_os()
    sos.ws.clear()
    
    # 1. Schedule tasks in reverse priority order
    results = []
    
    def handler(label):
        results.append(label)
        
    sos.schedule_task("t_bg", "background", handler, "background")
    sos.schedule_task("t_crit", "critical", handler, "critical")
    sos.schedule_task("t_urg", "urgent", handler, "urgent")
    
    # 2. Process
    sos.process_queue()
    
    # 3. Verify ordering (CRIT -> URG -> BG)
    assert results == ["critical", "urgent", "background"]

def test_budgeted_execution():
    sos = get_semantic_os()
    sos.ws.clear()
    
    results = []
    def slow_handler(label):
        time.sleep(0.05) # 50ms
        results.append(label)
        
    # Schedule two slow tasks
    sos.schedule_task("s1", "normal", slow_handler, "s1")
    sos.schedule_task("s2", "normal", slow_handler, "s2")
    
    # 2. Process with tight budget (40ms)
    # Only one should complete because each takes 50ms
    completed = sos.process_queue(budget_ms=40.0)
    
    assert completed == 1
    assert len(results) == 1
    assert "s1" in results

def test_pressure_preemption():
    ws = get_world_state()
    ws.clear()
    sos = get_semantic_os()
    
    # 1. Setup High Pressure
    ws._energy.set_energy(10.0)
    # Fragment communities to increase pressure
    ws._topology._communities = [{"a"}, {"b"}, {"c"}, {"d"}, {"e"}]
    pressure = ws.get_system_pressure()
    
    results = []
    def handler(label):
        results.append(label)
        
    # 2. Schedule Critical and Background tasks
    sos.schedule_task("t_crit", "critical", handler, "critical")
    sos.schedule_task("t_bg", "background", handler, "background")
    
    # Force the scheduler to pre-empt at this pressure level for the test
    # (The default is 1.8, but we'll use the current pressure + a bit less)
    original_threshold = sos.ws._scheduler._preemption_threshold if hasattr(sos.ws._scheduler, '_preemption_threshold') else 1.8
    sos.ws._scheduler._preemption_threshold = pressure - 0.1
    
    try:
        # 3. Process
        sos.process_queue()
        
        # 4. Verify BG task was pre-empted (only critical ran)
        assert "critical" in results
        assert "background" not in results
    finally:
        sos.ws._scheduler._preemption_threshold = original_threshold
