import pc from 'picocolors';
import { writeFileSync } from 'node:fs';
import { Issue, Repository } from './finder.js';
import { ScoreResult, scoreBand } from './signals.js';
import { DifficultyResult } from './difficulty.js';

export interface Row {
  issue: Issue;
  repo: Repository;
  score: ScoreResult;
  difficulty?: DifficultyResult;
}

// Always leaves at least one trailing space so neighbouring columns never touch.
const clip = (text: string, width: number) => (text.length > width - 1 ? text.slice(0, width - 2) + '… ' : text.padEnd(width));

export function renderTable(rows: Row[]): void {
  console.log(`\n${pc.bold(' #  ' + clip('Issue', 58) + clip('Merge Chance', 15) + clip('Difficulty', 12) + 'Status')}`);
  rows.forEach(({ issue, score, difficulty }, i) => {
    const color = score.score >= 70 ? pc.green : score.score >= 45 ? pc.yellow : pc.red;
    const dots = difficulty ? '●'.repeat(difficulty.difficulty) + '○'.repeat(5 - difficulty.difficulty) : '-';
    const status =
      score.status === 'Available' ? pc.green('🟢 Available') :
      score.status === 'Claimed' ? pc.yellow(`🟡 Claimed (${score.reason})`) :
      pc.red(`🔴 Taken (${score.reason})`);
    const label = `${issue.repo_full_name}#${issue.number} ${issue.title}`;
    console.log(`${String(i + 1).padStart(2)}  ${clip(label, 58)}${color(clip(`${score.score} ${scoreBand(score.score)}`, 15))}${clip(dots, 12)}${status}`);
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
