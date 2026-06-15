"""Convert a SchemaGraph to a compact, LLM-readable text representation."""

from collections import defaultdict

from models import EdgeType, NodeType, SchemaGraph


def to_llm_text(schema: SchemaGraph) -> str:
    node_types = {n.label: n.node_type for n in schema.nodes}

    # Determine if this is an ARIS diagram (any typed node beyond generic function)
    aris_types = {NodeType.event, NodeType.role, NodeType.system, NodeType.gateway,
                  NodeType.risk, NodeType.information}
    is_aris = any(t in aris_types for t in node_types.values())

    if is_aris:
        return _format_aris(schema, node_types)
    return _format_flowchart(schema)


# ── ARIS formatter ────────────────────────────────────────────────────────────

def _format_aris(schema: SchemaGraph, node_types: dict) -> str:
    seq_edges = [e for e in schema.edges if e.edge_type == EdgeType.sequence]
    support_edges = [e for e in schema.edges if e.edge_type != EdgeType.sequence]

    out_seq   = defaultdict(list)
    in_seq    = defaultdict(list)
    for e in seq_edges:
        out_seq[e.from_label].append(e)
        in_seq[e.to_label].append(e)

    performs_map  = defaultdict(list)   # function → [role, ...]
    supports_map  = defaultdict(list)   # function → [system, ...]
    for e in support_edges:
        if e.edge_type == EdgeType.performs:
            performs_map[e.to_label].append(e.from_label)
        elif e.edge_type == EdgeType.supports:
            supports_map[e.to_label].append(e.from_label)

    lines = ["=== ARIS EPC ===", ""]

    # ── Section A: Process flow ──────────────────────────────────────────────
    lines.append("SECTION A — PROCESS FLOW (sequence edges only):")
    lines.append("")

    roots = [n.label for n in schema.nodes
             if not in_seq[n.label]
             and node_types.get(n.label) in (NodeType.event, NodeType.function, NodeType.gateway)]

    visited_flow: set[str] = set()
    for root in roots:
        _render_flow(root, out_seq, node_types, lines, visited_flow, depth=0)

    if not roots:
        lines.append("  (no sequence edges found)")

    # ── Section B: Function context ──────────────────────────────────────────
    lines += ["", "SECTION B — FUNCTION CONTEXT (roles and systems per function):"]
    lines.append("")
    functions = [n.label for n in schema.nodes if node_types.get(n.label) == NodeType.function]
    if functions:
        for func in functions:
            lines.append(f"FUNCTION: {func}")
            roles   = performs_map.get(func, [])
            systems = supports_map.get(func, [])
            if roles:
                lines.append(f"  Performed by: {', '.join(roles)}")
            if systems:
                lines.append(f"  Supported by: {', '.join(systems)}")
            if not roles and not systems:
                lines.append("  (no role/system associations found)")
            lines.append("")
    else:
        lines.append("  (no functions found)")

    return "\n".join(lines)


def _render_flow(
    label: str,
    out_seq: dict,
    node_types: dict,
    lines: list,
    visited: set,
    depth: int,
) -> None:
    if label in visited:
        lines.append(f"{'  ' * depth}[loop → {label}]")
        return
    if depth > 60:
        return
    visited.add(label)

    ntype = node_types.get(label, NodeType.function)
    prefix = "  " * depth

    if ntype == NodeType.event:
        lines.append(f"{prefix}EVENT: {label}")
    elif ntype == NodeType.function:
        lines.append(f"{prefix}FUNCTION: {label}")
    elif ntype == NodeType.gateway:
        gtype = _gateway_symbol(label)
        lines.append(f"{prefix}GATEWAY [{gtype}]:")
    else:
        lines.append(f"{prefix}{label}")

    targets = out_seq.get(label, [])
    if len(targets) == 1:
        lines.append(f"{'  ' * depth}  |")
        _render_flow(targets[0].to_label, out_seq, node_types, lines, visited, depth)
    elif len(targets) > 1:
        for i, e in enumerate(targets, 1):
            branch_tag = f" [{e.edge_label}]" if e.edge_label else ""
            lines.append(f"{'  ' * (depth + 1)}BRANCH {i}{branch_tag} -->")
            _render_flow(e.to_label, out_seq, node_types, lines, visited, depth + 2)


def _gateway_symbol(label: str) -> str:
    label_upper = label.upper()
    if "XOR" in label_upper or "×" in label:
        return "XOR"
    if "AND" in label_upper or "+" in label:
        return "AND"
    if "OR" in label_upper or "∨" in label:
        return "OR"
    return label


# ── Generic flowchart formatter ───────────────────────────────────────────────

def _format_flowchart(schema: SchemaGraph) -> str:
    all_labels = [n.label for n in schema.nodes]

    out_edges = defaultdict(list)
    in_edges  = defaultdict(list)
    for e in schema.edges:
        out_edges[e.from_label].append((e.edge_label, e.to_label))
        in_edges[e.to_label].append((e.edge_label, e.from_label))

    lines = ["=== FLOWCHART ===", ""]
    lines.append(f"NODES ({len(schema.nodes)}):")
    for label in all_labels:
        n_in  = len(in_edges[label])
        n_out = len(out_edges[label])
        role  = _node_role(n_in, n_out)
        lines.append(f"  - {label}  ({n_in} in, {n_out} out){role}")

    lines += ["", f"CONNECTIONS ({len(schema.edges)}):"]
    for e in schema.edges:
        arrow = f"--[{e.edge_label}]-->" if e.edge_label else "-->"
        lines.append(f"  {e.from_label} {arrow} {e.to_label}")

    lines += ["", "NODE CONNECTION DETAIL:"]
    for label in all_labels:
        n_in  = len(in_edges[label])
        n_out = len(out_edges[label])
        role  = _node_role(n_in, n_out)
        lines.append(f"  {label}{role}")

        ins = in_edges[label]
        if ins:
            for edge_lbl, src in ins:
                tag = f" [{edge_lbl}]" if edge_lbl else ""
                lines.append(f"      IN:  {src}{tag}")
        else:
            lines.append("      IN:  (none — entry point)")

        outs = out_edges[label]
        if outs:
            for edge_lbl, tgt in outs:
                arrow = f"--[{edge_lbl}]-->" if edge_lbl else "-->"
                lines.append(f"      OUT: {arrow} {tgt}")
        else:
            lines.append("      OUT: (none — terminal)")

    roots = [label for label in all_labels if not in_edges[label]]
    if roots:
        lines += ["", "FLOW PATH (from entry nodes):"]
        for root in roots:
            path = _trace_path(root, out_edges, visited=set())
            lines.append("  " + path)

    lines.append("")
    return "\n".join(lines)


def _node_role(n_in: int, n_out: int) -> str:
    if n_in == 0:
        return "  [ENTRY]"
    if n_out == 0:
        return "  [TERMINAL]"
    if n_out > 1:
        return f"  [DECISION: {n_out} branches]"
    if n_in > 1:
        return f"  [MERGE: {n_in} inputs]"
    return ""


def _trace_path(label: str, out_edges: dict, visited: set, depth: int = 0) -> str:
    if label in visited or depth > 50:
        return f"[loop: {label}]"
    visited = visited | {label}
    targets = out_edges.get(label, [])

    if not targets:
        return label
    if len(targets) == 1:
        edge_lbl, nxt = targets[0]
        connector = f" --[{edge_lbl}]--> " if edge_lbl else " --> "
        return label + connector + _trace_path(nxt, out_edges, visited, depth + 1)

    indent = "  " * (depth + 1)
    branches = []
    for edge_lbl, nxt in targets:
        connector = f"--[{edge_lbl}]--> " if edge_lbl else "--> "
        branches.append(indent + connector + _trace_path(nxt, out_edges, visited, depth + 1))
    return label + "\n" + "\n".join(branches)
