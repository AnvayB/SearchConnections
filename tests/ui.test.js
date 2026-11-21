// Tests for jobs links, the Companies tab, result rendering, keyboard navigation
// and load-error handling in script.js. Fixtures only; see tests/helpers.js.

const test = require('node:test');
const assert = require('node:assert/strict');
const { loadApp, person, plain } = require('./helpers');

const FIELDS = ['First Name', 'Last Name', 'URL', 'Company', 'Position'];

// ---------------------------------------------------------------------------
// Jobs links
// ---------------------------------------------------------------------------

test('Jobs link: a known company page is used directly', () => {
  const app = loadApp({ rows: { anvay: [person('Oracle')], anil: [], bilwa: [] } });
  app.run(`jobsUrlByName.set('oracle', 'https://www.linkedin.com/company/oracle/jobs/')`);
  assert.deepEqual(plain(app.run(`jobsLinkFor('Oracle')`)),
    { url: 'https://www.linkedin.com/company/oracle/jobs/', direct: true, verified: false });
  // spelling variants resolve to the same page through normalisation
  assert.equal(app.run(`jobsLinkFor('Oracle Corp.').url`), 'https://www.linkedin.com/company/oracle/jobs/');
});

test('Jobs link: unknown companies get a LinkedIn job search, never Google', () => {
  const app = loadApp({ rows: { anvay: [person('Accelon Inc.')], anil: [], bilwa: [] } });
  const link = plain(app.run(`jobsLinkFor('Accelon Inc.')`));
  assert.equal(link.direct, false);
  assert.equal(link.url, 'https://www.linkedin.com/jobs/search/?keywords=Accelon%20Inc.');
  assert.ok(!/google\.com/.test(link.url));
});

test('Jobs link: placeholders that are not employers get no link', () => {
  const app = loadApp({ rows: { anvay: [], anil: [], bilwa: [] } });
  for (const name of ['Freelance', 'Self-employed', 'Stealth Startup', 'Career break', '5G Stealth', 'No company listed']) {
    assert.equal(app.run(`jobsLinkFor(${JSON.stringify(name)})`), null, name);
  }
});

test('Jobs link: a variant without its own page falls back to the parent company page', () => {
  const app = loadApp({ rows: { anvay: [person('Oracle America')], anil: [], bilwa: [] } });
  app.run(`jobsUrlByName.set('oracle', 'https://www.linkedin.com/company/oracle/jobs/')`);
  assert.equal(app.run(`jobsLinkFor('Oracle America').url`), 'https://www.linkedin.com/company/oracle/jobs/');
});

test('Jobs link: a verified page wins over the guessed one', () => {
  const app = loadApp({ rows: { anvay: [person('KLA')], anil: [], bilwa: [] } });
  app.run(`jobsUrlByName.set('kla', 'https://www.linkedin.com/company/kla/jobs/');
           verifiedUrlByName.set('kla', 'https://www.linkedin.com/company/klacorp/jobs/')`);
  const link = plain(app.run(`jobsLinkFor('KLA')`));
  assert.equal(link.url, 'https://www.linkedin.com/company/klacorp/jobs/');
  assert.equal(link.verified, true);
});

test('Jobs buttons: search links are labelled honestly and one is shown per distinct URL', () => {
  const app = loadApp({ rows: { anvay: [], anil: [], bilwa: [] } });
  const one = app.run(`createJobsButtons(['Accelon Inc.', 'Accelon Inc.'])`);
  assert.match(one, /Search jobs on LinkedIn/);
  assert.doesNotMatch(one, /View Jobs on LinkedIn/);
  assert.equal((one.match(/<a /g) || []).length, 1);
  assert.equal(app.run(`createJobsButtons(['Freelance'])`), '', 'no button for non-employers');
});

test('loadJobsLinks keeps only real LinkedIn company pages and converts verified URLs', async () => {
  const csv = {
    'linkedin_jobs_final.csv': { fields: ['Company', 'Job_page'], data: [
      { Company: 'Apple', Job_page: 'https://www.linkedin.com/company/apple/jobs/' },
      { Company: 'Mariana Minerals', Job_page: 'https://www.google.com/search?q=Mariana+Minerals+linkedin+jobs' }
    ] },
    'company_linkedin_urls.csv': { fields: ['Company', 'LinkedIn_URL'], data: [
      { Company: 'Mariana Minerals', LinkedIn_URL: 'https://www.linkedin.com/company/mariana-minerals/' },
      { Company: 'Arteris', LinkedIn_URL: '' }
    ] }
  };
  const app = loadApp({ papa: (p, o) => {
    const key = Object.keys(csv).find(k => p.includes(k));
    o.complete({ data: csv[key].data, meta: { fields: csv[key].fields } });
  } });
  await app.run('loadJobsLinks()');
  assert.equal(app.run(`jobsLinkFor('Apple').url`), 'https://www.linkedin.com/company/apple/jobs/');
  assert.equal(app.run(`jobsLinkFor('Mariana Minerals').url`), 'https://www.linkedin.com/company/mariana-minerals/jobs/');
  assert.equal(app.run(`jobsLinkFor('Arteris').direct`), false);
});

test('loadJobsLinks failures are not fatal', async () => {
  const app = loadApp({ papa: (p, o) => o.error(new Error('Not Found')) });
  await app.run('loadJobsLinks()');
  assert.equal(app.run(`jobsLinkFor('Apple').direct`), false);
});

// ---------------------------------------------------------------------------
// Companies tab
// ---------------------------------------------------------------------------

function companiesApp() {
  const shared = person('Amazon Web Services (AWS)');
  const app = loadApp({ rows: {
    anvay: [person('Amazon'), shared, person('Google'), person('Freelance'), person('Solo Inc'),
            person('Stealth Startup'), person('Stealth Startup'), person('Stealth Startup')],
    anil: [{ ...shared }, person('Google')],
    bilwa: [person('Google')]
  } });
  return app;
}

test('Companies tab: only companies with 2+ people; Amazon and AWS are one row', () => {
  const app = companiesApp();
  app.run('renderCompaniesView()');
  const html = app.els.jobsTableContainer.innerHTML;
  const rows = html.match(/class="company-row"/g) || [];
  assert.equal(rows.length, 2, 'Google (3 people) and Amazon (2 people) only');
  assert.equal((html.match(/>Amazon<\/button>/g) || []).length, 1);
  assert.match(html, /Includes: Amazon, Amazon Web Services \(AWS\)|Includes: Amazon Web Services \(AWS\), Amazon/);
  assert.doesNotMatch(html, />Solo Inc</, 'a single connection is not listed');
  assert.doesNotMatch(html, /Freelance/);
  assert.doesNotMatch(html, /Stealth Startup/, 'placeholder employers are not an overlap, even with 3 people');
  assert.match(app.els.jobsMeta.textContent, /^2 companies with 2\+ connections · 5 people$/);
});

test('Companies tab: sorted by unique people, each company lists its people with owner dots', () => {
  const app = companiesApp();
  app.run('renderCompaniesView()');
  const html = app.els.jobsTableContainer.innerHTML;
  assert.ok(html.indexOf('>Google</button>') < html.indexOf('>Amazon</button>'), '3 Google people > 2 Amazon people');
  assert.match(html, />3 connections</);
  // the person who is in both Anvay's and Anil's list gets two dots and a spoken label
  assert.match(html, /<span class="owner-dot owner-anvay"><\/span><span class="owner-dot owner-anil"><\/span><\/span>P\d+ X<span class="sr-only"> \(in Anvay&#39;s, Anil&#39;s list\)/);
  assert.equal((html.match(/<li class="member-chip"/g) || []).length, 5, '3 Google + 2 Amazon people');
});

test('Companies tab: filter uses the same company grouping (aws finds Amazon)', () => {
  const app = companiesApp();
  app.els.jobsTableFilter = Object.assign(app.els.jobsTableFilter || {}, { value: 'aws' });
  app.run('renderCompaniesView()');
  const html = app.els.jobsTableContainer.innerHTML;
  assert.match(html, />Amazon<\/button>/);
  assert.doesNotMatch(html, />Google<\/button>/);
  assert.match(app.els.jobsMeta.textContent, /^1 of 2 companies with 2\+ connections/);
});

test('Companies tab: a filter with no hit explains where single-connection companies went', () => {
  const app = companiesApp();
  app.els.jobsTableFilter = Object.assign(app.els.jobsTableFilter || {}, { value: 'solo' });
  app.run('renderCompaniesView()');
  assert.match(app.els.jobsTableContainer.innerHTML, /Companies with a single connection are not listed/);
});

test('Companies tab: jobs buttons are real links and rows open the company on the Connections tab', () => {
  const app = companiesApp();
  app.run(`jobsUrlByName.set('google', 'https://www.linkedin.com/company/google/jobs/')`);
  app.run('setupTabs(); renderCompaniesView()');
  assert.match(app.els.jobsTableContainer.innerHTML, /<a href="https:\/\/www\.linkedin\.com\/company\/google\/jobs\/"/);

  const click = app.els.jobsTableContainer.listeners.click[0];
  const rowTarget = { closest: sel => (sel === 'a' ? null : { getAttribute: () => 'google' }) };
  click({ target: rowTarget });
  assert.equal(app.els.companySearch.value, 'Google');
  assert.equal(app.els.tabConnections.attrs['aria-selected'], 'true');
  assert.ok(app.els.jobsPanel.classes.has('hidden'));
  assert.equal(app.els.anvayCount.textContent, 1);
  assert.equal(app.els.anilCount.textContent, 1);
  assert.equal(app.els.bilwaCount.textContent, 1);

  // a click on the jobs link itself must not navigate away from the Companies tab
  app.run(`showTab('jobs')`);
  click({ target: { closest: sel => (sel === 'a' ? {} : null) } });
  assert.equal(app.els.tabJobs.attrs['aria-selected'], 'true');
});

// ---------------------------------------------------------------------------
// Landing view, tabs (ARIA), login form, result markup
// ---------------------------------------------------------------------------

test('Landing: summary and biggest-overlap chips, hidden once a search runs and back after clear', () => {
  const app = companiesApp();
  app.run('renderLanding()');
  assert.match(app.els.landingSummary.innerHTML, /<strong>10<\/strong> people across 3 lists \(Anvay 8 · Anil 2 · Bilwa 1\)/);
  assert.match(app.els.landingSummary.innerHTML, /<strong>5<\/strong> companies/);
  const chips = app.els.landingChips.innerHTML;
  assert.match(chips, /data-key="google"[^>]*>Google <span class="landing-chip-count">3</);
  assert.ok(chips.indexOf('Google') < chips.indexOf('Amazon'));
  assert.doesNotMatch(chips, /Stealth|Freelance|Solo/);

  app.run(`searchCompany('Google')`);
  assert.ok(app.els.landing.classes.has('hidden'));
  assert.match(app.els.resultsStatus.textContent, /Google: 3 connections found/);
  app.run('clearSearch()');
  assert.ok(!app.els.landing.classes.has('hidden'));
  assert.equal(app.els.resultsStatus.textContent, '');
});

test('Landing: a chip opens that company', () => {
  const app = companiesApp();
  app.run('setupTabs(); renderLanding()');
  app.els.landingChips.listeners.click[0]({ target: { closest: () => ({ getAttribute: () => 'amazon' }) } });
  assert.equal(app.els.companySearch.value, 'Amazon');
  assert.equal(app.els.anvayCount.textContent, 2);
});

test('Tabs: arrow keys, Home and End move between tabs and keep one tab in the tab order', () => {
  const app = companiesApp();
  app.run('setupTabs()');
  const key = (el, k) => el.listeners.keydown[0]({ key: k, preventDefault() {} });

  key(app.els.tabConnections, 'ArrowRight');
  assert.equal(app.els.tabJobs.attrs['aria-selected'], 'true');
  assert.equal(app.els.tabJobs.attrs.tabindex, '0');
  assert.equal(app.els.tabConnections.attrs.tabindex, '-1');
  assert.ok(!app.els.jobsPanel.classes.has('hidden'));
  assert.ok(app.els.connectionsPanel.classes.has('hidden'));

  key(app.els.tabJobs, 'ArrowLeft');
  assert.equal(app.els.tabConnections.attrs['aria-selected'], 'true');
  key(app.els.tabConnections, 'End');
  assert.equal(app.els.tabJobs.attrs['aria-selected'], 'true');
  key(app.els.tabJobs, 'Home');
  assert.equal(app.els.tabConnections.attrs['aria-selected'], 'true');

  let prevented = false;
  app.els.tabConnections.listeners.keydown[0]({ key: 'a', preventDefault() { prevented = true; } });
  assert.equal(prevented, false, 'other keys are left alone');
});

test('Login: wrong password shows an inline error, right password opens the app and loads data', () => {
  const app = loadApp();
  app.run(`globalThis.loaded = 0; loadAllCSVs = () => { loaded += 1; return Promise.resolve([]); }; setupLogin();`);
  const submit = app.els.loginForm.listeners.submit[0];
  let prevented = 0;
  const ev = { preventDefault() { prevented += 1; } };

  app.els.loginPassword.value = 'nope';
  submit(ev);
  assert.ok(!app.els.loginError.classes.has('hidden'));
  assert.match(app.els.loginError.textContent, /Incorrect password/);
  assert.equal(app.els.loginPassword.attrs['aria-invalid'], 'true');
  assert.equal(app.els.loginPassword.value, '', 'the wrong guess is cleared');
  assert.equal(app.run('loaded'), 0);

  app.els.loginPassword.value = 'connections';
  submit(ev);
  assert.equal(prevented, 2, 'the form never submits natively');
  assert.equal(app.run('loaded'), 1);
  assert.ok(app.els.loginForm.classes.has('hidden'));
  assert.ok(!app.els.appPanel.classes.has('hidden'));
  assert.ok(app.els.loginError.classes.has('hidden'));
  assert.equal(app.els.loginPassword.getAttribute('aria-invalid'), null);
});

test('Result rows: stacked-card labels, descriptive View links, escaped fields', () => {
  const app = loadApp({ rows: { anvay: [{ ...person('Acme <b>'), 'First Name': '<i>Ann', Position: 'Dev & "Ops"' }], anil: [], bilwa: [] } });
  app.run(`searchCompany('Acme')`);
  const html = app.els.resultsContainer.innerHTML;
  for (const label of ['Name', 'Company', 'Position', 'LinkedIn']) assert.match(html, new RegExp(`<td data-label="${label}"`));
  assert.match(html, /aria-label="View &lt;i&gt;Ann X on LinkedIn \(opens in a new tab\)"/);
  assert.match(html, /rel="noopener noreferrer"/);
  assert.doesNotMatch(html, /<i>Ann|<b>/);
  assert.match(html, /Dev &amp; &quot;Ops&quot;/);
});

test('index.html: labels, tab roles and panel wiring that script.js relies on', () => {
  const fs = require('node:fs');
  const path = require('node:path');
  const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
  assert.match(html, /<label for="companySearch"/);
  assert.match(html, /<label for="jobsTableFilter"/);
  assert.match(html, /<label for="loginPassword"/);
  assert.match(html, /role="tablist"/);
  assert.equal((html.match(/role="tab"/g) || []).length, 2);
  assert.match(html, /id="tabConnections"[^>]*aria-controls="connectionsPanel"/);
  assert.match(html, /id="tabJobs"[^>]*aria-controls="jobsPanel"/);
  assert.match(html, /id="connectionsPanel" role="tabpanel" aria-labelledby="tabConnections"/);
  assert.match(html, /id="jobsPanel" class="hidden" role="tabpanel" aria-labelledby="tabJobs"/);
  assert.match(html, /type="password"[^>]*autocomplete="current-password"|autocomplete="current-password"[^>]*type="password"|id="loginPassword" type="password" autocomplete="current-password"/);
  // the whole app sits inside #appPanel, which starts hidden
  assert.match(html, /<div id="appPanel" class="hidden">/);
});

// ---------------------------------------------------------------------------
// Result rendering: overlap, unique counts, employment notes, clear
// ---------------------------------------------------------------------------

function overlapApp() {
  const both = person('Google');
  return loadApp({ rows: {
    anvay: [both, person('Google')],
    anil: [{ ...both }],
    bilwa: [{ ...both }, person('Google')]
  } });
}

test('Stat tiles show the per-list counts', () => {
  const app = overlapApp();
  app.run(`searchCompany('Google')`);
  const tiles = ['anvayCount', 'anilCount', 'bilwaCount'].map(id => app.els[id].textContent);
  assert.deepEqual(tiles, [2, 1, 2]);
  assert.equal(app.els.statsContainer.style.display, 'flex');
});

test('Every element id script.js looks up exists in index.html', () => {
  // The test DOM stub returns a fake element for any id, so a removed element would
  // pass the other tests and then throw in a real browser. This catches that.
  const fs = require('node:fs');
  const path = require('node:path');
  const root = path.join(__dirname, '..');
  const js = fs.readFileSync(path.join(root, 'script.js'), 'utf8');
  const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
  const ids = [...new Set([...js.matchAll(/getElementById\('([^']+)'\)/g)].map(m => m[1]))];
  const missing = ids.filter(id => !new RegExp(`id="${id}"`).test(html));
  assert.deepEqual(missing, [], `ids used in script.js but missing from index.html: ${missing.join(', ')}`);
  assert.ok(ids.length >= 10, 'sanity: the scan found the ids');
});

test('Results show which other lists a person is also in', () => {
  const app = overlapApp();
  app.run(`searchCompany('Google')`);
  const html = app.els.resultsContainer.innerHTML;
  assert.match(html, /Also in Anil's, Bilwa's list/);   // the shared person, in Anvay's table
  assert.match(html, /Also in Anvay's, Bilwa's list/);  // ... and in Anil's table
});

test('Employment notes: "may no longer work here", and Previously-at only for confirmed moves', () => {
  const app = loadApp({ rows: { anil: [], bilwa: [], anvay: [
    person('Acme', { Still_Employed: 'No' }),
    person('SI-BONE', { Employment_Changed: 'Yes', Previous_Company: 'NASA <b>Ames</b>', Previous_Position: 'Engineer' }),
    person('Initech', { Employment_Changed: 'Review', Scraped_Company: 'Experience' })
  ] } });
  app.run(`searchCompany('Acme')`);
  assert.match(app.els.resultsContainer.innerHTML, /may no longer work here/);
  app.run(`searchCompany('SI-BONE')`);
  const moved = app.els.resultsContainer.innerHTML;
  assert.match(moved, /Previously at NASA &lt;b&gt;Ames&lt;\/b&gt; \(Engineer\)/, 'escaped');
  app.run(`searchCompany('Initech')`);
  const review = app.els.resultsContainer.innerHTML;
  assert.doesNotMatch(review, /Previously at|Experience|may no longer/);
});

test('Clear button empties the input, the results and the stat tiles', () => {
  const app = loadApp({ rows: { anvay: [person('Google')], anil: [], bilwa: [] } });
  app.els.companySearch = Object.assign(app.els.companySearch || {}, { value: 'Google' });
  app.run(`searchCompany('Google')`);
  assert.notEqual(app.els.resultsContainer.innerHTML, '');
  assert.equal(app.els.statsContainer.style.display, 'flex');
  app.run('clearSearch()');
  assert.equal(app.els.companySearch.value, '');
  assert.equal(app.els.resultsContainer.innerHTML, '');
  assert.equal(app.els.statsContainer.style.display, 'none');
  assert.equal(app.els.companySuggestions.style.display, 'none');
});

// ---------------------------------------------------------------------------
// Dropdown: total counter and keyboard navigation
// ---------------------------------------------------------------------------

test('Suggestions report the total so the dropdown can say "Showing 10 of N"', () => {
  const many = Array.from({ length: 14 }, (_, i) => person(`Acme Labs ${String.fromCharCode(65 + i)}`));
  const app = loadApp({ rows: { anvay: many, anil: [], bilwa: [] } });
  const result = plain(app.run(`(() => { const r = suggestGroupsWithTotal('acme'); return { shown: r.groups.length, total: r.total }; })()`));
  assert.deepEqual(result, { shown: 10, total: 14 });
});

test('nextSuggestionIndex moves and wraps', () => {
  const app = loadApp({});
  const next = (a, c, k) => app.run(`nextSuggestionIndex(${a}, ${c}, '${k}')`);
  assert.equal(next(-1, 3, 'ArrowDown'), 0);
  assert.equal(next(2, 3, 'ArrowDown'), 0, 'wraps to the top');
  assert.equal(next(-1, 3, 'ArrowUp'), 2, 'from nothing, Up goes to the last item');
  assert.equal(next(0, 3, 'ArrowUp'), 2, 'wraps to the bottom');
  assert.equal(next(1, 0, 'ArrowDown'), -1, 'empty list');
});

test('Keyboard: ArrowDown + Enter picks the highlighted suggestion; Enter alone searches the text; Escape closes', () => {
  const app = loadApp({ rows: { anvay: [person('Amazon'), person('Amazon Web Services (AWS)'), person('Google')], anil: [], bilwa: [] } });
  app.run('setupUI()');
  const input = app.els.companySearch;
  const box = app.els.companySuggestions;
  const key = (k) => { const e = { key: k, preventDefault() { e.prevented = true; } }; input.listeners.keydown.forEach(fn => fn(e)); return e; };

  input.value = 'ama';
  input.listeners.input.forEach(fn => fn());
  assert.equal(box.style.display, 'block');
  assert.equal(input.attrs['aria-expanded'], 'true');

  assert.equal(key('ArrowDown').prevented, true);
  key('Enter');
  assert.equal(input.value, 'Amazon');
  assert.match(app.els.resultsContainer.innerHTML, /Search Results for: <span class="text-primary">Amazon/);

  input.value = 'google';
  input.listeners.input.forEach(fn => fn());
  key('Enter');   // nothing highlighted: plain search
  assert.match(app.els.resultsContainer.innerHTML, /Search Results for: <span class="text-primary">Google/);
  assert.equal(box.style.display, 'none');

  input.value = 'ama';
  input.listeners.input.forEach(fn => fn());
  assert.equal(box.style.display, 'block');
  key('Escape');
  assert.equal(box.style.display, 'none');
  assert.equal(input.attrs['aria-expanded'], 'false');
});

// ---------------------------------------------------------------------------
// Load errors
// ---------------------------------------------------------------------------

function fakePapa(spec) {
  return (path, options) => {
    const entry = Object.entries(spec).find(([k]) => path.includes(k));
    const result = entry ? entry[1] : { fields: ['Company', 'Job_page'], data: [] };
    if (result.error) { options.error(new Error(result.error)); return; }
    options.complete({ data: result.data, meta: { fields: result.fields } });
  };
}

test('Load: one failing CSV does not blank the app and is named in the banner', async () => {
  const app = loadApp({ papa: fakePapa({
    'anvay-connections': { fields: FIELDS, data: [person('Google')] },
    'anil-connections': { error: 'Not Found' },
    'bilwa-connections': { fields: ['Company', 'Position'], data: [{ Company: 'x' }] }   // missing columns
  }) });
  const failures = plain(await app.run('loadAllCSVs()'));
  assert.deepEqual(failures.map(f => f.file), [
    'updated_data/anil-connections_updated.csv',
    'updated_data/bilwa-connections_updated.csv'
  ]);
  assert.match(failures[0].message, /Not Found/);
  assert.match(failures[1].message, /missing column/);
  const banner = app.els.loadErrorBanner;
  assert.equal(banner.style.display, 'block');
  assert.match(banner.innerHTML, /anil-connections_updated\.csv: Not Found/);
  // the list that did load is still searchable
  assert.equal(app.run(`resolveQuery('Google')[0].anvay_count`), 1);
});

test('Load: the banner text is HTML-escaped', async () => {
  const app = loadApp({ papa: fakePapa({ 'anvay-connections': { error: '<img src=x onerror=alert(1)>' } }) });
  await app.run('loadAllCSVs()');
  assert.doesNotMatch(app.els.loadErrorBanner.innerHTML, /<img/);
});

test('Load: opening from file:// adds a hint to run a local server', async () => {
  const app = loadApp({ location: { protocol: 'file:' }, papa: fakePapa({ 'anvay-connections': { error: 'blocked' } }) });
  await app.run('loadAllCSVs()');
  assert.match(app.els.loadErrorBanner.innerHTML, /make start/);
});

test('Load: no failures hides the banner', async () => {
  const app = loadApp({ papa: fakePapa({
    'anvay-connections': { fields: FIELDS, data: [person('Google')] },
    'anil-connections': { fields: FIELDS, data: [] },
    'bilwa-connections': { fields: FIELDS, data: [] }
  }) });
  const failures = plain(await app.run('loadAllCSVs()'));
  assert.deepEqual(failures, []);
  assert.equal(app.els.loadErrorBanner.style.display, 'none');
});
