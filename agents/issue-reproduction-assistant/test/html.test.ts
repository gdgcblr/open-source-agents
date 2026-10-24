import assert from "node:assert/strict";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { test } from "node:test";
import { escapeHtml, extractRoutes, renderReportHtml } from "../src/html.js";
import { investigate } from "../src/pipeline.js";
import { detectSetup } from "../src/setup.js";

async function webRepo(): Promise<string> {
  const root = await mkdtemp(path.join(os.tmpdir(), "repro-html-"));
  await mkdir(path.join(root, "src"));
  await writeFile(
    path.join(root, "package.json"),
    JSON.stringify({ scripts: { dev: "astro dev", build: "astro build" }, dependencies: { astro: "^5" } }),
  );
  await writeFile(path.join(root, "package-lock.json"), "{}");
  await writeFile(path.join(root, "src", "gallery.ts"), "export const shot = '/images/missing.png';\n");
  return root;
}

test("detectSetup finds package manager, run command and default URL", async () => {
  const root = await webRepo();
  try {
    const setup = await detectSetup(root);
    assert.equal(setup.installCommand, "npm ci");
    assert.equal(setup.runCommand, "npm run dev");
    assert.equal(setup.framework, "Astro");
    assert.equal(setup.defaultUrl, "http://localhost:4321");
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("HTML report has from-scratch steps and escapes untrusted text", async () => {
  const root = await webRepo();
  try {
    const issueText = "# Broken image <script>alert(1)</script>\nThe image at `/images/missing.png` shows 404 on page `/gallery`.";
    const investigation = await investigate({ issueText, repositoryPath: root });
    const html = renderReportHtml(investigation, {
      title: "Broken image <script>alert(1)</script>",
      repoUrl: "https://github.com/o/r",
      commit: "abc1234567",
      issueText,
    });
    assert.ok(!html.includes("<script>alert"));
    assert.match(html, /git clone https:\/\/github\.com\/o\/r\.git/);
    assert.match(html, /npm ci/);
    assert.match(html, /http:\/\/localhost:4321\/gallery/);
    assert.match(html, /Network tab/);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("extractRoutes and escapeHtml", () => {
  assert.deepEqual(extractRoutes("see `/learnt` and `src/x.ts` and `/a/b.png`"), ["/learnt", "/a/b.png"]);
  assert.equal(escapeHtml(`<a href="x">&'`), "&lt;a href=&quot;x&quot;&gt;&amp;&#39;");
});
