// script.js

// Password configuration
const CORRECT_PASSWORD = 'connections'; // Change this to your desired password

const csvFiles = {
  anvay: 'updated_data/anvay-connections_updated.csv',
  anil: 'updated_data/anil-connections_updated.csv',
  bilwa: 'updated_data/bilwa-connections_updated.csv'
};

const linkedInJobsFile = 'linkedin_jobs_final.csv?v=20260521-4';

const dataStore = {
  anvay: [],
  anil: [],
  bilwa: []
};

let linkedInUrlByCompany = {};
let linkedInUrlByNormalized = {};
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
  'Albertsons Companies': 'albertsons',
  'Aya Healthcare': 'aya-healthcare',
  'Benjamin Moore & Co.': 'benjamin-moore-co',
  'Berkeley Lab': 'lawrence-berkeley-national-laboratory',
  'Axtria - Ingenious Insights': 'axtria',
  'Athos Therapeutics Inc': 'athos-therapeutics',
  'Actemium Avanceon': 'actemium-avanceon',
  'Amberoon Inc.': 'amberoon-inc',
  'Accelon Inc.': 'accelon-inc',
  'AdventHealth Central Florida': 'adventhealth',
  'BD': 'bd',
  'AC Wellness Medical Group @ Apple': 'ac-wellness',
  'Atreya Innovations': 'atreya-innovations',
  'Ayurvedamrut': 'ayurvedamrut',
};

async function loadAllCSVs() {
  for (let key in csvFiles) {
    await loadCSV(csvFiles[key], key);
  }
  await loadLinkedInJobsCSV();
  setupUI();
  setupTabs();
  renderCompaniesView();
}

function normalizeCompanyKey(name) {
  return name.split('·')[0].trim().replace(/[\uF8FF\uE000-\uF8FF\s]+$/g, '').trim().toLowerCase();
}

function loadLinkedInJobsCSV() {
  return new Promise((resolve) => {
    Papa.parse(linkedInJobsFile, {
      download: true,
      header: true,
      skipEmptyLines: true,
      complete: results => {
        linkedInUrlByCompany = {};
        linkedInUrlByNormalized = {};
        (results.data || []).forEach(row => {
          const company = (row.Company || '').trim();
          const url = (row.Job_page || row.LinkedIn_URL || '').trim();
          if (company && url) {
            linkedInUrlByCompany[company] = url;
            linkedInUrlByNormalized[normalizeCompanyKey(company)] = url;
          }
        });
        resolve();
      },
      error: () => {
        linkedInUrlByCompany = {};
        linkedInUrlByNormalized = {};
        resolve();
      }
    });
  });
}

function getStoredJobsUrl(company) {
  if (linkedInUrlByCompany[company]) {
    return linkedInUrlByCompany[company];
  }
  return linkedInUrlByNormalized[normalizeCompanyKey(company)] || '';
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

function getCompanyConnectionCount(companyName) {
  const key = companyName.split('·')[0].trim();
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
  const normalized = company.split('·')[0].trim().replace(/[\uF8FF\uE000-\uF8FF\s]+$/g, '').trim();
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
  const stored = getStoredJobsUrl(company);
  if (stored) {
    return stored;
  }

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
    renderCompaniesView();
  });

  document.getElementById('jobsTableFilter')?.addEventListener('input', renderCompaniesView);
}

function getFilteredCompanyRows() {
  const filter = (document.getElementById('jobsTableFilter')?.value || '').trim().toLowerCase();
  let companies = getAllCompanies();

  if (filter) {
    companies = companies.filter(company => company.toLowerCase().includes(filter));
  }

  companies.sort((a, b) => {
    const countDiff = getCompanyConnectionCount(b) - getCompanyConnectionCount(a);
    if (countDiff !== 0) return countDiff;
    return a.localeCompare(b);
  });

  return companies;
}

function renderCompaniesView() {
  const container = document.getElementById('jobsTableContainer');
  const meta = document.getElementById('jobsMeta');
  if (!container || !meta) return;

  const allCompanies = getAllCompanies();
  const companies = getFilteredCompanyRows();
  const verifiedCount = allCompanies.filter(company => getStoredJobsUrl(company)).length;

  meta.textContent = `Showing ${companies.length} of ${allCompanies.length} companies · Links verified for ${verifiedCount} companies`;

  if (!companies.length) {
    container.innerHTML = '<div class="result-card"><p class="text-muted mb-0">No companies match your filter.</p></div>';
    return;
  }

  let html = `
    <div class="result-card companies-table-card">
      <div class="table-container">
        <div class="table-responsive">
          <table class="table table-hover companies-table">
            <thead>
              <tr>
                <th>Company</th>
                <th>Jobs</th>
              </tr>
            </thead>
            <tbody>`;

  companies.forEach(company => {
    html += `
              <tr>
                <td><strong>${company}</strong></td>
                <td>${createJobsLinkHtml(company)}</td>
              </tr>`;
  });

  html += `
            </tbody>
          </table>
        </div>
      </div>
    </div>`;

  container.innerHTML = html;
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
