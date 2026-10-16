"""CLI: generate the synthetic driving-segment corpus.

Usage: python3 make_corpus.py <out.json> [num_segments=600] [seed=1]
"""
import sys

from scenario import generate_corpus, write_corpus, EVENT_CLASSES


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else "data/corpus.json"
    num_segments = int(sys.argv[2]) if len(sys.argv) > 2 else 600
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else 1

    segments = generate_corpus(num_segments, seed)
    write_corpus(segments, out_path)

    counts = {c: 0 for c in EVENT_CLASSES}
    for seg in segments:
        for ev in seg.planted_events:
            counts[ev.event_class] += 1

    print(f"wrote {len(segments)} segments to {out_path}")
    for c in EVENT_CLASSES:
        print(f"  {c}: {counts[c]} planted instances")


if __name__ == "__main__":
    main()
