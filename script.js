// script.js

// Password configuration
const CORRECT_PASSWORD = 'connections'; // Change this to your desired password

// Bump DATA_VERSION whenever a CSV changes, so browsers do not keep serving a cached copy.
const DATA_VERSION = '20261125-1';

const csvFiles = {
  anvay: `updated_data/anvay-connections_updated.csv?v=${DATA_VERSION}`,
  anil: `updated_data/anil-connections_updated.csv?v=${DATA_VERSION}`,
  bilwa: `updated_data/bilwa-connections_updated.csv?v=${DATA_VERSION}`
};

const linkedInJobsFile = 'linkedin_jobs_final.csv?v=20261120-1';
// Optional: company pages confirmed against real profiles by verify_company_linkedin_links.py.
const verifiedLinksFile = 'updated_data/company_linkedin_urls.csv?v=20261120-1';

const dataStore = {
  anvay: [],
  anil: [],
  bilwa: []
};

const OWNER_LABELS = { anvay: "Anvay's", anil: "Anil's", bilwa: "Bilwa's" };
const REQUIRED_COLUMNS = ['First Name', 'Last Name', 'URL', 'Company'];

const NO_COMPANY_KEY = 'no company listed';
const NO_COMPANY_LABEL = 'No company listed';

// Placeholders that are not employers: a LinkedIn jobs link would be meaningless.
const NON_EMPLOYERS = new Set([
  'freelance', 'self employed', 'stealth startup', 'stealth', '5g stealth', 'career break', NO_COMPANY_KEY
]);

const COMPANY_PAGE_RE = /^https?:\/\/(?:www\.)?linkedin\.com\/company\/([^/?#]+)/i;

let jobsUrlByName = new Map();      // normalized company name -> LinkedIn company jobs page
let verifiedUrlByName = new Map();  // same, but confirmed from real profiles (wins over the above)
let ownersByPerson = new Map();     // personKey -> Set of owners whose list contains them
let isAuthenticated = false;

// ---------------------------------------------------------------------------
// Loading
// ---------------------------------------------------------------------------

function parseCsv(path, requiredColumns = []) {
  return new Promise((resolve, reject) => {
    Papa.parse(path, {
      download: true,
      header: true,
      skipEmptyLines: true,
      complete: results => {
        const fields = (results.meta && results.meta.fields) || [];
        const missing = requiredColumns.filter(col => !fields.includes(col));
        if (missing.length) {
          reject(new Error(`file is empty or missing column(s): ${missing.join(', ')}`));
          return;
        }
        resolve(results.data || []);
      },
      error: err => reject(err instanceof Error ? err : new Error((err && err.message) || String(err || 'download failed')))
    });
  });
}

// A row marked Hidden=Yes (optional column) stays in the file but is never shown or counted,
// e.g. someone with no current employment.
function isHidden(row) {
  return /^(yes|true|1)$/i.test((row.Hidden || '').trim());
}

async function loadCSV(path, label) {
  const rows = await parseCsv(path, REQUIRED_COLUMNS);
  dataStore[label] = rows.filter(row => !isHidden(row));
}

// Jobs links are an enhancement: if these files fail to load, every company simply
// falls back to a LinkedIn job search, so failures here are not fatal.
async function loadJobsLinks() {
  jobsUrlByName = new Map();
  verifiedUrlByName = new Map();

  const load = async (file, target, column) => {
    try {
      const rows = await parseCsv(file);
      rows.forEach(row => {
        const company = (row.Company || '').trim();
        const match = COMPANY_PAGE_RE.exec((row[column] || '').trim());
        if (company && match) {
          target.set(normalizeCompany(company), `https://www.linkedin.com/company/${match[1]}/jobs/`);
        }
      });
    } catch (err) {
      /* optional file */
    }
  };

  await load(linkedInJobsFile, jobsUrlByName, 'Job_page');
  await load(verifiedLinksFile, verifiedUrlByName, 'LinkedIn_URL');
}

function showLoadErrors(failures) {
  const banner = document.getElementById('loadErrorBanner');
  if (!banner) return;
  if (!failures.length) {
    banner.style.display = 'none';
    banner.innerHTML = '';
    return;
  }
  const openedFromDisk = typeof location !== 'undefined' && location.protocol === 'file:';
  const hint = openedFromDisk
    ? '<div class="mt-1">This page was opened as a file. Browsers block that: run <code>make start</code> and open <code>http://localhost:8080</code> instead.</div>'
    : '';
  banner.innerHTML = `<strong>Some data could not be loaded.</strong><ul class="mb-0">${
    failures.map(f => `<li>${escapeHtml(f.file)}: ${escapeHtml(f.message)}</li>`).join('')
  }</ul>${hint}`;
  banner.style.display = 'block';
}

async function loadAllCSVs() {
  const failures = [];
  for (const key of Object.keys(csvFiles)) {
    try {
      await loadCSV(csvFiles[key], key);
    } catch (err) {
      dataStore[key] = [];
      failures.push({ file: csvFiles[key].split('?')[0], message: (err && err.message) || String(err) });
    }
  }
  await loadJobsLinks();
  buildCompanyIndex();
  showLoadErrors(failures);
  setupUI();
  setupTabs();
  renderLanding();
  renderCompaniesView();
  return failures;
}

// One stable id per human: LinkedIn URL when there is one, else the name.
function personKey(row) {
  const url = (row.URL || '').trim().toLowerCase().replace(/\/+$/, '');
  return url.startsWith('http')
    ? url
    : `name:${(row['First Name'] || '').trim().toLowerCase()}|${(row['Last Name'] || '').trim().toLowerCase()}`;
}

// ---------------------------------------------------------------------------
// LinkedIn jobs links
//   - a known company page (linkedin_jobs_final.csv / verified file) -> direct link
//   - anything else -> LinkedIn job search for the company name
//   - placeholders such as "Freelance" -> no link
// ---------------------------------------------------------------------------

function jobsLinkFor(name) {
  const norm = normalizeCompany(name);
  if (!norm || NON_EMPLOYERS.has(norm)) return null;

  // Own page first; otherwise the parent company's page (e.g. "Oracle America" -> Oracle).
  const key = companyKey(name);
  const own = verifiedUrlByName.get(norm) || jobsUrlByName.get(norm);
  const parent = verifiedUrlByName.get(key) || jobsUrlByName.get(key);
  const stored = own || parent;
  if (stored) {
    const verified = own ? verifiedUrlByName.has(norm) : verifiedUrlByName.has(key);
    return { url: stored, direct: true, verified };
  }

  const keywords = String(name).split('·')[0].replace(/[-]/g, '').trim();
  return {
    url: `https://www.linkedin.com/jobs/search/?keywords=${encodeURIComponent(keywords)}`,
    direct: false,
    verified: false
  };
}

// One button per distinct destination among the given company names
// (Amazon and AWS have separate job pages, so both get a button).
function createJobsButtons(names, maxButtons = 4) {
  const byUrl = new Map();
  names.forEach(name => {
    const link = jobsLinkFor(name);
    if (link && !byUrl.has(link.url)) byUrl.set(link.url, { name, link });
  });
  if (byUrl.size === 0 || byUrl.size > maxButtons) return '';

  const many = byUrl.size > 1;
  return Array.from(byUrl.values()).map(({ name, link }) => {
    const label = link.direct
      ? (many ? `${name} Jobs` : 'View Jobs on LinkedIn')
      : (many ? `Search "${name}"` : 'Search jobs on LinkedIn');
    return `
    <a href="${escapeHtml(link.url)}" target="_blank" rel="noopener noreferrer" class="jobs-link-btn${link.direct ? '' : ' jobs-link-btn-search'}">
      <i class="${link.direct ? 'fab fa-linkedin' : 'fas fa-search'}"></i> ${escapeHtml(label)}
    </a>`;
  }).join('');
}

// ---------------------------------------------------------------------------
// Company normalization and grouping
//
// The CSVs store company as free text, so "Amazon", "Amazon Web Services (AWS)",
// "Oracle Corp." and "Oracle Corp[oration" are all different strings. We map every
// raw name to a canonical group key so a search finds all of them together.
//   1. normalizeCompany() lowercases, strips punctuation and legal suffixes
//      ("Inc.", "Corporation", ...), so spelling variants collapse by themselves.
//   2. COMPANY_ALIASES covers names that are genuinely different strings for the
//      same company (subsidiaries, rebrands, typos).
// ---------------------------------------------------------------------------

// Canonical display name -> other names that should be treated as the same company.
// Add a line here whenever two names in the data refer to one company.
const COMPANY_ALIASES = {
  'Amazon': ['Amazon Web Services (AWS)', 'Amazon Web Services', 'AWS', 'Amazon.com'],
  'Meta': ['Facebook', 'Meta Platforms'],
  'Google': ['Alphabet', 'Google LLC'],
  'Oracle': ['Oracle Corp[oration', 'Oracle America'],
  'KLA': ['KLA-Tencor', 'KLA Corporation']
};

const LEGAL_SUFFIXES = new Set([
  'inc', 'incorporated', 'llc', 'llp', 'lp', 'ltd', 'limited',
  'corp', 'corporation', 'co', 'company', 'plc', 'gmbh'
]);

// Commas that belong to the company name ("Reddit, Inc."), not list separators.
const MULTI_SEARCH_SPLIT = /,(?!\s*(?:inc|llc|llp|ltd|corp|co|plc|lp)\b)/i;

function tokenizeCompany(name) {
  return String(name || '')
    .split('·')[0]
    .replace(/[-]/g, ' ')   // private-use glyphs (e.g. the Apple logo char)
    .toLowerCase()
    .replace(/&/g, ' and ')
    .replace(/[^\p{L}\p{N}]+/gu, ' ')
    .trim()
    .split(' ')
    .filter(Boolean);
}

function normalizeCompany(name) {
  const tokens = tokenizeCompany(name);
  if (tokens.length > 1 && tokens[0] === 'the') tokens.shift();
  while (tokens.length > 1) {
    const last = tokens[tokens.length - 1];
    if (!LEGAL_SUFFIXES.has(last) && last !== 'and') break;
    tokens.pop();
  }
  return tokens.join(' ');
}

// normalized alias -> normalized canonical key
const aliasIndex = new Map();
const aliasNamesByKey = new Map();   // canonical key -> [alias display names]
Object.entries(COMPANY_ALIASES).forEach(([canonical, aliases]) => {
  const key = normalizeCompany(canonical);
  aliasNamesByKey.set(key, aliases);
  aliasIndex.set(key, key);
  aliases.forEach(alias => aliasIndex.set(normalizeCompany(alias), key));
});

function companyKey(rawName) {
  const norm = normalizeCompany(rawName);
  return aliasIndex.get(norm) || norm;
}

// key -> { key, label, variants: Map(rawName -> count), words: Set,
//          people (rows), peopleKeys: Set of unique people,
//          members: Map(personKey -> { name, owners: Set }) }
let companyGroups = new Map();

function buildCompanyIndex() {
  companyGroups = new Map();
  ownersByPerson = new Map();
  Object.keys(dataStore).forEach(owner => {
    dataStore[owner].forEach(row => {
      const raw = (row.Company || '').trim();
      // People with no usable company are kept findable under one shared bucket.
      const key = (raw && companyKey(raw)) || NO_COMPANY_KEY;
      const name = raw || NO_COMPANY_LABEL;
      row._companyKey = key;

      let group = companyGroups.get(key);
      if (!group) {
        group = { key, label: '', variants: new Map(), words: new Set(), people: 0, peopleKeys: new Set(), members: new Map() };
        companyGroups.set(key, group);
      }
      group.variants.set(name, (group.variants.get(name) || 0) + 1);
      group.people += 1;
      const pk = personKey(row);
      group.peopleKeys.add(pk);
      let member = group.members.get(pk);
      if (!member) {
        member = { name: `${row['First Name'] || ''} ${row['Last Name'] || ''}`.trim() || 'Unnamed', owners: new Set() };
        group.members.set(pk, member);
      }
      member.owners.add(owner);
      tokenizeCompany(name).forEach(w => group.words.add(w));

      if (!ownersByPerson.has(pk)) ownersByPerson.set(pk, new Set());
      ownersByPerson.get(pk).add(owner);
    });
  });

  companyGroups.forEach(group => {
    const canonical = Object.keys(COMPANY_ALIASES).find(name => normalizeCompany(name) === group.key);
    if (group.key === NO_COMPANY_KEY) {
      group.label = NO_COMPANY_LABEL;
    } else if (canonical) {
      group.label = canonical;
    } else {
      // Most common spelling wins; ties go to the first one seen.
      group.label = Array.from(group.variants.entries()).sort((a, b) => b[1] - a[1])[0][0];
    }
    tokenizeCompany(group.label).forEach(w => group.words.add(w));
    (aliasNamesByKey.get(group.key) || []).forEach(alias => {
      tokenizeCompany(alias).forEach(w => group.words.add(w));
    });
  });
}

function groupVariantNames(group) {
  return Array.from(group.variants.entries())
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([name]) => name);
}

// Resolve a typed term to company groups.
//  - exact: the term is a known company name or alias -> that one group
//  - otherwise: every word of the term must start a word in the company name
function findGroups(term) {
  const qn = normalizeCompany(term);
  if (!qn) return { groups: [], exact: false };

  const exactGroup = companyGroups.get(aliasIndex.get(qn) || qn);
  if (exactGroup) return { groups: [exactGroup], exact: true };

  const queryWords = tokenizeCompany(term);
  const groups = Array.from(companyGroups.values()).filter(group => {
    const words = Array.from(group.words);
    return queryWords.every(q => words.some(w => w.startsWith(q)));
  });
  groups.sort((a, b) => b.people - a.people || a.label.localeCompare(b.label));
  return { groups, exact: false };
}

function buildBlock(label, groups, exact) {
  const keys = new Set(groups.map(g => g.key));
  const pick = owner => dataStore[owner].filter(row => keys.has(row._companyKey));
  const anvay_matches = pick('anvay');
  const anil_matches = pick('anil');
  const bilwa_matches = pick('bilwa');
  return {
    label,
    groups,
    exact,
    anvay_matches,
    anil_matches,
    bilwa_matches,
    anvay_count: anvay_matches.length,
    anil_count: anil_matches.length,
    bilwa_count: bilwa_matches.length
  };
}

// Turn the contents of the search box into result blocks (one per company searched).
function resolveQuery(query) {
  const trimmed = (query || '').trim();
  if (!trimmed) return [];

  // A whole-string match wins, so "University of California, San Francisco" stays one company.
  const whole = findGroups(trimmed);
  let terms = whole.exact ? [trimmed] : trimmed.split(MULTI_SEARCH_SPLIT).map(s => s.trim()).filter(Boolean);

  const seen = new Set();
  const blocks = [];
  terms.forEach(term => {
    const { groups, exact } = findGroups(term);
    const signature = groups.map(g => g.key).sort().join('|');
    if (groups.length && seen.has(signature)) return;   // "Amazon, AWS" -> one block
    seen.add(signature);
    blocks.push(buildBlock(exact ? groups[0].label : term, groups, exact));
  });
  return blocks;
}

// Every company group whose name (or alias) contains the text, best matches first.
// Used for the dropdown and for the Companies-tab filter.
function matchingGroups(value) {
  const v = value.trim().toLowerCase();
  if (!v) return [];
  // Match against normalized names so "Corporation"/"Inc." don't produce false hits.
  const vn = normalizeCompany(value) || v;
  const matches = [];
  companyGroups.forEach(group => {
    const names = groupVariantNames(group).concat(aliasNamesByKey.get(group.key) || []);
    if (names.some(n => normalizeCompany(n).includes(vn))) matches.push(group);
  });
  matches.sort((a, b) => {
    const aStarts = normalizeCompany(a.label).startsWith(vn) ? 0 : 1;
    const bStarts = normalizeCompany(b.label).startsWith(vn) ? 0 : 1;
    return aStarts - bStarts || b.peopleKeys.size - a.peopleKeys.size || a.label.localeCompare(b.label);
  });
  return matches;
}

function suggestGroupsWithTotal(value, limit = 10) {
  if (value.trim().length < 2) return { groups: [], total: 0 };
  const all = matchingGroups(value);
  return { groups: all.slice(0, limit), total: all.length };
}

function suggestGroups(value, limit = 10) {
  return suggestGroupsWithTotal(value, limit).groups;
}

// ArrowDown/ArrowUp move through the dropdown and wrap around.
function nextSuggestionIndex(active, count, key) {
  if (count <= 0) return -1;
  if (key === 'ArrowDown') return active < 0 ? 0 : (active + 1) % count;
  if (key === 'ArrowUp') return active <= 0 ? count - 1 : active - 1;
  return active;
}

function escapeHtml(value) {
  return String(value == null ? '' : value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

function createBlockJobsLinks(block) {
  const names = [];
  block.groups.forEach(group => names.push(...groupVariantNames(group)));
  return createJobsButtons(names);
}

function createBlockSubtitle(block) {
  if (block.exact) {
    const names = groupVariantNames(block.groups[0]);
    return names.length > 1 ? `Includes: ${names.map(escapeHtml).join(', ')}` : '';
  }
  if (block.groups.length === 0) return '';
  const labels = block.groups.slice(0, 8).map(g => escapeHtml(g.label));
  const more = block.groups.length > 8 ? ` +${block.groups.length - 8} more` : '';
  return `Matched companies: ${labels.join(', ')}${more}`;
}

function createSearchHeader(block) {
  const subtitle = createBlockSubtitle(block);
  return `
    <div class="search-header-row mb-4">
      <div>
        <h3 class="search-header-title">Search Results for: <span class="text-primary">${escapeHtml(block.label)}</span></h3>
        ${subtitle ? `<div class="text-muted small">${subtitle}</div>` : ''}
      </div>
      <div class="search-header-links">${createBlockJobsLinks(block)}</div>
    </div>`;
}

function searchCompany(query) {
  displayResults(resolveQuery(query));
}

function searchGroup(group) {
  displayResults([buildBlock(group.label, [group], true)]);
}

function displayResults(blocks) {
  const statsContainer = document.getElementById('statsContainer');
  const resultsContainer = document.getElementById('resultsContainer');
  const isMulti = blocks.length > 1;
  setLandingVisible(blocks.length === 0);
  const status = document.getElementById('resultsStatus');
  if (status) {
    status.textContent = blocks
      .map(b => `${b.label}: ${b.anvay_count + b.anil_count + b.bilwa_count} connections found`)
      .join('. ');
  }

  if (isMulti || blocks.length === 0) {
    statsContainer.style.display = 'none';
  } else {
    const data = blocks[0];
    statsContainer.style.display = 'flex';
    document.getElementById('anvayCount').textContent = data.anvay_count;
    document.getElementById('anilCount').textContent = data.anil_count;
    document.getElementById('bilwaCount').textContent = data.bilwa_count;
  }

  let html = '';
  blocks.forEach((block, idx) => {
    const highlightClass = isMulti ? `company-highlight-${idx % 5}` : '';
    html += `<div class="${isMulti ? 'multi-company-block mt-8' : ''}">${createSearchHeader(block)}`;
    const total = block.anvay_count + block.anil_count + block.bilwa_count;
    if (total === 0) {
      html += `<div class="result-card mb-8"><div class="table-container"><p class="text-muted mb-0">No connections found for "${escapeHtml(block.label)}".</p></div></div>`;
    } else {
      if (block.anvay_matches.length > 0) {
        html += createResultSection("Anvay's Connections", block.anvay_matches, false, highlightClass);
      }
      if (block.anil_matches.length > 0) {
        html += createResultSection("Anil's Connections", block.anil_matches, false, highlightClass);
      }
      if (block.bilwa_matches.length > 0) {
        html += createResultSection("Bilwa's Connections", block.bilwa_matches, false, highlightClass);
      }
    }
    html += '</div>';
  });
  resultsContainer.innerHTML = html;
}

// "Also in Anil's, Bilwa's list" for people who appear in more than one list.
function alsoInLabels(person, ownerKey) {
  const owners = ownersByPerson.get(personKey(person));
  if (!owners) return [];
  return Object.keys(OWNER_LABELS).filter(key => key !== ownerKey && owners.has(key)).map(key => OWNER_LABELS[key]);
}

function createResultSection(title, data, includeCloseness, highlightClass = '') {
  let sectionClass = '';
  let ownerKey = '';
  if (title.includes("Anvay")) { sectionClass = 'result-anvay'; ownerKey = 'anvay'; }
  else if (title.includes("Anil")) { sectionClass = 'result-anil'; ownerKey = 'anil'; }
  else if (title.includes("Bilwa")) { sectionClass = 'result-bilwa'; ownerKey = 'bilwa'; }
  let allClasses = `result-card ${sectionClass} mb-8`;
  if (highlightClass) allClasses += ` ${highlightClass}`;
  let html = `
    <div class="${allClasses}">
      <div class="result-header">${title} (${data.length} results)</div>
      <div class="table-container">
  `;

  if (data.length === 0) {
    html += '<p class="text-muted">No connections found</p>';
  } else {
    html += `
      <div class="table-responsive">
        <table class="table table-hover">
          <thead>
            <tr>
              <th>Name</th>
              <th>Company</th>
              <th>Position</th>
              ${includeCloseness ? '<th>Closeness</th>' : ''}
              <th>LinkedIn</th>
            </tr>
          </thead>
          <tbody>
    `;

    data.forEach(person => {
      let closenessClass = '';
      if (person['Closeness'] === "1.0" || person['Closeness'] === 1 || person['Closeness'] === "1") {
        closenessClass = 'badge-closeness-1';
      } else if (person['Closeness'] === "2.0" || person['Closeness'] === 2 || person['Closeness'] === "2") {
        closenessClass = 'badge-closeness-2';
      } else {
        closenessClass = 'badge-closeness';
      }
      const colSpan = includeCloseness ? 5 : 4;
      const alsoIn = alsoInLabels(person, ownerKey);
      const fullName = `${person['First Name']} ${person['Last Name']}`;
      // data-label feeds the stacked-card layout on narrow screens (see style.css).
      html += `<tr>
        <td data-label="Name"><div><strong>${escapeHtml(fullName)}</strong>${alsoIn.length ? `<div class="also-in">Also in ${alsoIn.join(', ')} list</div>` : ''}</div></td>
        <td data-label="Company">${escapeHtml(person['Company'])}</td>
        <td data-label="Position">${escapeHtml(person['Position'])}</td>
        ${includeCloseness ? `<td data-label="Closeness"><span class="${closenessClass}">${escapeHtml(person['Closeness'])}</span></td>` : ''}
        <td data-label="LinkedIn"><a href="${escapeHtml(person['URL'])}" target="_blank" rel="noopener noreferrer" class="btn btn-sm btn-outline-primary" aria-label="View ${escapeHtml(fullName)} on LinkedIn (opens in a new tab)"><i class="fab fa-linkedin" aria-hidden="true"></i> View</a></td>
      </tr>`;
      if (person['Still_Employed'] === 'No') {
        html += `<tr class="disclaimer-row"><td colspan="${colSpan}" class="disclaimer-cell">⚠️ LinkedIn suggests this person may no longer work here, but they may still have connections.</td></tr>`;
      }
      if (person['Employment_Changed'] === 'Yes' && (person['Previous_Company'] || '').trim()) {
        const prevPosition = (person['Previous_Position'] || '').trim();
        html += `<tr class="previous-row"><td colspan="${colSpan}" class="previous-cell">↪ Previously at ${escapeHtml(person['Previous_Company'].trim())}${prevPosition ? ` (${escapeHtml(prevPosition)})` : ''}</td></tr>`;
      }
    });

    html += '</tbody></table></div>';
  }

  html += '</div></div>';
  return html;
}

// Reset the search box, results, stat tiles and dropdown.
function clearSearch() {
  const searchInput = document.getElementById('companySearch');
  searchInput.value = '';
  document.getElementById('clearSearchBtn').style.display = 'none';
  document.getElementById('companySuggestions').style.display = 'none';
  document.getElementById('resultsContainer').innerHTML = '';
  document.getElementById('statsContainer').style.display = 'none';
  const status = document.getElementById('resultsStatus');
  if (status) status.textContent = '';
  setLandingVisible(true);
}

function setupUI() {
  const searchInput = document.getElementById('companySearch');
  const suggestionsBox = document.getElementById('companySuggestions');
  const clearBtn = document.getElementById('clearSearchBtn');

  let current = [];   // groups currently listed in the dropdown
  let active = -1;    // keyboard-highlighted index, -1 = none

  searchInput.setAttribute('role', 'combobox');
  searchInput.setAttribute('aria-autocomplete', 'list');
  searchInput.setAttribute('aria-controls', 'companySuggestions');
  searchInput.setAttribute('aria-expanded', 'false');
  suggestionsBox.setAttribute('role', 'listbox');

  function closeSuggestions() {
    suggestionsBox.style.display = 'none';
    searchInput.setAttribute('aria-expanded', 'false');
    active = -1;
  }

  function highlight(index) {
    active = index;
    Array.from(suggestionsBox.getElementsByClassName('suggestion-item')).forEach((el, i) => {
      el.classList.toggle('suggestion-active', i === index);
      el.setAttribute('aria-selected', String(i === index));
      if (i === index && el.scrollIntoView) el.scrollIntoView({ block: 'nearest' });
    });
  }

  searchInput.addEventListener('input', () => {
    const val = searchInput.value;
    clearBtn.style.display = val.length ? 'block' : 'none';
    active = -1;
    if (val.trim().length < 2) {
      closeSuggestions();
      return;
    }
    const { groups, total } = suggestGroupsWithTotal(val);
    current = groups;
    suggestionsBox.innerHTML = groups.map(group => {
      const others = groupVariantNames(group).filter(name => name !== group.label);
      const also = others.length
        ? `<div class="text-xs text-gray-500">also: ${others.slice(0, 2).map(escapeHtml).join(', ')}${others.length > 2 ? '…' : ''}</div>`
        : '';
      return `<div class="suggestion-item px-4 py-2 cursor-pointer hover:bg-indigo-100 active:bg-indigo-200 transition-colors" role="option" aria-selected="false">${escapeHtml(group.label)}${also}</div>`;
    }).join('') + (total > groups.length
      ? `<div class="suggestion-more px-4 py-2 text-xs text-gray-500">Showing ${groups.length} of ${total} matches. Keep typing to narrow it down.</div>`
      : '');
    Array.from(suggestionsBox.getElementsByClassName('suggestion-item')).forEach((el, idx) => {
      el.addEventListener('click', () => selectSuggestion(groups[idx]));
    });
    suggestionsBox.style.display = groups.length ? 'block' : 'none';
    searchInput.setAttribute('aria-expanded', groups.length ? 'true' : 'false');
  });

  searchInput.addEventListener('keydown', e => {
    const open = suggestionsBox.style.display === 'block' && current.length > 0;
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      if (!open) return;
      e.preventDefault();
      highlight(nextSuggestionIndex(active, current.length, e.key));
    } else if (e.key === 'Escape') {
      closeSuggestions();
    } else if (e.key === 'Enter') {
      if (open && active >= 0) {
        e.preventDefault();
        selectSuggestion(current[active]);
      } else {
        searchCompany(searchInput.value);
        closeSuggestions();
      }
    }
  });

  clearBtn.style.display = searchInput.value.length ? 'block' : 'none';

  document.addEventListener('click', e => {
    if (!e.target.closest('#companySearch') && !e.target.closest('#companySuggestions')) {
      closeSuggestions();
    }
  });

  clearBtn.addEventListener('click', () => {
    clearSearch();
    current = [];
    active = -1;
    searchInput.setAttribute('aria-expanded', 'false');
    searchInput.focus();
  });
  clearBtn.addEventListener('mousedown', e => { e.stopPropagation(); });
}

function selectSuggestion(group) {
  document.getElementById('companySearch').value = group.label;
  document.getElementById('companySuggestions').style.display = 'none';
  searchGroup(group);
}

// ---------------------------------------------------------------------------
// Tabs
// ---------------------------------------------------------------------------

function showTab(which) {
  const tabs = { connections: 'tabConnections', jobs: 'tabJobs' };
  const panels = { connections: 'connectionsPanel', jobs: 'jobsPanel' };
  Object.keys(tabs).forEach(name => {
    const on = name === which;
    const tab = document.getElementById(tabs[name]);
    tab.classList.toggle('tab-btn-active', on);
    tab.setAttribute('aria-selected', String(on));
    tab.setAttribute('tabindex', on ? '0' : '-1');
    document.getElementById(panels[name]).classList.toggle('hidden', !on);
  });
  if (which === 'jobs') renderCompaniesView();
}

function setupTabs() {
  const order = ['connections', 'jobs'];
  const ids = { connections: 'tabConnections', jobs: 'tabJobs' };
  order.forEach((name, i) => {
    const tab = document.getElementById(ids[name]);
    tab.addEventListener('click', () => showTab(name));
    // WAI-ARIA tabs: arrow keys, Home and End move between tabs.
    tab.addEventListener('keydown', e => {
      let target = null;
      if (e.key === 'ArrowRight') target = order[(i + 1) % order.length];
      else if (e.key === 'ArrowLeft') target = order[(i + order.length - 1) % order.length];
      else if (e.key === 'Home') target = order[0];
      else if (e.key === 'End') target = order[order.length - 1];
      if (!target) return;
      e.preventDefault();
      showTab(target);
      document.getElementById(ids[target]).focus();
    });
  });

  document.getElementById('jobsTableFilter')?.addEventListener('input', renderCompaniesView);
  document.getElementById('jobsTableContainer')?.addEventListener('click', e => {
    if (e.target.closest('a')) return;               // the jobs buttons are real links
    const row = e.target.closest('.company-row');
    if (row) openGroup(row.getAttribute('data-key'));
  });
  document.getElementById('landingChips')?.addEventListener('click', e => {
    const chip = e.target.closest('[data-key]');
    if (chip) openGroup(chip.getAttribute('data-key'));
  });
}

// Show one company's connections on the Connections tab (used by chips and company rows).
function openGroup(key) {
  const group = companyGroups.get(key);
  if (!group) return;
  showTab('connections');
  document.getElementById('companySearch').value = group.label;
  document.getElementById('clearSearchBtn').style.display = 'block';
  document.getElementById('companySuggestions').style.display = 'none';
  searchGroup(group);
  document.getElementById('tabConnections').focus();   // keep keyboard focus somewhere visible
}

// ---------------------------------------------------------------------------
// Landing view (shown until a search is made)
// ---------------------------------------------------------------------------

const MIN_SHARED = 2;      // the Companies tab lists companies with at least this many people
const LANDING_CHIPS = 8;

function setLandingVisible(visible) {
  const landing = document.getElementById('landing');
  if (landing) landing.classList.toggle('hidden', !visible);
}

// Real employers where at least MIN_SHARED different people work, biggest first.
function sharedCompanyGroups() {
  return Array.from(companyGroups.values())
    .filter(g => !NON_EMPLOYERS.has(g.key) && g.peopleKeys.size >= MIN_SHARED)
    .sort((a, b) => b.peopleKeys.size - a.peopleKeys.size || a.label.localeCompare(b.label));
}

function renderLanding() {
  const summary = document.getElementById('landingSummary');
  const chips = document.getElementById('landingChips');
  const chipsBox = document.getElementById('landingChipsBox');
  if (!summary || !chips) return;

  const pills = Object.keys(OWNER_LABELS).map(k =>
    `<div class="landing-stat tile-${k}"><span class="landing-stat-n">${dataStore[k].length}</span><span class="landing-stat-l">${OWNER_LABELS[k]} list</span></div>`
  ).join('');
  const companies = Array.from(companyGroups.keys()).filter(k => k !== NO_COMPANY_KEY).length;
  summary.innerHTML = `<div class="landing-stats">${pills}</div>` +
    `<p class="landing-total"><strong>${ownersByPerson.size}</strong> unique people at <strong>${companies}</strong> companies</p>`;

  const top = sharedCompanyGroups().slice(0, LANDING_CHIPS);
  chips.innerHTML = top.map(g =>
    `<button type="button" class="landing-chip" data-key="${escapeHtml(g.key)}">${escapeHtml(g.label)} <span class="landing-chip-count">${g.peopleKeys.size}</span></button>`
  ).join('');
  if (chipsBox) chipsBox.classList.toggle('hidden', top.length === 0);
}

// ---------------------------------------------------------------------------
// Companies tab: companies where two or more connections work
// ---------------------------------------------------------------------------

function getFilteredCompanyGroups() {
  const all = sharedCompanyGroups();
  const filter = (document.getElementById('jobsTableFilter')?.value || '').trim();
  if (!filter) return all;
  const keys = new Set(matchingGroups(filter).map(g => g.key));
  return all.filter(g => keys.has(g.key));
}

function ownerDots(owners) {
  return Object.keys(OWNER_LABELS)
    .filter(k => owners.has(k))
    .map(k => `<span class="owner-dot owner-${k}"></span>`).join('');
}

// Soft background for a person chip: the list's tint, or a blend when they are in several lists.
function chipBackground(owners) {
  const tints = Object.keys(OWNER_LABELS).filter(k => owners.has(k)).map(k => `var(--${k}-tint)`);
  if (tints.length === 1) return tints[0];
  return `linear-gradient(90deg, ${tints.join(', ')})`;
}

function ownerListLabel(owners) {
  return Object.keys(OWNER_LABELS).filter(k => owners.has(k)).map(k => OWNER_LABELS[k]).join(', ');
}

function renderCompaniesView() {
  const container = document.getElementById('jobsTableContainer');
  const meta = document.getElementById('jobsMeta');
  if (!container || !meta) return;

  const allShared = sharedCompanyGroups();
  const groups = getFilteredCompanyGroups();
  const people = new Set();
  groups.forEach(g => g.peopleKeys.forEach(pk => people.add(pk)));
  meta.textContent = `${groups.length === allShared.length ? groups.length : `${groups.length} of ${allShared.length}`} companies with ${MIN_SHARED}+ connections · ${people.size} people`;

  if (!groups.length) {
    container.innerHTML = `<div class="company-empty">${
      allShared.length
        ? 'No company here matches that filter. Companies with a single connection are not listed: search for them on the Connections tab.'
        : `No company has ${MIN_SHARED} or more connections yet.`
    }</div>`;
    return;
  }

  container.innerHTML = groups.map(group => {
    const names = groupVariantNames(group);
    const includes = names.length > 1 ? `<div class="text-muted small">Includes: ${names.map(escapeHtml).join(', ')}</div>` : '';
    const buttons = createJobsButtons(names);
    const members = Array.from(group.members.values())
      .sort((a, b) => a.name.localeCompare(b.name))
      .map(m => `<li class="member-chip" style="background: ${chipBackground(m.owners)}" title="In ${escapeHtml(ownerListLabel(m.owners))} list"><span class="owner-dots" aria-hidden="true">${ownerDots(m.owners)}</span>${escapeHtml(m.name)}<span class="sr-only"> (in ${escapeHtml(ownerListLabel(m.owners))} list)</span></li>`)
      .join('');
    return `
      <div class="company-row" data-key="${escapeHtml(group.key)}">
        <div class="company-row-main">
          <div class="company-row-head">
            <button type="button" class="company-open" aria-label="Show ${escapeHtml(group.label)} connections">${escapeHtml(group.label)}</button>
            <span class="company-count">${group.peopleKeys.size} connections</span>
          </div>
          ${includes}
          <ul class="member-chips">${members}</ul>
        </div>
        ${buttons ? `<div class="company-row-jobs">${buttons}</div>` : ''}
      </div>`;
  }).join('');
}

// ---------------------------------------------------------------------------
// Login (a page gate, not real security: the password is in this file)
// ---------------------------------------------------------------------------

function unlock() {
  isAuthenticated = true;
  document.getElementById('loginForm').classList.add('hidden');
  document.getElementById('appPanel').classList.remove('hidden');
  loadAllCSVs().catch(err => showLoadErrors([{ file: 'application', message: (err && err.message) || String(err) }]));
}

function setupLogin() {
  const form = document.getElementById('loginForm');
  const input = document.getElementById('loginPassword');
  const error = document.getElementById('loginError');
  if (!form || !input) return;
  form.addEventListener('submit', e => {
    e.preventDefault();
    if (input.value === CORRECT_PASSWORD) {
      error.classList.add('hidden');
      input.removeAttribute('aria-invalid');
      unlock();
    } else {
      error.textContent = 'Incorrect password. Please try again.';
      error.classList.remove('hidden');
      input.setAttribute('aria-invalid', 'true');
      input.value = '';
      input.focus();
    }
  });
  input.focus();
}

document.addEventListener('DOMContentLoaded', setupLogin);
