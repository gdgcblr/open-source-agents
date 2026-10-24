import test from 'node:test';
import assert from 'node:assert/strict';
import { NammaSahayakaAgent } from '../agent/civic-agent.js';

test('NammaSahayakaAgent processes English query with multi-step tools', async () => {
  const agent = new NammaSahayakaAgent(undefined, 'gemini-2.5-flash');
  const res = await agent.processGrievance('Deep pothole near 27th Main HSR Layout road');

  assert.equal(res.ward.locality, 'HSR Layout');
  assert.equal(res.ward.wardNumber, 174);
  assert.equal(res.triage.agency, 'BBMP');
  assert.ok(res.toolCallsExecuted.includes('lookup_ward_jurisdiction'));
  assert.ok(res.toolCallsExecuted.includes('classify_and_triage_issue'));
  assert.ok(res.toolCallsExecuted.includes('generate_bilingual_complaint'));
  assert.ok(res.toolCallsExecuted.includes('generate_escalation_dispatch'));
  assert.ok(res.bilingualComplaint.kannada.body.includes('ಮಾನ್ಯರೇ'));
  assert.ok(res.dispatch.tweetLength <= 280);
});

test('NammaSahayakaAgent handles Kanglish power outage query', async () => {
  const agent = new NammaSahayakaAgent();
  const res = await agent.processGrievance('Current illa since 4 hours in Indiranagar 100ft road');

  assert.equal(res.ward.locality, 'Indiranagar');
  assert.equal(res.triage.agency, 'BESCOM');
  assert.equal(res.triage.agencyContact.primaryHelpline, '1912');
  assert.ok(res.dispatch.tweetText.includes('@NammaBESCOM'));
});

test('NammaSahayakaAgent handles pure Kannada water scarcity query', async () => {
  const agent = new NammaSahayakaAgent();
  const res = await agent.processGrievance('ಮಲ್ಲೇಶ್ವರಂ ನಲ್ಲಿ ಕಾವೇರಿ ನೀರು ಸರಬರಾಜು ಇಲ್ಲ ಪೈಪ್ ಒಡೆದಿರುವುದು ಕಂಡುಬಂದಿದೆ');

  assert.equal(res.ward.locality, 'Malleshwaram');
  assert.equal(res.triage.agency, 'BWSSB');
  assert.equal(res.triage.agencyContact.primaryHelpline, '1916');
});

test('NammaSahayakaAgent handles event venue context (Google Ananta, Mahadevapura)', async () => {
  const agent = new NammaSahayakaAgent();
  const res = await agent.processGrievance('Rainwater flooding on service road near Google Ananta, Mahadevapura');

  assert.equal(res.ward.locality, 'Mahadevapura');
  assert.equal(res.ward.zone, 'Mahadevapura');
  assert.equal(res.ward.wardNumber, 82);
  assert.equal(res.triage.agency, 'BBMP');
  assert.equal(res.triage.severity, 'critical');
});
