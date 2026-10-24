import {mkdirSync, mkdtempSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {describe, expect, it} from 'vitest';
import {runAllChecks} from '../src/checks/index.js';
import {checkReadme, REQUIRED_SECTIONS} from '../src/checks/readme.js';
import {checkScope, detectProjectPath} from '../src/checks/scope.js';
import {scanSecrets, scanText} from '../src/checks/secrets.js';
import {checkStructure} from '../src/checks/structure.js';
import {buildReport} from '../src/report.js';
import {loadLocalSource} from '../src/source.js';

// Built at runtime so this file never contains a string that looks like a real key.
const FAKE_GOOGLE_KEY = 'AIza' + 'X'.repeat(35);

const COMPLETE_README = [
  '# Meeting Summarizer',
  ...REQUIRED_SECTIONS.map((s) => `## ${s.title}\n\nReal content.`),
].join('\n\n');

const GOOD_FILES = ['README.md', '.gitignore', '.env.example', 'package.json', 'src/index.ts'];

describe('checkStructure', () => {
  it('passes a well-formed project', () => {
    const result = checkStructure('agents/meeting-summarizer', GOOD_FILES);
    expect(result.passed).toBe(true);
    expect(result.findings).toEqual([]);
  });

  it('rejects non-kebab-case and generic names', () => {
    expect(checkStructure('agents/My_Agent', GOOD_FILES).passed).toBe(false);
    expect(checkStructure('tools/demo', GOOD_FILES).passed).toBe(false);
  });

  it('rejects projects outside agents/ or tools/', () => {
    expect(checkStructure('template', GOOD_FILES).passed).toBe(false);
  });

  it('requires a README and a manifest', () => {
    const result = checkStructure('tools/token-cost-tracker', ['.gitignore', '.env.example', 'main.py']);
    expect(result.findings.filter((f) => f.severity === 'error')).toHaveLength(2);
  });
});

describe('secrets', () => {
  it('detects and masks a Google API key', () => {
    const findings = scanText('src/config.ts', `const key = "${FAKE_GOOGLE_KEY}";`);
    expect(findings).toHaveLength(1);
    expect(findings[0].severity).toBe('error');
    expect(findings[0].message).toContain('src/config.ts:1');
    expect(findings[0].message).not.toContain(FAKE_GOOGLE_KEY);
  });

  it('ignores placeholder values', () => {
    expect(scanText('.env.example', 'GEMINI_API_KEY=your_gemini_api_key_here')).toEqual([]);
    expect(scanText('a.ts', 'const apiKey = "your-api-key-goes-here-123";')).toEqual([]);
  });

  it('flags committed .env files and dependency folders but allows .env.example', async () => {
    const files = ['.env', '.env.example', 'node_modules/a/index.js', 'node_modules/b/index.js'];
    const result = await scanSecrets(files, async () => '');
    expect(result.passed).toBe(false);
    expect(result.findings).toHaveLength(2);
  });
});

describe('checkReadme', () => {
  it('passes a README with every section', () => {
    expect(checkReadme(COMPLETE_README).findings).toEqual([]);
  });

  it('flags missing sections and leftover template text', () => {
    const result = checkReadme('# [Project Name]\n\n## Overview\n\n- Feature 1: Brief description of the capability.');
    expect(result.passed).toBe(false);
    expect(result.findings.some((f) => f.message.includes('Technical Stack'))).toBe(true);
    expect(result.findings.some((f) => f.message.includes('placeholder(s) left in README.md (lines 1, 5)'))).toBe(true);
  });
});

describe('checkScope', () => {
  it('is skipped without PR data', () => {
    expect(checkScope('agents/x-agent').skipped).toBeDefined();
  });

  it('allows the project folder plus an index row', () => {
    const changed = ['agents/pr-helper/README.md', 'agents/pr-helper/main.py', 'agents/README.md'];
    expect(detectProjectPath(changed)).toBe('agents/pr-helper');
    expect(checkScope('agents/pr-helper', changed).findings).toEqual([]);
  });

  it('flags root files and other projects', () => {
    const changed = ['agents/pr-helper/main.py', 'package.json', 'tools/other-tool/index.ts'];
    expect(checkScope('agents/pr-helper', changed).findings).toHaveLength(2);
  });
});

describe('buildReport', () => {
  it('scores errors and warnings', () => {
    const report = buildReport('t', 'agents/x', [{
      check: 'c',
      passed: false,
      findings: [{severity: 'error', message: 'e'}, {severity: 'warning', message: 'w'}],
    }]);
    expect(report.score).toBe(80);
    expect(report.verdict).toBe('Changes requested');
  });
});

describe('runAllChecks on a local folder', () => {
  function makeProject(files: Record<string, string>): string {
    const dir = join(mkdtempSync(join(tmpdir(), 'cra-')), 'agents', 'meeting-summarizer');
    for (const [name, content] of Object.entries(files)) {
      mkdirSync(join(dir, name, '..'), {recursive: true});
      writeFileSync(join(dir, name), content);
    }
    return dir;
  }

  it('gives a clean project 100/100', async () => {
    const dir = makeProject({
      'README.md': COMPLETE_README,
      '.gitignore': 'node_modules/\n.env\n',
      '.env.example': 'GEMINI_API_KEY=your_gemini_api_key_here\n',
      'package.json': '{}',
      'src/index.ts': 'export {};\n',
    });
    const report = await runAllChecks(loadLocalSource(dir));
    expect(report.projectPath).toBe('agents/meeting-summarizer');
    expect(report.score).toBe(100);
  });

  it('catches a hardcoded key in source', async () => {
    const dir = makeProject({
      'README.md': COMPLETE_README,
      'package.json': '{}',
      'src/index.ts': `export const KEY = "${FAKE_GOOGLE_KEY}";\n`,
    });
    const report = await runAllChecks(loadLocalSource(dir));
    expect(report.errors).toBeGreaterThan(0);
    expect(JSON.stringify(report)).not.toContain(FAKE_GOOGLE_KEY);
  });
});
