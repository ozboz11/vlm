PROMPT_NODES = """\
You are a precise flowchart analyst. Examine this flowchart image very carefully.

STEP 1 — SYSTEMATIC SCAN: Sweep the image from TOP to BOTTOM, LEFT to RIGHT.
Find EVERY enclosed shape that contains text. Shape types to look for:
  • Rectangles / rounded rectangles  (process steps, Start, End)
  • Diamonds / rotated squares       (decision nodes — contain questions like "Valid?" or "Is the balance alright?")
  • Any other closed shape with text

STEP 2 — LIST ALL SHAPES: For each shape, record:
  - label : the EXACT text written inside the shape (include every word, even across multiple lines; join lines with a space)

CRITICAL RULES:
  • Diamond shapes are decision nodes. They are often placed between other nodes and easy to miss. Look for every diamond.
  • Each distinct enclosed area is its own node. Do NOT merge two shapes into one.
  • Do NOT skip any shape, no matter how small or how many arrows connect to it.
  • Copy the label text exactly as it appears — do not paraphrase or shorten.

Reply with ONLY a valid JSON array of label strings — no prose, no markdown fences:
["Start", "Customer Arrives", "Valid?", ...]
"""

PROMPT_EDGES = """\
The following nodes were identified in this flowchart:
{nodes_list}

Now find EVERY directed arrow (edge) in the image.
For each arrow provide:
  - from_label : exact label of the node the arrow LEAVES (must match one of the labels above)
  - to_label   : exact label of the node the arrow POINTS TO (must match one of the labels above)
  - edge_label : text written alongside the arrow ("YES", "NO", or "" if none)

Rules:
  • Use only labels from the list above — copy them exactly, character for character.
  • Include ALL arrows, including ones entering or leaving decision diamonds.
  • If an arrow has no text beside it, set edge_label to "".

Reply with ONLY a valid JSON array — no prose, no markdown fences:
[{{"from_label": "Start", "to_label": "Customer Arrives", "edge_label": ""}}, ...]
"""
