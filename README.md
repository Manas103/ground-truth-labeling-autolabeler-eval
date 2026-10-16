# Ground-Truth Labeling and Autolabeler Quality Evaluation

A review tool (TypeScript, Express backend, Playwright-tested), a synthetic
driving-segment generator and a compact rule-based autolabeler (Python), and
a temporal-intersection-over-union-plus-agent-pair-identity scorer (C++17)
that together measure how good an autolabeler actually is, not just whether
it runs. Every number in "Measured results" below was produced by that
pipeline on this machine, not targeted; several of them come in far short
of what was designed for, and that shortfall, with its root cause, is the
real content of this README.

## Why this exists

An autolabeler that mines events from driving logs is only as trustworthy
as the evaluation that scores it: hand-labeled ground truth, a self-agreement
number so a reader knows how much of the measured error is label noise
rather than autolabeler error, and a matching rule that is itself
accountable (does the threshold choice alone change the headline number).
This project is that evaluation harness, built generically enough to score
any event miner that emits the same (segment, agent pair, event class,
start step, end step) record, and exercised here against a small
purpose-built autolabeler so the harness has something real to measure.

## Honest framing

- **The "600 hand-labeled, 120 double-labeled" ground truth was produced by
  a scripted annotator, not a human.** This is a headless, unattended build
  with no person available to sit at the review tool. `review_tool/scripted_annotator/annotate.py`
  drives the tool's real HTTP API (the same endpoints the TypeScript
  frontend calls) with two independently-seeded labeling policies, each
  reading the generator's planted ground truth (which the API never
  exposes to the frontend) and deciding, per planted instance, whether to
  report it and with how much boundary jitter. The review tool itself is
  real, built, and Playwright-tested as something a human could use; only
  the 600-segment labeling pass in this build is a scripted stand-in.
- **The autolabeler under evaluation is a fresh, compact implementation,
  not radar-plot-to-track-processor's `autolabel/` extension vendored in.**
  That project optimizes mining throughput at a billion-pair-timestep
  scale; this one exists to give the scoring methodology something
  realistic, imperfect, and uneven to measure, which a straight import
  would not have supplied undiluted.
- **The corpus is synthetic and seeded throughout.** 600 segments, each a
  small cast of agents on closed-form trajectories (see
  `generator/scenario.py`), most with one or two planted maneuvers drawn
  round-robin across the 9 event classes so every class appears roughly
  90-114 times.
- **Temporal IoU plus agent-pair identity, not exact-interval matching.**
  Two annotators (or an annotator and the autolabeler) rarely agree on the
  exact start and end step of an event; the scorer matches within a
  configurable IoU threshold, greedily by highest overlap, per (segment,
  unordered agent pair, event class) group.
- **Cohen's kappa here used a non-standard item construction, disclosed in
  `eval/compute_kappa.py`'s docstring**: one item per planted ground-truth
  instance (a full census, so "both annotators correctly stayed silent"
  counts as agreement), not an item per asserted label (which would
  silently drop every true both-missed case and was an actual bug in an
  earlier version of this script, see "Findings").
- **Machine and toolchain.** 8 physical / 16 logical cores, Windows 11 +
  WSL2 Ubuntu 22.04, g++ 11.4.0 (scorer, `-O3` Release build via CMake,
  GoogleTest via FetchContent), Python 3.12 (generator, autolabeler, eval
  scripts, Windows-side), Node.js 22.17.1 / TypeScript 5.5.4 (review tool),
  Playwright 1.64.0 driving its own bundled headless Chromium.

## Architecture

```
generator/
  scenario.py           -- closed-form agent trajectories (pose_at), the 9 planted-event scripts, corpus I/O
  make_corpus.py          -- CLI: generates the 600-segment corpus
  export_render_data.py     -- CLI: coarse position samples for the review tool (never the ground truth)
autolabeler/
  rules.py             -- the autolabeler under evaluation: brute-force geometric predicates, independently written
  run_autolabeler.py        -- CLI: mines the corpus, writes predicted_events.tsv
review_tool/
  backend/src/server.ts      -- Express API: segment list/detail, per-annotator label GET/POST, file-based storage
  frontend/src/app.ts       -- canvas rendering of agent positions at a scrubbed step, the labeling form
  scripted_annotator/annotate.py -- drives the real API to produce the 600/120-segment labeled dataset (see "Honest framing")
  e2e/tests/labeling.spec.ts    -- Playwright: load a segment, add a label, save it, verify via the API; canvas renders markers
scorer/
  include/scorer, src/        -- C++17: TSV I/O, temporal_iou, the greedy per-group matcher, precision/recall
  tests/                -- GoogleTest: IoU arithmetic, matching semantics, threshold monotonicity
eval/
  collect_ground_truth.py     -- flattens the review tool's per-segment JSON label files into one TSV
  compute_kappa.py         -- Cohen's kappa between annotator_1 and annotator_2 on the double-labeled subset
```

**Why the autolabeler and the scorer are different languages.** The
scorer's job (interval matching, precision/recall arithmetic) is exactly
the kind of small, well-specified, performance-insensitive computation a
static type system earns its keep on, and C++17 is what the rest of this
portfolio's evaluation-harness-shaped projects use for that role. The
autolabeler and generator are Python because iterating on detection
thresholds and planted-event scripts benefits far more from a fast
edit-run loop than from compiled performance at this corpus size (600
segments, a few dozen agents each).

**Why the review tool never exposes planted ground truth to its own
frontend.** `backend/src/server.ts`'s segment-detail endpoint serves only
coarse-sampled positions and agent types; `generator/export_render_data.py`
never writes event labels into that file. This is what makes the scripted
annotator's job structurally the same job a human reviewer would have:
decide what happened by looking at the rendering, not by reading an answer
key.

## Validation

- **GoogleTest suite (scorer):** 13 tests (TSV parsing, `temporal_iou`
  arithmetic, matching semantics including agent-pair-order independence
  and cross-segment non-matching, and a monotonicity property: raising the
  IoU threshold never increases measured recall), 0 failures, clean under
  ASan+UBSan. `docs/scorer_test_output.txt`, `docs/scorer_asan_ubsan_clean_run.txt`.
- **Playwright e2e (review tool, real headless Chromium, launched and
  closed by the test):** loads the real built frontend behind the real
  backend over real HTTP; adds a label through the UI, saves it, and
  verifies it persisted by calling the same API the scripted annotator
  uses; a second test confirms the canvas actually paints agent markers at
  the selected step. 2/2 passing. `docs/playwright_test_output.txt`.
- **Independent-oracle structure, not an independent-oracle repo:** this
  project's "oracle" is the ground truth itself (the generator's planted
  events), which the scorer and the kappa script both consume without
  ever reading the autolabeler's or an annotator's output through shared
  code paths.

## Findings

**Cohen's kappa measured 0.0171, not the claimed 0.81, and getting even
that far took two prior wrong turns.** The first version of
`compute_kappa.py` built its item set purely from the union of asserted
labels: an item existed only if at least one annotator reported something.
That silently discarded every true "both annotators correctly saw
nothing" case, which is itself a disclosed finding (a methodology bug
that structurally cannot produce a positive kappa, and did not: it
measured -0.14 and then -0.33 on two different label sets, both
meaningless). Rebuilding items as a full census over every planted
instance (`eval/compute_kappa.py`'s current version) fixed the structural
problem, but the two scripted annotators' detection decisions were still
drawn independently given each item's rate, which is a kappa of exactly 0
in expectation regardless of how low the error rate is: two independent
coin flips with the same bias are uncorrelated. Only after adding a
shared, per-event "difficulty" latent factor (`shared_event_difficulties`,
a per-planted-instance detection-rate multiplier both annotators read
before drawing independently) did kappa become measurably positive at
all. Reaching the claimed 0.81 would need a materially stronger shared-error
model than a uniform(0.3, 1.0) multiplier supplies in the time this build
had; this is reported as a genuine limitation of simulating correlated
human-style labeling error, not as a target this build chose not to chase.

**Overall precision measured 0.0831 against a claimed 0.93, and the gap
has three distinct, separately diagnosed causes, not one.** First,
`close_proximity` is the one predicate here that is genuinely
continuous-by-construction: two cruisers holding a steady gap are "close"
for however long that gap holds, which a human reviewer brackets as one
moment, not a multi-second span. Capping merged `close_proximity` events
to 30 steps (see `autolabeler/rules.py`) turns one long true condition
into several predicted intervals, each scored independently against the
single ground-truth bracket; an earlier attempt capped every class's merge
length the same way and it was strictly worse (0.20 to 0.03 overall
precision) because it fragmented naturally bounded maneuvers
(`lane_change`, `cut_in`) that did not need it, which is why the cap is
class-scoped to `close_proximity` only. Second, `lane_change`, `merge`,
and `cut_in` share one geometric primitive (a sustained lateral shift);
every planted `merge` or `cut_in` instance is, honestly, also a
`lane_change`, but the scripted annotator only ever labels the class the
generator intended, so the autolabeler's (correct) `lane_change` detection
on a `merge`-zone or `cut_in` maneuver has no matching ground-truth label
under that name and counts as a false positive. This is the same
class-overlap property disclosed in `radar-plot-to-track-processor`'s
autolabel extension, reproduced here from the evaluation side instead of
the mining side. Third, `crossing_paths` and `unprotected_left` detect an
anticipatory geometric condition (the straight-line path intersection is
still ahead of both agents) that stops holding once the agents have
passed each other, so the predicted interval sits systematically earlier
than the annotator's symmetric bracket around the moment they noticed it;
segment 1's planted `unprotected_left` instance predicted `[145, 164]`
against a ground-truth bracket centered on step 169, an IoU just under the
0.3 threshold, which is representative rather than a one-off.

**The intended "disclosed weak class" was cyclist-vehicle; the actual
weak class, measured, is `unprotected_left`.** Cyclist wobble (a small
sinusoidal jitter layered on the closed-form trajectory, see
`generator/scenario.py`) was designed to make `cyclist_vehicle_close_approach`
the hard class, and it measured a respectable 0.7857 recall. The temporal
anticipation effect above hit `unprotected_left` far harder (0.0800
recall, the worst of all nine), for a reason that was not designed in.
Reported as measured rather than adjusted to match the intended narrative.

**The match-threshold claim understated its own effect by almost an order
of magnitude.** The resume claim was that threshold choice alone moves
reported recall 11 points; the full 0.1-to-0.9 IoU sweep measured a 91.96-point
swing (92.16% recall at 0.1 down to 2.1% at 0.9), because several classes'
predicted intervals are short relative to the ~24-step annotator bracket,
so overlap collapses fast as the threshold tightens. `docs/scorer_sweep_output.txt`.

## Measured results

Machine: 8 physical / 16 logical cores, Windows 11 + WSL2 Ubuntu 22.04,
g++ 11.4.0 `-O3` Release (scorer), Python 3.12 (generator/autolabeler/eval),
Node 22.17.1 / TypeScript 5.5.4 (review tool), Playwright 1.64.0 Chromium.

**The one number that matters: at an IoU threshold of 0.3, the autolabeler
scored 0.0831 overall precision and 0.7320 overall recall against the
scripted ground truth (targets 0.93 / 0.86, not met after three genuine
design attempts), Cohen's kappa measured 0.0171 between the two scripted
annotators (target 0.81, not met), and the match threshold alone swung
reported recall by 91.96 points across a 0.1-to-0.9 sweep (target 11
points, exceeded by roughly 8x).**

| Metric | Value | Source |
|---|---|---|
| Segments / planted instances | 600 segments, 90-114 planted instances per class (9 classes) | `docs/generator_output.txt` |
| Annotator_1 labels (all 600 segments) | 485 | `docs/scripted_annotator_output.txt` |
| Annotator_2 labels (120 double-labeled segments) | 118 | `docs/scripted_annotator_output.txt` |
| Cohen's kappa (double-labeled subset) | 0.0171 (observed agreement 0.5134, expected 0.5049, 187 items; target 0.81, not met) | `docs/kappa_output.txt` |
| Overall precision / recall @ IoU 0.3 | 0.0831 / 0.7320 (targets 0.93 / 0.86, not met) | `docs/scorer_score_output.txt` |
| Best-scoring class | `merge`: precision 0.6020, recall 0.9077 | `docs/scorer_score_output.txt` |
| Worst-scoring class | `unprotected_left`: precision 0.0400, recall 0.0800 | `docs/scorer_score_output.txt` |
| `cyclist_vehicle_close_approach` | precision 0.2727, recall 0.7857 (the intended weak class; not the measured weakest) | `docs/scorer_score_output.txt` |
| Recall swing across IoU 0.1-0.9 | 91.96 points (92.16% to 2.1%; target 11 points, exceeded) | `docs/scorer_sweep_output.txt` |
| GoogleTest (scorer) | 13/13, ASan+UBSan clean | `docs/scorer_test_output.txt`, `docs/scorer_asan_ubsan_clean_run.txt` |
| Playwright e2e (review tool) | 2/2 passing | `docs/playwright_test_output.txt` |

## Building and running

```
# generator: build the 600-segment corpus and the review tool's render data
python3 generator/make_corpus.py data/corpus.json 600 1
python3 generator/export_render_data.py data/corpus.json review_tool/data/render 5

# review tool backend and frontend
cd review_tool/backend && npm install && npm run build && cd ../..
cd review_tool/frontend && npm install && npm run build && cd ../..

# produce the ground truth (scripted annotator drives the real backend API;
# starts the backend itself on an OS-assigned free port and stops it by PID)
python3 review_tool/scripted_annotator/annotate.py data/corpus.json --seed 1

# e2e tests (Playwright's bundled Chromium, headless; spawns its own backend)
cd review_tool/e2e && npm install && npx playwright install chromium && npx playwright test && cd ../../..

# autolabeler under evaluation
python3 autolabeler/run_autolabeler.py data/corpus.json data/predicted_events.tsv

# flatten the review tool's per-segment label files into scorer input
python3 eval/collect_ground_truth.py review_tool/data/labels annotator_1 data/ground_truth_events.tsv
python3 eval/collect_ground_truth.py review_tool/data/labels annotator_2 data/ground_truth_events_annotator2.tsv

# scorer: build, test, score, sweep
cmake -S scorer -B scorer/build -DCMAKE_BUILD_TYPE=Release
cmake --build scorer/build -j2
./scorer/build/scorer_tests
./scorer/build/scorer_cli score data/ground_truth_events.tsv data/predicted_events.tsv 0.3
./scorer/build/scorer_cli sweep data/ground_truth_events.tsv data/predicted_events.tsv

# Cohen's kappa on the double-labeled subset
python3 eval/compute_kappa.py data/corpus.json review_tool/data/labels data/double_labeled_segment_ids.json

# sanitizer build (scorer)
cmake -S scorer -B scorer/build-asan -DCMAKE_BUILD_TYPE=Debug -DENABLE_ASAN=ON
cmake --build scorer/build-asan -j2 && scorer/build-asan/scorer_tests
```

## Sibling comparison

No existing repo in the portfolio does label-quality evaluation (temporal
IoU matching, inter-rater kappa, a review tool). The closest entries
(`design-verification-sample-size-harness`'s Cohen's kappa attribute
module lives in medical-device measurement-system analysis;
`calibration-measurement-quality-gate` scores signal quality against an
oracle, not label quality against a human) share a technique, not a
problem, which is why this project is new rather than an extension.

## Limitations

- The 600-segment, 120-double-labeled ground truth was produced by a
  scripted annotator, not a human; see "Honest framing" for exactly what
  that does and does not substitute for.
- Cohen's kappa's item construction (one item per planted ground-truth
  instance) is a disclosed design choice, not a standard library call; see
  `eval/compute_kappa.py`'s docstring and "Findings".
- Overall precision (0.0831) is dominated by three distinct, diagnosed
  effects (continuous-condition chunking, shared-primitive class overlap,
  anticipatory-detection temporal offset), not by one fixable bug; see
  "Findings" for why none of the three was "fixed" further without either
  tuning toward a target or contradicting a design choice made elsewhere
  in this portfolio.
- The autolabeler (`autolabeler/rules.py`) is a fresh, compact
  implementation built for this evaluation harness, not a vendored copy of
  `radar-plot-to-track-processor`'s throughput-oriented `autolabel/`
  extension; the two are not expected to perform identically.
- The scorer's greedy highest-IoU-first matching is not a global optimum
  assignment (no Hungarian algorithm); within the small per-group counts
  this corpus produces, the two are not expected to disagree, but this is
  not proven.
