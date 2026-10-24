import assert from "node:assert/strict";
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { afterEach, test } from "node:test";
import { collectRepositoryContext, redactSensitiveContent } from "../src/repository-context.js";

const temporaryDirectories: string[] = [];

async function createFixture(): Promise<string> {
  const root = await mkdtemp(path.join(os.tmpdir(), "issue-repro-test-"));
  temporaryDirectories.push(root);
  return root;
}

afterEach(async () => {
  await Promise.all(
    temporaryDirectories.splice(0).map((directory) =>
      rm(directory, { recursive: true, force: true }),
    ),
  );
});

test("collects relevant source files but skips hidden, generated, and secret files", async () => {
  const root = await createFixture();
  await mkdir(path.join(root, "src"));
  await mkdir(path.join(root, "node_modules", "library"), { recursive: true });
  await mkdir(path.join(root, ".private"));
  await writeFile(path.join(root, "src", "cache.ts"), "export function cache() { return true; }");
  await writeFile(path.join(root, "src", "unrelated.ts"), "export const unrelated = 1;");
  await writeFile(path.join(root, "src", "credentials.json"), '{"password":"do-not-send"}');
  await writeFile(path.join(root, ".private", "notes.md"), "hidden data");
  await writeFile(path.join(root, "node_modules", "library", "index.js"), "vendor code");

  const files = await collectRepositoryContext(root, "cache is stale");
  const paths = files.map((file) => file.path);

  assert.ok(paths.includes(path.join("src", "cache.ts")));
  assert.ok(!paths.some((filePath) => filePath.includes("credentials")));
  assert.ok(!paths.some((filePath) => filePath.includes(".private")));
  assert.ok(!paths.some((filePath) => filePath.includes("node_modules")));
});

test("redacts common credentials from selected text", () => {
  const content = [
    'API_KEY="super-secret-value-123"',
    "Authorization: Bearer abcdefghijklmnopqrstuvwxyz",
    "ghp_abcdefghijklmnopqrstuvwxyz0123456789",
  ].join("\n");

  const redacted = redactSensitiveContent(content);

  assert.match(redacted, /\[REDACTED\]/);
  assert.doesNotMatch(redacted, /super-secret-value-123/);
  assert.doesNotMatch(redacted, /abcdefghijklmnopqrstuvwxyz/);
});

test("rejects a non-directory repository path", async () => {
  const root = await createFixture();
  const filePath = path.join(root, "file.txt");
  await writeFile(filePath, "not a directory");

  await assert.rejects(
    collectRepositoryContext(filePath, "bug"),
    /Repository path is not a directory/,
  );
});
