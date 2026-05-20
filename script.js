// script.js

// Password configuration
const CORRECT_PASSWORD = 'connections'; // Change this to your desired password

const csvFiles = {
  anvay: 'updated_data/anvay-connections_updated.csv',
  anil: 'updated_data/anil-connections_updated.csv',
  bilwa: 'updated_data/bilwa-connections_updated.csv'
};

const jobCountsFile = 'updated_data/top20_job_counts.csv?v=20260520-4';

const dataStore = {
  anvay: [],
  anil: [],
  bilwa: []
};

let jobCountsData = [];
let jobsSortKey = 'Connection_Count';
let jobsSortAsc = false;
let isAuthenticated = false;

// Manual overrides when LinkedIn slugs differ from the generated slug.
const COMPANY_SLUG_OVERRIDES = {
  'Intel Corporation': 'intel',
  'Amazon Web Services (AWS)': 'amazon-web-services',
  'Meta': 'meta',
  'Google': 'google',
  'Microsoft': 'microsoft',
  'Apple': 'apple',
  'NVIDIA': 'nvidia',
  'Netflix': 'netflix',
  'Oracle': 'oracle',
  'IBM': 'ibm',
  'Salesforce': 'salesforce',
  'Adobe': 'adobe',
  'Uber': 'uber',
  'Airbnb': 'airbnb',
  'LinkedIn': 'linkedin',
  'Tesla': 'tesla',
  'SpaceX': 'spacex',
  'Palantir Technologies': 'palantir-technologies',
  'Snowflake': 'snowflake-computing',
  'Databricks': 'databricks',
  'Stripe': 'stripe',
  'Coinbase': 'coinbase',
  'Robinhood': 'robinhood',
  'DoorDash': 'doordash',
  'Instacart': 'instacart',
  'Roche': 'roche',
  'Abbott': 'abbott',
  'AMD': 'amd',
  'Agilent Technologies': 'agilent-technologies',
  'BAE Systems, Inc.': 'bae-systems',
  'Honeywell': 'honeywell',
  'Applied Materials': 'applied-materials',
  'Entegris': 'entegris',
  'KLA': 'kla',
  'PayPal': 'paypal',
  'Sila Nanotechnologies Inc.': 'sila-nanotechnologies',
  'MacDermid Alpha Electronics Solutions': 'macdermid-alpha-electronics-solutions',
  'Mariana Minerals': 'mariana-minerals',
  'Arteris': 'arteris',
};

async function loadAllCSVs() {
  for (let key in csvFiles) {
    await loadCSV(csvFiles[key], key);
  }
  await loadJobCountsCSV();
  setupUI();
  setupTabs();
  renderCompanyJobsView();
}

function loadCSV(path, label) {
  return new Promise((resolve, reject) => {
    Papa.parse(path, {
      download: true,
      header: true,
      complete: results => {
        dataStore[label] = results.data;
        resolve();
      },
      error: reject
    });
  });
}

function loadJobCountsCSV() {
  return new Promise((resolve) => {
    Papa.parse(jobCountsFile, {
      download: true,
      header: true,
      skipEmptyLines: true,
      complete: results => {
        jobCountsData = (results.data || []).filter(row => (row.Company || '').trim());
        resolve();
      },
      error: () => {
        jobCountsData = [];
        resolve();
      }
    });
  });
}

function getAllCompanies() {
  const set = new Set();
  Object.values(dataStore).forEach(data => {
    data.forEach(d => {
      if (d.Company) set.add(d.Company);
    });
  });
  return Array.from(set).sort();
}

function companyToLinkedInSlug(company) {
  const normalized = company.split('·')[0].trim();
  if (COMPANY_SLUG_OVERRIDES[normalized]) {
    return COMPANY_SLUG_OVERRIDES[normalized];
  }

  return normalized
    .toLowerCase()
    .replace(/['']/g, '')
    .replace(/\([^)]*\)/g, ' ')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

function linkedInJobsUrl(company) {
  const slug = companyToLinkedInSlug(company);
  return `https://www.linkedin.com/company/${encodeURIComponent(slug)}/jobs/`;
}

function createJobsLinkHtml(company) {
  const url = linkedInJobsUrl(company);
  return `
    <a href="${url}" target="_blank" rel="noopener noreferrer" class="jobs-link-btn">
      <i class="fab fa-linkedin"></i> View Jobs on LinkedIn
    </a>`;
}

function createSearchHeader(company) {
  return `
    <div class="search-header-row mb-4">
      <h3 class="search-header-title">Search Results for: <span class="text-primary">${company}</span></h3>
      ${createJobsLinkHtml(company)}
    </div>`;
}

function searchCompany(companyName, exactCaseSensitive = false) {
  const companyNames = companyName.split(',').map(s => s.trim()).filter(Boolean);
  if (companyNames.length > 1) {
    const results = companyNames.map(name => {
      if (exactCaseSensitive) {
        const anvay_matches = dataStore.anvay.filter(d => d.Company === name);
        const anil_matches = dataStore.anil.filter(d => d.Company === name);
        const bilwa_matches = dataStore.bilwa.filter(d => d.Company === name);
        return {
          company: name,
          anvay_matches,
          anil_matches,
          bilwa_matches,
          anvay_count: anvay_matches.length,
          anil_count: anil_matches.length,
          bilwa_count: bilwa_matches.length
        };
      }

      const lcWords = name.trim().toLowerCase().split(/\s+/).filter(Boolean);
      function matchesAnyWord(company) {
        if (!company) return false;
        const companyLc = company.toLowerCase();
        return lcWords.some(word => companyLc.includes(word));
      }
      const anvay_matches = dataStore.anvay.filter(d => matchesAnyWord(d.Company));
      const anil_matches = dataStore.anil.filter(d => matchesAnyWord(d.Company));
      const bilwa_matches = dataStore.bilwa.filter(d => matchesAnyWord(d.Company));
      return {
        company: name,
        anvay_matches,
        anil_matches,
        bilwa_matches,
        anvay_count: anvay_matches.length,
        anil_count: anil_matches.length,
        bilwa_count: bilwa_matches.length
      };
    });
    displayResults(results, true);
    return;
  }

  if (exactCaseSensitive) {
    const anvay_matches = dataStore.anvay.filter(d => d.Company === companyName);
    const anil_matches = dataStore.anil.filter(d => d.Company === companyName);
    const bilwa_matches = dataStore.bilwa.filter(d => d.Company === companyName);
    displayResults({
      company: companyName,
      anvay_matches,
      anil_matches,
      bilwa_matches,
      anvay_count: anvay_matches.length,
      anil_count: anil_matches.length,
      bilwa_count: bilwa_matches.length
    });
    return;
  }

  const lcWords = companyName.trim().toLowerCase().split(/\s+/).filter(Boolean);
  function matchesAnyWord(company) {
    if (!company) return false;
    const companyLc = company.toLowerCase();
    return lcWords.some(word => companyLc.includes(word));
  }
  const anvay_matches = dataStore.anvay.filter(d => matchesAnyWord(d.Company));
  const anil_matches = dataStore.anil.filter(d => matchesAnyWord(d.Company));
  const bilwa_matches = dataStore.bilwa.filter(d => matchesAnyWord(d.Company));
  displayResults({
    company: companyName,
    anvay_matches,
    anil_matches,
    bilwa_matches,
    anvay_count: anvay_matches.length,
    anil_count: anil_matches.length,
    bilwa_count: bilwa_matches.length
  });
}

function displayResults(data, isMulti = false) {
  const statsContainer = document.getElementById('statsContainer');
  const resultsContainer = document.getElementById('resultsContainer');

  if (isMulti) {
    statsContainer.style.display = 'none';
    let html = '';
    data.forEach((result, idx) => {
      const highlightClass = `company-highlight-${idx % 5}`;
      html += `
        <div class="multi-company-block mt-8">
          ${createSearchHeader(result.company)}
        `;
      if (result.anvay_matches.length > 0) {
        html += createResultSection("Anvay's Connections", result.anvay_matches, false, highlightClass);
      }
      if (result.anil_matches.length > 0) {
        html += createResultSection("Anil's Connections", result.anil_matches, false, highlightClass);
      }
      if (result.bilwa_matches.length > 0) {
        html += createResultSection("Bilwa's Connections", result.bilwa_matches, false, highlightClass);
      }
      html += '</div>';
    });
    resultsContainer.innerHTML = html;
    return;
  }

  statsContainer.style.display = 'flex';
  document.getElementById('anvayCount').textContent = data.anvay_count;
  document.getElementById('anilCount').textContent = data.anil_count;
  document.getElementById('bilwaCount').textContent = data.bilwa_count;

  let html = createSearchHeader(data.company);
  if (data.anvay_matches.length > 0) {
    html += createResultSection("Anvay's Connections", data.anvay_matches, false);
  }
  if (data.anil_matches.length > 0) {
    html += createResultSection("Anil's Connections", data.anil_matches, false);
  }
  if (data.bilwa_matches.length > 0) {
    html += createResultSection("Bilwa's Connections", data.bilwa_matches, false);
  }
  resultsContainer.innerHTML = html;
}

function createResultSection(title, data, includeCloseness, highlightClass = '') {
  let sectionClass = '';
  if (title.includes("Anvay")) sectionClass = 'result-anvay';
  else if (title.includes("Anil")) sectionClass = 'result-anil';
  else if (title.includes("Bilwa")) sectionClass = 'result-bilwa';
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
      html += `<tr>
        <td><strong>${person['First Name']} ${person['Last Name']}</strong></td>
        <td>${person['Company']}</td>
        <td>${person['Position']}</td>
        ${includeCloseness ? `<td><span class="${closenessClass}">${person['Closeness']}</span></td>` : ''}
        <td><a href="${person['URL']}" target="_blank" class="btn btn-sm btn-outline-primary"><i class="fab fa-linkedin"></i> View</a></td>
      </tr>`;
      if (person['Still_Employed'] === 'No') {
        html += `<tr class="disclaimer-row"><td colspan="${colSpan}" class="disclaimer-cell">⚠️ This person no longer works here but they may still have connections.</td></tr>`;
      }
    });

    html += '</tbody></table></div>';
  }

  html += '</div></div>';
  return html;
}

function setupUI() {
  const searchInput = document.getElementById('companySearch');
  const suggestionsBox = document.getElementById('companySuggestions');
  const clearBtn = document.getElementById('clearSearchBtn');

  const companies = getAllCompanies();

  searchInput.addEventListener('input', () => {
    const val = searchInput.value.toLowerCase();
    clearBtn.style.display = val.length ? 'block' : 'none';
    if (val.length < 2) {
      suggestionsBox.style.display = 'none';
      return;
    }
    const filtered = companies.filter(c => c.toLowerCase().includes(val)).slice(0, 10);
    suggestionsBox.innerHTML = filtered.map(c => `<div class="suggestion-item px-4 py-2 cursor-pointer hover:bg-indigo-100 active:bg-indigo-200 transition-colors">${c}</div>`).join('');
    Array.from(suggestionsBox.getElementsByClassName('suggestion-item')).forEach((el, idx) => {
      el.addEventListener('click', () => selectSuggestion(filtered[idx]));
    });
    suggestionsBox.style.display = filtered.length ? 'block' : 'none';
  });

  searchInput.addEventListener('keypress', e => {
    if (e.key === 'Enter') {
      searchCompany(searchInput.value);
      suggestionsBox.style.display = 'none';
    }
  });

  clearBtn.style.display = searchInput.value.length ? 'block' : 'none';

  document.addEventListener('click', e => {
    if (!e.target.closest('#companySearch') && !e.target.closest('#companySuggestions')) {
      suggestionsBox.style.display = 'none';
    }
  });

  clearBtn.addEventListener('click', () => {
    if (searchInput.value === '') {
      document.getElementById('resultsContainer').innerHTML = '';
      document.getElementById('statsContainer').style.display = 'none';
    }
    searchInput.value = '';
    clearBtn.style.display = 'none';
    suggestionsBox.style.display = 'none';
    searchInput.focus();
  });
  clearBtn.addEventListener('mousedown', e => { e.stopPropagation(); });
}

function selectSuggestion(company) {
  document.getElementById('companySearch').value = company;
  document.getElementById('companySuggestions').style.display = 'none';
  searchCompany(company, true);
}

function setupTabs() {
  const tabConnections = document.getElementById('tabConnections');
  const tabJobs = document.getElementById('tabJobs');
  const connectionsPanel = document.getElementById('connectionsPanel');
  const jobsPanel = document.getElementById('jobsPanel');

  tabConnections.addEventListener('click', () => {
    tabConnections.classList.add('tab-btn-active');
    tabConnections.setAttribute('aria-selected', 'true');
    tabJobs.classList.remove('tab-btn-active');
    tabJobs.setAttribute('aria-selected', 'false');
    connectionsPanel.classList.remove('hidden');
    jobsPanel.classList.add('hidden');
  });

  tabJobs.addEventListener('click', () => {
    tabJobs.classList.add('tab-btn-active');
    tabJobs.setAttribute('aria-selected', 'true');
    tabConnections.classList.remove('tab-btn-active');
    tabConnections.setAttribute('aria-selected', 'false');
    jobsPanel.classList.remove('hidden');
    connectionsPanel.classList.add('hidden');
    renderCompanyJobsView();
  });

  document.getElementById('jobsTableFilter')?.addEventListener('input', renderCompanyJobsView);
  document.getElementById('jobsSortSelect')?.addEventListener('change', e => {
    jobsSortKey = e.target.value;
    jobsSortAsc = jobsSortKey === 'Company';
    renderCompanyJobsView();
  });
}

const ROLE_BUCKET_PATTERNS = [
  {
    key: 'Data_Scientist_ML',
    label: 'DS / ML',
    className: 'role-badge-dsml',
    patterns: [/data scientist/i, /machine learning engineer/i, /\bml engineer\b/i, /\bai engineer\b/i, /research scientist/i, /applied scientist/i, /deep learning/i]
  },
  {
    key: 'Data_Engineer',
    label: 'Data Engineer',
    className: 'role-badge-de',
    patterns: [/data engineer/i, /analytics engineer/i, /\betl engineer\b/i, /data platform/i, /pipeline engineer/i]
  },
  {
    key: 'Data_Analyst',
    label: 'Data Analyst',
    className: 'role-badge-da',
    patterns: [/data analyst/i, /business intelligence/i, /\bbi analyst\b/i, /analytics analyst/i, /reporting analyst/i]
  },
  {
    key: 'SWE',
    label: 'SWE',
    className: 'role-badge-swe',
    patterns: [/software engineer/i, /software developer/i, /\bsde\b/i, /\bswe\b/i, /backend engineer/i, /frontend engineer/i, /full.?stack/i, /platform engineer/i, /member of technical staff/i, /\bmtse\b/i, /firmware engineer/i]
  }
];

const SENIOR_TITLE_PATTERNS = [
  /\bsenior\b/i, /\bsr\.?\b/i, /\bstaff\b/i, /\bprincipal\b/i, /\bdirector\b/i,
  /\bvice president\b/i, /\bvp\b/i, /\bhead of\b/i, /\bdistinguished\b/i,
  /\bfellow\b/i, /\barchitect\b/i, /\bmanager\b/i, /\btech lead\b/i,
  /\bteam lead\b/i, /\bleading\b/i
];

function isSeniorTitle(title) {
  return SENIOR_TITLE_PATTERNS.some(p => p.test(title));
}

function classifyJobTitle(title) {
  for (const bucket of ROLE_BUCKET_PATTERNS) {
    if (bucket.patterns.some(p => p.test(title))) {
      return bucket;
    }
  }
  return null;
}

function parseJobTitles(raw) {
  if (!raw) return [];
  return raw
    .split('|')
    .map(t => t.trim())
    .filter(t => t && t.toLowerCase() !== 'posted' && !/has \d+ posted jobs/i.test(t))
    .filter(t => !isSeniorTitle(t))
    .filter(t => !/^[A-Z][a-z]+(\s[A-Z][a-z]+){1,2}$/.test(t) || classifyJobTitle(t))
    .filter((t, i, arr) => arr.indexOf(t) === i);
}

function getDedupedConnectionCount(companyName) {
  const key = companyName.trim();
  const seen = new Set();

  Object.values(dataStore).forEach(rows => {
    rows.forEach(row => {
      const company = (row.Company || '').split('·')[0].trim();
      if (company !== key) return;
      const url = (row.URL || '').trim().toLowerCase().replace(/\/$/, '');
      const personKey = url.startsWith('http')
        ? url
        : `name:${(row['First Name'] || '').trim().toLowerCase()}|${(row['Last Name'] || '').trim().toLowerCase()}`;
      seen.add(personKey);
    });
  });

  return seen.size;
}

function roleSummaryBadges(row) {
  const titles = parseJobTitles(row.Recommended_Titles);
  const counts = { SWE: 0, Data_Analyst: 0, Data_Engineer: 0, Data_Scientist_ML: 0 };

  titles.forEach(title => {
    const bucket = classifyJobTitle(title);
    if (bucket) counts[bucket.key] += 1;
  });

  const fields = [
    ['SWE', 'role-badge-swe'],
    ['Data_Analyst', 'role-badge-da'],
    ['Data_Engineer', 'role-badge-de'],
    ['Data_Scientist_ML', 'role-badge-dsml']
  ];

  return fields
    .map(([field, cls]) => {
      const n = counts[field];
      if (n <= 0) return '';
      const label = field === 'Data_Scientist_ML' ? 'DS / ML' : field.replace('_', ' ');
      return `<span class="role-badge ${cls}">${label}: ${n}</span>`;
    })
    .filter(Boolean)
    .join('');
}

function parseCount(value) {
  if (value === undefined || value === null || value === '') return -1;
  const n = Number(value);
  return Number.isFinite(n) ? n : -1;
}

function formatCount(value) {
  const n = parseCount(value);
  return n < 0 ? '—' : n.toLocaleString();
}

function getFilteredJobRows() {
  const filter = (document.getElementById('jobsTableFilter')?.value || '').trim().toLowerCase();
  let rows = jobCountsData.map(row => ({
    ...row,
    _connectionCount: getDedupedConnectionCount(row.Company || '') || parseCount(row.Connection_Count)
  }));

  if (filter) {
    rows = rows.filter(row => (row.Company || '').toLowerCase().includes(filter));
  }

  rows.sort((a, b) => {
    if (jobsSortKey === 'Company') {
      const av = (a.Company || '').toLowerCase();
      const bv = (b.Company || '').toLowerCase();
      if (av === bv) return 0;
      return jobsSortAsc ? (av < bv ? -1 : 1) : (av > bv ? -1 : 1);
    }

    if (jobsSortKey === 'Connection_Count') {
      const av = a._connectionCount;
      const bv = b._connectionCount;
      if (av === bv) return (a.Company || '').localeCompare(b.Company || '');
      return jobsSortAsc ? av - bv : bv - av;
    }

    const av = parseCount(a[jobsSortKey]);
    const bv = parseCount(b[jobsSortKey]);
    if (av === bv) {
      return (a.Company || '').localeCompare(b.Company || '');
    }
    return jobsSortAsc ? av - bv : bv - av;
  });

  return rows;
}

function renderCompanyJobsView() {
  const container = document.getElementById('jobsTableContainer');
  const meta = document.getElementById('jobsMeta');
  if (!container || !meta) return;

  const rows = getFilteredJobRows();

  if (!jobCountsData.length) {
    meta.textContent = 'No job scan data yet.';
    container.innerHTML = `
      <div class="result-card">
        <p class="text-muted mb-2">Run the scanner to populate this view:</p>
        <p class="mb-0"><code>.venv/bin/python scan_company_jobs.py --limit 3</code></p>
        <p class="text-muted mt-2 mb-0">Full top-17 run: <code>.venv/bin/python scan_company_jobs.py</code></p>
      </div>`;
    return;
  }

  const latestScan = jobCountsData.map(r => r.Last_Scanned).filter(Boolean).sort().pop();
  meta.textContent = `Showing ${rows.length} of ${jobCountsData.length} companies${latestScan ? ` · Last scan: ${latestScan}` : ''}`;

  if (!rows.length) {
    container.innerHTML = '<div class="result-card"><p class="text-muted mb-0">No companies match your filter.</p></div>';
    return;
  }

  let html = '';
  rows.forEach(row => {
    const company = row.Company || '';
    const connections = getDedupedConnectionCount(company) || parseCount(row.Connection_Count) || 0;
    const titles = parseJobTitles(row.Recommended_Titles);
    const badges = roleSummaryBadges(row);

    let jobsHtml = '';
    if (!titles.length) {
      jobsHtml = `<p class="company-jobs-empty">${row.Scan_Notes || 'No recommended jobs found yet.'}</p>`;
    } else {
      jobsHtml = `<ul class="company-jobs-items">${titles.map(title => {
        const bucket = classifyJobTitle(title);
        const badge = bucket
          ? `<span class="role-badge ${bucket.className}">${bucket.label}</span>`
          : `<span class="role-badge role-badge-other">Other</span>`;
        return `<li class="company-job-item">${badge}<span class="company-job-title">${title}</span></li>`;
      }).join('')}</ul>`;
    }

    html += `
      <div class="company-jobs-card result-card">
        <div class="company-jobs-header">
          <div>
            <h3 class="company-jobs-name">${company}</h3>
            <div class="company-jobs-meta">
              <span class="connection-pill"><i class="fas fa-user-friends"></i> ${connections} connection${connections === 1 ? '' : 's'}</span>
              ${badges ? `<span class="company-jobs-badges">${badges}</span>` : ''}
            </div>
          </div>
          ${createJobsLinkHtml(company)}
        </div>
        <div class="company-jobs-body">
          <div class="company-jobs-section-title">Recommended jobs for you</div>
          ${jobsHtml}
        </div>
      </div>`;
  });

  container.innerHTML = html;
}

function renderJobsTable() {
  renderCompanyJobsView();
}

function checkPassword() {
  const password = prompt('Please enter the password to access this application:');

  if (password === null) {
    alert('Password is required to access this application.');
    checkPassword();
    return;
  }

  if (password === CORRECT_PASSWORD) {
    isAuthenticated = true;
    loadAllCSVs();
  } else {
    alert('Incorrect password. Please try again.');
    checkPassword();
  }
}

document.addEventListener('DOMContentLoaded', checkPassword);
