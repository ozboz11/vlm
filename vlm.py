"""Qwen 2.5 VL 3B inference wrapper with JSON extraction and retry logic."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

import torch
from PIL import Image
from qwen_vl_utils import process_vision_info
from transformers import AutoProcessor, BitsAndBytesConfig, Qwen2_5_VLForConditionalGeneration

_MODEL_ID = "Qwen/Qwen2.5-VL-7B-Instruct"
_MAX_RETRIES = 3

_model: Optional[Qwen2_5_VLForConditionalGeneration] = None
_processor: Optional[AutoProcessor] = None


def load_model(device: str = "auto") -> None:
    global _model, _processor
    if _model is not None:
        return
    print(f"Loading {_MODEL_ID} …")
    _processor = AutoProcessor.from_pretrained(_MODEL_ID)

    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        bnb_cfg = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type="nf4",
        )
        _model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            _MODEL_ID,
            quantization_config=bnb_cfg,
            device_map="cuda:0",
        )
        print("Model ready (4-bit on CUDA).")
    else:
        _model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            _MODEL_ID,
            torch_dtype=torch.float32,
            device_map=device,
        )
        print("Model ready (CPU).")


def _extract_json(text: str) -> Any:
    """Return the first JSON array or object found in text."""
    text = text.strip()
    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Strip markdown code fences
    text = re.sub(r"```(?:json)?", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Grab first [...] or {...} block
    for pattern in (r"\[.*\]", r"\{.*\}"):
        m = re.search(pattern, text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                continue
    raise ValueError(f"No valid JSON found in model output:\n{text[:500]}")


def generate(image_path: str | Path, prompt: str, max_new_tokens: int = 1024) -> Any:
    """
    Run the VLM on image_path with the given prompt.
    Returns the parsed JSON (list or dict). Retries up to _MAX_RETRIES times.
    """
    if _model is None or _processor is None:
        load_model()

    raw = Image.open(image_path).convert("RGB")
    # Upscale small images so each node label gets more pixels per patch
    max_side = 1920
    w, h = raw.size
    if max(w, h) < max_side:
        scale = max_side / max(w, h)
        pil_image = raw.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    else:
        pil_image = raw
    extra = ""
    last_error: Exception = RuntimeError("No attempts made")

    for attempt in range(1, _MAX_RETRIES + 1):
        full_prompt = prompt + extra
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": pil_image},
                    {"type": "text", "text": full_prompt},
                ],
            }
        ]
        text_input = _processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        image_inputs, video_inputs = process_vision_info(messages)
        inputs = _processor(
            text=[text_input],
            images=image_inputs,
            videos=video_inputs,
            return_tensors="pt",
        )
        inputs = {k: v.to(_model.device) for k, v in inputs.items()}

        with torch.no_grad():
            output_ids = _model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=False,
            )

        # Decode only the generated tokens
        input_len = inputs["input_ids"].shape[1]
        generated = _processor.decode(
            output_ids[0][input_len:], skip_special_tokens=True
        )

        try:
            return _extract_json(generated)
        except ValueError as e:
            last_error = e
            print(f"[vlm] Attempt {attempt}/{_MAX_RETRIES} failed: {e}")
            extra = "\n\nReply ONLY with valid JSON. Do not add any explanation."

    raise RuntimeError(
        f"Failed to get valid JSON after {_MAX_RETRIES} attempts. Last error: {last_error}"
    )
