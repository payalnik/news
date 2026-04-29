"""Benchmark gemini-3-flash-preview vs gemini-3.1-flash-lite-preview.

Runs both models on the same prompts derived from real NewsSection sources,
saves outputs side-by-side, and reports auto-measurable metrics.

Usage: sudo -u www-data /var/www/news/venv/bin/python3 \
       /var/www/news/news_updater/benchmark_models.py [--sections N] [--no-fetch]
"""
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, "/var/www/news/news_updater")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "news_updater.settings")

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402
from google import genai as google_genai  # noqa: E402
from google.genai import types  # noqa: E402

from news_app.models import NewsSection  # noqa: E402
from news_app.tasks import fetch_url_content  # noqa: E402

OLD_MODEL = "gemini-3-flash-preview"
NEW_MODEL = "gemini-3.1-flash-lite-preview"

OUT_DIR = Path("/var/www/news/benchmark_out")
OUT_DIR.mkdir(parents=True, exist_ok=True)

NEWS_ITEMS_SCHEMA = types.Schema(
    type=types.Type.ARRAY,
    items=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "headline": types.Schema(type=types.Type.STRING),
            "details": types.Schema(type=types.Type.STRING),
            "sources": types.Schema(
                type=types.Type.ARRAY,
                items=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "url": types.Schema(type=types.Type.STRING),
                        "title": types.Schema(type=types.Type.STRING),
                    },
                    required=["url", "title"],
                ),
            ),
            "confidence": types.Schema(type=types.Type.STRING),
        },
        required=["headline", "details", "sources", "confidence"],
    ),
)


def build_prompt(section_name: str, section_prompt: str, sources_content: list[str]) -> str:
    joined = "\n\n".join(sources_content)
    return f"""
    I need to create a news summary for the section "{section_name}" based on the following sources:

    {joined}

    User's instructions for summarizing this section. Please follow them carefully, they take priority over any other guidelines:
    {section_prompt}

    -----------------

    Please provide a concise, well-organized summary of the most important news from these sources.

    CRITICAL ANTI-HALLUCINATION INSTRUCTIONS:
    1. ONLY include information that is EXPLICITLY stated in the provided sources
    2. DO NOT add any details, context, or background information that is not directly from the sources
    3. If the sources are insufficient to create a meaningful summary, state this clearly instead of inventing content
    4. Each fact MUST be directly attributable to at least one of the provided sources
    5. If sources contradict each other, note the contradiction and present both perspectives
    6. Use phrases like "according to [source]" to clearly attribute information
    7. If you're unsure about any information, indicate this uncertainty rather than making assumptions

    IMPORTANT: Return your response as a JSON array with each news item having the following structure:
    {{"headline": "...", "details": "...", "sources": [{{"url": "...", "title": "..."}}], "confidence": "high/medium/low"}}

    Make sure to:
    1. Include 3-5 of the most important news items from the sources unless stated otherwise
    2. Provide detailed but concise information in the details field WITH CLEAR ATTRIBUTION
    3. Link to the original sources for EVERY claim made
    4. Keep source titles short and clean (use the publication name)
    """


def call_model(client, model: str, prompt: str) -> dict:
    cfg = types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(thinking_level="MINIMAL"),
        response_mime_type="application/json",
        response_schema=NEWS_ITEMS_SCHEMA,
    )
    t0 = time.monotonic()
    err = None
    text = None
    usage = None
    try:
        resp = client.models.generate_content(model=model, contents=prompt, config=cfg)
        text = resp.text
        u = getattr(resp, "usage_metadata", None)
        if u:
            usage = {
                "prompt_tokens": getattr(u, "prompt_token_count", None),
                "output_tokens": getattr(u, "candidates_token_count", None),
                "total_tokens": getattr(u, "total_token_count", None),
            }
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
    latency = time.monotonic() - t0

    parsed = None
    parse_ok = False
    if text:
        try:
            parsed = json.loads(text)
            parse_ok = isinstance(parsed, list)
        except json.JSONDecodeError:
            m = re.search(r"\[\s*\{.*\}\s*\]", text or "", re.DOTALL)
            if m:
                try:
                    parsed = json.loads(m.group(0))
                    parse_ok = isinstance(parsed, list)
                except json.JSONDecodeError:
                    pass
    return {
        "model": model,
        "latency_s": round(latency, 2),
        "error": err,
        "raw_text": text,
        "parsed": parsed,
        "parse_ok": parse_ok,
        "usage": usage,
    }


def analyze(parsed: list, source_urls: list[str]) -> dict:
    if not parsed:
        return {"items": 0}
    valid_conf = {"high", "medium", "low"}
    items = len(parsed)
    headlines = [p.get("headline", "") for p in parsed]
    details_lens = [len(p.get("details", "")) for p in parsed]
    bad_conf = sum(1 for p in parsed if str(p.get("confidence", "")).lower() not in valid_conf)
    confs = {c: 0 for c in valid_conf}
    for p in parsed:
        c = str(p.get("confidence", "")).lower()
        if c in confs:
            confs[c] += 1
    src_url_set = {u.rstrip("/") for u in source_urls}
    cited_urls = []
    invalid_urls = 0
    for p in parsed:
        for s in p.get("sources", []) or []:
            url = (s.get("url") or "").rstrip("/")
            cited_urls.append(url)
            if not url.startswith("http"):
                invalid_urls += 1
    matching_input = sum(1 for u in cited_urls if any(u.startswith(s) or s.startswith(u) for s in src_url_set))
    return {
        "items": items,
        "headlines": headlines,
        "avg_details_len": round(sum(details_lens) / items, 1) if items else 0,
        "confidence_dist": confs,
        "bad_confidence_values": bad_conf,
        "total_citations": len(cited_urls),
        "citations_matching_input": matching_input,
        "citations_invalid_url": invalid_urls,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sections", type=int, default=3, help="number of NewsSections to sample")
    ap.add_argument("--no-fetch", action="store_true", help="skip live fetching, use cached file if present")
    args = ap.parse_args()

    client = google_genai.Client(api_key=settings.GOOGLE_API_KEY)

    sections = list(NewsSection.objects.all().order_by("id")[: args.sections])
    if not sections:
        print("no NewsSection rows in DB")
        sys.exit(1)

    cache_path = OUT_DIR / "fetched_sources.json"
    cache: dict = {}
    if cache_path.exists():
        try:
            cache = json.loads(cache_path.read_text())
        except Exception:
            cache = {}

    results = []
    for section in sections:
        urls = section.get_sources_list()[:5]
        print(f"\n=== Section: {section.name} ({len(urls)} sources) ===")
        sources_content = []
        for url in urls:
            key = url
            if args.no_fetch and key in cache:
                sources_content.append(cache[key])
                print(f"  cached: {url}")
                continue
            try:
                print(f"  fetching: {url}")
                raw = fetch_url_content(url)
                snippet = f"Content from {url}:\n{raw[:8000]}"
                sources_content.append(snippet)
                cache[key] = snippet
            except Exception as e:
                print(f"  fetch failed: {url} -> {e}")
                sources_content.append(f"Error fetching content from {url}")
        cache_path.write_text(json.dumps(cache))

        prompt = build_prompt(section.name, section.prompt, sources_content)
        per_section = {"section": section.name, "section_prompt": section.prompt[:200], "urls": urls}

        for model in [OLD_MODEL, NEW_MODEL]:
            print(f"  calling {model} ...")
            r = call_model(client, model, prompt)
            r["analysis"] = analyze(r.get("parsed") or [], urls)
            per_section[model] = r
            print(
                f"    {model}: {r['latency_s']}s, parse_ok={r['parse_ok']}, "
                f"items={r['analysis'].get('items', 0)}, "
                f"tokens={r['usage']}"
            )
            if r["error"]:
                print(f"    ERROR: {r['error']}")
        results.append(per_section)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = OUT_DIR / f"benchmark_{stamp}.json"
    out_path.write_text(json.dumps(results, indent=2))
    print(f"\nWrote {out_path}")

    print("\n=== Summary ===")
    for r in results:
        print(f"\n[{r['section']}]")
        for m in [OLD_MODEL, NEW_MODEL]:
            d = r[m]
            a = d.get("analysis", {})
            print(
                f"  {m:40s} latency={d['latency_s']}s items={a.get('items', 0)} "
                f"parse_ok={d['parse_ok']} citations_in_input={a.get('citations_matching_input', 0)}/{a.get('total_citations', 0)} "
                f"conf={a.get('confidence_dist')} tokens={d.get('usage')}"
            )


if __name__ == "__main__":
    main()
