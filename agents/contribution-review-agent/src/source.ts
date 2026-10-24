import {execFileSync} from 'node:child_process';
import {existsSync, readdirSync, readFileSync, realpathSync, statSync} from 'node:fs';
import {basename, dirname, join, relative, resolve, sep} from 'node:path';
import {loadPullRequestSource, parsePullRequestUrl} from './github.js';
import type {ProjectSource} from './types.js';

const SKIP_DIRS = new Set(['.git', 'node_modules', '.venv', 'venv', '__pycache__', 'dist', 'build']);
const MAX_FILE_BYTES = 1_000_000;

export async function loadSource(target: string, cwd = process.cwd()): Promise<ProjectSource> {
  return parsePullRequestUrl(target) ? loadPullRequestSource(target) : loadLocalSource(resolve(cwd, target));
}

function git(args: string[], cwd: string): string | null {
  try {
    return execFileSync('git', args, {cwd, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore']});
  } catch {
    return null;
  }
}

function walk(root: string, dir = root): string[] {
  return readdirSync(dir, {withFileTypes: true}).flatMap((entry) => {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) return SKIP_DIRS.has(entry.name) ? [] : walk(root, full);
    return [relative(root, full).split(sep).join('/')];
  });
}

export function loadLocalSource(dir: string): ProjectSource {
  if (!existsSync(dir) || !statSync(dir).isDirectory()) throw new Error(`Not a directory: ${dir}`);
  const root = realpathSync(dir);

  // Inside a git repo, list exactly what would be committed: tracked files plus untracked, non-ignored files.
  const listed = git(['ls-files', '--cached', '--others', '--exclude-standard', '-z'], root);
  const files = listed !== null ? listed.split('\0').filter(Boolean) : walk(root);
  const repoRoot = git(['rev-parse', '--show-toplevel'], root)?.trim();
  const projectPath = repoRoot
    ? relative(realpathSync(repoRoot), root).split(sep).join('/')
    : `${basename(dirname(root))}/${basename(root)}`;

  return {
    label: projectPath,
    projectPath,
    files: [...new Set(files)].sort(),
    async readFile(relPath) {
      const full = resolve(root, relPath);
      if (!full.startsWith(root + sep)) return null;
      if (!existsSync(full) || statSync(full).size > MAX_FILE_BYTES) return null;
      return readFileSync(full, 'utf8');
    },
  };
}
