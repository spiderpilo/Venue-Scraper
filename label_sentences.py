#!/usr/bin/env python3
"""
Label every row in sentence_dataset.csv by applying keyword-matching rules.
No LLM API used — pure keyword matching in Python.

Handles corrupted rows (where two rows got concatenated) by always taking
columns [0..3] as the first four fields and the LAST column as the label.

Runs a fresh label on every row regardless of existing label value.
"""

import csv
import re


def label_sentence(sentence):
    s = sentence.lower()

    # ------------------------------------------------------------------
    # 1. Group Friendly (highest priority)
    # ------------------------------------------------------------------
    group_patterns = [
        r'\bprivate (dining|event|events|room|space|party|parties)\b',
        r'\bgroup (events?|booking|dining|reservations?|celebration|party|parties)\b',
        r'\blarge (groups?|parties|party)\b',
        r'\bhost (your|the|a|an)\b',
        r'\bcatering\b',
        r'\bprivate space\b',
        r'\bgroup booking\b',
        r'\bevent form\b',
        r'\bparty (menu|room|space|planner)\b',
        r'\bin[- ]?house party\b',
        r'\bprivate events?\b',
        r'\bgroup events?\b',
    ]
    for pat in group_patterns:
        if re.search(pat, s):
            return 'Group Friendly'

    # ------------------------------------------------------------------
    # 2. Happy Hour
    # ------------------------------------------------------------------
    if re.search(r'\bhappy hour\b', s):
        return 'Happy Hour'

    # ------------------------------------------------------------------
    # 3. Live Music
    # ------------------------------------------------------------------
    live_music_patterns = [
        r'\blive music\b',
        r'\blive band\b',
        r'\bkaraoke\b',
        r'\b(dj|d\.j\.)\b',
        r'\btribute band\b',
        r'\bconcert\b',
        r'\bperformance[s]?\b',
        r'\bburlesque\b',
        r'\bcabaret\b',
        r'\blive belly dance\b',
        r'\bswing band\b',
        r'\blive show\b',
        r'\bband\b',
    ]
    for pat in live_music_patterns:
        if re.search(pat, s):
            return 'Live Music'

    # ------------------------------------------------------------------
    # 4. Free
    # ------------------------------------------------------------------
    for pat in [r'\bfree\b', r'\bno cover\b', r'\bno cover charge\b']:
        if re.search(pat, s):
            return 'Free'

    # ------------------------------------------------------------------
    # 5. Discount
    # Exclude idiomatic phrases that are not actual price discounts first.
    # ------------------------------------------------------------------
    fp_exclusions = [
        r'\bbig deal\b',                        # "what's the big deal" — idiomatic
        r'\bspecial rates & accessibility\b',   # hotel booking-form widget
        r'\baccessible room required\b',
    ]
    for fp in fp_exclusions:
        if re.search(fp, s):
            return 'No Incentive'

    discount_patterns = [
        r'\d+\s*%\s*(off|discount|savings?)\b',
        r'\b(savings?|discount[s]?)\b.*\d+\s*%',
        r'\b\d+\s*%\s*off\b',
        r'\bpercent off\b',
        r'\bdollars? off\b',
        r'\bcoupon[s]?\b',
        r'\bspecial (deal|offer|discount|rate[s]?|price[s]?|promotion[s]?)\b',
        r'\bour special deal\b',
        r'\bspecial discounts?\b',
        r'\bdeals?\b',
        r'\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+special[s]?\b',
        r'\beveryday special\b',
        r'\bfamily meal deal\b',
        r'\bcoupon code\b',
        r'\buse coupon\b',
        r'\bsave\d+\b',
        r'\bdiscounted pricing\b',
        r'\bdiscounted\b',
        r'\bflexible subscription with discount\b',
        r'\bpresale\b',
    ]
    for pat in discount_patterns:
        if re.search(pat, s):
            return 'Discount'

    # "$X available for $N" limited-time price patterns
    if re.search(r'available for \$\d+', s):
        return 'Discount'

    # ------------------------------------------------------------------
    # 6. No Incentive (default)
    # ------------------------------------------------------------------
    return 'No Incentive'


def main():
    input_path = '/Users/piolo/Desktop/venue-scraper/data/processed/sentence_dataset.csv'
    output_path = input_path

    rows = []

    with open(input_path, newline='', encoding='utf-8') as f:
        reader = csv.reader(f, quoting=csv.QUOTE_MINIMAL)
        for i, row in enumerate(reader):
            if i == 0:
                # Header row — keep as-is
                rows.append(row)
                continue

            # Corrupted rows have more than 5 columns (two data rows fused).
            # Use cols 0-3 as our fields; label the sentence in col 3 fresh.
            if len(row) < 2:
                rows.append(row)
                continue

            if len(row) == 2:
                # Bare fragment: [sentence_fragment, label]
                sentence = row[0]
                new_label = label_sentence(sentence)
                rows.append([row[0], new_label])
                continue

            # Normal case (5 cols) OR corrupted/merged case (>5 cols):
            # Always use first 4 columns and re-label sentence (col 3).
            venue_id   = row[0]
            venue_name = row[1]
            source_url = row[2]
            sentence   = row[3]
            new_label  = label_sentence(sentence)

            rows.append([venue_id, venue_name, source_url, sentence, new_label])

    # Write back
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
        writer.writerows(rows)

    # Sanity report
    labeled_counts = {}
    unlabeled_count = 0
    for row in rows[1:]:
        lbl = row[-1] if row else '?'
        if lbl == 'UNLABELED':
            unlabeled_count += 1
        labeled_counts[lbl] = labeled_counts.get(lbl, 0) + 1

    print(f"Done. Data rows processed: {len(rows) - 1}")
    print(f"Still UNLABELED: {unlabeled_count}")
    print("Label distribution:")
    for lbl, cnt in sorted(labeled_counts.items()):
        print(f"  {lbl}: {cnt}")


if __name__ == '__main__':
    main()
