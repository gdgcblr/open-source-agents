import {readFileSync} from 'node:fs';
import {analyzeMessage, HIGH_RISK_AT} from './analyze.js';

interface Sample {
  id: string;
  label: 'scam' | 'legit';
  text: string;
}

export function loadSamples(): Sample[] {
  return JSON.parse(readFileSync(new URL('../samples/messages.json', import.meta.url), 'utf8')) as Sample[];
}

export function evaluate(samples: Sample[]) {
  const rows = samples.map((s) => {
    const a = analyzeMessage(s.text);
    const predicted = a.score >= HIGH_RISK_AT ? 'scam' : 'legit';
    return {id: s.id, label: s.label, predicted, score: a.score, verdict: a.verdict, correct: predicted === s.label};
  });
  const count = (label: string, predicted: string) => rows.filter((r) => r.label === label && r.predicted === predicted).length;
  const tp = count('scam', 'scam');
  const fp = count('legit', 'scam');
  const fn = count('scam', 'legit');
  return {
    rows,
    accuracy: rows.filter((r) => r.correct).length / rows.length,
    precision: tp / Math.max(1, tp + fp),
    recall: tp / Math.max(1, tp + fn),
    falsePositives: fp,
    missedScams: fn,
  };
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const result = evaluate(loadSamples());
  console.log('| Sample | Label | Score | Verdict | |');
  console.log('| :--- | :--- | ---: | :--- | :--- |');
  for (const r of result.rows) {
    console.log(`| ${r.id} | ${r.label} | ${r.score} | ${r.verdict} | ${r.correct ? 'OK' : 'WRONG'} |`);
  }
  const pct = (n: number) => `${(n * 100).toFixed(0)}%`;
  console.log(
    `\nAccuracy ${pct(result.accuracy)} · Precision ${pct(result.precision)} · Recall ${pct(result.recall)} · ` +
      `${result.missedScams} missed scam(s) · ${result.falsePositives} false alarm(s) · threshold score >= ${HIGH_RISK_AT}`,
  );
}
