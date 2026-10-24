import test from 'node:test';
import assert from 'node:assert/strict';
import { WardResolver } from '../services/ward-resolver.js';
import { TriageEngine } from '../services/triage-engine.js';
import { BilingualFormatter } from '../services/bilingual-formatter.js';
import { SocialDispatcher } from '../services/social-dispatcher.js';
import { executeTool } from '../index.js';

test('WardResolver resolves Mahadevapura / Google Ananta', () => {
  const result = WardResolver.resolve('Google Ananta');
  assert.equal(result.found, true);
  assert.equal(result.matchedWard?.zone, 'Mahadevapura');
  assert.equal(result.matchedWard?.wardNumber, 82);
  assert.equal(result.matchedWard?.wardName, 'Garudacharpalya');
});

test('WardResolver resolves PIN code 560102 to HSR Layout', () => {
  const result = WardResolver.resolve('My area pin code is 560102');
  assert.equal(result.found, true);
  assert.equal(result.matchedWard?.locality, 'HSR Layout');
  assert.equal(result.matchedWard?.wardNumber, 174);
  assert.equal(result.matchedWard?.zone, 'Bommanahalli');
});

test('TriageEngine correctly routes potholes to BBMP', () => {
  const triage = TriageEngine.classify('Deep dangerous pothole crater on main road near bus stop');
  assert.equal(triage.agency, 'BBMP');
  assert.equal(triage.category.id, 'pothole_road');
  assert.equal(triage.agencyContact.primaryHelpline, '080-22660000');
});

test('TriageEngine routes power cut and current illa to BESCOM', () => {
  const triage = TriageEngine.classify('Transformer blast in our area, current illa since 4 hours');
  assert.equal(triage.agency, 'BESCOM');
  assert.equal(triage.category.id, 'power_outage');
  assert.equal(triage.agencyContact.primaryHelpline, '1912');
});

test('TriageEngine routes water pipeline leak to BWSSB', () => {
  const triage = TriageEngine.classify('Kaveri water pipe burst drinking water wasting on street');
  assert.equal(triage.agency, 'BWSSB');
  assert.equal(triage.category.id, 'water_leakage_contamination');
  assert.equal(triage.agencyContact.primaryHelpline, '1916');
});

test('BilingualFormatter generates English and authentic Kannada letters', () => {
  const ward = WardResolver.resolve('Koramangala').matchedWard!;
  const triage = TriageEngine.classify('Garbage not picked up for 4 days stench');
  const complaint = BilingualFormatter.generate({
    ward,
    agencyContact: triage.agencyContact,
    category: triage.category,
    description: 'Black spot garbage accumulation near Sony World signal',
    landmark: 'Near Sony World Signal'
  });

  assert.ok(complaint.english.body.includes('Koramangala'));
  assert.ok(complaint.english.body.includes('Ward: No. 151'));
  assert.ok(complaint.kannada.body.includes('ಮಾನ್ಯರೇ'));
  assert.ok(complaint.kannada.body.includes('ವಾರ್ಡ್ ವಿವರ: ಸಂಖ್ಯೆ 151'));
  assert.ok(complaint.kannada.body.includes('ಧನ್ಯವಾದಗಳೊಂದಿಗೆ'));
});

test('SocialDispatcher creates X/Twitter dispatch under 280 characters', () => {
  const ward = WardResolver.resolve('Bellandur').matchedWard!;
  const triage = TriageEngine.classify('Sewage overflow onto service road');
  const dispatch = SocialDispatcher.generateDispatch({
    ward,
    agencyContact: triage.agencyContact,
    category: triage.category,
    description: 'Sewage overflowing near Ecospace back gate'
  });

  assert.ok(dispatch.tweetLength <= 280, `Tweet length ${dispatch.tweetLength} exceeds 280 chars`);
  assert.ok(dispatch.tweetText.includes('@BWSSBOnline'));
  assert.ok(dispatch.hashtags.includes('#NammaBengaluru'));
  assert.equal(dispatch.helplineNumber, '1916');
});

test('executeTool executes MCP lookup_ward_jurisdiction cleanly', async () => {
  const res = await executeTool('lookup_ward_jurisdiction', { query: 'Indiranagar' });
  assert.ok(res.content && res.content.length > 0);
  const data = JSON.parse(res.content[0].text);
  assert.equal(data.found, true);
  assert.equal(data.matchedWard.locality, 'Indiranagar');
});
