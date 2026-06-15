"""Two-pass (+ optional third-pass) schema extraction pipeline."""

from __future__ import annotations

import json
from pathlib import Path

import vlm
from models import Edge, EdgeType, Node, NodeType, SchemaGraph
from prompts import PROMPT_EDGES, PROMPT_NODES


def _parse_nodes(raw: list, aris_mode: bool = False) -> list[Node]:
    nodes, seen = [], set()
    for item in raw:
        if isinstance(item, str):
            label = item.strip()
            node_type = NodeType.function
        elif isinstance(item, dict):
            label = item.get("label", "").strip()
            raw_type = item.get("node_type", "function")
            try:
                node_type = NodeType(raw_type)
            except ValueError:
                node_type = NodeType.function
        else:
            continue
        if not label or label in seen:
            continue
        seen.add(label)
        nodes.append(Node(label=label, node_type=node_type))
    return nodes


def _parse_edges(raw: list, valid_labels: set[str]) -> list[Edge]:
    edges = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        raw_type = item.get("edge_type", "sequence")
        try:
            edge_type = EdgeType(raw_type)
        except ValueError:
            edge_type = EdgeType.sequence
        try:
            edge = Edge(
                from_label=item.get("from_label", "").strip(),
                to_label=item.get("to_label", "").strip(),
                edge_label=item.get("edge_label", "").strip(),
                edge_type=edge_type,
            )
        except Exception as e:
            print(f"[pipeline] Skipping malformed edge {item}: {e}")
            continue
        if edge.from_label not in valid_labels:
            print(f"[pipeline] Unknown source label '{edge.from_label}', skipping.")
            continue
        if edge.to_label not in valid_labels:
            print(f"[pipeline] Unknown target label '{edge.to_label}', skipping.")
            continue
        edges.append(edge)
    return edges


_CONTEXT_ONLY_TYPES = {NodeType.role, NodeType.system, NodeType.information, NodeType.risk}


def _find_stranded_nodes(nodes: list[Node], edges: list[Edge]) -> list[str]:
    """Labels of nodes that have incoming sequence edges but no outgoing sequence edges.

    These are interior nodes the model failed to connect forward.
    Context-only node types (roles, systems, information, risks) are excluded
    because they never appear as sequence sources.
    """
    seq_edges = [e for e in edges if e.edge_type == EdgeType.sequence]
    has_out = {e.from_label for e in seq_edges}
    has_in  = {e.to_label   for e in seq_edges}
    return [
        n.label for n in nodes
        if n.label in has_in
        and n.label not in has_out
        and n.node_type not in _CONTEXT_ONLY_TYPES
    ]


def _merge_role_assignment(
    edges: list[Edge],
    assignment: dict,
    nodes_by_label: dict[str, Node],
    valid_labels: set[str],
) -> list[Edge]:
    """
    Merge role-assignment pass results into the edge list.
    Existing performs/supports edges are replaced to avoid duplication.
    """
    # Remove existing performs/supports edges (they may be wrong from pass 2)
    seq_edges = [e for e in edges if e.edge_type == EdgeType.sequence]
    new_edges = list(seq_edges)

    seen_support = set()
    for func_label, info in assignment.items():
        if func_label not in valid_labels:
            continue
        for role_label in info.get("performed_by", []):
            role_label = role_label.strip()
            if role_label not in valid_labels:
                continue
            key = (role_label, func_label, "performs")
            if key not in seen_support:
                seen_support.add(key)
                new_edges.append(Edge(
                    from_label=role_label,
                    to_label=func_label,
                    edge_label="",
                    edge_type=EdgeType.performs,
                ))
        for sys_label in info.get("supported_by", []):
            sys_label = sys_label.strip()
            if sys_label not in valid_labels:
                continue
            key = (sys_label, func_label, "supports")
            if key not in seen_support:
                seen_support.add(key)
                new_edges.append(Edge(
                    from_label=sys_label,
                    to_label=func_label,
                    edge_label="",
                    edge_type=EdgeType.supports,
                ))
    return new_edges


def run(image_path: str | Path, diagram_type: str = "flowchart") -> SchemaGraph:
    image_path = Path(image_path)
    if not image_path.exists():
        raise FileNotFoundError(image_path)

    vlm.load_model()
    aris_mode = diagram_type == "aris"

    if aris_mode:
        from prompts_aris import (
            PROMPT_EDGES as ARIS_PROMPT_EDGES,
            PROMPT_NODES as ARIS_PROMPT_NODES,
            PROMPT_ROLE_ASSIGNMENT,
        )
        node_prompt = ARIS_PROMPT_NODES
        edge_prompt_template = ARIS_PROMPT_EDGES
    else:
        node_prompt = PROMPT_NODES
        edge_prompt_template = PROMPT_EDGES

    # Pass 1 — node extraction
    print("[pipeline] Pass 1: extracting nodes …")
    raw_nodes = vlm.generate(image_path, node_prompt)
    if not isinstance(raw_nodes, list):
        raise ValueError(f"Expected list from node extraction, got: {type(raw_nodes)}")
    nodes = _parse_nodes(raw_nodes, aris_mode=aris_mode)
    if not nodes:
        raise RuntimeError("No nodes extracted — check the image and model output.")
    print(f"[pipeline] Found {len(nodes)} nodes.")

    # Pass 2 — edge extraction
    valid_labels = {n.label for n in nodes}
    nodes_list = json.dumps([n.label for n in nodes], ensure_ascii=False)
    edge_prompt = edge_prompt_template.format(nodes_list=nodes_list)

    print("[pipeline] Pass 2: extracting edges …")
    raw_edges = vlm.generate(image_path, edge_prompt)
    if not isinstance(raw_edges, list):
        raise ValueError(f"Expected list from edge extraction, got: {type(raw_edges)}")
    edges = _parse_edges(raw_edges, valid_labels)
    print(f"[pipeline] Found {len(edges)} edges.")

    # Pass 2b (ARIS only) — repair stranded nodes
    if aris_mode:
        from prompts_aris import PROMPT_REPAIR_EDGES
        stranded = _find_stranded_nodes(nodes, edges)
        if stranded:
            print(f"[pipeline] Stranded nodes (no outgoing sequence edge): {stranded}")
            repair_prompt = PROMPT_REPAIR_EDGES.format(
                stranded_list=json.dumps(stranded, ensure_ascii=False),
                nodes_list=nodes_list,
            )
            raw_repair = vlm.generate(image_path, repair_prompt)
            if isinstance(raw_repair, list):
                already_has_out = {e.from_label for e in edges if e.edge_type == EdgeType.sequence}
                repair_edges = [
                    e for e in _parse_edges(raw_repair, valid_labels)
                    if e.from_label not in already_has_out
                ]
                edges.extend(repair_edges)
                print(f"[pipeline] Repair pass added {len(repair_edges)} edges.")
            else:
                print(f"[pipeline] Repair pass returned unexpected type {type(raw_repair)}, skipping.")
        else:
            print("[pipeline] No stranded nodes — skipping repair pass.")

    # Pass 3 (ARIS only) — role/system assignment pass
    if aris_mode:
        nodes_by_label = {n.label: n for n in nodes}
        functions = [n.label for n in nodes if n.node_type == NodeType.function]
        roles_and_systems = [
            n.label for n in nodes
            if n.node_type in (NodeType.role, NodeType.system)
        ]

        if functions and roles_and_systems:
            print("[pipeline] Pass 3: role/system assignment …")
            assignment_prompt = PROMPT_ROLE_ASSIGNMENT.format(
                functions_list=json.dumps(functions, ensure_ascii=False),
                roles_and_systems_list=json.dumps(roles_and_systems, ensure_ascii=False),
            )
            raw_assignment = vlm.generate(image_path, assignment_prompt)
            if isinstance(raw_assignment, dict):
                edges = _merge_role_assignment(edges, raw_assignment, nodes_by_label, valid_labels)
                print(f"[pipeline] After role assignment: {len(edges)} edges.")
            else:
                print(f"[pipeline] Pass 3 returned unexpected type {type(raw_assignment)}, skipping.")

    return SchemaGraph(nodes=nodes, edges=edges)


def debug_for_nodes(image_path: str | Path, diagram_type: str = "flowchart") -> None:
    """Run only the node extraction pass and print raw output."""
    image_path = Path(image_path)
    if not image_path.exists():
        raise FileNotFoundError(image_path)

    vlm.load_model()
    if diagram_type == "aris":
        from prompts_aris import PROMPT_NODES as node_prompt
    else:
        from prompts import PROMPT_NODES as node_prompt

    raw_nodes = vlm.generate(image_path, node_prompt)
    nodes = _parse_nodes(raw_nodes, aris_mode=(diagram_type == "aris"))
    print("Node extraction output:")
    print(nodes)
