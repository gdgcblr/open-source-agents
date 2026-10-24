import assert from 'node:assert/strict';
import test from 'node:test';

import {parseGithubUrl} from '../src/github-rest.ts';

test('parses a personal or organization repository URL', () => {
  assert.deepEqual(parseGithubUrl('https://github.com/alice/private-app'), {
    owner: 'alice',
    repo: 'private-app',
  });
});

test('parses an issue URL and extracts its numeric issue number', () => {
  assert.deepEqual(
    parseGithubUrl('https://github.com/alice/private-app/issues/27', true),
    {owner: 'alice', repo: 'private-app', issueNumber: 27},
  );
});

test('rejects untrusted hosts, paths, credentials, and invalid issue numbers', () => {
  assert.throws(() => parseGithubUrl('https://github.example.com/alice/repo'));
  assert.throws(() => parseGithubUrl('http://github.com/alice/repo'));
  assert.throws(() => parseGithubUrl('https://user@github.com/alice/repo'));
  assert.throws(() => parseGithubUrl('https://github.com/alice/repo/tree/main'));
  assert.throws(() => parseGithubUrl('https://github.com/alice/repo/issues/nope', true));
});