# ARIS EPC Extraction — Implementation Plan

## 1. What ARIS EPC Is (and How It Differs)

An ARIS EPC (Event-driven Process Chain) has a fundamentally different structure
from a generic flowchart. There are two orthogonal graphs layered on top of each other:

### 1a. Main process flow (vertical, sequential)
```
Event → Function → Gateway → Event
                           ↘ Event
```
This is the true process sequence. Only Events, Functions, and Gateways participate.

### 1b. Support associations (lateral, non-sequential)
```
Role   → Function   (who performs it)
System → Function   (what tool supports it)
```
These are NOT process flow. They annotate each Function with context.

---

## 2. Node Types (from aris_lookup.png)

| Type        | Visual                          | Semantic meaning                              |
|-------------|---------------------------------|-----------------------------------------------|
| event       | Pink/magenta hexagon + flag     | State that triggers or results from a function|
| function    | Green rectangle + fast-forward  | Task or activity (process step)               |
| system      | Blue rectangle + screen icon    | Software system supporting a function         |
| role        | Orange rectangle + person icon  | Who performs the function                     |
| risk        | Red rectangle + triangle icon   | Risk on a process objective                   |
| information | Gray rectangle + document icon  | Knowledge or data carrier                     |
| gateway     | Circle with ×, +, or ∨ symbol  | Logical split/merge (XOR, AND, OR)            |

Gateway variants:
- × = XOR (exclusive or — exactly one branch taken)
- + = AND (all branches taken in parallel)
- ∨ = OR  (one or more branches taken)

---

## 3. Edge Types

| Edge type   | Connects                    | Meaning                              |
|-------------|----------------------------|--------------------------------------|
| sequence    | event↔function, function↔gateway, gateway↔event | Process control flow |
| performs    | role → function            | Role responsible for function        |
| supports    | system → function          | System used by function              |
| produces    | function → information     | Function outputs an information object|
| uses        | information → function     | Function consumes an information object|

For the MVP, we need at minimum: sequence, performs, supports.

---

## 4. Required Code Changes

### 4a. `models.py`
Add `node_type` to Node. Add `edge_type` to Edge.

```python
class NodeType(str, Enum):
    event       = "event"
    function    = "function"
    system      = "system"
    role        = "role"
    risk        = "risk"
    information = "information"
    gateway     = "gateway"

class EdgeType(str, Enum):
    sequence = "sequence"   # process flow
    performs = "performs"   # role → function
    supports = "supports"   # system → function
    produces = "produces"   # function → information
    uses     = "uses"       # information → function

class Node(BaseModel):
    label:     str
    node_type: NodeType

class Edge(BaseModel):
    from_label: str
    to_label:   str
    edge_label: str = ""
    edge_type:  EdgeType = EdgeType.sequence

class SchemaGraph(BaseModel):
    nodes: list[Node]
    edges: list[Edge]
```

### 4b. `prompts.py` — replace with ARIS-specific prompts

**PROMPT_NODES** must teach the model to classify node types by color+icon:
- Pink/magenta hexagon with flag    → event
- Green rectangle with >> arrows    → function
- Blue rectangle with screen icon   → system
- Orange rectangle with person icon → role
- Circle with ×, +, or ∨           → gateway
- Red rectangle with triangle       → risk
- Gray rectangle with document      → information

The model returns: `[{"label": "...", "node_type": "function"}, ...]`

**PROMPT_EDGES** must distinguish the two relationship types:
- Vertical arrows between events/functions/gateways → edge_type: "sequence"
- Horizontal arrows from roles/systems to functions → edge_type: "performs" or "supports"

The model returns:
```json
[{"from_label": "Role A", "to_label": "Function B",
  "edge_label": "", "edge_type": "performs"}, ...]
```

### 4c. `pipeline.py`
- `_parse_nodes` must extract and validate `node_type`
- `_parse_edges` must extract and validate `edge_type`
- Consider a **third pass** for ARIS: after extracting nodes+edges, do a
  "role/system assignment pass" that asks which roles and systems belong to
  which functions — this is more reliable than trying to read lateral arrows
  whose spatial distance from the function can be ambiguous.

### 4d. `formatter.py`
Output must be split into two sections:

**Section A — Process flow** (sequence edges only):
```
EVENT: Application data recorded
  |
FUNCTION: Check and preselect job applicants
  |
FUNCTION: Interview applicant
  |
...
GATEWAY [XOR]:
  -> EVENT: New employee hired
  -> EVENT: Applicant declined job offer
```

**Section B — Function context** (support associations grouped by function):
```
FUNCTION: Check and preselect job applicants
  Performed by: Recruiting Manager
  Supported by: Recruiting-Tool

FUNCTION: Offer job
  Performed by: Recruiting Manager
  Supported by: Recruiting-Tool
```

This two-section format gives a downstream LLM both the process logic and the
organizational/system context without mixing them.

### 4e. `vlm.py`
No structural changes needed. The image upscaling and 4-bit CUDA loading already work.
The ARIS schemas tend to be tall and narrow — consider rotating or padding to square
before upscaling if the aspect ratio is extreme.

---

## 5. Implementation Steps (in order)

1. Update `models.py` — add NodeType, EdgeType enums; update Node and Edge
2. Write `prompts_aris.py` — ARIS-specific PROMPT_NODES and PROMPT_EDGES with
   color+icon classification guide
3. Update `pipeline.py` — handle node_type/edge_type in parse functions;
   optionally add a third "role assignment" pass
4. Update `formatter.py` — split output into process flow section + function
   context section
5. Update `main.py` — add `--diagram-type` flag ("flowchart" | "aris") to select
   the correct prompt set
6. Test on `aris_schema.png` and verify all 4 functions, 3 events, 1 gateway,
   2 systems (Recruiting-Tool), and 4 role instances (Recruiting Manager) are found
   with the correct types

---

## 6. Expected Output for aris_schema.png

### Nodes (10 unique labels, 13 total instances)
| Label                        | Type     |
|------------------------------|----------|
| Application data recorded    | event    |
| Check and preselect job applicants | function |
| Interview applicant          | function |
| Select proper applicant      | function |
| Offer job                    | function |
| New employee hired           | event    |
| Applicant declined job offer | event    |
| Recruiting-Tool              | system   |
| Recruiting Manager           | role     |
| (XOR gateway)                | gateway  |

### Edges
Sequence flow:
```
Application data recorded → Check and preselect job applicants
Check and preselect job applicants → Interview applicant
Interview applicant → Select proper applicant
Select proper applicant → Offer job
Offer job → [XOR gateway]
[XOR gateway] → New employee hired
[XOR gateway] → Applicant declined job offer
```

Support associations:
```
Recruiting-Tool    --supports--> Check and preselect job applicants
Recruiting Manager --performs--> Check and preselect job applicants
Recruiting Manager --performs--> Interview applicant
Recruiting Manager --performs--> Select proper applicant
Recruiting-Tool    --supports--> Offer job
Recruiting Manager --performs--> Offer job
```

---

## 7. Key Risks

- **Repeated role/system instances**: "Recruiting Manager" appears 4 times in the
  image as separate visual objects. The model must deduplicate by label while still
  correctly assigning each instance to its adjacent function. The label-based edge
  approach handles this naturally — duplicate labels collapse into one node with
  multiple outgoing edges.

- **Gateway label**: The XOR circle has no text label, only a symbol (×). The model
  must detect the symbol and assign a synthetic label like "XOR_1" or use the symbol
  itself as the label.

- **Lateral vs. sequence edge confusion**: The model may misclassify a horizontal
  role→function arrow as a sequence edge. The third "role assignment pass" mitigates
  this by asking the question differently: "For each function, list which roles
  perform it and which systems support it."
