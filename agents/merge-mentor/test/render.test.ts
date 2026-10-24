import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { renderMentor, renderTable, saveMarkdown } from '../src/render.js';
import type { Issue, Repository, Row, ScoreResult } from '../src/types.js';

const strip = (s: string) => s.replace(/\x1b\[[0-9;]*m/g, '');
function capture(fn: () => void): string {
  const out: string[] = [];
  const original = console.log;
  console.log = (...args: unknown[]) => void out.push(args.join(' '));
  try {
    fn();
  } finally {
    console.log = original;
  }
  return strip(out.join('\n'));
}

const health = { closedPRs: 1, mergedPRs: 1, outsideMerged: 1, medianDaysToMerge: 1 };
const row = (n: number, title: string, score: number, status: ScoreResult['status'], reason?: string, difficulty?: number): Row => ({
  issue: { number: n, title, repo_full_name: 'o/r', html_url: `https://github.com/o/r/issues/${n}` } as Issue,
  repo: { full_name: 'o/r' } as Repository,
  score: { score, status, reason, health, parts: [] },
  difficulty: difficulty ? { difficulty, reason: 'r' } : undefined,
});

test('renderTable shows every status, score band and difficulty dots', () => {
  const out = capture(() =>
    renderTable([
      row(1, 'Free issue', 94, 'Available', undefined, 2),
      row(2, 'Someone asked', 50, 'Claimed', '@sam asked 2d ago', 3),
      row(3, 'Has a PR', 15, 'Taken', 'PR #9 open'),
      row(4, 'Already merged', 15, 'Fixed', 'PR #8 already merged'),
    ]),
  );
  assert.match(out, /Available/);
  assert.match(out, /Claimed \(@sam asked 2d ago\)/);
  assert.match(out, /Taken \(PR #9 open\)/);
  assert.match(out, /Likely fixed \(PR #8 already merged\)/);
  assert.match(out, /94 High/);
  assert.match(out, /50 Medium/);
  assert.match(out, /15 Low/);
  assert.match(out, /●●○○○/);
  assert.match(out, /●●●○○/);
});

test('renderTable shortens long titles with an ellipsis so columns never collide', () => {
  const out = capture(() => renderTable([row(1, 'x'.repeat(200), 80, 'Available')]));
  const line = out.split('\n').find((l) => l.includes('o/r#1'))!;
  assert.match(line, /… +80 High/);
});

test('renderMentor prints the answer with its headings', () => {
  const out = capture(() => renderMentor('## 1. What the issue is\nIt crashes.'));
  assert.match(out, /## 1\. What the issue is/);
  assert.match(out, /It crashes\./);
});

test('saveMarkdown writes a titled file with the issue link', () => {
  const dir = mkdtempSync(path.join(tmpdir(), 'mm-'));
  const file = path.join(dir, 'out.md');
  saveMarkdown(file, row(7, 'Crash on empty input', 90, 'Available').issue, '## body');
  const text = readFileSync(file, 'utf8');
  assert.match(text, /^# o\/r#7: Crash on empty input/);
  assert.match(text, /https:\/\/github\.com\/o\/r\/issues\/7/);
  assert.match(text, /## body/);
});
