import test from 'node:test';
import assert from 'node:assert/strict';
import { scanContentForSecrets, maskSecret } from '../src/tools/secrets.js';

test('secrets scanner detects Gemini API keys', () => {
  const content = 'const key = "AIzaSyB8z9X1234567890123456789012345678";';
  const findings = scanContentForSecrets(content, 'test.js');
  assert.equal(findings.length >= 1, true);
  assert.equal(findings[0].type, 'gemini_api_key');
  assert.equal(findings[0].severity, 'CRITICAL');
  assert.equal(findings[0].maskedSecret.startsWith('AIza'), true);
  assert.equal(findings[0].maskedSecret.includes('...'), true);
});

test('secrets scanner detects OpenAI API keys', () => {
  const content = 'const openaiKey = "sk-live-abc12345678901234567890abcdef";';
  const findings = scanContentForSecrets(content, 'test.js');
  assert.equal(findings.length >= 1, true);
  assert.equal(findings[0].type, 'openai_api_key');
  assert.equal(findings[0].severity, 'CRITICAL');
});

test('secrets scanner detects AWS Access Keys', () => {
  const content = 'const aws = "AKIAIOSFODNN7ABCD123";';
  const findings = scanContentForSecrets(content, 'test.js');
  assert.equal(findings.length >= 1, true);
  assert.equal(findings[0].type, 'aws_access_key');
});

test('secrets scanner ignores placeholder values in .env.example', () => {
  const content = 'GEMINI_API_KEY=your_gemini_api_key_here\nOPENAI_API_KEY=placeholder';
  const findings = scanContentForSecrets(content, '.env.example');
  assert.equal(findings.length, 0);
});

test('maskSecret safely truncates credentials', () => {
  const masked = maskSecret('AIzaSyB8z9X1234567890123456789012345678');
  assert.equal(masked, 'AIza...5678');
  assert.equal(maskSecret('short'), '****');
});
