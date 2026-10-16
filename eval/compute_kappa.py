"""Cohen's kappa for the 120 double-labeled segments: self-agreement
between annotator_1 and annotator_2.

Item construction (disclosed, not a standard off-the-shelf kappa call):
one item per planted ground-truth instance (known from the generator, not
reconstructed from the labels), so that "both annotators correctly stayed
silent" counts as an agreement, the same as "both annotators labeled it".
An early version of this script built items only from the union of
asserted labels, which silently dropped every true both-missed item and
measured a kappa that was actually mostly an artifact of that omission
(always negative, regardless of how correlated the two annotators' miss
patterns actually were); that is why this version takes the corpus file
too, not just the two label directories. A spurious label from either
annotator that matches no planted instance becomes its own extra item,
rated 1 for its author and 0 for the other annotator (unless, as will
essentially never happen by construction, the other annotator happens to
have an unrelated spurious label at the same pair/class/time).

Usage: python3 compute_kappa.py <corpus.json> <labels_dir> <double_labeled_ids.json>
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "generator"))
from scenario import read_corpus  # noqa: E402

MATCH_WINDOW_STEPS = 15


def load_annotator_labels(labels_dir: Path, segment_id: int, annotator: str):
    f = labels_dir / f"{segment_id}__{annotator}.json"
    if not f.exists():
        return []
    return json.loads(f.read_text())


def pair_key(a, b):
    return (min(a, b), max(a, b))


def label_matches_event(label, ev):
    if pair_key(label["agentA"], label["agentB"]) != pair_key(ev.agent_a, ev.agent_b):
        return False
    if label["eventClass"] != ev.event_class:
        return False
    midpoint = (label["startStep"] + label["endStep"]) / 2.0
    return abs(midpoint - ev.t_center) <= MATCH_WINDOW_STEPS


def build_items(seg, labels_1, labels_2):
    items = []
    used_1, used_2 = [False] * len(labels_1), [False] * len(labels_2)

    for ev in seg.planted_events:
        rating_1 = 0
        for i, lbl in enumerate(labels_1):
            if not used_1[i] and label_matches_event(lbl, ev):
                used_1[i] = True
                rating_1 = 1
                break
        rating_2 = 0
        for j, lbl in enumerate(labels_2):
            if not used_2[j] and label_matches_event(lbl, ev):
                used_2[j] = True
                rating_2 = 1
                break
        items.append((rating_1, rating_2))

    for i, lbl in enumerate(labels_1):
        if not used_1[i]:
            items.append((1, 0))
    for j, lbl in enumerate(labels_2):
        if not used_2[j]:
            items.append((0, 1))
    return items


def cohens_kappa(items):
    n = len(items)
    if n == 0:
        return 0.0, 0.0, 0.0
    agree = sum(1 for r1, r2 in items if r1 == r2)
    po = agree / n
    p1_rate1 = sum(r1 for r1, _ in items) / n
    p2_rate1 = sum(r2 for _, r2 in items) / n
    pe = p1_rate1 * p2_rate1 + (1 - p1_rate1) * (1 - p2_rate1)
    kappa = 1.0 if pe == 1.0 else (po - pe) / (1 - pe)
    return kappa, po, pe


def main():
    corpus_path = Path(sys.argv[1])
    labels_dir = Path(sys.argv[2])
    double_ids_path = Path(sys.argv[3])
    double_ids = json.loads(double_ids_path.read_text())

    segments_by_id = {s.segment_id: s for s in read_corpus(str(corpus_path))}

    all_items = []
    for seg_id in double_ids:
        seg = segments_by_id[seg_id]
        l1 = load_annotator_labels(labels_dir, seg_id, "annotator_1")
        l2 = load_annotator_labels(labels_dir, seg_id, "annotator_2")
        all_items.extend(build_items(seg, l1, l2))

    kappa, po, pe = cohens_kappa(all_items)
    print(f"segments={len(double_ids)} items={len(all_items)}")
    print(f"observed_agreement={po:.4f} expected_agreement={pe:.4f}")
    print(f"COHENS_KAPPA={kappa:.4f}")


if __name__ == "__main__":
    main()
