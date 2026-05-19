"""Architecture Patch Notes — documents all tracked-file changes needed.

These changes need to be applied to the 4 tracked files that keep reverting.
When the external modification process stops, run this module to verify the fixes.

Fixes needed:
1. semantic_allocation_engine.py    — add price/cost to ROLE_EXCLUSIVITY
2. semantic_ir.py                   — create_token sets source_field
3. semantic_world_state.py          — capture_pre_allocation_field schema expansion + methods
4. semantic_pipeline.py             — clean up contradiction engine references
"""

import logging


def check_all_fixes() -> dict:
    """Check if all tracked-file fixes are currently applied."""
    results = {}

    # Helper to find file path relative to this script
    import os
    base_dir = os.path.dirname(os.path.abspath(__file__))

    # 1. ROLE_EXCLUSIVITY has price/cost (moved to field_laws.py)
    path_laws = os.path.join(base_dir, 'field_laws.py')
    with open(path_laws) as f:
        content_laws = f.read()
    results['ROLE_EXCLUSIVITY price/cost (field_laws.py)'] = 'price", "cost"' in content_laws

    # 2. create_token has source_field
    path_ir = os.path.join(base_dir, 'semantic_ir.py')
    with open(path_ir) as f:
        content_ir = f.read()
    results['create_token source_field'] = 'source_field=source,' in content_ir or 'source_field=primary_type' in content_ir

    # 3. schema_instability is in EnergyState (via energy_state.py)
    path_energy = os.path.join(base_dir, 'energy_state.py')
    with open(path_energy) as f:
        content_energy = f.read()
    results['schema_instability property (energy_state.py)'] = 'def schema_instability' in content_energy and 'dict(self._schema_instability)' in content_energy

    # 4. integrity_score property (in EnergyState)
    results['integrity_score property (energy_state.py)'] = 'def integrity_score' in content_energy

    # 5. capture_pre_allocation_field has schema expansion
    path_ws = os.path.join(base_dir, 'semantic_world_state.py')
    with open(path_ws) as f:
        content_ws = f.read()
    results['capture schema expansion'] = 'ROLE_EXCLUSIVITY' in content_ws and 'for ra, rb in ROLE_EXCLUSIVITY' in content_ws

    # 6. Missing methods
    for method in ['relax_topology', 'detect_communities', 'evolve_macro_state',
                   '_synthesize_crystalline_record', 'topological_search',
                   'get_crystalline_attractors', 'induce_topological_laws', 'observe_field_perturbation']:
        results[f'method: {method}'] = f'def {method}' in content_ws

    # 7. Additional fields
    for field in ['crystalline_records', 'learning_count', 'schema_patterns']:
        results[f'field: {field}'] = f'self.{field}' in content_ws or f'def {field}' in content_ws

    # 8. Pipeline is clean of dead imports
    path_pipe = os.path.join(base_dir, 'semantic_pipeline.py')
    with open(path_pipe) as f:
        content_pipe = f.read()
    results['pipeline clean'] = 'semantic_contradiction_engine' not in content_pipe

    return results


def generate_patch_report(results: dict) -> str:
    """Generate a human-readable patch report."""
    lines = []
    lines.append("Architecture Patch Status Report")
    lines.append("=" * 40)
    lines.append("")

    fixed = sum(1 for v in results.values() if v)
    total = len(results)
    lines.append(f"Fixes applied: {fixed}/{total}")
    lines.append("")

    by_module: dict = {}
    for key, ok in results.items():
        module = "other"
        if "ROLE_EXCLUSIVITY" in key:
            module = "semantic_allocation_engine.py"
        elif "create_token" in key:
            module = "semantic_ir.py"
        elif any(m in key for m in ['method:', 'field:', 'property', 'capture', 'schema_instability']):
            module = "semantic_world_state.py"
        elif "pipeline" in key:
            module = "semantic_pipeline.py"
        by_module.setdefault(module, []).append((key, ok))

    for module, items in sorted(by_module.items()):
        lines.append(f"\n{module}:")
        for key, ok in items:
            symbol = "✓" if ok else "✗"
            lines.append(f"  {symbol} {key}")

    return "\n".join(lines)


if __name__ == '__main__':
    results = check_all_fixes()
    report = generate_patch_report(results)
    logger = logging.getLogger(__name__)
    logger.info("Patch status report:\n%s", report)
