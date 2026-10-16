"""CLI: run the autolabeler over the corpus, write predicted events as TSV.

Usage: python3 run_autolabeler.py <corpus.json> <out_predicted_events.tsv>
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "generator"))
from scenario import read_corpus  # noqa: E402
from rules import mine_segment  # noqa: E402


def main():
    corpus_path, out_path = sys.argv[1], sys.argv[2]
    segments = read_corpus(corpus_path)

    total = 0
    with open(out_path, "w") as f:
        f.write("segment_id\tagent_a\tagent_b\tevent_class\tstart_step\tend_step\n")
        for seg in segments:
            for ev in mine_segment(seg):
                f.write(f"{seg.segment_id}\t{ev['agent_a']}\t{ev['agent_b']}\t{ev['event_class']}\t"
                        f"{ev['start_step']}\t{ev['end_step']}\n")
                total += 1
    print(f"mined {total} predicted events from {len(segments)} segments -> {out_path}")


if __name__ == "__main__":
    main()
