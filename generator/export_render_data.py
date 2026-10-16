"""Exports coarse-sampled agent positions (no event labels: the review
tool's annotator sees trajectories, never the planted ground truth) for
the review tool's backend to serve statically.

Usage: python3 export_render_data.py <corpus.json> <out_render_dir> [stride_steps=5]
"""
import json
import sys
from pathlib import Path

from scenario import read_corpus, pose_at_with_wobble


def main():
    corpus_path, out_dir = sys.argv[1], sys.argv[2]
    stride = int(sys.argv[3]) if len(sys.argv) > 3 else 5

    segments = read_corpus(corpus_path)
    Path(out_dir).mkdir(parents=True, exist_ok=True)

    for seg in segments:
        agents_out = []
        for a in seg.agents:
            positions = []
            for t in range(0, seg.num_steps, stride):
                x, y, _heading, _speed = pose_at_with_wobble(a, t, seg.dt_s)
                positions.append([round(x, 3), round(y, 3)])
            agents_out.append({"id": a.id, "type": a.type, "positions": positions})

        out = {
            "segmentId": seg.segment_id,
            "dtS": seg.dt_s,
            "numSteps": seg.num_steps,
            "renderStrideSteps": stride,
            "agents": agents_out,
        }
        with open(Path(out_dir) / f"{seg.segment_id}.json", "w") as f:
            json.dump(out, f)

    print(f"exported render data for {len(segments)} segments to {out_dir}")


if __name__ == "__main__":
    main()
