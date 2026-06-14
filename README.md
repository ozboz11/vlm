# VLM Schema Extraction

Extracts structured graphs from process diagram images using [Qwen2.5-VL-7B-Instruct](https://huggingface.co/Qwen/Qwen2.5-VL-7B-Instruct). Supports generic flowcharts and ARIS EPC diagrams.

## How it works

The pipeline runs 2–3 inference passes over the image:

1. **Node extraction** — identifies all nodes and their types (event, function, role, system, gateway, etc.)
2. **Edge extraction** — maps connections between the extracted nodes
3. **Role/system assignment** *(ARIS only)* — resolves which roles perform and which systems support each function

Each pass sends the diagram image + a structured prompt to the VLM and parses the JSON response, with up to 3 retries on malformed output.

## Requirements

- Python 3.10+
- CUDA GPU recommended (runs 4-bit quantized via bitsandbytes); CPU fallback available

```bash
pip install -r requirements.txt
```

## Usage

```bash
python main.py --image <path-to-image> --output result.json [--diagram-type flowchart|aris]
```

**Examples:**

```bash
# Flowchart (default)
python main.py --image schema.png --output result.json

# ARIS EPC
python main.py --image aris_schema3.png --output aris_result.json --diagram-type aris
```

Outputs two files:
- `result.json` — structured graph with nodes and edges
- `result.txt` — human-readable / LLM-ready text representation

## Output format

```json
{
  "diagram_type": "aris",
  "nodes": [
    { "label": "Create sales order", "node_type": "function" },
    { "label": "Sales contract complete", "node_type": "event" }
  ],
  "edges": [
    { "from_label": "Create sales order", "to_label": "Sales contract complete", "edge_label": "", "edge_type": "sequence" }
  ],
  "stats": { "node_count": 14, "edge_count": 14 }
}
```

**Node types:** `event`, `function`, `role`, `system`, `gateway`, `risk`, `information`

**Edge types:** `sequence` (flow), `performs` (role → function), `supports` (system → function), `produces` (function → information), `uses` (information → function)

## Project structure

```
main.py          # CLI entry point
pipeline.py      # Multi-pass extraction orchestration
vlm.py           # Qwen2.5-VL inference wrapper (load, generate, JSON retry)
models.py        # Pydantic models (Node, Edge, SchemaGraph)
prompts.py       # Prompts for flowchart mode
prompts_aris.py  # Prompts for ARIS EPC mode
formatter.py     # SchemaGraph → human-readable text
graph_builder.py # NetworkX graph utilities
```
