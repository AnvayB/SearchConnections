// script.js

const csvFiles = {
    anvay: 'data/anvay-connections.csv',
    anil: 'data/anil-connections.csv',
    bilwa: 'data/bilwa-connections.csv'
  };
  
  const dataStore = {
    anvay: [],
    anil: [],
    bilwa: []
  };
  
  async function loadAllCSVs() {
    for (let key in csvFiles) {
      await loadCSV(csvFiles[key], key);
    }
    setupUI();
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
  
  function getAllCompanies() {
    const set = new Set();
    Object.values(dataStore).forEach(data => {
      data.forEach(d => {
        if (d.Company) set.add(d.Company);
      });
    });
    return Array.from(set).sort();
  }
  
  function searchCompany(companyName) {
    const lc = companyName.trim().toLowerCase();
  
    const anvay_matches = dataStore.anvay.filter(d => d.Company?.toLowerCase() === lc);
    const anil_matches = dataStore.anil.filter(d => {
      const closeness = String(d.Closeness).trim();
      return d.Company?.toLowerCase() === lc && ["1", "2", 1, 2].includes(closeness);
    });
    const bilwa_matches = dataStore.bilwa.filter(d => d.Company?.toLowerCase() === lc);
  
    const result = {
      company: companyName,
      anvay_matches,
      anil_matches,
      bilwa_matches,
      anvay_count: anvay_matches.length,
      anil_count: anil_matches.length,
      bilwa_count: bilwa_matches.length
    };
  
    displayResults(result);
  }
  
  function displayResults(data) {
    const statsContainer = document.getElementById('statsContainer');
    const resultsContainer = document.getElementById('resultsContainer');
  
    statsContainer.style.display = 'flex';
    statsContainer.style.flexDirection = 'row';
    document.getElementById('anvayCount').textContent = data.anvay_count;
    document.getElementById('anilCount').textContent = data.anil_count;
    document.getElementById('bilwaCount').textContent = data.bilwa_count;
  
    let html = `<h3 class="mb-4">Search Results for: <span class="text-primary">${data.company}</span></h3>`;
    html += createResultSection("Anvay's Connections", data.anvay_matches, false);
    html += createResultSection("Anil's Close Connections", data.anil_matches, true);
    html += createResultSection("Bilwa's Connections", data.bilwa_matches, false);
  
    resultsContainer.innerHTML = html;
  }
  
  function createResultSection(title, data, includeCloseness) {
    let html = `
      <div class="result-card">
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
        html += `<tr>
          <td><strong>${person['First Name']} ${person['Last Name']}</strong></td>
          <td>${person['Company']}</td>
          <td>${person['Position']}</td>
          ${includeCloseness ? `<td><span class="badge ${person['Closeness'] === "1.0" ? 'badge-closeness-1' : 'badge-closeness'}">${person['Closeness']}</span></td>` : ''}
          <td><a href="${person['URL']}" target="_blank" class="btn btn-sm btn-outline-primary"><i class="fab fa-linkedin"></i> View</a></td>
        </tr>`;
      });
  
      html += '</tbody></table></div>';
    }
  
    html += '</div></div>';
    return html;
  }
  
  function setupUI() {
    const searchInput = document.getElementById('companySearch');
    const searchBtn = document.getElementById('searchBtn');
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
      // Add click event listeners to each suggestion item
      Array.from(suggestionsBox.getElementsByClassName('suggestion-item')).forEach((el, idx) => {
        el.addEventListener('click', () => selectSuggestion(filtered[idx]));
      });
      suggestionsBox.style.display = filtered.length ? 'block' : 'none';
    });
  
    searchBtn.addEventListener('click', () => {
      searchCompany(searchInput.value);
    });
  
    searchInput.addEventListener('keypress', e => {
      if (e.key === 'Enter') {
        searchCompany(searchInput.value);
        suggestionsBox.style.display = 'none'; // Hide dropdown after Enter
      }
    });
  
    // Show/hide clear button on page load
    clearBtn.style.display = searchInput.value.length ? 'block' : 'none';
  
    document.addEventListener('click', e => {
      if (!e.target.closest('#companySearch') && !e.target.closest('#companySuggestions')) {
        suggestionsBox.style.display = 'none';
      }
    });
  
    clearBtn.addEventListener('click', () => {
      if (searchInput.value === '') {
        // Clear output if nothing in search bar
        document.getElementById('resultsContainer').innerHTML = '';
        document.getElementById('statsContainer').style.display = 'none';
      }
      searchInput.value = '';
      clearBtn.style.display = 'none';
      suggestionsBox.style.display = 'none';
      searchInput.focus();
    });
    // Prevent clear button from losing focus or being blocked
    clearBtn.addEventListener('mousedown', e => { e.stopPropagation(); });
  }
  
  function selectSuggestion(company) {
    document.getElementById('companySearch').value = company;
    document.getElementById('companySuggestions').style.display = 'none';
    searchCompany(company);
  }
  
  document.addEventListener('DOMContentLoaded', loadAllCSVs);
  