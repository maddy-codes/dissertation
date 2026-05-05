import fs from "node:fs/promises";
import path from "node:path";
import pw from "/Users/jatinarora/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.js";

const { chromium } = pw;

const ROOT = process.cwd();
const SOURCE_DIR = path.join(ROOT, "dissertation_material", "mermaid");
const OUTPUT_DIR = path.join(ROOT, "dissertation_material", "figures");
const CHROME_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";

const diagramFiles = [
  "architecture_diagram.mmd",
  "ui_flow_diagram.mmd",
  "data_pipeline_lifecycle.mmd",
  "provenance_trace.mmd",
  "privacy_controls_flow.mmd",
  "evaluation_workflow.mmd",
];

function buildHtml(diagramCode) {
  return `<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <style>
      html, body {
        margin: 0;
        padding: 0;
        background: #ffffff;
        font-family: "Inter", "Helvetica Neue", Arial, sans-serif;
      }

      #frame {
        display: inline-block;
        padding: 28px;
        background: #ffffff;
      }

      svg {
        max-width: none;
        height: auto;
      }
    </style>
  </head>
  <body>
    <div id="frame"></div>
    <script type="module">
      import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";

      mermaid.initialize({
        startOnLoad: false,
        securityLevel: "loose",
        theme: "neutral",
        fontFamily: "Inter, Helvetica Neue, Arial, sans-serif",
        flowchart: { useMaxWidth: false, htmlLabels: true, curve: "basis" },
        sequence: { useMaxWidth: false },
      });

      const code = ${JSON.stringify(diagramCode)};
      const { svg } = await mermaid.render("diagramRoot", code);
      document.getElementById("frame").innerHTML = svg;
      document.body.dataset.rendered = "true";
    </script>
  </body>
</html>`;
}

async function renderDiagram(page, sourcePath, outputPath) {
  const code = await fs.readFile(sourcePath, "utf8");
  await page.setContent(buildHtml(code), { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => document.body.dataset.rendered === "true", null, { timeout: 20000 });
  await page.waitForSelector("svg", { timeout: 20000 });
  await page.locator("#frame").screenshot({ path: outputPath });
}

async function main() {
  await fs.mkdir(OUTPUT_DIR, { recursive: true });
  const browser = await chromium.launch({
    headless: true,
    executablePath: CHROME_PATH,
  });
  const page = await browser.newPage({
    viewport: { width: 1600, height: 1200 },
    deviceScaleFactor: 2,
  });

  try {
    for (const filename of diagramFiles) {
      const sourcePath = path.join(SOURCE_DIR, filename);
      const outputPath = path.join(OUTPUT_DIR, filename.replace(".mmd", ".png"));
      await renderDiagram(page, sourcePath, outputPath);
      console.log(`Rendered ${path.basename(outputPath)}`);
    }
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
