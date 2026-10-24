import { test } from 'node:test';
import assert from 'node:assert/strict';
import { InjectionPlugin } from '../src/injector.js';

// The ADK wiring (afterToolCallback receiving the real tool) is covered by the
// end-to-end tests; these check the injection decision itself.

test('payload is appended to the delivery tool result', () => {
  const plugin = new InjectionPlugin('read_webpage', 'INJECTED-NOTE');
  const out = plugin.inject('read_webpage', { content: 'page text' });
  assert.ok(out, 'a replacement result is returned');
  assert.match(String(out.content), /page text/);
  assert.match(String(out.content), /INJECTED-NOTE/);
  assert.equal(plugin.injected, 1);
});

test('non-delivery tools are left untouched', () => {
  const plugin = new InjectionPlugin('read_webpage', 'INJECTED-NOTE');
  const out = plugin.inject('send_email', { status: 'sent' });
  assert.equal(out, undefined);
  assert.equal(plugin.injected, 0);
});
