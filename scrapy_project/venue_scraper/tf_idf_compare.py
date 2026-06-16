import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


INPUT = "data/test_output.csv"
OUTPUT = "data/tfidf_comparison.csv"


def split_chunks(chunk_blob):
    if not isinstance(chunk_blob, str):
        return []
    return [c.strip() for c in chunk_blob.split("|||") if c.strip()]


def dedupe_keep_order(items):
    seen = set()
    output = []

    for item in items:
        key = " ".join(item.lower().split())
        if key in seen:
            continue
        seen.add(key)
        output.append(item)

    return output


df = pd.read_csv(INPUT)

rows = []

for source_url, group in df.groupby("source_url", dropna=False):
    first = group.iloc[0]

    venue_name = first.get("venue_name", "")
    gold_description = str(first.get("description_gold", "") or "").strip()
    gold_teaser = str(first.get("teaser_gold", "") or "").strip()
    gold_category = str(first.get("incentive_category_gold", "") or "").strip()

    all_chunks = []

    for _, row in group.iterrows():
        top_candidate = row.get("top_candidate_text", "")
        if isinstance(top_candidate, str) and top_candidate.strip():
            all_chunks.append(top_candidate.strip())

        all_chunks.extend(split_chunks(row.get("all_candidate_chunks", "")))

    all_chunks = dedupe_keep_order(all_chunks)

    failure_types = sorted(
        set(str(x) for x in group["failure_type"].dropna().tolist())
    )

    best_failure_type = "ok" if "ok" in failure_types else (
        failure_types[0] if failure_types else ""
    )

    if not gold_description or not all_chunks:
        rows.append({
            "venue_name": venue_name,
            "source_url": source_url,
            "gold_category": gold_category,
            "gold_teaser": gold_teaser,
            "gold_description": gold_description,
            "best_chunk": "",
            "tfidf_similarity": 0.0,
            "num_chunks": len(all_chunks),
            "failure_types": ", ".join(failure_types),
            "best_failure_type": best_failure_type,
            "manual_label": "",
        })
        continue

    corpus = [gold_description] + all_chunks

    vectorizer = TfidfVectorizer(
        lowercase=True,
        stop_words="english",
        ngram_range=(1, 2),
        min_df=1,
    )

    matrix = vectorizer.fit_transform(corpus)

    gold_vec = matrix[0]
    chunk_vecs = matrix[1:]

    sims = cosine_similarity(gold_vec, chunk_vecs)[0]
    best_idx = int(sims.argmax())

    rows.append({
        "venue_name": venue_name,
        "source_url": source_url,
        "gold_category": gold_category,
        "gold_teaser": gold_teaser,
        "gold_description": gold_description,
        "best_chunk": all_chunks[best_idx],
        "tfidf_similarity": round(float(sims[best_idx]), 4),
        "num_chunks": len(all_chunks),
        "failure_types": ", ".join(failure_types),
        "best_failure_type": best_failure_type,
        "manual_label": "",
    })


out = pd.DataFrame(rows)
out = out.sort_values(
    by=["best_failure_type", "tfidf_similarity"],
    ascending=[True, False],
)

out.to_csv(OUTPUT, index=False)
print(f"Saved {OUTPUT}")
print(out[[
    "venue_name",
    "best_failure_type",
    "tfidf_similarity",
    "num_chunks",
]].to_string(index=False))