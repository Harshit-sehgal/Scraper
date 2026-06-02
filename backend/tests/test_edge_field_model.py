from app.semantic_world_state import SemanticWorldState


def test_unified_edge_field_combines_topology_forces():
    ws = SemanticWorldState()
    ws.clear()

    with ws.transaction("edge_field_setup"):
        ws._topology.add(["origin", "destination"], "route", instability=0.4)
        ws._topology.set_neighborhood_cohesion(("origin", "destination"), 0.7)
        ws._topology.set_topological_law(("origin", "destination"), 0.5)
        ws._topology.set_topological_law(("price", "date"), -0.8)
        ws._topology.add_impossible_neighborhood({"price", "date"})

    edges = {(edge.source, edge.target): edge for edge in ws.get_topology_view().get_edge_fields()}

    route_edge = edges[("destination", "origin")]
    assert route_edge.semantics == "attractive"
    assert route_edge.affinity > route_edge.repulsion
    assert route_edge.route_strength > 0.0
    assert route_edge.uncertainty == 0.4

    contradiction_edge = edges[("date", "price")]
    assert contradiction_edge.semantics == "repulsive"
    assert contradiction_edge.repulsion == 1.0
    assert contradiction_edge.route_strength == 0.0
    assert contradiction_edge.impossible is True


def test_negative_topological_laws_survive_decay_and_merge():
    local = SemanticWorldState(node_id="edge_local")
    remote = SemanticWorldState(node_id="edge_remote")
    local.clear()
    remote.clear()

    with local.transaction("local_repulsion"):
        local._topology.set_topological_law(("a", "b"), -0.8)
        local._topology.decay_topological_laws()
    assert local.topological_laws[("a", "b")] < 0.0

    with remote.transaction("remote_repulsion"):
        remote._topology.set_topological_law(("a", "b"), -0.9)
    local.merge_state(remote.to_dict())
    assert local.topological_laws[("a", "b")] == -0.9
