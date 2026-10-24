import { test } from "node:test";
import assert from "node:assert/strict";
import { explainOffline, likelyFilesOffline, setupCommands, missingMentionedFiles } from "../src/mentor.js";

const paths = [
  "package.json", "tsconfig.json", "next.config.js", "src/components/Button.tsx", "src/components/DarkModeToggle.tsx",
  "src/lib/theme.ts", "tests/Button.test.tsx", "docs/intro.md", ".github/workflows/ci.yml", "pnpm-lock.yaml",
];

test("offline likely files only returns real paths that match the issue", () => {
  const files = likelyFilesOffline("Dark mode toggle button has wrong theme color", paths);
  assert.ok(files.length > 0);
  assert.ok(files.every((f) => paths.includes(f.path) && f.verified));
  assert.equal(files[0].path, "src/components/DarkModeToggle.tsx");
  assert.ok(!files.some((f) => f.path.startsWith("tests/")));
});

test("setup commands are pulled from fenced code blocks", () => {
  const readme = "## Dev\n```bash\n$ pnpm install\npnpm dev\necho hi\n```\n```sh\nnpm test\n```";
  assert.deepEqual(setupCommands(readme), ["pnpm install", "pnpm dev", "npm test"]);
});

test("offline explanation works with no AI and never invents files", () => {
  const ex = explainOffline({
    meta: { description: "A tiny UI kit", language: "TypeScript" },
    readme: "# ui-kit\n\n[![badge](x)](y)\n\nA small React component library for dashboards.\n\n```bash\npnpm install\n```",
    contributing: "", contributingPath: undefined, paths,
    issue: { title: "Button color wrong in dark mode", body: "<!-- template -->The button is invisible.", labels: [{ name: "good first issue" }] },
  });
  assert.equal(ex.offline, true);
  assert.match(ex.what_it_does, /React component library/);
  assert.ok(ex.tech_stack.includes("Next.js") && ex.tech_stack.includes("TypeScript"));
  assert.deepEqual(ex.how_to_run, ["pnpm install"]);
  assert.ok(ex.folder_map.some((f) => f.path === "src/" && /source/i.test(f.purpose)));
  assert.equal(ex.difficulty, "easy");
  assert.ok(!ex.issue_in_plain_words.includes("<!--"));
  assert.equal(ex.questions.length, 0);
});


test("flags files the issue links to that no longer exist", () => {
  const body = "See https://github.com/videojs/video.js/blob/master/src/js/media/html5.js#L213 and https://github.com/x/y/blob/main/src/lib/theme.ts";
  assert.deepEqual(missingMentionedFiles(body, ["src/lib/theme.ts"]), ["src/js/media/html5.js"]);
});
