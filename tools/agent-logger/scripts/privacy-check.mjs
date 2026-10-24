import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { lstat, readFile } from 'node:fs/promises';
import { homedir, tmpdir } from 'node:os';
import { dirname, join, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const repository = execFileSync('git', ['rev-parse', '--show-toplevel'], {
  cwd: root,
  encoding: 'utf8',
}).trim();
const scope = relative(repository, root);
const listed = execFileSync(
  'git',
  ['ls-files', '-z', '--cached', '--others', '--exclude-standard', '--', scope],
  { cwd: repository, encoding: 'utf8' },
);
const deleted = new Set(
  execFileSync('git', ['ls-files', '-z', '--deleted', '--', scope], {
    cwd: repository,
    encoding: 'utf8',
  }).split('\0'),
);
const candidates = [...new Set(listed.split('\0').filter(Boolean))].filter(
  (path) => !deleted.has(path),
);
const localRoots = [homedir(), tmpdir(), repository].filter((value) => value.length > 1);
const secret = process.env.GOOGLE_API_KEY?.trim();
const machinePath = /\/(?:Users|home)\/[^\s"'`]+|[A-Za-z]:\\Users\\[^\s"'`]+/u;
const credential =
  /\b(?:AIza[A-Za-z0-9_-]{30,}|npm_[A-Za-z0-9]{30,}|ghp_[A-Za-z0-9]{30,}|sk-proj-[A-Za-z0-9_-]{30,})\b/u;

for (const path of candidates) {
  const local = relative(root, join(repository, path));
  assert.ok(
    !local.startsWith('..' + sep),
    'Candidate escaped the contribution directory.',
  );
  assert.ok(
    !/(^|\/)(?:node_modules|dist|test-dist|\.agent-logs|coverage)(\/|$)|\.(?:tgz|map|log|pem|key)$/u.test(
      local,
    ),
    `Local artifact is a Git candidate: ${local}`,
  );
  assert.ok(
    !/(^|\/)(?:\.env(?:\..*)?|\.envrc|\.npmrc(?:\..*)?)$/u.test(local) ||
      local === '.env.example',
    `Private configuration is a Git candidate: ${local}`,
  );
  const location = join(repository, path);
  const info = await lstat(location);
  assert.ok(
    info.isFile() && !info.isSymbolicLink() && info.size < 2 * 1024 * 1024,
    `Unexpected candidate type or size: ${local}`,
  );
  const content = await readFile(location, 'utf8');
  assert.ok(
    !localRoots.some((value) => content.includes(value)),
    `Private local path detected in ${local}`,
  );
  assert.ok(!machinePath.test(content), `Machine-specific path detected in ${local}`);
  assert.ok(!credential.test(content), `Credential-shaped value detected in ${local}`);
  assert.ok(
    !secret || !content.includes(secret),
    `Configured API key detected in ${local}`,
  );
}
console.log(`Privacy check passed for ${candidates.length} Git candidate files.`);
