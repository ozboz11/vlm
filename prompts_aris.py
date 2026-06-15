PROMPT_NODES = """\
You are an expert ARIS EPC diagram analyst. Examine this ARIS EPC image carefully.

STEP 1 — IDENTIFY ALL VISUAL ELEMENTS:
Scan the entire image from TOP to BOTTOM, LEFT to RIGHT.
Find EVERY shape/element and classify it by its visual appearance:

NODE TYPES and their visual signatures:
  • event       — Pink or magenta HEXAGON shape with a flag/bookmark icon
  • function    — Green RECTANGLE with fast-forward (>>) arrows icon
  • system      — Blue RECTANGLE with a screen/monitor icon
  • role        — Orange RECTANGLE with a person/user icon
  • gateway     — A SMALL CIRCLE (NOT a rectangle) containing ONLY one symbol:
                    × = XOR gateway (exclusive split or join)
                    + = AND gateway (parallel split or join)
                    ∨ = OR  gateway (inclusive split or join)
                  Gateways have NO text label — only the symbol inside the circle.
                  They are ROUTING nodes: the flow enters and BRANCHES out from them.
                  DO NOT confuse them with any rectangular shape.
  • risk        — Red RECTANGLE with a warning triangle icon
  • information — Gray RECTANGLE with a document/page icon

STEP 2 — RECORD EACH ELEMENT:
For each element, record:
  - label     : the EXACT text inside the shape (join multi-line text with a space)
  - node_type : one of: event, function, system, role, gateway, risk, information

For gateways (circles with a symbol), use the symbol as the label: "XOR_1", "AND_1", or "OR_1".
If multiple gateways of the same type exist, number them: XOR_1, XOR_2, etc.

CRITICAL RULES:
  • A shape appearing multiple times (e.g., "Recruiting Manager" appears 4 times) counts as
    ONE unique node — list it only once.
  • Do NOT skip any shape, no matter how many times it appears.
  • Copy label text exactly as written — do not paraphrase.

Reply with ONLY a valid JSON array — no prose, no markdown fences:
[{"label": "Application data recorded", "node_type": "event"}, ...]
"""

PROMPT_EDGES = """\
You are an expert ARIS EPC diagram analyst. The following nodes were identified in this diagram:
{nodes_list}

Now identify EVERY directed arrow (edge) in the image.

ARIS EPC has TWO fundamentally different arrow types:

1. SEQUENCE edges (process flow — typically VERTICAL arrows):
   Connect: event → function, function → gateway, gateway → event
   edge_type: "sequence"

2. SUPPORT association edges (lateral/horizontal arrows from context elements):
   - role → function    → edge_type: "performs"
   - system → function  → edge_type: "supports"
   - function → information → edge_type: "produces"
   - information → function → edge_type: "uses"

GATEWAY SEMANTICS (critical — read before tracing edges):
  A gateway circle is a SPLIT or JOIN point in the flow:
  • SPLIT gateway: exactly 1 arrow comes IN, and 2 or more arrows go OUT (one per branch).
    Example: function → XOR_1, then XOR_1 → event_A  AND  XOR_1 → event_B
  • JOIN gateway:  2 or more arrows come IN, and exactly 1 arrow goes OUT.
  Every gateway in the node list MUST appear as BOTH a to_label (incoming) AND a from_label
  (outgoing). If a gateway only appears on one side, you missed an arrow.

STEP 1 — TRACE THE PROCESS BACKBONE (sequence edges only):
Start at the TOP of the diagram. Find the topmost event or function shape.
Follow each arrow downward one step at a time, recording every connection:
  top element → next → ... → gateway → branch A AND branch B → ...
When you reach a gateway, record ALL outgoing arrows from it (one edge per branch).

SELF-CHECK before finishing Step 1:
  • Every gateway in the node list must appear at least once as a to_label AND at least once
    as a from_label. A split gateway will have MULTIPLE from_label entries with the same gateway.
  • The topmost element must appear as a from_label.
  • If a gateway is missing from your sequence edges — you missed an arrow. Add it.

STEP 2 — TRACE LATERAL ASSOCIATIONS:
Scan left and right of each function for role/system arrows. Record each one.

For each arrow provide:
  - from_label : exact label of the node the arrow LEAVES (must match a label above)
  - to_label   : exact label of the node the arrow POINTS TO (must match a label above)
  - edge_label : any text alongside the arrow, or "" if none
  - edge_type  : one of: sequence, performs, supports, produces, uses

RULES:
  • Use only labels from the list above — copy them exactly, character for character.
  • If a role/system label appears multiple times visually, each visual instance still maps to
    the same label. List one edge per function it connects to.
  • Include ALL arrows — do not skip any.

Reply with ONLY a valid JSON array — no prose, no markdown fences:
[{{"from_label": "Application data recorded", "to_label": "Check and preselect job applicants", "edge_label": "", "edge_type": "sequence"}}, ...]
"""

PROMPT_REPAIR_EDGES = """\
You are an expert ARIS EPC diagram analyst. Look at this diagram carefully.

The following nodes were extracted but have NO outgoing sequence arrow in the current edge list.
These are interior nodes — they must connect to something next in the flow:
{stranded_list}

All known nodes in this diagram:
{nodes_list}

For each stranded node, find the arrow leaving it and report the connection.

For each arrow provide:
  - from_label : the stranded node label (copy exactly as given above)
  - to_label   : the label of the next node it points to (must be from the nodes list)
  - edge_label : any text on the arrow, or ""
  - edge_type  : "sequence"

RULES:
  • Only include edges where from_label is one of the stranded nodes listed above.
  • Use only labels from the nodes list — copy them character for character.
  • If a stranded node is genuinely the last node in the diagram (no outgoing arrow), omit it.

Reply with ONLY a valid JSON array — no prose, no markdown fences:
[{{"from_label": "...", "to_label": "...", "edge_label": "", "edge_type": "sequence"}}, ...]
"""

PROMPT_ROLE_ASSIGNMENT = """\
You are an expert ARIS EPC diagram analyst. Look at this ARIS EPC image.

The functions identified in this diagram are:
{functions_list}

The roles and systems identified are:
{roles_and_systems_list}

For each FUNCTION, carefully examine which ROLES and SYSTEMS are connected to it by a VISIBLE
ARROW in the image (the lateral/horizontal arrows pointing directly to that specific function box).

IMPORTANT: Only assign a role or system if there is a clearly visible arrow from that role/system
directly to THIS function. Do NOT infer or carry over from other functions — examine each function
independently. A role/system that appears in the diagram but has no arrow to a particular function
must NOT be listed for that function.

Return a JSON object where each key is a function label and the value has:
  - "performed_by": list of role labels that have an arrow pointing to this function
  - "supported_by": list of system labels that have an arrow pointing to this function

If a function has no connected role, use an empty list. Same for systems.

Reply with ONLY a valid JSON object — no prose, no markdown fences:
{{
  "Check and preselect job applicants": {{
    "performed_by": ["Recruiting Manager"],
    "supported_by": ["Recruiting-Tool"]
  }},
  ...
}}
"""
