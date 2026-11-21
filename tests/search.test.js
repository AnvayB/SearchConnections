// Regression tests for company search (script.js).
// Run with: make test-search   (or: node --test "tests/*.test.js")
// Uses inline fixtures only: no network, no LinkedIn login, no data/ folder.

const test = require('node:test');
const assert = require('node:assert/strict');
const { loadApp, person, plain } = require('./helpers');

const app = loadApp({ rows: {
  anvay: [
    person('Amazon'), person('Amazon'),
    person('Amazon Web Services (AWS)'),
    person('Meta'), person('Facebook'),
    person('Metanoia Technologies'),
    person('Intel Corporation'), person('Raytheon Intelligence & Space'),
    person('BAE Systems, Inc.'),
    person('Apple'), person('AC Wellness Medical Group @ Apple '),
    person('Oracle'), person('Oracle Corp.'), person('Oracle Corp[oration'),
    person('Google'), person('Microsoft'),
    person('University of California, San Francisco'),
    person('')
  ],
  anil: [person('Amazon Web Services (AWS)'), person('Sila Nanotechnologies Inc.')],
  bilwa: [person('Sila Nanotechnologies, Inc.'), person('Google')]
} });

const total = block => block.anvay_count + block.anil_count + block.bilwa_count;
const search = q => app.run(`resolveQuery(${JSON.stringify(q)})`);

test('Amazon and AWS are one company: every spelling returns the same rows', () => {
  const queries = ['Amazon', 'amazon', 'AWS', 'aws', 'Amazon Web Services', 'Amazon Web Services (AWS)'];
  for (const q of queries) {
    const blocks = search(q);
    assert.equal(blocks.length, 1, q);
    assert.equal(total(blocks[0]), 4, `${q}: 3 Amazon/AWS in anvay + 1 AWS in anil`);
    assert.equal(blocks[0].label, 'Amazon', q);
  }
});

test('Searching "Amazon, AWS" does not render the same company twice', () => {
  assert.equal(search('Amazon, AWS').length, 1);
});

test('Rebrands and spelling variants are grouped', () => {
  assert.equal(total(search('Meta')[0]), 2);
  assert.equal(total(search('Facebook')[0]), 2);
  assert.equal(total(search('Oracle')[0]), 3);
  assert.equal(total(search('Oracle Corp.')[0]), 3);
  assert.equal(total(search('Sila Nanotechnologies, Inc.')[0]), 2);
});

test('An exact company does not pull in look-alike names', () => {
  const meta = search('Meta')[0];
  assert.ok(!meta.anvay_matches.some(r => r.Company === 'Metanoia Technologies'));
  const intel = search('Intel')[0];
  assert.ok(!intel.anvay_matches.some(r => /Raytheon/.test(r.Company)));
  const apple = search('Apple')[0];
  assert.ok(!apple.anvay_matches.some(r => /AC Wellness/.test(r.Company)));
});

test('Company names containing commas are not split into a multi-search', () => {
  for (const name of ['BAE Systems, Inc.', 'University of California, San Francisco']) {
    const blocks = search(name);
    assert.equal(blocks.length, 1, name);
    assert.equal(total(blocks[0]), 1, name);
  }
});

test('Comma-separated searches still produce one block per company', () => {
  const blocks = search('Google, Microsoft');
  assert.deepEqual(plain(blocks.map(b => b.label)), ['Google', 'Microsoft']);
  assert.equal(search('BAE Systems, Inc., Google').length, 2);
});

test('Multi-word fallback requires every word, not any word', () => {
  // old behaviour: "Google Inc" matched every company containing "inc"
  assert.equal(total(search('Google Inc')[0]), 2, 'the two Google rows only');
  const partial = search('Raytheon Space')[0];
  assert.equal(partial.groups.length, 1);
  assert.equal(partial.groups[0].label, 'Raytheon Intelligence & Space');
});

test('Partial names still find companies when there is no exact match', () => {
  const blocks = search('metanoia');
  assert.equal(total(blocks[0]), 1);
});

test('No match, blank and whitespace queries behave sanely', () => {
  assert.equal(total(search('zzzz')[0]), 0);
  assert.deepEqual(plain(search('')), []);
  assert.deepEqual(plain(search('   ')), []);
  assert.equal(total(search('(')[0]), 0);
});

test('Rows with a blank company are findable under "No company listed"', () => {
  assert.equal(app.run('Array.from(companyGroups.values()).some(g => !g.key)'), false, 'no empty group keys');
  const blocks = search('No company listed');
  assert.equal(blocks.length, 1);
  assert.equal(total(blocks[0]), 1);
});

test('Suggestions: AWS suggests the Amazon group; legal suffixes do not cause false hits', () => {
  const labels = q => plain(app.run(`suggestGroups(${JSON.stringify(q)}).map(g => g.label)`));
  assert.deepEqual(labels('aws'), ['Amazon']);
  assert.ok(!labels('ora').includes('Intel Corporation'), '"Corporation" must not match "ora"');
  assert.deepEqual(labels('a'), [], 'single character does not suggest');
});

test('Zero-result search renders an empty-state message', () => {
  app.run(`searchCompany('zzzz')`);
  assert.match(app.els.resultsContainer.innerHTML, /No connections found/);
});

test('Results header offers a jobs button for each distinct LinkedIn page', () => {
  app.run(`jobsUrlByName.set('amazon', 'https://www.linkedin.com/company/amazon/jobs/');
           jobsUrlByName.set('amazon web services aws', 'https://www.linkedin.com/company/amazon-web-services/jobs/')`);
  app.run(`searchCompany('Amazon')`);
  const html = app.els.resultsContainer.innerHTML;
  assert.match(html, /Amazon Jobs/);
  assert.match(html, /Amazon Web Services \(AWS\) Jobs/);
  app.run('jobsUrlByName = new Map()');
});

test('Company names are HTML-escaped in headers and suggestions', () => {
  app.run(`searchCompany('<img src=x onerror=alert(1)>')`);
  assert.ok(!/<img src=x/.test(app.els.resultsContainer.innerHTML));
});
