// Ground-truth review tool backend. Deliberately file-based (no SQLite:
// this project's stack claim is C++17/Python/TypeScript, and a database
// would be the wrong tool for a few hundred small JSON label files).
//
// GET  /api/segments               -> [{segmentId, numAgents, numSteps, dtS}]
// GET  /api/segments/:id           -> render data (agent types + coarse
//                                      sampled positions), never the
//                                      planted ground truth: an annotator
//                                      labels from the same trajectory data
//                                      a real reviewer would see.
// GET  /api/segments/:id/labels?annotator=x -> stored label list (or [])
// POST /api/segments/:id/labels    -> body {annotator, events: Label[]},
//                                      overwrites that annotator's file
import express from "express";
import fs from "fs";
import path from "path";

export interface Label {
  agentA: number;
  agentB: number;
  eventClass: string;
  startStep: number;
  endStep: number;
}

const DATA_DIR = process.env.REVIEW_TOOL_DATA_DIR || path.join(__dirname, "..", "..", "data");
const RENDER_DIR = path.join(DATA_DIR, "render");
const LABELS_DIR = path.join(DATA_DIR, "labels");

function ensureDir(p: string) {
  fs.mkdirSync(p, { recursive: true });
}

function listSegmentIds(): number[] {
  if (!fs.existsSync(RENDER_DIR)) return [];
  return fs
    .readdirSync(RENDER_DIR)
    .filter((f) => f.endsWith(".json"))
    .map((f) => parseInt(f.replace(".json", ""), 10))
    .sort((a, b) => a - b);
}

function labelPath(segmentId: number, annotator: string): string {
  const safeAnnotator = annotator.replace(/[^a-zA-Z0-9_-]/g, "");
  return path.join(LABELS_DIR, `${segmentId}__${safeAnnotator}.json`);
}

export function createApp(): express.Express {
  const app = express();
  app.use(express.json({ limit: "5mb" }));
  app.use(express.static(path.join(__dirname, "..", "..", "frontend")));

  app.get("/api/segments", (_req, res) => {
    const ids = listSegmentIds();
    const out = ids.map((id) => {
      const render = JSON.parse(fs.readFileSync(path.join(RENDER_DIR, `${id}.json`), "utf-8"));
      return { segmentId: id, numAgents: render.agents.length, numSteps: render.numSteps, dtS: render.dtS };
    });
    res.json(out);
  });

  app.get("/api/segments/:id", (req, res) => {
    const id = parseInt(req.params.id, 10);
    const file = path.join(RENDER_DIR, `${id}.json`);
    if (!fs.existsSync(file)) {
      res.status(404).json({ error: "segment not found" });
      return;
    }
    res.json(JSON.parse(fs.readFileSync(file, "utf-8")));
  });

  app.get("/api/segments/:id/labels", (req, res) => {
    const id = parseInt(req.params.id, 10);
    const annotator = String(req.query.annotator || "default");
    const file = labelPath(id, annotator);
    if (!fs.existsSync(file)) {
      res.json([]);
      return;
    }
    res.json(JSON.parse(fs.readFileSync(file, "utf-8")));
  });

  app.post("/api/segments/:id/labels", (req, res) => {
    const id = parseInt(req.params.id, 10);
    const { annotator, events } = req.body as { annotator: string; events: Label[] };
    if (!annotator || !Array.isArray(events)) {
      res.status(400).json({ error: "expected {annotator, events[]}" });
      return;
    }
    ensureDir(LABELS_DIR);
    fs.writeFileSync(labelPath(id, annotator), JSON.stringify(events, null, 2));
    res.json({ ok: true, segmentId: id, annotator, count: events.length });
  });

  return app;
}

if (require.main === module) {
  const app = createApp();
  const requestedPort = process.env.PORT ? parseInt(process.env.PORT, 10) : 0;
  const server = app.listen(requestedPort, () => {
    const addr = server.address();
    const port = typeof addr === "object" && addr ? addr.port : requestedPort;
    // eslint-disable-next-line no-console
    console.log(`LISTENING_PORT=${port}`);
  });
}
