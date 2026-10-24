import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import {
  parseArgs,
  getHelpText,
  formatReport,
  observeGitDiff,
  analyzeWithGemini,
} from '../index.js';

describe('git-diff-summarizer', () => {
  describe('parseArgs', () => {
    it('should parse default options correctly', () => {
      const options = parseArgs([]);
      assert.equal(options.repoPath, process.cwd());
      assert.equal(options.outputPath, undefined);
      assert.equal(options.help, false);
      assert.equal(options.staged, false);
      assert.ok(options.model);
    });

    it('should parse custom flags correctly', () => {
      const options = parseArgs([
        '--repo', '/tmp/my-repo',
        '--output', 'out.md',
        '--model', 'gemini-2.5-pro',
        '--staged',
      ]);
      assert.equal(options.repoPath, path.resolve(process.cwd(), '/tmp/my-repo'));
      assert.equal(options.outputPath, path.resolve(process.cwd(), 'out.md'));
      assert.equal(options.model, 'gemini-2.5-pro');
      assert.equal(options.staged, true);
    });

    it('should recognize -h and --help', () => {
      assert.equal(parseArgs(['-h']).help, true);
      assert.equal(parseArgs(['--help']).help, true);
    });

    it('should throw when flag values are missing', () => {
      assert.throws(() => parseArgs(['--repo']), /Missing value for --repo/);
      assert.throws(() => parseArgs(['--output']), /Missing value for --output/);
      assert.throws(() => parseArgs(['--model']), /Missing value for --model/);
    });

    it('should throw on unknown argument', () => {
      assert.throws(() => parseArgs(['--invalid-flag']), /Unknown argument/);
    });
  });

  describe('getHelpText & formatReport', () => {
    it('should return help text containing usage and options', () => {
      const text = getHelpText();
      assert.match(text, /Usage:/);
      assert.match(text, /--repo/);
      assert.match(text, /--output/);
      assert.match(text, /GEMINI_API_KEY/);
    });

    it('should format report with proper metadata', () => {
      const report = formatReport('## Summary\nAll good.', {
        repoPath: '/workspace/test',
        model: 'gemini-2.5-flash',
      });
      assert.match(report, /# Git Diff Summary/);
      assert.match(report, /gemini-2.5-flash/);
      assert.match(report, /\/workspace\/test/);
      assert.match(report, /## Summary/);
    });
  });

  describe('observeGitDiff', () => {
    it('should throw error for non-existent path', async () => {
      await assert.rejects(
        observeGitDiff('/path/that/does/not/exist/at/all'),
        /does not exist/
      );
    });

    it('should throw error for non-git directory', async () => {
      const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'diff-test-not-git-'));
      try {
        await assert.rejects(
          observeGitDiff(tmpDir),
          /not a valid Git repository/
        );
      } finally {
        fs.rmSync(tmpDir, { recursive: true, force: true });
      }
    });

    it('should return hasChanges=false when repository has no changes', async () => {
      const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'diff-test-clean-git-'));
      try {
        execFileSync('git', ['init'], { cwd: tmpDir });
        execFileSync('git', ['config', 'user.name', 'Test'], { cwd: tmpDir });
        execFileSync('git', ['config', 'user.email', 'test@example.com'], { cwd: tmpDir });
        
        fs.writeFileSync(path.join(tmpDir, 'file.txt'), 'hello');
        execFileSync('git', ['add', '.'], { cwd: tmpDir });
        execFileSync('git', ['commit', '-m', 'initial'], { cwd: tmpDir });

        const result = await observeGitDiff(tmpDir);
        assert.equal(result.hasChanges, false);
        assert.equal(result.diff, '');
      } finally {
        fs.rmSync(tmpDir, { recursive: true, force: true });
      }
    });

    it('should detect unstaged changes', async () => {
      const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'diff-test-dirty-git-'));
      try {
        execFileSync('git', ['init'], { cwd: tmpDir });
        execFileSync('git', ['config', 'user.name', 'Test'], { cwd: tmpDir });
        execFileSync('git', ['config', 'user.email', 'test@example.com'], { cwd: tmpDir });
        
        const filePath = path.join(tmpDir, 'file.txt');
        fs.writeFileSync(filePath, 'version 1');
        execFileSync('git', ['add', '.'], { cwd: tmpDir });
        execFileSync('git', ['commit', '-m', 'initial'], { cwd: tmpDir });

        fs.writeFileSync(filePath, 'version 2 with additions');

        const result = await observeGitDiff(tmpDir);
        assert.equal(result.hasChanges, true);
        assert.match(result.diff, /version 2 with additions/);
        assert.match(result.stat, /file\.txt/);
      } finally {
        fs.rmSync(tmpDir, { recursive: true, force: true });
      }
    });
  });

  describe('analyzeWithGemini', () => {
    it('should throw clear error if GEMINI_API_KEY is missing', async () => {
      const originalKey = process.env.GEMINI_API_KEY;
      delete process.env.GEMINI_API_KEY;

      try {
        await assert.rejects(
          analyzeWithGemini('diff data', 'stat data', { apiKey: '' }),
          /Missing GEMINI_API_KEY/
        );
      } finally {
        if (originalKey) {
          process.env.GEMINI_API_KEY = originalKey;
        }
      }
    });

    it('should handle mock client and return response text', async () => {
      const mockClient = {
        models: {
          generateContent: async () => ({
            text: '## Summary of Changes\nAdded a new test file.\n\n## Key Changed Files\n- test.ts\n\n## Suggested Pull Request Description\nfeat: add test',
          }),
        },
      } as any;

      const result = await analyzeWithGemini('some diff', '1 file changed', {
        apiKey: 'fake-test-key',
        client: mockClient,
      });

      assert.match(result, /## Summary of Changes/);
      assert.match(result, /feat: add test/);
    });

    it('should format API errors with clear error messages', async () => {
      const failingClient = {
        models: {
          generateContent: async () => {
            throw new Error('API_KEY_INVALID: API key expired');
          },
        },
      } as any;

      await assert.rejects(
        analyzeWithGemini('diff', 'stat', {
          apiKey: 'invalid-key',
          client: failingClient,
        }),
        /Gemini API Error: The provided GEMINI_API_KEY is invalid/
      );
    });
  });
});
