"""Load cached MedlinePlus content into DashVector with embeddings.

Usage: python scripts/ingest_medlineplus_to_dashvector.py
Requires: LABLENS_DASHSCOPE_API_KEY, LABLENS_DASHVECTOR_API_KEY, LABLENS_DASHVECTOR_ENDPOINT
"""

import json
import os
from pathlib import Path

CACHE_DIR = Path("data/medlineplus-cache")


def embed(text: str) -> list[float]:
    from dashscope import TextEmbedding

    resp = TextEmbedding.call(
        model="text-embedding-v3",
        input=text[:2048],
        api_key=os.getenv("LABLENS_DASHSCOPE_API_KEY"),
    )
    return resp.output["embeddings"][0]["embedding"]


def load_to_dashvector():
    import dashvector

    client = dashvector.Client(
        api_key=os.getenv("LABLENS_DASHVECTOR_API_KEY"),
        endpoint=os.getenv("LABLENS_DASHVECTOR_ENDPOINT"),
    )
    collection = client.get("lab_education")

    docs = []
    for cache_file in sorted(CACHE_DIR.glob("*.json")):
        stem = cache_file.stem
        # Filename: {loinc_code}-{lang}.json (e.g., "2345-7-en.json")
        parts = stem.rsplit("-", 1)
        if len(parts) != 2:
            continue
        loinc_code, lang = parts[0], parts[1]

        data = json.loads(cache_file.read_text())
        provenance = "machine-translated" if data.get("_language") else "original"
        entries = data.get("feed", {}).get("entry", [])

        for i, entry in enumerate(entries):
            title = entry.get("title", {}).get("_value", "")
            summary = entry.get("summary", {}).get("_value", "")
            text = f"{title}\n{summary}".strip()
            if not text:
                continue

            vector = embed(text)
            doc_id = f"medlineplus-{loinc_code}-{lang}-{i}"
            docs.append(dashvector.Doc(
                id=doc_id,
                vector=vector,
                fields={
                    "loinc_code": loinc_code,
                    "test_name": title,
                    "content_type": "overview",
                    "language": lang,
                    "source": "medlineplus",
                    "provenance": provenance,
                    "text": text[:4000],
                    "url": (entry.get("link") or [{}])[0].get("href", ""),
                },
            ))
            print(f"  Prepared: {doc_id}")

    # Batch insert (50 docs per batch)
    for i in range(0, len(docs), 50):
        batch = docs[i : i + 50]
        collection.insert(batch)
        print(f"Inserted batch {i // 50 + 1} ({len(batch)} docs)")

    print(f"Total: {len(docs)} documents loaded into DashVector")


if __name__ == "__main__":
    load_to_dashvector()
