# ─────────────────────────────────────────────────────────────────────────────
# tf_idf_compare.py — Evaluate how well the scraper found the right content
#
# PURPOSE:
# After the spider scrapes a batch of venues, this script measures whether
# the text chunks it extracted actually contain the known "gold" offer text
# (i.e. the correct answer from a manually labelled dataset).
#
# HOW IT WORKS:
# For each venue, it compares the scraped chunks against the gold description
# using TF-IDF cosine similarity — a standard NLP technique that measures
# how much two pieces of text share the same important words.
#
# A similarity score close to 1.0 = the scraper found very similar text.
# A score close to 0.0 = the scraper missed the relevant content entirely.
#
# OUTPUT:
# A CSV file ranked by similarity score so you can quickly see which venues
# the scraper is failing on and investigate why.
# ─────────────────────────────────────────────────────────────────────────────

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


INPUT = "data/test_output.csv"   # Spider output CSV (scraped candidates)
OUTPUT = "data/tfidf_comparison.csv"  # Where this script saves its results


def split_chunks(chunk_blob):
    # The spider stores multiple candidate text blocks in one CSV cell,
    # separated by "|||". This splits them back into a list.
    # e.g. "Happy hour 3-6pm ||| $5 wells Mon-Fri" → ["Happy hour 3-6pm", "$5 wells Mon-Fri"]
    if not isinstance(chunk_blob, str):
        return []
    return [c.strip() for c in chunk_blob.split("|||") if c.strip()]


def dedupe_keep_order(items):
    # Remove duplicate chunks while preserving the original order.
    # Comparison is case-insensitive and whitespace-normalized so
    # "Happy Hour" and "happy hour" are treated as duplicates.
    seen = set()
    output = []

    for item in items:
        key = " ".join(item.lower().split())
        if key in seen:
            continue
        seen.add(key)
        output.append(item)

    return output


# ── Load the spider output ────────────────────────────────────────────────────
df = pd.read_csv(INPUT)

rows = []  # Will hold one result row per venue

# Group rows by source_url — one venue can produce multiple scraped rows
# (one per page visited), so we need to collect all chunks across all pages
for source_url, group in df.groupby("source_url", dropna=False):
    # Take metadata from the first row of the group (venue name, gold labels)
    first = group.iloc[0]

    venue_name = first.get("venue_name", "")
    # Gold fields = the manually labelled "correct answer" for this venue
    gold_description = str(first.get("description_gold", "") or "").strip()
    gold_teaser = str(first.get("teaser_gold", "") or "").strip()
    gold_category = str(first.get("incentive_category_gold", "") or "").strip()

    # Collect all scraped text chunks from every page visited for this venue
    all_chunks = []

    for _, row in group.iterrows():
        # top_candidate_text = the best single block the spider found on that page
        top_candidate = row.get("top_candidate_text", "")
        if isinstance(top_candidate, str) and top_candidate.strip():
            all_chunks.append(top_candidate.strip())

        # all_candidate_chunks = all other blocks found, packed as "|||"-separated string
        all_chunks.extend(split_chunks(row.get("all_candidate_chunks", "")))

    all_chunks = dedupe_keep_order(all_chunks)

    # Collect any failure types logged by the spider for this venue
    # (e.g. "timeout", "blocked", "no_content")
    failure_types = sorted(
        set(str(x) for x in group["failure_type"].dropna().tolist())
    )

    # If "ok" is in the failure types, treat the overall result as ok;
    # otherwise use the first failure type as the representative status
    best_failure_type = "ok" if "ok" in failure_types else (
        failure_types[0] if failure_types else ""
    )

    # If we have no gold description to compare against, or no scraped chunks,
    # skip the similarity calculation and record a zero-score row
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
            "manual_label": "",  # Placeholder for manual review later
        })
        continue

    # ── TF-IDF similarity calculation ─────────────────────────────────────────
    # Build a corpus where the first item is the gold description and the rest
    # are the scraped chunks. TfidfVectorizer converts each text into a vector
    # of word importance scores, then we measure how close each chunk vector
    # is to the gold vector.
    corpus = [gold_description] + all_chunks

    vectorizer = TfidfVectorizer(
        lowercase=True,       # Treat "Happy" and "happy" as the same word
        stop_words="english", # Ignore common words like "the", "is", "at"
        ngram_range=(1, 2),   # Consider both single words and 2-word phrases
        min_df=1,             # Include a term even if it only appears once
    )

    # fit_transform: learn the vocabulary from all texts and convert them to
    # TF-IDF vectors. matrix[0] = gold, matrix[1:] = scraped chunks.
    matrix = vectorizer.fit_transform(corpus)

    gold_vec = matrix[0]      # The "correct answer" vector
    chunk_vecs = matrix[1:]   # All scraped candidate vectors

    # cosine_similarity returns a score between 0 and 1 for each chunk vs gold.
    # argmax() finds the index of the chunk with the highest similarity.
    sims = cosine_similarity(gold_vec, chunk_vecs)[0]
    best_idx = int(sims.argmax())

    rows.append({
        "venue_name": venue_name,
        "source_url": source_url,
        "gold_category": gold_category,
        "gold_teaser": gold_teaser,
        "gold_description": gold_description,
        "best_chunk": all_chunks[best_idx],           # The chunk most similar to the gold answer
        "tfidf_similarity": round(float(sims[best_idx]), 4),  # Similarity score (0-1)
        "num_chunks": len(all_chunks),
        "failure_types": ", ".join(failure_types),
        "best_failure_type": best_failure_type,
        "manual_label": "",  # Placeholder for manual review later
    })


# ── Save and print results ────────────────────────────────────────────────────
out = pd.DataFrame(rows)

# Sort: "ok" venues first (alphabetically best_failure_type), then by
# similarity descending so the most successful extractions appear at the top
out = out.sort_values(
    by=["best_failure_type", "tfidf_similarity"],
    ascending=[True, False],
)

out.to_csv(OUTPUT, index=False)
print(f"Saved {OUTPUT}")
# Print a condensed summary table to the terminal for a quick read
print(out[[
    "venue_name",
    "best_failure_type",
    "tfidf_similarity",
    "num_chunks",
]].to_string(index=False))