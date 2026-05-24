import time
import logging
from typing import Tuple, Dict, List, Optional, Any, Set, Callable
from app.invariant_firewall import requires_invariants
from app.core_types import FieldConflictRegion

logger = logging.getLogger(__name__)

class TopologyMixin:
    def detect_communities(self):
        self._topology.detect_communities()

    @requires_invariants
    def propagate_field_regions(self) -> int:
        """Propagate instability through the unified edge field — topology canonical.

        Repulsive edges redirect pressure waves through alternative high-affinity
        routes in the edge field instead of only mutating scalar exclusions.
        """
        with self.transaction("propagation"):
            from app.failure_injector import get_injector
            get_injector().inject("propagate_field_regions")

            effects = self._topology.propagate_all()
            for key, delta in effects:
                if delta > 0:
                    current = self._instability.get_exclusion_by_key(key)
                    self._instability.set_exclusion(key, current + delta)
            count = self._topology.region_count()
            self.record_delta("topology", "propagate_all", {
                "regions": count,
                "exclusion_effects": len(effects),
            })
            return count

    @requires_invariants
    def evolve_field(self):
        """Single topology-canonical entry point for field evolution."""
        with self.transaction("field_evolution"):
            effects = self._topology.evolve_all()
            for key, delta in effects:
                if delta > 0:
                    current = self._instability.get_exclusion_by_key(key)
                    self._instability.set_exclusion(key, current + delta)

            self.aggregate_from_regions()
            self.redistribute_instability()
            self._topology.detect_communities()
            self._topology.cross_scale_pressure_flow()

            self.record_delta("topology", "evolve_field", {
                "region_count": self._topology.region_count(),
                "pressure": self.metrics.field_pressure,
            })

    @requires_invariants
    def capture_pre_allocation_field(self, tokens: list, schema_fields: list, is_noise: bool = False, domain: str = "") -> int:
        """Capture pre-allocation conflict topology from tokens with Relational Recall (Phase 31)."""
        with self.transaction("pre_allocation_capture"):
            from app.failure_injector import get_injector
            get_injector().inject("capture_pre_allocation_field")

            from app.field_laws import ROLE_EXCLUSIVITY
            captured = 0
            value_roles: Dict[str, List[str]] = {}
            for t in tokens:
                if not t.raw or not t.source_field:
                    continue
                if t.raw not in value_roles:
                    value_roles[t.raw] = []
                value_roles[t.raw].append(t.source_field)

            # Expand single tokens against schema exclusivity
            for t in tokens:
                if not t.raw:
                    continue
                src = t.source_field if t.source_field else (schema_fields[0] if schema_fields else '')
                if t.raw in value_roles and len(value_roles[t.raw]) >= 2:
                    continue
                for ra, rb in ROLE_EXCLUSIVITY:
                    if src in (ra, rb):
                        other = rb if src == ra else ra
                        fnames = set(t.source_field for t in tokens if t.source_field)
                        if other not in fnames:
                            if t.raw not in value_roles:
                                value_roles[t.raw] = []
                            if src not in value_roles[t.raw]:
                                value_roles[t.raw].append(src)
                            if other not in value_roles[t.raw]:
                                value_roles[t.raw].append(other)

            # ─── Relational Recall (Phase 31) ───
            knowledge_boost = {}
            current_idx = self.metrics.total_records_processed
            for t in tokens:
                if not t.raw:
                    continue
                boost = self._history.find_crystalline_matches(t.raw, current_record=current_idx)
                if boost > 0:
                    knowledge_boost[t.raw] = min(0.3, boost * 0.2)

            tokens_with_basins = set()

            # Create field regions from schema field pairs
            view = self._topology.get_view()
            for t in tokens:
                if not t.raw:
                    continue
                if len(schema_fields) >= 2:
                    for i in range(len(schema_fields)):
                        for j in range(i + 1, len(schema_fields)):
                            sorted_roles = tuple(sorted([schema_fields[i], schema_fields[j]]))
                            existing_region = view.find_by_token_and_roles(t.raw, sorted_roles)
                            if existing_region:
                                tokens_with_basins.add(t.raw)
                                continue

                            initial_u = 0.2 - knowledge_boost.get(t.raw, 0.0)
                            region = FieldConflictRegion(
                                competing_roles=[schema_fields[i], schema_fields[j]],
                                token=t.raw,
                                instability=max(0.01, initial_u),
                                stability_momentum=0.6 if t.raw in knowledge_boost else 0.5,
                                semantic_pressure=self.metrics.field_pressure,
                                recurrence_score=0.0,
                                topology_neighbors=schema_fields,
                                domain=domain,
                            )
                            self._topology.append_region(region)
                            captured += 1
                            tokens_with_basins.add(t.raw)

            for token_val, roles in value_roles.items():
                if len(roles) < 2:
                    continue
                for i in range(len(roles)):
                    for j in range(i + 1, len(roles)):
                        pair = (roles[i], roles[j])
                        rev_pair = (roles[j], roles[i])
                        if pair in ROLE_EXCLUSIVITY or rev_pair in ROLE_EXCLUSIVITY:
                            sorted_roles = tuple(sorted([roles[i], roles[j]]))
                            region_id = self._topology.find_region_for_mutation(token_val, sorted_roles)
                            if region_id:
                                self._topology.update_region_after_recurrence(region_id, self.metrics.field_pressure)
                                if token_val in knowledge_boost:
                                    self._topology.adjust_region_instability(region_id, -0.05)
                            else:
                                initial_u = 0.5 - knowledge_boost.get(token_val, 0.0)
                                region = FieldConflictRegion(
                                    competing_roles=[roles[i], roles[j]],
                                    token=token_val,
                                    instability=max(0.01, initial_u),
                                    stability_momentum=0.6 if token_val in knowledge_boost else 0.5,
                                    semantic_pressure=self.metrics.field_pressure,
                                    recurrence_score=self.learned_exclusions.get(sorted_roles, 0.0),
                                    topology_neighbors=list(set(roles)),
                                    domain=domain,
                                )
                                self._topology.append_region(region)
                            captured += 1
                            tokens_with_basins.add(token_val)
                            self.field_activation_count += 1

            # Create _unidentified basins for tokens not matching any schema field
            for t in tokens:
                if not t.raw:
                    continue
                if t.raw in value_roles and len(value_roles[t.raw]) >= 2:
                    continue

                if t.raw not in tokens_with_basins:
                    # ─── Predictive Basin Pre-Heating (Phase 34) ───
                    hypo_roles = ["_unidentified"]
                    from app.topological_query import get_tql_engine
                    tql = get_tql_engine(ws=self)

                    nearby = tql.find_roles_near_type(t.primary_type, radius=0.4)
                    if nearby:
                        schema_set = set(schema_fields)
                        candidates = [r["role"] for r in nearby if r["role"] not in schema_set]
                        hypo_roles.extend(candidates[:2])

                    sorted_roles = tuple(sorted(hypo_roles))
                    region_id = self._topology.find_region_for_mutation(t.raw, sorted_roles)
                    if region_id:
                        self._topology.adjust_region_recurrence(region_id, 0.1)
                    else:
                        region = FieldConflictRegion(
                            competing_roles=list(hypo_roles),
                            token=t.raw,
                            instability=0.4,
                            domain=domain,
                        )
                        self._topology.append_region(region)
                    captured += 1

            if self._topology.region_count() > 100:
                self._topology.trim(100, 50)
            return captured

    def capture_governance_snapshot(self) -> Any:
        from app.observability import GovernanceSnapshot

        role_names = tuple(self.role_manifold.keys())
        role_certainties = {r: self._manifold.get_role_certainty(r) for r in role_names}
        snapshots = tuple(self._history.topology_snapshots)
        global_energy = self.metrics.global_energy
        total_records = self.metrics.total_records_processed

        drift_data = {}
        for r in role_names:
            drifts = self._observability.get_role_drift(r)
            if drifts:
                drift_data[r] = tuple(drifts)

        topo_dict = self._topology.to_dict()
        manifold_dict = self._manifold.to_dict()
        motif_dict = self._motif.to_dict()
        history_dict = self._history.to_dict()
        telemetry = tuple(self._observability.telemetry)
        system_pressure = self.get_system_pressure()
        centrality = dict(self._topology.global_centrality)

        return GovernanceSnapshot(
            role_names=role_names,
            role_certainties=role_certainties,
            topology_snapshots=snapshots,
            global_energy=global_energy,
            total_records_processed=total_records,
            drift_log_data=drift_data,
            topology_dict=topo_dict,
            manifold_dict=manifold_dict,
            motif_dict=motif_dict,
            history_dict=history_dict,
            telemetry_stream=telemetry,
            system_pressure=system_pressure,
            topology_centrality=centrality,
        )

    @requires_invariants
    def redistribute_instability(self):
        """Govern the semantic field dynamics using adaptive policies (Phase 56)."""
        snapshot = self.capture_governance_snapshot()
        report = self._observability.get_governance_report(snapshot)
        policy = self._observability.get_stability_policy(snapshot)

        damping = policy.get("propagation_damping", 1.0)
        diversity = report.get("diversity", 1.0)
        if diversity < 0.4:
            damping *= 0.7

        flow_data = self._topology.redistribute_instability(damping=damping)

        if flow_data["total_flow"] > 0.0:
            self._energy.record_energy_flow(
                source_delta=flow_data["source_flow"],
                sink_delta=flow_data["sink_flow"],
            )

        role_stabilities = {r: self._manifold.get_role_certainty(r) for r in self.role_manifold}
        self._energy.rebalance_attractors(role_stabilities)

        global_certainty = self._manifold.get_certainty()
        if global_certainty > 0.85 and diversity < 0.5:
            self._energy.inject_diversification_entropy(scale=0.04)
        elif global_certainty > 0.7 and diversity < 0.7:
            self._energy.inject_diversification_entropy(scale=0.01)

        if policy.get("lock_escape_required", False):
            logger.warning("METASTABLE LOCK DETECTED: Forcing topology restructuring on node [%s]", self.node_id)
            self._topology.restructure_topology()
            self._energy.set_entropy(min(1.0, self.metrics.global_entropy + 0.2))

        self.emit_telemetry("governance_pulse", report)

    @requires_invariants
    def evolve_macro_state(self):
        with self.transaction("macro_evolution"):
            macro = self.compute_macro_from_meso()
            macro_pressure = 0.0

            if self._topology.region_count() > 0:
                regions = list(self._topology.iterate_regions())
                self._energy.evolve_from_regions(regions, len(regions))
                self._energy.set_exclusion_count(len(self.learned_exclusions))

            if self.meso_clusters:
                macro_instability = macro.get("avg_instability", 0.5)
                fragmentation = macro.get("fragmentation", 0.0)
                macro_pressure = macro.get("pressure", 0.0)
            else:
                macro_instability = self._topology.compute_macro_energy(self._energy.convergence)
                fragmentation = min(1.0, self._energy.global_energy / 10.0)
                macro_pressure = 0.0

                prune_threshold = macro_instability * 0.3 + self._energy.global_entropy * 0.2
                self._topology.filter_regions(lambda r: r.instability > prune_threshold or r.local_energy > 0.1)

                if fragmentation > 0.5 and macro_instability > 0.6:
                    self._energy.adjust_stability_debt(fragmentation * 0.1)

            self._topology.decay_topological_laws()
            for (r1, r2), val in self.learned_exclusions.items():
                self._topology.update_schema_patterns((r1, r2), val)
                if val > 0.9 and self._topology.topological_laws.get((r1, r2), 0) > 0.8:
                    self._topology.record_anchor((r1, r2))

            for law_key, law_val in self._topology.topological_laws.items():
                if law_val < -0.3:
                    current_excl = self._instability.get_exclusion_by_key(law_key)
                    expected_excl = min(1.0, abs(law_val) * 0.5)
                    if expected_excl > current_excl + 0.1:
                        self._instability.set_exclusion(law_key, expected_excl)

            self._topology.detect_communities()
            self._manifold.shard_manifold(self._topology.global_communities)
            self._manifold.rebalance_shards(max_shard_size=50)

            self._self_heal_topology()
            self._re_seed_unstable_roles()
            self._spawn_hypo_roles()
            self._promote_stable_hypotheses()
            self._forecast_causal_needs()

            health = self.get_cognitive_health()
            if health["system_energy"] > 8.0:
                self._observability.emit_telemetry("health_alert", {
                    "reason": "critical_energy",
                    "value": health["system_energy"]
                })
                logger.warning("COGNITIVE HEALTH ALERT: Critical Energy Level Detected")

            if health["certainty"] < 0.1:
                self._observability.emit_telemetry("health_alert", {
                    "reason": "manifold_collapse",
                    "value": health["certainty"]
                })
                logger.warning("COGNITIVE HEALTH ALERT: Manifold Resolution Collapse")

            for role in self._manifold.role_anchors:
                instability = self.metrics.schema_instability.get(role, 0.0)
                if instability > 0.8:
                    from app.semantic_allocation_engine import _infer_role_type
                    from app.semantic_inference_engine import RoleEmbeddingEngine
                    reng = RoleEmbeddingEngine()

                    seed_type = _infer_role_type(role)
                    seed_vec = reng._get_type_vector(seed_type)

                    self._manifold.set_manifold_vector(role, seed_vec)
                    self._energy.set_schema_instability(role, 0.5)

                    self._observability.emit_telemetry("immune_recovery", {
                        "role": role,
                        "reason": "high_instability_anchor"
                    })
                    logger.info(f"IMMUNE RESPONSE: Recovered corrupted anchor role [{role}]")

            if macro_pressure > 0.8 or self.metrics.stability_debt > 1.0:
                self.trigger_phase_transition()

    def _promote_stable_hypotheses(self):
        for role in self._manifold.get_manifold_roles():
            if role.startswith("hypo_"):
                instability = self._energy.get_schema_instability(role)
                if instability < 0.2:
                    clean_name = role[5:]
                    self._evolved_schema.add(clean_name)
                    vec = self._manifold.get_manifold_vector(role)
                    self._manifold.set_manifold_vector(clean_name, vec)
                    self._manifold.remove_manifold_role(role)
                    self._energy.set_schema_instability(role, 0.5)
                    logger.info(f"DYNAMIC SCHEMA EXPANSION: Promoted {role} to active role: {clean_name}")
                    self.record_delta("global", "promote_hypo", {"hypo": role, "active": clean_name})

    def trigger_phase_transition(self):
        logger.info("METASTABILITY TRIGGERED: Executing Phase Transition.")
        with self.transaction("phase_transition"):
            anchors = self._topology.anchors
            for key in list(self.learned_exclusions.keys()):
                if key not in anchors:
                    current = self._instability.get_exclusion_by_key(key)
                    self._instability.set_exclusion(key, current * 0.2)

            try:
                from app.semantic_inference_engine import RoleEmbeddingEngine
                reng = RoleEmbeddingEngine()
                anchored_roles = set()
                for a, b in anchors:
                    anchored_roles.add(a)
                    anchored_roles.add(b)

                import random
                for role in reng.manifold.keys():
                    if role not in anchored_roles:
                        noise = [random.uniform(-0.1, 0.1) for _ in range(16)]
                        self._manifold.apply_force_to_manifold(role, noise)
            except Exception as e:
                logger.warning("Manifold perturbation failed: %s", e)

            self._energy.stability_debt = 0.0
            self.record_delta("global", "phase_transition", {
                "debt_cleared": 1.0,
                "anchors_preserved": len(anchors)
            })

    def _forecast_causal_needs(self):
        current = self.metrics.total_records_processed
        forecast = self._motif.predict_future_motifs(current)
        for motif in forecast:
            logger.info(f"Causal Forecast: emerging schema motif detected: {motif}")

    def _self_heal_topology(self):
        laws = self.topological_laws
        exclusions = self.learned_exclusions
        self._topology.clear_impossible_neighborhoods()

        for key, law_val in laws.items():
            exclusion_val = exclusions.get(key, 0.0)
            if law_val > 0.4 and exclusion_val > 0.4:
                self._topology.add_impossible_neighborhood(set(key))

                if law_val >= exclusion_val:
                    current = self._instability.get_exclusion_by_key(key)
                    self._instability.set_exclusion(key, current * 0.5)
                else:
                    self._topology.set_topological_law(key, law_val * 0.5)

    def _re_seed_unstable_roles(self):
        communities = self.global_communities
        if not communities:
            for (ra, rb), cohesion in self.neighborhood_cohesion.items():
                if cohesion > 0.6:
                    communities = [{ra, rb}]
                    break
        if not communities:
            return
        for community in communities:
            stable_members = [m for m in community if self._energy.get_schema_instability(m) < 0.2]
            unstable_members = [m for m in community if self._energy.get_schema_instability(m) >= 0.5]
            if not stable_members or not unstable_members:
                continue

            consensus_vec = [0.0] * 16
            for stable in stable_members:
                vec = self._manifold.get_manifold_vector(stable) or [0.5]*16
                for i in range(16):
                    consensus_vec[i] += vec[i]
            for i in range(16):
                consensus_vec[i] /= len(stable_members)

            for role in unstable_members:
                self._manifold.blend_manifold_vector(role, consensus_vec, alpha=0.6, beta=0.4)
                self._energy.set_schema_instability(role, 0.4)

    def _spawn_hypo_roles(self):
        for region in self._topology.iterate_regions():
            if "_unidentified" in region.competing_roles and region.integrity > 0.5 and region.recurrence_score > 0.3:
                hypo_role = f"hypo_{region.token.lower().replace(' ', '_')}"
                if not self._manifold.has_manifold_role(hypo_role):
                    self._manifold.set_manifold_vector(hypo_role, [0.5] * 16)
                    self._energy.set_schema_instability(hypo_role, 0.5)

    def local_view(self, role: str) -> dict:
        from app.field_laws import ROLE_EXCLUSIVITY
        neighbors = set()
        for ra, rb in ROLE_EXCLUSIVITY:
            if role == ra:
                neighbors.add(rb)
            elif role == rb:
                neighbors.add(ra)
        local_exclusions = {
            k: v for k, v in self.learned_exclusions.items()
            if role in k
        }
        view = self._topology.get_view()
        local_regions = view.get_regions_for_role(role)
        local_compat = {
            k: v for k, v in self.role_compatibility.items()
            if k[0] == role
        }
        return {
            "role": role,
            "neighbors": list(neighbors),
            "local_exclusions": local_exclusions,
            "local_regions": len(local_regions),
            "local_compatibilities": len(local_compat),
        }

    def trace_field_evolution(self, token: str = "") -> dict:
        view = self._topology.get_view()
        chain = {
            "regions": view.region_count(),
            "activations": self.field_activation_count,
            "current_pressure": self.metrics.field_pressure,
            "topology_density": self.topology_density,
            "exclusion_count": len(self.learned_exclusions),
            "wave_events": len(self.trace_waves()),
        }
        if token:
            chain["lineage"] = [
                {
                    "roles": list(r.competing_roles),
                    "instability": round(r.instability, 3),
                    "pressure": round(r.semantic_pressure, 3),
                    "persistence": round(r.persistence, 3),
                }
                for r in view.find_by_token(token)
            ]
        elif view.region_count() > 0:
            regions_by_token: dict = {}
            for r in view.all_regions():
                regions_by_token.setdefault(r.token, []).append({
                    "roles": list(r.competing_roles),
                    "instability": round(r.instability, 3),
                    "pressure": round(r.semantic_pressure, 3),
                    "recurrence": round(r.recurrence_score, 3),
                    "persistence": round(r.persistence, 3),
                })
            chain["regions_by_token"] = regions_by_token
        return chain

    def multi_scale_regions(self) -> dict:
        view = self._topology.get_view()
        regions = view.all_regions()

        micro = [{"token": r.token, "roles": list(r.competing_roles),
                   "instability": round(r.instability, 3),
                   "convergence": round(r.local_convergence, 3)}
                  for r in regions]

        meso = []
        for cluster in view.get_meso_clusters():
            meso.append({
                "cluster_id": cluster.get("cluster_id", ""),
                "size": cluster["size"],
                "avg_instability": cluster["avg_instability"],
                "avg_convergence": cluster["avg_convergence"],
                "avg_pressure": cluster["avg_pressure"],
                "tokens": cluster["tokens"],
                "shared_roles": cluster["shared_roles"],
                "all_roles": cluster["all_roles"],
                "entropy": cluster.get("entropy", 0.0),
                "drift": cluster.get("drift", 0.0),
                "stability": cluster.get("stability", 0.5),
                "boundary_strength": cluster.get("boundary_strength", 0.5),
                "interaction_policy": cluster.get("interaction_policy", "neutral"),
            })

        macro_continents = view.get_macro_continents()
        continents_list: List[dict] = []
        macro: Dict[str, Any] = {
            "total_regions": view.region_count(),
            "meso_clusters": len(meso),
            "macro_continents": len(macro_continents),
            "field_pressure": round(self.metrics.field_pressure, 3),
            "convergence": round(self.metrics.convergence_score, 3),
            "continents": continents_list,
        }

        for continent in macro_continents:
            continents_list.append({
                "continent_id": continent.get("continent_id", ""),
                "size": continent.get("size", 0),
                "pressure": continent.get("pressure", 0.0),
                "entropy": continent.get("entropy", 0.0),
                "stability": continent.get("stability", 0.0),
                "convergence": continent.get("convergence", 0.0),
                "guidance_strength": continent.get("guidance_strength", 0.0),
                "diversity_pressure": continent.get("diversity_pressure", 0.0),
                "meso_cluster_count": len(continent.get("meso_cluster_ids", [])),
                "all_roles": continent.get("all_roles", []),
            })

        return {"micro": micro, "meso": meso, "macro": macro}

    @requires_invariants
    def observe_field_perturbation(self, output: dict, tokens: list):
        from app.instability_api import get_immune_system
        immune = get_immune_system(ws=self)

        source = output.get("source_url", "unknown_source")
        from app.field_laws import ROLE_EXCLUSIVITY
        alloc_conflicts = output.get("_allocation_conflicts", [])

        contested_roles = [fc.get("role", "") for fc in alloc_conflicts]
        if not immune.validate_perturbation(source, "various", contested_roles):
            self._observability.emit_telemetry("immunity_block", {"source": source})
            return

        for fc in alloc_conflicts:
            role = fc.get("role", "")
            peer = fc.get("peer", "")
            candidate = fc.get("candidate", "")
            if not peer:
                for ra, rb in ROLE_EXCLUSIVITY:
                    if role == ra:
                        peer = rb
                        break
                    elif role == rb:
                        peer = ra
                        break
            if candidate and peer:
                key = tuple(sorted([role, peer]))
                result = self._topology.route_contradiction(role, peer, strength=0.1)

                if result["excluded"] > 0:
                    current = self._instability.get_exclusion(role, peer)
                    self._instability.set_exclusion(key, current + result["excluded"])

                self._observability.emit_telemetry("allocation_conflict", {
                    "role": role,
                    "peer": peer,
                    "candidate": candidate,
                    "excluded": result["excluded"],
                    "redirected": result["redirected"],
                    "through_edge_field": result["through_edge_field"],
                })

        contested_tokens_in_conflicts = set()
        for fc in alloc_conflicts:
            if fc.get("candidate"):
                contested_tokens_in_conflicts.add(fc["candidate"])
        edge_field_routes = sum(
            1 for fc in alloc_conflicts
            for ra, rb in ROLE_EXCLUSIVITY
            if fc.get("role", "") in (ra, rb) and fc.get("candidate")
        )

        self._observability.emit_telemetry("contradiction_pressure", {
            "conflict_count": len(alloc_conflicts),
            "edge_field_routes": edge_field_routes,
            "contested_tokens": len(contested_tokens_in_conflicts),
            "system_pressure": round(self.metrics.field_pressure, 3),
        })

        contradiction_pressure = (len(alloc_conflicts) + edge_field_routes) / max(len(ROLE_EXCLUSIVITY), 1)
        if contradiction_pressure > 0.3 and self.metrics.field_pressure > 0.5:
            logger.info(
                "CONTRADICTION PRESSURE TRIGGER: %.3f contradiction pressure, "
                "forcing topology restructuring on node [%s]",
                contradiction_pressure, self.node_id
            )
            self._topology.restructure_topology()
            self._observability.emit_telemetry("contradiction_restructuring", {
                "contradiction_pressure": round(contradiction_pressure, 3),
                "field_pressure": round(self.metrics.field_pressure, 3),
                "conflict_count": len(alloc_conflicts),
            })

        all_exclusions = set(ROLE_EXCLUSIVITY)
        for (r1, r2), strength in self.learned_exclusions.items():
            if strength > 0.3:
                all_exclusions.add(tuple(sorted([r1, r2])))

        contested_tokens = set(contested_tokens_in_conflicts)
        view = self._topology.get_view()
        for r in view.all_regions():
            if r.token not in contested_tokens:
                contested_tokens.add(r.token)

        for token_val in contested_tokens:
            exclusive_roles = []
            for r in view.find_by_token(token_val):
                for role in r.competing_roles:
                    if role not in exclusive_roles:
                        exclusive_roles.append(role)
            sr = tuple(sorted(exclusive_roles))
            for i in range(len(sr)):
                for j in range(i + 1, len(sr)):
                    pair = tuple(sorted([sr[i], sr[j]]))
                    if pair in all_exclusions:
                        if sr[i] not in exclusive_roles:
                            exclusive_roles.append(sr[i])
                        if sr[j] not in exclusive_roles:
                            exclusive_roles.append(sr[j])
            if len(exclusive_roles) < 2:
                continue
            existing = self._topology.find_region_for_mutation(token_val, tuple(sorted(exclusive_roles)))
            if existing:
                self._topology.adjust_region_recurrence(existing, 0.05)
            else:
                new_region = FieldConflictRegion(
                    token=token_val,
                    competing_roles=list(exclusive_roles),
                    instability=0.6,
                )
                self._topology.append_region(new_region)

    @requires_invariants
    def update_scale_coupling(self) -> int:
        if self._topology.region_count() < 2:
            return 0
        pressure = self.metrics.field_pressure
        hot_neighborhoods = 0
        self._total_energy_before = sum(r.local_energy for r in self._topology.iterate_regions()) if self._topology.region_count() > 0 else 0.0
        role_map: dict = {}
        for r in self._topology.iterate_regions():
            for role in r.competing_roles:
                role_map.setdefault(role, []).append(r)
        for r in self._topology.iterate_regions():
            peers_map = {}
            for role in r.competing_roles:
                for peer in role_map.get(role, []):
                    if peer.region_id != r.region_id:
                        if r.domain and peer.domain and r.domain != peer.domain:
                            continue
                        peers_map[peer.region_id] = peer
            peers = list(peers_map.values())
            if not peers:
                continue
            n_peers = len(peers)
            avg_u = sum(p.instability for p in peers) / n_peers
            avg_c = sum(p.integrity for p in peers) / n_peers
            coupling = 0.05 * (0.5 + pressure)
            self._topology.set_region_temperature(r.region_id, r.local_temperature * 0.98 + (avg_u * 0.4) * 0.02)
            u_gap = avg_u - r.instability
            self._topology.adjust_region_instability(r.region_id, u_gap * coupling * avg_c)
            self._topology.set_region_integrity(r.region_id, r.integrity * 0.9 + avg_c * 0.1)
            avg_e = sum(p.local_energy for p in peers) / n_peers
            e_gap = avg_e - r.local_energy
            transfer = e_gap * coupling * 0.5
            self._topology.adjust_region_energy(r.region_id, transfer)
            self._topology.set_region_instability(r.region_id, r.instability + e_gap * 0.1 * coupling)
            if avg_u > 0.3:
                hot_neighborhoods += 1
        if self._topology.region_count() > 0:
            total = sum(r.local_energy for r in self._topology.iterate_regions())
            target = getattr(self, '_total_energy_before', total)
            if total > 0 and abs(total - target) / max(target, 0.001) > 0.001:
                scale = target / total
                for r in self._topology.iterate_regions():
                    self._topology.set_region_energy(r.region_id, r.local_energy * scale)
        return hot_neighborhoods

    def induce_topological_laws(self, min_success_rate: float = 0.8, min_attempts: int = 10):
        self._topology.induce_topological_laws(min_success_rate=min_success_rate, min_attempts=min_attempts)

    @requires_invariants
    def relax_topology(self, budget: Optional[Any] = None):
        """Gradual erosion of weak structures."""
        from app.runtime_budget import get_default_budget
        b = budget or get_default_budget()

        with self.transaction("relaxation"):
            self._instability.decay(rate=0.05)
            self._topology.decay_topological_laws()
            for key in list(self.role_compatibility.keys()):
                if not b.increment_cycle():
                    break
                val = self.role_compatibility.get(key, 0.5)
                if val < 0.5:
                    new_val = max(0.0, val - 0.01)
                    if new_val <= 0.0:
                        self._manifold.clear_compatibility_for_key(key)
                    else:
                        self._manifold.set_compatibility(key[0], key[1] if len(key) > 1 else "unknown", new_val)
            self._motif.prune_weak(threshold=0.1)
            pruned_regions = self._topology.garbage_collect(max_idle=20)
            pruned_roles = self._manifold.prune_manifold(self.metrics.schema_instability, threshold=0.9)
            distilled_atoms = self._topology.distill_crystalline_atoms()
            try:
                from app.semantic_inference_engine import RoleEmbeddingEngine
                reng = RoleEmbeddingEngine()

                before_manifold = {k: list(v) for k, v in self.role_manifold.items()}
                reng.relax_manifold()

                for role, v_after in self.role_manifold.items():
                    v_before = before_manifold.get(role)
                    if v_before:
                        drift = sum((a - b)**2 for a, b in zip(v_before, v_after))**0.5
                        if drift > 0.001:
                            self._observability.log_drift(role, drift)

                self._observability.emit_telemetry("manifold_relaxation", {
                    "role_count": len(self.role_manifold),
                    "active_drift": len([r for r in self.role_manifold if r in before_manifold])
                })
            except Exception as e:
                logger.warning("RoleEmbeddingEngine.relax_manifold failed in relax_topology: %s", e)
                
            self.record_delta("global", "relax_topology", {
                "budget": b.usage_report,
                "regions_pruned": pruned_regions,
                "roles_pruned": pruned_roles,
                "atoms_distilled": distilled_atoms
            })
            return 0

    @requires_invariants
    def dream(self, cycles: int = 1, budget: Optional[Any] = None) -> dict:
        dreams = []
        from app.runtime_budget import CognitiveBudget

        pressure = self.get_system_pressure()
        max_time = 500.0 / pressure
        b = budget or CognitiveBudget(max_cycles=cycles * 10, max_time_ms=max_time)

        with self.transaction("dreaming"):
            for _ in range(cycles):
                if not b.increment_cycle():
                    break

                effects = self._topology.evolve_all()
                for key, delta in effects:
                    if delta > 0:
                        current = self._instability.get_exclusion_by_key(key)
                        self._instability.set_exclusion(key, current + delta)
                self.relax_topology(budget=b)
                self.evolve_macro_state()
                for region in self._topology.iterate_regions():
                    if region.instability > 0.6 and region.recurrence_score > 0.5:
                        key = tuple(sorted(region.competing_roles))
                        current = self._instability.get_exclusion_by_key(key)
                        self._instability.set_exclusion(key, current + 0.05)
                        dreams.append({
                            "type": "exclusion",
                            "roles": region.competing_roles,
                            "token": region.token,
                        })
            self._topology.update_local_memory_from_instability()
            self.record_delta("global", "dream", {
                "requested_cycles": cycles,
                "actual_cycles": b.cycle_count,
                "dreams_count": len(dreams),
                "budget": b.usage_report
            })
        return {
            "dreams": dreams,
            "status": "converging" if not dreams else "learning",
            "budget_exhausted": b.is_exhausted
        }
