"""CLI entry point.

Usage:
    python main.py --image schema.png --output result.json [--device auto] [--diagram-type aris]
"""

import argparse
import json
import sys
from pathlib import Path

import pipeline
from formatter import to_llm_text


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Extract flowchart/ARIS EPC schema using Qwen 2.5 VL 3B")
    p.add_argument("--image",        required=True,              help="Path to diagram image")
    p.add_argument("--output",       default="result.json",      help="Output JSON path")
    p.add_argument("--device",       default="auto",             help="PyTorch device (auto/cpu/cuda)")
    p.add_argument("--diagram-type", default="flowchart",
                   choices=["flowchart", "aris"],
                   help="Diagram type: 'flowchart' (default) or 'aris'")
    return p.parse_args()


def main() -> None:
    sys.stdout.reconfigure(encoding='utf-8')
    args = parse_args()

    image_path = Path(args.image)
    if not image_path.exists():
        print(f"Error: image not found: {image_path}", file=sys.stderr)
        sys.exit(1)

    diagram_type = args.diagram_type
    print(f"[main] Diagram type: {diagram_type}")

    schema = pipeline.run(image_path, diagram_type=diagram_type)

    llm_text = to_llm_text(schema)
    print("\n" + llm_text)

    output = {
        "diagram_type": diagram_type,
        "nodes": [n.model_dump() for n in schema.nodes],
        "edges": [e.model_dump() for e in schema.edges],
        "stats": {
            "node_count": len(schema.nodes),
            "edge_count": len(schema.edges),
        },
    }
    out_path = Path(args.output)
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")

    txt_path = out_path.with_suffix(".txt")
    txt_path.write_text(llm_text, encoding="utf-8")

    print(f"Saved JSON -> {out_path}")
    print(f"Saved LLM text -> {txt_path}")


if __name__ == "__main__":
    main()
