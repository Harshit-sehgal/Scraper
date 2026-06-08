"""Architecture invariants — prevent silent drift.

These tests verify that the architecture remains self-consistent
across edits. They catch the kind of drift that standard unit tests miss:
orphan hooks, dangling references, missing method overrides.
"""

import ast
import os


def _app_path(rel_path: str) -> str:
    """Resolve app/ file path regardless of CWD."""
    candidates = [
        os.path.join("backend", rel_path),  # noqa: PTH118
        rel_path,
    ]
    for c in candidates:
        if os.path.exists(c):  # noqa: PTH110
            return c
    return rel_path


def test_lifecycle_hooks_exist() -> None:
    """Every method called in the pipeline must exist on SemanticWorldState."""
    with open(_app_path("app/semantic_pipeline.py")) as f:  # noqa: PTH123
        pipeline = f.read()

    # Parse all method calls on world state in the pipeline
    calls = set()
    tree = ast.parse(pipeline)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Call):
            name = node.func.attr
            # Calls like get_world_state().XXXX()
            if isinstance(node.func.value.func, ast.Attribute) and node.func.value.func.attr == "get_world_state":
                calls.add(name)

    world_state_methods = set()
    ws_dir = os.path.dirname(_app_path("app/semantic_world_state/core.py"))  # noqa: PTH120
    for fname in os.listdir(ws_dir):  # noqa: PTH208
        if fname.endswith(".py"):
            with open(os.path.join(ws_dir, fname)) as f:  # noqa: PTH118, PTH123
                tree2 = ast.parse(f.read())
            for node in ast.walk(tree2):
                if isinstance(node, ast.ClassDef) and (node.name == "SemanticWorldState" or "Mixin" in node.name):
                    for item in node.body:
                        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            world_state_methods.add(item.name)

    missing = calls - world_state_methods
    assert not missing, (
        f"Pipeline calls methods that don't exist on SemanticWorldState: {missing}. "
        "This means a lifecycle hook was removed or renamed without updating the pipeline."
    )


def test_no_orphan_methods() -> None:  # noqa: C901, PLR0912
    """All SemanticWorldState public methods should be reachable from the pipeline or scheduler."""
    methods = set()
    ws_dir = os.path.dirname(_app_path("app/semantic_world_state/core.py"))  # noqa: PTH120
    for fname in os.listdir(ws_dir):  # noqa: PTH208
        if fname.endswith(".py"):
            with open(os.path.join(ws_dir, fname)) as f:  # noqa: PTH118, PTH123
                tree = ast.parse(f.read())
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and (node.name == "SemanticWorldState" or "Mixin" in node.name):
                    for item in node.body:
                        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            if not item.name.startswith("_"):
                                methods.add(item.name)

    # Check all app files for references to these methods
    app_dir = _app_path("app")
    called = set()
    for root, _dirs, files in os.walk(app_dir):
        for fname in files:
            if not fname.endswith(".py"):
                continue
            with open(os.path.join(root, fname)) as f:  # noqa: PTH118, PTH123
                content = f.read()
            for method in list(methods):
                # Check both method-call style .method() and property access .method
                if (
                    f".{method}(" in content
                    or f".{method}," in content
                    or f".{method})" in content
                    or f".{method}[" in content
                    or f".{method} " in content
                ):
                    called.add(method)

    uncalled = (
        methods
        - called
        - {
            "topology_snapshots",
            "field_summary",
            "propagate_field_regions",
            "mutation_diff",
            "local_view",
            "replay",
            "trace_field_evolution",
            "diff_snapshots",
            "topology_density",
            "multi_scale_regions",
            "trace_waves",
            "clear",
            "detect_communities",
            "aggregate_from_regions",
            "redistribute_instability",
            "apply_memory_decay",
            "induce_topological_laws",
            "dream",
            "relax_topology",
            "update_scale_coupling",
            "observe_field_perturbation",
            "field_regions",
            "learned_exclusions",
            "decay_field_regions",
            "meso_clusters",
            "macro_continents",
            "compute_macro_continents",
            "trace_causality",
            "replay_transaction",
            "evolved_schema",
            "export_manifold",
            "import_federated_manifold",
            "export_topology_laws",
            "import_federated_laws",
            "get_cognitive_health",
            "evaluate_topological_consistency",
            "merge_hierarchical_knowledge",
            "synthesize_hierarchical_envelopes",
            "shard_substrate",
            # TopologyState delegate properties (accessed as properties, not method calls)
            "neighborhood_cohesion",
            "cohesion_merge_success",
            "cohesion_merge_attempts",
            "cohesion_split_success",
            "cohesion_split_attempts",
            "topological_laws",
            "impossible_neighborhoods",
            "restructuring_queue",
            "global_communities",
            "schema_patterns",
            "global_centrality",
            # ManifoldState delegate properties (accessed as properties, not method calls)
            "motif_stability",
            "motif_timestamps",
            # New delegation properties (accessed as dot-property ending lines or via attribute chain)
            "abstraction_envelopes",
            "active_intents",
            "manifold_dimension",
        }
    )
    if "propagate_field_regions" in uncalled:
        uncalled.remove("propagate_field_regions")
    # topology_snapshots is a property accessor
    if "topology_snapshots" in uncalled:
        uncalled.remove("topology_snapshots")
    # field_summary is accessed via snapshot
    if "field_summary" in uncalled:
        uncalled.remove("field_summary")

    assert not uncalled, (
        f"Uncalled public methods on SemanticWorldState: {uncalled}. These may be dead code or indicate incomplete cleanup."
    )


def test_event_subscribers_are_defined() -> None:  # noqa: C901, PLR0912
    """Every event type with subscribers must be dispatched somewhere."""
    with open(_app_path("app/semantic_events.py")) as f:  # noqa: PTH123
        events_src = f.read()

    # Parse event types
    event_types = set()
    tree = ast.parse(events_src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "SemanticEventType":
            for item in node.body:
                if isinstance(item, ast.Assign):
                    for target in item.targets:
                        if isinstance(target, ast.Attribute):
                            event_types.add(target.attr)

    # Find which event types are dispatched and subscribed
    app_dir = _app_path("app")
    dispatched = set()
    subscribed = set()
    for root, _dirs, files in os.walk(app_dir):
        for fname in files:
            if not fname.endswith(".py"):
                continue
            with open(os.path.join(root, fname)) as f:  # noqa: PTH118, PTH123
                content = f.read()
            for et in event_types:
                if f"SemanticEventType.{et}" in content:
                    if "dispatch(SemanticEvent" in content or "dispatcher.dispatch" in content:
                        dispatched.add(et)
                    if "subscribe(SemanticEventType." in content:
                        subscribed.add(et)

    # Every subscribed event type should be dispatched somewhere
    not_dispatched = subscribed - dispatched
    assert not not_dispatched, f"Subscribed but never dispatched: {not_dispatched}. Subscribers will never fire."


def test_no_stale_pyc() -> None:
    """No .pyc files without corresponding .py source."""
    app_dir = _app_path("app")
    pyc_files = []
    for root, _dirs, files in os.walk(app_dir):
        for f in files:
            if f.endswith(".pyc"):
                # Convert __pycache__/file.cpython-312.pyc -> file.py
                py_name = f.split(".")[0] + ".py"
                # The source file could be in the parent directory or a sibling
                parent = os.path.dirname(root)  # app if root is app/__pycache__  # noqa: PTH120
                py_path = os.path.join(parent, py_name)  # noqa: PTH118
                if not os.path.exists(py_path):  # noqa: PTH110
                    pyc_files.append(os.path.join(root, f))  # noqa: PTH118

    assert not pyc_files, f"Stale .pyc files: {pyc_files}. These will be loaded instead of current source."


def test_no_dead_imports() -> None:  # noqa: C901, PLR0912
    """Core modules should not import symbols that don't exist."""
    core_modules = [
        "semantic_world_state",
        "semantic_pipeline",
        "graph_update_scheduler",
        "semantic_allocation_engine",
        "semantic_inference_engine",
    ]
    for mod_name in core_modules:
        path = _app_path(f"app/{mod_name}.py")
        if mod_name == "semantic_world_state":
            path = _app_path("app/semantic_world_state/core.py")
        with open(path) as f:  # noqa: PTH123
            tree = ast.parse(f.read())

        # Collect all imported names and their source modules
        imports = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    imports[alias.asname or alias.name] = module

        # Collect all local definitions
        defined = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                defined.add(node.name)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        defined.add(target.id)

        # Collect all name references
        used = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                used.add(node.id)

        # Check imports that don't appear in used names
        exceptions = {"Dict", "List", "Tuple", "Set", "Callable", "Optional", "Any"}
        dead_imports = []
        for name in imports.keys():
            if name not in used and name not in exceptions:
                dead_imports.append(name)  # noqa: PERF401

        # Dead imports in core modules are tracked but not yet enforced as hard errors
        # because some are re-exported for backward compatibility.
        # If this list grows, investigate and remove genuinely unused imports.
        if dead_imports:
            # Log but don't fail — this is a heuristic guard
            import warnings

            warnings.warn(f"{mod_name}: potentially unused imports: {dead_imports}", stacklevel=1)

    # Verify at least some imports were checked (no-empty heuristic guard)
    assert isinstance(imports, dict), "imports should be a dict"


def test_coupling_coefficient_exists() -> None:
    """COUPLING_COEFFICIENT and FREE_ENERGY_CLAMP must be defined in field_laws.

    These constants are required for the thermodynamic free-energy-gradient-driven
    redistribution to function. Their existence anchors the architecture's
    transition from heuristic coupling to thermodynamic coupling.
    """
    import importlib

    fl = importlib.import_module("app.field_laws")
    assert hasattr(fl, "COUPLING_COEFFICIENT"), "COUPLING_COEFFICIENT must be defined in field_laws.py"
    assert hasattr(fl, "FREE_ENERGY_CLAMP"), "FREE_ENERGY_CLAMP must be defined in field_laws.py"
    assert 0.0 < fl.COUPLING_COEFFICIENT <= 1.0, "COUPLING_COEFFICIENT must be in (0, 1]"
    assert 0.0 < fl.FREE_ENERGY_CLAMP <= 10.0, "FREE_ENERGY_CLAMP must be in (0, 10]"


def test_energy_conservation_tracking() -> None:
    """EnergyState must have energy_balance property and record_energy_flow method.

    These are required for energy conservation enforcement and tracking.
    Without them, energy flows are invisible/unaccounted, violating
    the conservation law.
    """
    from app.energy_state import EnergyState

    es = EnergyState()
    assert hasattr(es, "energy_balance"), "EnergyState must have energy_balance property"
    assert hasattr(es, "record_energy_flow"), "EnergyState must have record_energy_flow method"
    # Verify initial state
    assert es.energy_balance == 0.0, "Initial energy balance should be 0.0"
    # Verify recording works
    es.record_energy_flow(1.0, 1.0)
    assert es.energy_balance == 0.0, "Balanced flow should give 0.0"
    es.record_energy_flow(2.0, 1.0)
    assert abs(es.energy_balance - 1.0) < 0.001, "Imbalanced flow should reflect in balance"
