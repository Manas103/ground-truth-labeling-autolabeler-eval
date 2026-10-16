"""Collects the review tool's per-segment, per-annotator JSON label files
into one flat TSV the C++ scorer reads, same schema as the autolabeler's
predicted_events.tsv.

Usage: python3 collect_ground_truth.py <labels_dir> <annotator> <out.tsv>
"""
import json
import re
import sys
from pathlib import Path


def main():
    labels_dir, annotator, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
    pattern = re.compile(rf"^(\d+)__{re.escape(annotator)}\.json$")

    rows = []
    for f in sorted(Path(labels_dir).glob(f"*__{annotator}.json")):
        m = pattern.match(f.name)
        if not m:
            continue
        segment_id = int(m.group(1))
        events = json.loads(f.read_text())
        for ev in events:
            rows.append((segment_id, ev["agentA"], ev["agentB"], ev["eventClass"], ev["startStep"],
                         ev["endStep"]))

    rows.sort()
    with open(out_path, "w") as f:
        f.write("segment_id\tagent_a\tagent_b\tevent_class\tstart_step\tend_step\n")
        for r in rows:
            f.write("\t".join(str(x) for x in r) + "\n")

    print(f"collected {len(rows)} labels from annotator '{annotator}' -> {out_path}")


if __name__ == "__main__":
    main()
