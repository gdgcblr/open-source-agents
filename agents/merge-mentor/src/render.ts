import pc from 'picocolors';
import { writeFileSync } from 'node:fs';
import { scoreBand } from './github/signals.js';
import type { Issue, Row } from './types.js';
import { DIFFICULTY_MAX, MERGE_CHANCE, TABLE } from './constants.js';

// Always leaves at least one trailing space so neighbouring columns never touch.
const clip = (text: string, width: number) => (text.length > width - 1 ? text.slice(0, width - 2) + '… ' : text.padEnd(width));

export function renderTable(rows: Row[]): void {
  console.log(`\n${pc.bold(' #  ' + clip('Issue', TABLE.issueWidth) + clip('Merge Chance', TABLE.mergeWidth) + clip('Difficulty', TABLE.difficultyWidth) + 'Status')}`);
  rows.forEach(({ issue, score, difficulty }, i) => {
    const color = score.score >= MERGE_CHANCE.bandHigh ? pc.green : score.score >= MERGE_CHANCE.bandMedium ? pc.yellow : pc.red;
    const dots = difficulty ? '●'.repeat(difficulty.difficulty) + '○'.repeat(DIFFICULTY_MAX - difficulty.difficulty) : '-';
    const status =
      score.status === 'Available' ? pc.green('🟢 Available') :
      score.status === 'Claimed' ? pc.yellow(`🟡 Claimed (${score.reason})`) :
      pc.red(`🔴 Taken (${score.reason})`);
    const label = `${issue.repo_full_name}#${issue.number} ${issue.title}`;
    console.log(`${String(i + 1).padStart(2)}  ${clip(label, TABLE.issueWidth)}${color(clip(`${score.score} ${scoreBand(score.score)}`, TABLE.mergeWidth))}${clip(dots, TABLE.difficultyWidth)}${status}`);
  });
  console.log('');
}

export function renderMentor(markdown: string): void {
  const out = markdown
    .split('\n')
    .map((line) => (line.startsWith('## ') ? '\n' + pc.bold(pc.cyan(line)) : line))
    .join('\n');
  console.log(`\n${out}\n`);
}

export function saveMarkdown(file: string, issue: Issue, markdown: string): void {
  writeFileSync(file, `# ${issue.repo_full_name}#${issue.number}: ${issue.title}\n\n${issue.html_url}\n\n${markdown}\n`);
}
