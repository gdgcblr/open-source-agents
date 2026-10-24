import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

/**
 * The web page renders text written by strangers (issue text, AI output). These tests run the page's real
 * rendering code, taken straight from web/index.html, against hostile input.
 */
const html = readFileSync(fileURLToPath(new URL('../web/index.html', import.meta.url)), 'utf8');
const script = html.match(/<script>([\s\S]*)<\/script>/)![1];
const from = script.indexOf('/* Only ever link to github.com');
const to = script.indexOf('function buildControls');
const page = new Function(`${script.slice(from, to)}; return { esc, safeUrl, renderBlocks, renderExplanation };`)() as {
  esc: (s: string) => string;
  safeUrl: (u: string) => string;
  renderBlocks: (s: string) => string;
  renderExplanation: (s: string) => string;
};
const withoutOwnTags = (out: string) => out.replace(/<\/?(code|strong|em|pre|span|div|li|ul|ol|p|h3|button|blockquote)\b[^>]*>/g, '');

test('hostile HTML in AI or issue text is shown as text, never run', () => {
  const evil = '## 1. Title <img src=x onerror=alert(1)>\n<script>alert(2)</script> **bold<b>** `<svg onload=alert(3)>`\n```diff\n+<iframe src=javascript:alert(4)>\n```';
  const out = withoutOwnTags(page.renderExplanation(evil));
  assert.doesNotMatch(out, /<(script|img|iframe|svg|b)[\s>]/i);
  assert.match(out, /&lt;script&gt;/);
  assert.match(out, /&lt;img src=x onerror=alert\(1\)&gt;/);
});

test('markdown links are never turned into clickable links', () => {
  const out = page.renderExplanation('## 1. Links\n- [click me](javascript:alert(1))');
  assert.doesNotMatch(out, /<a[\s>]/);
});

test('esc escapes quotes too, so text cannot break out of an HTML attribute', () => {
  assert.equal(page.esc(`"><x onmouseover='y'>`), '&quot;&gt;&lt;x onmouseover=&#39;y&#39;&gt;');
});

test('only github.com links are ever used for "open on GitHub"', () => {
  assert.equal(page.safeUrl('https://github.com/o/r/issues/1'), 'https://github.com/o/r/issues/1');
  for (const bad of ['javascript:alert(1)', 'https://evil.example/x', 'http://github.com/x', '//github.com/x', '']) assert.equal(page.safeUrl(bad), '#', bad);
});

test('diff blocks are colour-coded line by line and get a copy button', () => {
  const out = page.renderBlocks('```diff\n--- a/f.ts\n+++ b/f.ts\n@@ -1 +1 @@\n-old\n+new\n```');
  assert.match(out, /class="l del">-old/);
  assert.match(out, /class="l add">\+new/);
  assert.match(out, /class="l hunk">@@/);
  assert.match(out, /data-copy/);
});

test('a paragraph wrapped in underscores is italic, but snake_case names are left alone', () => {
  assert.match(page.renderBlocks('_These checks run without AI._'), /<p><em>These checks run without AI\.<\/em><\/p>/);
  assert.equal(page.renderBlocks('uses list_files and read_file here'), '<p>uses list_files and read_file here</p>');
});

test('numbered section headings become numbered cards; a plain answer still renders', () => {
  const cards = page.renderExplanation('## 1. What it is\nA bug.\n\n## 2. Where\nIn `a.ts:3`.');
  assert.equal((cards.match(/class="step"/g) ?? []).length, 2);
  assert.match(cards, /<span class="n">1<\/span>What it is/);
  assert.match(page.renderExplanation('just text, no headings'), /<div class="step"><p>just text, no headings<\/p><\/div>/);
});
