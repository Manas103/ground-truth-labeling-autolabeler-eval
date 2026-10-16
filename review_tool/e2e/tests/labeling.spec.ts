// Loads the real built review-tool frontend behind the real backend over
// real HTTP, in Playwright's bundled Chromium (headless, launched and
// closed by this test only). Starts the backend on an OS-assigned free
// port (PORT=0), never a fixed or "cleared" port, and stops it by the
// exact child-process handle this test itself spawned.
import { test, expect } from "@playwright/test";
import { ChildProcessWithoutNullStreams, spawn } from "child_process";
import path from "path";

let serverProcess: ChildProcessWithoutNullStreams;
let baseUrl: string;

test.beforeAll(async () => {
  const backendDir = path.resolve(__dirname, "..", "..", "backend");
  serverProcess = spawn("node", ["dist/server.js"], {
    cwd: backendDir,
    env: { ...process.env, PORT: "0", REVIEW_TOOL_DATA_DIR: path.resolve(__dirname, "..", "..", "data") },
  });

  baseUrl = await new Promise<string>((resolve, reject) => {
    let buf = "";
    const onData = (chunk: Buffer) => {
      buf += chunk.toString();
      const m = buf.match(/LISTENING_PORT=(\d+)/);
      if (m) {
        serverProcess.stdout.off("data", onData);
        resolve(`http://127.0.0.1:${m[1]}`);
      }
    };
    serverProcess.stdout.on("data", onData);
    serverProcess.stderr.on("data", (d) => process.stderr.write(d));
    serverProcess.on("error", reject);
    setTimeout(() => reject(new Error("backend did not report a port in time")), 15_000);
  });
});

test.afterAll(async () => {
  serverProcess.kill();
});

test("a reviewer can load a segment, add a label, and save it", async ({ page }) => {
  await page.goto(baseUrl);

  const segmentSelect = page.locator("#segmentSelect");
  await expect(segmentSelect.locator("option")).not.toHaveCount(0);

  // Set the annotator before selecting the segment: loadSegment() fetches
  // that annotator's existing labels at select-time. A unique name per
  // run (not a fixed "e2e_annotator") avoids colliding with a label file
  // a previous run of this same test left on disk (review_tool/data/labels
  // is real, gitignored, scratch storage, not reset between runs).
  const annotatorName = `e2e_annotator_${Date.now()}`;
  await page.fill("#annotatorInput", annotatorName);
  await page.selectOption("#segmentSelect", "1");

  await page.selectOption("#eventClassSelect", "hard_brake");
  await page.fill("#agentAInput", "2");
  await page.fill("#agentBInput", "2");
  await page.fill("#startStepInput", "100");
  await page.fill("#endStepInput", "110");
  await page.click("#addLabelBtn");

  await expect(page.locator("#labelList li")).toHaveCount(1);
  await expect(page.locator("#labelList li").first()).toContainText("hard_brake");

  await page.click("#saveLabelsBtn");
  await expect(page.locator("#saveStatus")).toContainText("saved 1 labels");

  const resp = await page.request.get(`${baseUrl}/api/segments/1/labels?annotator=${annotatorName}`);
  const labels = await resp.json();
  expect(labels).toEqual([{ agentA: 2, agentB: 2, eventClass: "hard_brake", startStep: 100, endStep: 110 }]);
});

test("the canvas renders agent markers at the selected step", async ({ page }) => {
  await page.goto(baseUrl);
  await page.selectOption("#segmentSelect", "2");
  await page.waitForTimeout(200);

  const canvas = page.locator("#canvas");
  await expect(canvas).toBeVisible();

  const coloredPixelCount = await page.evaluate(() => {
    const c = document.getElementById("canvas") as HTMLCanvasElement;
    const ctx = c.getContext("2d")!;
    const data = ctx.getImageData(0, 0, c.width, c.height).data;
    let coloredPixels = 0;
    for (let i = 0; i < data.length; i += 4) {
      if (data[i] !== 0 || data[i + 1] !== 0 || data[i + 2] !== 0) coloredPixels++;
    }
    return coloredPixels;
  });
  expect(coloredPixelCount).toBeGreaterThan(0);
});
