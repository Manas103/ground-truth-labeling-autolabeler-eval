interface RenderAgent {
  id: number;
  type: string;
  // coarse-sampled [x, y] positions, one every renderStrideSteps steps
  positions: [number, number][];
}

interface RenderSegment {
  segmentId: number;
  dtS: number;
  numSteps: number;
  renderStrideSteps: number;
  agents: RenderAgent[];
}

interface Label {
  agentA: number;
  agentB: number;
  eventClass: string;
  startStep: number;
  endStep: number;
}

const segmentSelect = document.getElementById("segmentSelect") as HTMLSelectElement;
const annotatorInput = document.getElementById("annotatorInput") as HTMLInputElement;
const stepSlider = document.getElementById("stepSlider") as HTMLInputElement;
const stepLabel = document.getElementById("stepLabel") as HTMLSpanElement;
const canvas = document.getElementById("canvas") as HTMLCanvasElement;
const ctx = canvas.getContext("2d")!;
const labelListEl = document.getElementById("labelList") as HTMLUListElement;
const saveStatus = document.getElementById("saveStatus") as HTMLSpanElement;

let currentSegment: RenderSegment | null = null;
let currentLabels: Label[] = [];

function worldToCanvas(x: number, y: number): [number, number] {
  // fixed, generous world window; good enough for a review tool, not a
  // production HUD: the segments in this corpus stay within +-400m x, +-40m y.
  const px = ((x + 400) / 800) * canvas.width;
  const py = canvas.height / 2 - y * 4;
  return [px, py];
}

function stepToSampleIndex(step: number, strideSteps: number): number {
  return Math.min(Math.round(step / strideSteps), 999999);
}

function render() {
  if (!currentSegment) return;
  const step = parseInt(stepSlider.value, 10);
  stepLabel.textContent = String(step);
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  for (const agent of currentSegment.agents) {
    const idx = Math.min(stepToSampleIndex(step, currentSegment.renderStrideSteps), agent.positions.length - 1);
    const [x, y] = agent.positions[idx];
    const [px, py] = worldToCanvas(x, y);
    ctx.beginPath();
    ctx.fillStyle = agent.type === "cyclist" ? "#c0392b" : "#2980b9";
    ctx.arc(px, py, 5, 0, 2 * Math.PI);
    ctx.fill();
    ctx.fillStyle = "#000";
    ctx.fillText(String(agent.id), px + 6, py - 6);
  }

  labelListEl.innerHTML = "";
  for (const [i, lbl] of currentLabels.entries()) {
    const li = document.createElement("li");
    li.textContent = `[${i}] ${lbl.eventClass} agents=(${lbl.agentA},${lbl.agentB}) steps=[${lbl.startStep},${lbl.endStep}]`;
    labelListEl.appendChild(li);
  }
}

async function loadSegmentList() {
  const resp = await fetch("/api/segments");
  const segments: { segmentId: number }[] = await resp.json();
  segmentSelect.innerHTML = "";
  for (const s of segments) {
    const opt = document.createElement("option");
    opt.value = String(s.segmentId);
    opt.textContent = `segment ${s.segmentId}`;
    segmentSelect.appendChild(opt);
  }
}

async function loadSegment(segmentId: number) {
  const [segResp, labelsResp] = await Promise.all([
    fetch(`/api/segments/${segmentId}`),
    fetch(`/api/segments/${segmentId}/labels?annotator=${encodeURIComponent(annotatorInput.value)}`),
  ]);
  currentSegment = await segResp.json();
  currentLabels = await labelsResp.json();
  stepSlider.max = String(currentSegment!.numSteps - 1);
  stepSlider.value = "0";
  render();
}

segmentSelect.addEventListener("change", () => loadSegment(parseInt(segmentSelect.value, 10)));
stepSlider.addEventListener("input", render);
annotatorInput.addEventListener("change", () => {
  if (currentSegment) loadSegment(currentSegment.segmentId);
});

document.getElementById("addLabelBtn")!.addEventListener("click", () => {
  const eventClassSelect = document.getElementById("eventClassSelect") as HTMLSelectElement;
  const agentAInput = document.getElementById("agentAInput") as HTMLInputElement;
  const agentBInput = document.getElementById("agentBInput") as HTMLInputElement;
  const startStepInput = document.getElementById("startStepInput") as HTMLInputElement;
  const endStepInput = document.getElementById("endStepInput") as HTMLInputElement;

  currentLabels.push({
    eventClass: eventClassSelect.value,
    agentA: parseInt(agentAInput.value, 10),
    agentB: parseInt(agentBInput.value, 10),
    startStep: parseInt(startStepInput.value, 10),
    endStep: parseInt(endStepInput.value, 10),
  });
  render();
});

document.getElementById("saveLabelsBtn")!.addEventListener("click", async () => {
  if (!currentSegment) return;
  const resp = await fetch(`/api/segments/${currentSegment.segmentId}/labels`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ annotator: annotatorInput.value, events: currentLabels }),
  });
  const body = await resp.json();
  saveStatus.textContent = resp.ok ? `saved ${body.count} labels` : `error: ${body.error}`;
});

async function main() {
  await loadSegmentList();
  if (segmentSelect.options.length > 0) {
    await loadSegment(parseInt(segmentSelect.value, 10));
  }
}

main();
