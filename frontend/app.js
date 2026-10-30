/**
 * JobBoards Explorer Client Logic
 * Handles real-time search, filters, view toggle, and SQLite API communication.
 */

// State
const state = {
  query: '',
  ats: 'all',
  company: '',
  remoteOnly: false,
  sortBy: 'recent',
  page: 1,
  limit: 24,
  viewMode: 'grid', // 'grid' | 'table'
  activeModalJob: null,
};

// DOM Elements
const searchInput = document.getElementById('searchInput');
const clearSearchBtn = document.getElementById('clearSearchBtn');
const atsPills = document.querySelectorAll('#atsPillGroup .filter-pill');
const companySelect = document.getElementById('companySelect');
const sortSelect = document.getElementById('sortSelect');
const remoteOnlyToggle = document.getElementById('remoteOnlyToggle');
const resetFiltersBtn = document.getElementById('resetFiltersBtn');
const limitSelect = document.getElementById('limitSelect');
const viewGridBtn = document.getElementById('viewGridBtn');
const viewTableBtn = document.getElementById('viewTableBtn');

const jobsGrid = document.getElementById('jobsGrid');
const jobsTableWrap = document.getElementById('jobsTableWrap');
const jobsTableBody = document.getElementById('jobsTableBody');
const emptyState = document.getElementById('emptyState');
const emptyResetBtn = document.getElementById('emptyResetBtn');
const resultsCount = document.getElementById('resultsCount');

const paginationBar = document.getElementById('paginationBar');
const prevPageBtn = document.getElementById('prevPageBtn');
const nextPageBtn = document.getElementById('nextPageBtn');
const pageNumbers = document.getElementById('pageNumbers');

const jobModalBackdrop = document.getElementById('jobModalBackdrop');
const modalCloseBtn = document.getElementById('modalCloseBtn');
const modalCopyBtn = document.getElementById('modalCopyBtn');
const modalApplyBtn = document.getElementById('modalApplyBtn');
const toast = document.getElementById('toast');

// Stats Elements
const statTotalJobs = document.getElementById('statTotalJobs');
const statCompanies = document.getElementById('statCompanies');
const statRemote = document.getElementById('statRemote');
const statRemotePercent = document.getElementById('statRemotePercent');
const statAshbyCount = document.getElementById('statAshbyCount');
const statGreenhouseCount = document.getElementById('statGreenhouseCount');
const statLeverCount = document.getElementById('statLeverCount');
const statusText = document.getElementById('statusText');
const dbStatusIndicator = document.getElementById('dbStatusIndicator');
const refreshStatsBtn = document.getElementById('refreshStatsBtn');

// Debounce Utility
function debounce(func, wait) {
  let timeout;
  return function executedFunction(...args) {
    const later = () => {
      clearTimeout(timeout);
      func(...args);
    };
    clearTimeout(timeout);
    timeout = setTimeout(later, wait);
  };
}

// Toast notification
function showToast(message) {
  toast.textContent = message;
  toast.classList.add('show');
  setTimeout(() => {
    toast.classList.remove('show');
  }, 2500);
}

// Format relative date
function formatPublished(isoString) {
  if (!isoString) return 'Undated';
  try {
    const date = new Date(isoString);
    if (isNaN(date.getTime())) return 'Undated';
    
    const now = new Date();
    const diffMs = now - date;
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
    const diffDays = Math.floor(diffHours / 24);

    if (diffHours < 1) return 'Just now';
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays === 1) return 'Yesterday';
    if (diffDays < 30) return `${diffDays}d ago`;
    const months = Math.floor(diffDays / 30);
    return `${months}mo ago`;
  } catch (e) {
    return 'Recently';
  }
}

// Fetch Global Stats
async function loadStats() {
  try {
    const res = await fetch('/api/stats');
    if (!res.ok) throw new Error('Stats API returned error');
    const data = await res.json();

    statTotalJobs.textContent = (data.total_jobs || 0).toLocaleString();
    statCompanies.textContent = (data.total_companies || 0).toLocaleString();
    statRemote.textContent = (data.remote_jobs || 0).toLocaleString();

    const remotePercent = data.total_jobs ? Math.round((data.remote_jobs / data.total_jobs) * 100) : 0;
    statRemotePercent.textContent = `${remotePercent}% of total positions`;

    statAshbyCount.textContent = (data.ats_counts?.ashby || 0).toLocaleString();
    statGreenhouseCount.textContent = (data.ats_counts?.greenhouse || 0).toLocaleString();
    statLeverCount.textContent = (data.ats_counts?.lever || 0).toLocaleString();

    statusText.textContent = `SQLite Connected (${(data.total_jobs || 0).toLocaleString()} jobs)`;
    dbStatusIndicator.style.background = 'rgba(16, 185, 129, 0.1)';
    dbStatusIndicator.style.borderColor = 'rgba(16, 185, 129, 0.25)';
  } catch (err) {
    console.error('Failed to load stats:', err);
    statusText.textContent = 'Offline / No DB';
    dbStatusIndicator.style.background = 'rgba(239, 68, 68, 0.1)';
    dbStatusIndicator.style.borderColor = 'rgba(239, 68, 68, 0.25)';
  }
}

// Fetch Company List for Dropdown
async function loadCompanies() {
  try {
    const res = await fetch('/api/companies');
    if (!res.ok) return;
    const companies = await res.json();

    companySelect.innerHTML = `<option value="">All Companies (${companies.length})</option>`;
    companies.forEach((item) => {
      const opt = document.createElement('option');
      opt.value = item.company;
      opt.textContent = `${item.company.charAt(0).toUpperCase() + item.company.slice(1)} (${item.count})`;
      companySelect.appendChild(opt);
    });
  } catch (err) {
    console.error('Failed to load companies:', err);
  }
}

// Fetch and Render Jobs
async function loadJobs() {
  resultsCount.textContent = 'Searching database...';

  const params = new URLSearchParams({
    page: state.page,
    limit: state.limit,
    sort: state.sortBy,
  });

  if (state.query) params.set('q', state.query);
  if (state.ats && state.ats !== 'all') params.set('ats', state.ats);
  if (state.company) params.set('company', state.company);
  if (state.remoteOnly) params.set('remote', 'true');

  try {
    const res = await fetch(`/api/jobs?${params.toString()}`);
    if (!res.ok) throw new Error('Jobs API error');
    const data = await res.json();

    const jobs = data.jobs || [];
    const total = data.total || 0;
    const pages = data.pages || 1;

    renderResultsCount(total, jobs.length);

    if (jobs.length === 0) {
      jobsGrid.style.display = 'none';
      jobsTableWrap.style.display = 'none';
      emptyState.style.display = 'block';
      paginationBar.style.display = 'none';
      return;
    }

    emptyState.style.display = 'none';

    if (state.viewMode === 'grid') {
      jobsGrid.style.display = 'grid';
      jobsTableWrap.style.display = 'none';
      renderGrid(jobs);
    } else {
      jobsGrid.style.display = 'none';
      jobsTableWrap.style.display = 'block';
      renderTable(jobs);
    }

    renderPagination(state.page, pages);
  } catch (err) {
    console.error('Failed to fetch jobs:', err);
    resultsCount.textContent = 'Error querying jobs database.';
  }
}

function renderResultsCount(total, showing) {
  if (total === 0) {
    resultsCount.textContent = '0 jobs found';
    return;
  }
  const start = (state.page - 1) * state.limit + 1;
  const end = Math.min(start + showing - 1, total);
  resultsCount.innerHTML = `Showing <span style="color: white">${start}–${end}</span> of <span style="color: #818cf8">${total.toLocaleString()}</span> jobs`;
}

// Render Card Grid View
function renderGrid(jobs) {
  jobsGrid.innerHTML = '';
  jobs.forEach((job) => {
    const card = document.createElement('div');
    card.className = 'job-card';

    const isRemote = job.isRemote === 'True' || job.isRemote === true;
    const atsClass = (job.ats || 'ashby').toLowerCase();
    const publishedText = formatPublished(job.publishedAt);

    card.innerHTML = `
      <div class="card-top">
        <div class="card-company-bar">
          <span class="company-name">${escapeHtml(job.company)}</span>
          <span class="ats-badge ${atsClass}">${escapeHtml(job.ats)}</span>
        </div>
        <h3 class="job-title">${escapeHtml(job.title)}</h3>
        <div class="card-meta-chips">
          ${job.location ? `<span class="meta-chip">📍 ${escapeHtml(job.location)}</span>` : ''}
          ${isRemote ? `<span class="meta-chip chip-remote">⚡ Remote</span>` : ''}
          ${job.department ? `<span class="meta-chip">🏷️ ${escapeHtml(job.department)}</span>` : ''}
          ${job.employmentType ? `<span class="meta-chip">⏱️ ${escapeHtml(job.employmentType)}</span>` : ''}
        </div>
      </div>
      <div class="card-footer">
        <span class="published-ago">${publishedText}</span>
        <div class="card-actions">
          <button class="btn btn-outline btn-card-details" data-id="${job.id}">Details</button>
          <a href="${job.jobUrl}" target="_blank" rel="noopener noreferrer" class="btn-apply-direct">Apply ↗</a>
        </div>
      </div>
    `;

    card.querySelector('.btn-card-details').addEventListener('click', () => openModal(job));
    jobsGrid.appendChild(card);
  });
}

// Render Table View
function renderTable(jobs) {
  jobsTableBody.innerHTML = '';
  jobs.forEach((job) => {
    const tr = document.createElement('tr');
    const isRemote = job.isRemote === 'True' || job.isRemote === true;
    const atsClass = (job.ats || 'ashby').toLowerCase();
    const publishedText = formatPublished(job.publishedAt);

    tr.innerHTML = `
      <td class="table-company">${escapeHtml(job.company)}</td>
      <td class="table-title" title="${escapeHtml(job.title)}">${escapeHtml(job.title)}</td>
      <td><span class="ats-badge ${atsClass}">${escapeHtml(job.ats)}</span></td>
      <td>${job.location ? escapeHtml(job.location) : '—'}</td>
      <td>${isRemote ? '<span style="color: #34d399; font-weight: 600;">Remote</span>' : (job.workplaceType || 'On-site')}</td>
      <td>${publishedText}</td>
      <td>
        <div style="display: flex; gap: 6px;">
          <button class="btn btn-outline btn-card-details" style="padding: 4px 8px;" data-id="${job.id}">View</button>
          <a href="${job.jobUrl}" target="_blank" rel="noopener noreferrer" class="btn-apply-direct" style="padding: 4px 8px;">Apply ↗</a>
        </div>
      </td>
    `;

    tr.querySelector('.btn-card-details').addEventListener('click', () => openModal(job));
    jobsTableBody.appendChild(tr);
  });
}

// Render Pagination Numbers
function renderPagination(current, totalPages) {
  if (totalPages <= 1) {
    paginationBar.style.display = 'none';
    return;
  }

  paginationBar.style.display = 'flex';
  prevPageBtn.disabled = current <= 1;
  nextPageBtn.disabled = current >= totalPages;

  pageNumbers.innerHTML = '';

  const maxButtons = 5;
  let startPage = Math.max(1, current - 2);
  let endPage = Math.min(totalPages, startPage + maxButtons - 1);

  if (endPage - startPage < maxButtons - 1) {
    startPage = Math.max(1, endPage - maxButtons + 1);
  }

  for (let i = startPage; i <= endPage; i++) {
    const btn = document.createElement('button');
    btn.className = `page-num ${i === current ? 'active' : ''}`;
    btn.textContent = i;
    btn.addEventListener('click', () => {
      state.page = i;
      loadJobs();
      window.scrollTo({ top: 380, behavior: 'smooth' });
    });
    pageNumbers.appendChild(btn);
  }
}

// Modal Dialog
let currentStandardJobJson = null;

async function openModal(job) {
  state.activeModalJob = job;
  currentStandardJobJson = null;

  // Reset tab to overview
  switchModalTab('overview');

  document.getElementById('modalCompany').textContent = job.company;
  const atsBadge = document.getElementById('modalAts');
  atsBadge.textContent = job.ats;
  atsBadge.className = `ats-badge ${job.ats.toLowerCase()}`;

  document.getElementById('modalTitle').textContent = job.title;
  document.getElementById('modalLocation').textContent = job.location || 'Not specified';
  document.getElementById('modalWorkplace').textContent = (job.isRemote === 'True' || job.isRemote === true) ? 'Remote' : (job.workplaceType || 'On-site');
  document.getElementById('modalDepartment').textContent = job.department || job.team || 'Engineering';
  document.getElementById('modalPublished').textContent = job.publishedAt ? new Date(job.publishedAt).toLocaleString() : 'Undated';
  document.getElementById('modalIdentityKey').textContent = `("ats", "${job.id}")`;
  document.getElementById('modalId').textContent = `${job.ats.toUpperCase()} • ${job.company}`;

  // Default skills
  const skillsContainer = document.getElementById('modalSkillsChips');
  skillsContainer.innerHTML = '<span class="modal-skill-chip">Software Engineering</span>';

  document.getElementById('modalJsonCode').textContent = 'Loading schema JSON...';

  modalApplyBtn.href = job.jobUrl;
  jobModalBackdrop.style.display = 'flex';

  // Fetch standardized schema from API
  try {
    const res = await fetch(`/api/standard-job?id=${encodeURIComponent(job.id)}&source=ats`);
    if (res.ok) {
      const stdData = await res.json();
      currentStandardJobJson = stdData;
      document.getElementById('modalJsonCode').textContent = JSON.stringify(stdData, null, 2);
      document.getElementById('modalExpLevel').textContent = stdData.experience_level || '2-5';

      if (stdData.skills && stdData.skills.length > 0) {
        skillsContainer.innerHTML = stdData.skills
          .map((s) => `<span class="modal-skill-chip">${escapeHtml(s)}</span>`)
          .join('');
      }
    } else {
      document.getElementById('modalJsonCode').textContent = JSON.stringify({
        source: 'ats',
        source_id: job.id,
        og_source: job.ats,
        url: job.jobUrl,
        title: job.title,
        organization: job.company,
        date_posted: job.publishedAt,
        note: 'Saved in standard schema'
      }, null, 2);
    }
  } catch (err) {
    document.getElementById('modalJsonCode').textContent = 'Failed to load standard schema JSON.';
  }
}

function switchModalTab(tab) {
  const tabOverview = document.getElementById('modalTabOverview');
  const tabSchema = document.getElementById('modalTabSchema');
  const contentOverview = document.getElementById('modalOverviewContent');
  const contentSchema = document.getElementById('modalSchemaContent');

  if (tab === 'overview') {
    tabOverview.classList.add('active');
    tabSchema.classList.remove('active');
    contentOverview.style.display = 'block';
    contentSchema.style.display = 'none';
  } else {
    tabOverview.classList.remove('active');
    tabSchema.classList.add('active');
    contentOverview.style.display = 'none';
    contentSchema.style.display = 'block';
  }
}

function closeModal() {
  jobModalBackdrop.style.display = 'none';
  state.activeModalJob = null;
  currentStandardJobJson = null;
}

// Escape HTML for safety
function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

// Reset Filters
function resetFilters() {
  state.query = '';
  state.ats = 'all';
  state.company = '';
  state.remoteOnly = false;
  state.sortBy = 'recent';
  state.page = 1;

  searchInput.value = '';
  clearSearchBtn.style.display = 'none';
  companySelect.value = '';
  sortSelect.value = 'recent';
  remoteOnlyToggle.checked = false;

  atsPills.forEach((p) => {
    p.classList.toggle('active', p.dataset.ats === 'all');
  });

  loadJobs();
  showToast('Filters reset to default');
}

// Event Listeners
searchInput.addEventListener(
  'input',
  debounce((e) => {
    state.query = e.target.value.trim();
    state.page = 1;
    clearSearchBtn.style.display = state.query ? 'block' : 'none';
    loadJobs();
  }, 250)
);

clearSearchBtn.addEventListener('click', () => {
  searchInput.value = '';
  clearSearchBtn.style.display = 'none';
  state.query = '';
  state.page = 1;
  loadJobs();
});

atsPills.forEach((pill) => {
  pill.addEventListener('click', () => {
    atsPills.forEach((p) => p.classList.remove('active'));
    pill.classList.add('active');
    state.ats = pill.dataset.ats;
    state.page = 1;
    loadJobs();
  });
});

companySelect.addEventListener('change', (e) => {
  state.company = e.target.value;
  state.page = 1;
  loadJobs();
});

sortSelect.addEventListener('change', (e) => {
  state.sortBy = e.target.value;
  state.page = 1;
  loadJobs();
});

remoteOnlyToggle.addEventListener('change', (e) => {
  state.remoteOnly = e.target.checked;
  state.page = 1;
  loadJobs();
});

limitSelect.addEventListener('change', (e) => {
  state.limit = parseInt(e.target.value, 10);
  state.page = 1;
  loadJobs();
});

viewGridBtn.addEventListener('click', () => {
  viewGridBtn.classList.add('active');
  viewTableBtn.classList.remove('active');
  state.viewMode = 'grid';
  loadJobs();
});

viewTableBtn.addEventListener('click', () => {
  viewTableBtn.classList.add('active');
  viewGridBtn.classList.remove('active');
  state.viewMode = 'table';
  loadJobs();
});

prevPageBtn.addEventListener('click', () => {
  if (state.page > 1) {
    state.page--;
    loadJobs();
    window.scrollTo({ top: 380, behavior: 'smooth' });
  }
});

nextPageBtn.addEventListener('click', () => {
  state.page++;
  loadJobs();
  window.scrollTo({ top: 380, behavior: 'smooth' });
});

resetFiltersBtn.addEventListener('click', resetFilters);
emptyResetBtn.addEventListener('click', resetFilters);

refreshStatsBtn.addEventListener('click', () => {
  loadStats();
  loadCompanies();
  loadJobs();
  showToast('Synced with SQLite database');
});

modalCloseBtn.addEventListener('click', closeModal);
jobModalBackdrop.addEventListener('click', (e) => {
  if (e.target === jobModalBackdrop) closeModal();
});

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && jobModalBackdrop.style.display === 'flex') {
    closeModal();
  }
});

modalCopyBtn.addEventListener('click', () => {
  if (state.activeModalJob?.jobUrl) {
    navigator.clipboard.writeText(state.activeModalJob.jobUrl);
    showToast('Job link copied to clipboard!');
  }
});

const modalTabOverview = document.getElementById('modalTabOverview');
const modalTabSchema = document.getElementById('modalTabSchema');
const modalCopySchemaBtn = document.getElementById('modalCopySchemaBtn');

if (modalTabOverview) modalTabOverview.addEventListener('click', () => switchModalTab('overview'));
if (modalTabSchema) modalTabSchema.addEventListener('click', () => switchModalTab('schema'));
if (modalCopySchemaBtn) {
  modalCopySchemaBtn.addEventListener('click', () => {
    const text = document.getElementById('modalJsonCode').textContent;
    if (text) {
      navigator.clipboard.writeText(text);
      showToast('Schema JSON copied to clipboard!');
    }
  });
}

// Initial boot
loadStats();
loadCompanies();
loadJobs();
