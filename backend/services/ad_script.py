"""Writes a short Bangla product-ad script with an OpenAI chat model.

Returns one spoken/on-screen line per scene plus a tagline and a
call-to-action, in the classic commercial shape: problem -> product ->
benefits -> result, then the brand card.
"""
import json
from typing import Dict

from openai import OpenAI

from ..config import settings


def write_script(product_name: str, description: str, num_scenes: int = 4) -> Dict:
    if not settings.openai_api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set, so the script can't be written for you. "
            "Add it to .env, or type your own lines into the scene boxes."
        )
    num_scenes = max(2, min(8, int(num_scenes)))

    prompt = (
        "You are a copywriter for short social-media video commercials in "
        "Bangladesh. Write a Bangla (Bengali script) commercial for this "
        "product.\n\n"
        f"Product name: {product_name}\n"
        f"About the product: {description or '(not given)'}\n\n"
        f"Write exactly {num_scenes} scene lines. Each line is shown as a "
        "caption AND read aloud as the voiceover, so keep each one short and "
        "natural to speak: 6-12 words, about 2-4 seconds. Structure: start "
        "with a relatable problem or hook, then introduce the product, then "
        "its key benefits/ingredients, then the result. Warm, confident, "
        "everyday spoken Bangla — not overly formal. Do not invent medical "
        "claims, prices, or discounts that weren't given.\n\n"
        "Also write a short tagline (3-7 words) and a call-to-action button "
        "text (2-4 words, e.g. 'এখনই অর্ডার করুন').\n\n"
        'Reply with JSON only: {"scenes": ["...", ...], "tagline": "...", "cta": "..."}'
    )
    client = OpenAI(api_key=settings.openai_api_key)
    resp = client.chat.completions.create(
        model=settings.translation_model,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.8,
    )
    data = json.loads(resp.choices[0].message.content)
    scenes = [str(s).strip() for s in data.get("scenes", []) if str(s).strip()]
    if not scenes:
        raise RuntimeError("The model didn't return any scene lines; try again.")
    return {
        "scenes": scenes[:num_scenes],
        "tagline": str(data.get("tagline", "")).strip(),
        "cta": str(data.get("cta", "")).strip() or "এখনই অর্ডার করুন",
    }
