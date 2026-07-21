/* ── Surveyor Job Dashboard — Frontend App ── */
'use strict';

const API = '/api';
const PAGE_SIZE = 50;

// ── State ──
let jobs = [];
let currentTab = 'jobs';
let jobPage = 0;
let debounceTimer = null;
let currentJobId = null;
let matchLoading = false;
let sortMode = 'date'; // 'date' or 'match'

// ── Init ──
document.addEventListener('DOMContentLoaded', () => {
  initNavigation();
  initTheme();
  loadJobs();
  loadJobCount();
  loadCV();
  initJobFilters();
  initSortToggle();
  initApplicationTab();
  initCVTab();
  initModal();
});

/* ── Navigation ── */
function initNavigation() {
  document.querySelectorAll('.nav-tab, .mobile-tab').forEach(tab => {
    tab.addEventListener('click', () => switchTab(tab.dataset.tab));
  });
  document.getElementById('scrapeBtn').addEventListener('click', triggerScrape);
}

function switchTab(tab) {
  currentTab = tab;
  document.querySelectorAll('.nav-tab, .mobile-tab').forEach(t => t.classList.remove('active'));
  const navTab = document.querySelector(`.nav-tab[data-tab="${tab}"]`);
  const mobileTab = document.querySelector(`.mobile-tab[data-tab="${tab}"]`);
  if (navTab) navTab.classList.add('active');
  if (mobileTab) mobileTab.classList.add('active');
  document.querySelectorAll('.tab-content').forEach(s => s.classList.remove('active'));
  document.getElementById(`tab-${tab}`).classList.add('active');

  if (tab === 'jobs') loadJobs();
  else if (tab === 'applications') loadApplications();
  else if (tab === 'pipeline') loadPipeline();
  else if (tab === 'schemes') loadSchemes();
  else if (tab === 'analytics') loadAnalytics();
}

/* ── Theme ── */
function initTheme() {
  const html = document.documentElement;
  const btn = document.getElementById('themeToggle');
  const saved = localStorage.getItem('theme');
  if (saved === 'light') html.classList.remove('dark');
  btn.addEventListener('click', () => {
    html.classList.toggle('dark');
    localStorage.setItem('theme', html.classList.contains('dark') ? 'dark' : 'light');
  });
}

/* ── Toast ── */
function showToast(msg, error = false) {
  const container = document.getElementById('toastContainer');
  const el = document.createElement('div');
  el.className = 'toast' + (error ? ' error' : '');
  el.textContent = msg;
  container.appendChild(el);
  // Animate out after 3s
  setTimeout(() => {
    el.style.opacity = '0';
    el.style.transform = 'translateY(12px)';
    el.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
    setTimeout(() => el.remove(), 300);
  }, 3000);
  // Limit to max 3 visible toasts
  const toasts = container.querySelectorAll('.toast');
  if (toasts.length > 3) toasts[0].remove();
}

function icon(name) {
  const icons = {
    check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><polyline points="20 6 9 17 4 12"/></svg>',
    alert: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>',
    external: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>',
    building: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><rect x="4" y="2" width="16" height="20" rx="2"/><line x1="9" y1="6" x2="9" y2="6.01"/><line x1="15" y1="6" x2="15" y2="6.01"/><line x1="9" y1="10" x2="9" y2="10.01"/><line x1="15" y1="10" x2="15" y2="10.01"/><line x1="9" y1="14" x2="9" y2="14.01"/><line x1="15" y1="14" x2="15" y2="14.01"/></svg>',
    users: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>',
    calendar: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>',
    'map-pin': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>',
    'graduation-cap': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M22 10v6M2 10l10-5 10 5-10 5z"/><path d="M6 12v5c3 3 9 3 12 0v-5"/></svg>',
    'thumbs-up': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3H14zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"/></svg>',
    'thumbs-down': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3H10zM17 2h3a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2h-3"/></svg>',
    shuffle: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><polyline points="16 3 21 3 21 8"/><line x1="4" y1="20" x2="21" y2="3"/><polyline points="21 16 21 21 16 21"/><line x1="15" y1="15" x2="21" y2="21"/><line x1="4" y1="4" x2="9" y2="9"/></svg>',
    'alert-triangle': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
    'hard-hat': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M2 18v1c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2v-1"/><path d="M4 18v-6a8 8 0 0 1 16 0v6"/><path d="M2 18h20"/><rect x="9" y="14" width="6" height="4" rx="1"/></svg>',
    newspaper: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M4 22h16a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2H8a2 2 0 0 0-2 2v16a2 2 0 0 1-2 2zm0 0a2 2 0 0 1-2-2v-9h2"/><path d="M10 6h6"/><path d="M10 10h6"/><path d="M10 14h4"/></svg>',
    star: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>',
    'check-circle': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>',
    'clipboard-list': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="9" y1="11" x2="9" y2="11.01"/><line x1="9" y1="15" x2="9" y2="15.01"/><line x1="11" y1="11" x2="14" y2="11"/><line x1="11" y1="15" x2="14" y2="15"/><line x1="8" y1="7" x2="16" y2="7"/></svg>',
  };
  return icons[name] || '';
}

function disciplineLabel(d) {
  const map = { quantity_surveying:'QS', land_surveying:'Land', building_surveying:'Building', general_practice:'GP', planning:'Planning', other:'Other' };
  return map[d] || d;
}

function statusColor(status) {
  const map = { saved:'#64748B', applied:'#3B82F6', interview:'#D97706', offer:'#16A34A', accepted:'#16A34A', rejected:'#DC2626', withdrawn:'#64748B' };
  return map[status] || '#64748B';
}

/* ── Jobs ── */
async function loadJobs() {
  if (currentTab !== 'jobs') return;
  const list = document.getElementById('jobList');
  // Show skeleton cards while loading
  list.innerHTML = Array(5).fill(`<div class="job-card-skeleton">
    <div class="job-info">
      <div class="sk-line sk-title"></div>
      <div class="sk-line sk-company"></div>
    </div>
    <div class="sk-select"></div>
  </div>`).join('');

  const disc = document.getElementById('disciplineFilter').value;
  const expLevel = document.getElementById('experienceFilter').value;
  const status = document.getElementById('statusFilter').value;
  const search = document.getElementById('jobSearch').value;

  let url = `${API}/jobs?experience_level=${expLevel}&limit=${PAGE_SIZE}&offset=${jobPage * PAGE_SIZE}`;
  if (disc) url += `&discipline=${disc}`;
  if (status && status !== 'none') url += `&status=${status}`;
  if (search) url += `&search=${encodeURIComponent(search)}`;

  try {
    const r = await fetch(url);
    const data = await r.json();
    jobs = data.jobs || [];
    renderJobs(jobs);
    renderPagination(data.total);
    document.getElementById('jobCount').textContent = data.total;
  } catch (e) {
    list.innerHTML = `<div class="empty-state"><h3>Failed to load</h3><p>${e.message}</p></div>`;
  }
}

function renderJobs(jobsArr) {
  const list = document.getElementById('jobList');
  if (!jobsArr.length) {
    const statusFilter = document.getElementById('statusFilter').value;
    const msg = statusFilter === 'none' ? 'No unapplied jobs match your filters.' : 'No jobs match your filters.';
    list.innerHTML = `<div class="empty-state"><h3>No jobs found</h3><p>${msg}</p></div>`;
    return;
  }
  list.innerHTML = jobsArr.map(j => {
    const matchBadge = j.has_match && j.match_score != null
      ? `<span class="job-tag matched-badge">${icon('check-circle')} Matched</span>`
      : '';
    const matchCell = j.match_score != null
      ? `<div class="match-cell"><div class="match-badge ${j.match_score >= 70 ? 'match-high' : j.match_score >= 40 ? 'match-medium' : 'match-low'}">${j.match_score}%</div></div>`
      : '';

    const status = j.application_status || '';
    const statusSel = `<select class="status-select" data-job-id="${j.id}" data-current="${status}">
      <option value="" ${!status?'selected':''}>Not applied</option>
      <option value="saved" ${status==='saved'?'selected':''}>Saved</option>
      <option value="applied" ${status==='applied'?'selected':''}>Applied</option>
      <option value="interview" ${status==='interview'?'selected':''}>Interview</option>
      <option value="offer" ${status==='offer'?'selected':''}>Offer</option>
      <option value="rejected" ${status==='rejected'?'selected':''}>Rejected</option>
      <option value="withdrawn" ${status==='withdrawn'?'selected':''}>Withdrawn</option>
    </select>`;

    return `<div class="job-card" data-job-id="${j.id}" data-status="${status || 'none'}" tabindex="0" role="button" aria-label="View details for ${escapeHtml(j.title)} at ${escapeHtml(j.company)}">
      <div class="job-info">
        <div class="job-title">${escapeHtml(j.title)}</div>
        <div class="job-company">${icon('building')} ${escapeHtml(j.company)}</div>
        <div class="job-meta">
          <span class="job-tag tag-discipline">${disciplineLabel(j.discipline)}</span>
          ${j.location ? `<span class="job-tag tag-location">${escapeHtml(j.location)}</span>` : ''}
          ${j.salary_range ? `<span class="job-tag tag-salary">${escapeHtml(j.salary_range)}</span>` : ''}
          ${j.fresh_grad_friendly ? '<span class="job-tag tag-fresh">Graduate</span>' : ''}
          ${status ? `<span class="job-tag status-tag" style="background:${statusColor(status)}15;color:${statusColor(status)}">${status}</span>` : ''}
        </div>
      </div>
      ${matchCell}
      <div class="status-cell">${statusSel}</div>
    </div>`;
  }).join('');

  // Click handlers
  list.querySelectorAll('.job-card').forEach(card => {
    const handleActivate = (e) => {
      if (e.target.closest('.status-select')) return;
      openJobDetail(parseInt(card.dataset.jobId));
    };
    card.addEventListener('click', handleActivate);
    card.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        handleActivate(e);
      }
    });
  });

  // Status change handlers
  list.querySelectorAll('.status-select').forEach(sel => {
    sel.addEventListener('change', (e) => {
      e.stopPropagation();
      updateJobStatus(parseInt(sel.dataset.jobId), sel.value);
    });
  });
}

function renderPagination(total) {
  const el = document.getElementById('jobsPagination');
  const pages = Math.ceil(total / PAGE_SIZE);
  if (pages <= 1) { el.innerHTML = ''; return; }
  let html = `<button ${jobPage === 0 ? 'disabled' : ''} data-page="${jobPage - 1}">Prev</button>`;
  for (let i = 0; i < pages; i++) {
    html += `<button class="${i === jobPage ? 'active' : ''}" data-page="${i}">${i + 1}</button>`;
  }
  html += `<button ${jobPage >= pages - 1 ? 'disabled' : ''} data-page="${jobPage + 1}">Next</button>`;
  el.innerHTML = html;
  el.querySelectorAll('button:not([disabled])').forEach(b => {
    b.addEventListener('click', () => { jobPage = parseInt(b.dataset.page); loadJobs(); });
  });
}

function initJobFilters() {
  ['disciplineFilter', 'experienceFilter', 'statusFilter'].forEach(id => {
    document.getElementById(id).addEventListener('change', () => { jobPage = 0; loadJobs(); });
  });
  document.getElementById('jobSearch').addEventListener('input', () => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => { jobPage = 0; loadJobs(); }, 300);
  });
}

function initSortToggle() {
  document.querySelectorAll('.sort-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.sort-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      sortMode = btn.dataset.sort;
      jobPage = 0;
      if (sortMode === 'match') loadRankedJobs();
      else loadJobs();
    });
  });
}

async function loadRankedJobs() {
  const list = document.getElementById('jobList');
  const banner = document.getElementById('topPicksBanner');
  list.innerHTML = '<div class="loading">Ranking jobs by CV match...</div>';

  try {
    const r = await fetch(`${API}/jobs/ranked`);
    const data = await r.json();
    const jobsArr = data.jobs || data || [];

    // Top Picks Banner
    const topPicks = jobsArr.filter(j => j.has_match).slice(0, 3);
    if (topPicks.length) {
      banner.style.display = 'block';
      banner.innerHTML = `<h3>${icon('star')} Top Picks for You</h3><div class="top-pick-cards">${topPicks.map(j => `
        <div class="top-pick-card" onclick="openJobDetail(${j.job_id})">
          <div class="tp-company">${escapeHtml(j.company)}</div>
          <div class="tp-title">${escapeHtml(j.title)}</div>
          <div class="tp-score">Match: ${Math.round(j.match_score)}%</div>
        </div>`).join('')}</div>`;
    } else {
      banner.style.display = 'none';
    }

    renderMatchRankedJobs(jobsArr);
  } catch (e) {
    list.innerHTML = `<div class="empty-state"><h3>Failed to load</h3><p>Upload your CV and run CV Matching first to see ranked results.</p></div>`;
  }
}

function renderMatchRankedJobs(jobsArr) {
  const list = document.getElementById('jobList');
  if (!jobsArr.length) {
    list.innerHTML = `<div class="empty-state"><h3>No match data</h3><p>Upload your CV and run "Match All" to get ranked results.</p></div>`;
    return;
  }

  list.innerHTML = jobsArr.map(j => {
    const score = j.has_match ? Math.round(j.match_score) : null;
    let matchCellHtml = '';
    if (score !== null) {
      const tier = score >= 70 ? 'match-high' : score >= 40 ? 'match-medium' : 'match-low';
      matchCellHtml = `<div class="match-cell"><div class="match-badge ${tier}">${score}%</div></div>`;
    }

    const status = j.application_status || '';
    const statusSel = `<select class="status-select" data-job-id="${j.job_id}" data-current="${status}">
      <option value="" ${!status?'selected':''}>Not applied</option>
      <option value="saved" ${status==='saved'?'selected':''}>Saved</option>
      <option value="applied" ${status==='applied'?'selected':''}>Applied</option>
      <option value="interview" ${status==='interview'?'selected':''}>Interview</option>
      <option value="offer" ${status==='offer'?'selected':''}>Offer</option>
      <option value="rejected" ${status==='rejected'?'selected':''}>Rejected</option>
      <option value="withdrawn" ${status==='withdrawn'?'selected':''}>Withdrawn</option>
    </select>`;

    return `<div class="job-card" data-job-id="${j.job_id}" data-status="${status || 'none'}" tabindex="0" role="button" aria-label="View details for ${escapeHtml(j.title)} at ${escapeHtml(j.company)}">
      <div class="job-info">
        <div class="job-title">${escapeHtml(j.title)}</div>
        <div class="job-company">${icon('building')} ${escapeHtml(j.company)}</div>
        <div class="job-meta">
          <span class="job-tag tag-discipline">${disciplineLabel(j.discipline)}</span>
          ${j.location ? `<span class="job-tag tag-location">${escapeHtml(j.location)}</span>` : ''}
          ${j.salary_range ? `<span class="job-tag tag-salary">${escapeHtml(j.salary_range)}</span>` : ''}
          ${j.fresh_grad_friendly ? '<span class="job-tag tag-fresh">Graduate</span>' : ''}
          ${status ? `<span class="job-tag status-tag" style="background:${statusColor(status)}15;color:${statusColor(status)}">${status}</span>` : ''}
        </div>
      </div>
      ${matchCellHtml}
      <div class="status-cell">${statusSel}</div>
    </div>`;
  }).join('');

  // Click handlers
  list.querySelectorAll('.job-card').forEach(card => {
    const handleActivate = (e) => {
      if (e.target.closest('.status-select')) return;
      openJobDetail(parseInt(card.dataset.jobId));
    };
    card.addEventListener('click', handleActivate);
    card.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        handleActivate(e);
      }
    });
  });

  // Status select handlers
  list.querySelectorAll('.status-select').forEach(sel => {
    sel.addEventListener('change', (e) => {
      e.stopPropagation();
      const jobId = parseInt(sel.dataset.jobId);
      const newStatus = sel.value;
      updateJobStatus(jobId, newStatus);
    });
  });
}

async function updateJobStatus(jobId, status) {
  const card = document.querySelector(`.job-card[data-job-id="${jobId}"]`);
  const select = card?.querySelector('.status-select');

  try {
    if (status) {
      await fetch(`${API}/applications/${jobId}`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({status})
      });
    } else {
      // Clear status — delete the application record
      await fetch(`${API}/applications/${jobId}`, { method: 'DELETE' });
    }

    // Flash the card to confirm the change
    if (card) {
      card.classList.add('status-flash');
      card.dataset.status = status || 'none';
      setTimeout(() => card.classList.remove('status-flash'), 600);
    }
    // Briefly highlight the select too
    if (select) {
      select.classList.add('status-select-flash');
      setTimeout(() => select.classList.remove('status-select-flash'), 600);
    }

    showToast(status ? `Status updated to ${status}` : 'Application removed');

    // Update the card in-place — no full page reload
    if (card) {
      // Update the status tag in the job-meta area
      const meta = card.querySelector('.job-meta');
      if (meta) {
        // Remove old status tag if present
        const oldTag = meta.querySelector('.status-tag');
        if (oldTag) oldTag.remove();
        // Add new status tag
        if (status) {
          const tag = document.createElement('span');
          tag.className = 'job-tag status-tag';
          tag.style.background = statusColor(status) + '15';
          tag.style.color = statusColor(status);
          tag.textContent = status;
          meta.appendChild(tag);
        }
      }
      // Update the select value without triggering change event
      if (select) {
        select.value = status || '';
        select.dataset.current = status || '';
      }
    }
    loadJobCount();
  } catch (e) {
    showToast('Failed to update status', true);
  }
}

async function loadJobCount() {
  try {
    const r = await fetch(`${API}/jobs?experience_level=all&limit=1`);
    const data = await r.json();
    document.getElementById('jobCount').textContent = data.total || 0;
  } catch (e) {}
}

async function triggerScrape() {
  const btn = document.getElementById('scrapeBtn');
  btn.disabled = true;
  btn.textContent = 'Scraping...';
  showToast('Scraping job boards — this may take a minute...');
  try {
    const r = await fetch(`${API}/jobs/scrape`, {method: 'POST'});
    const data = await r.json();
    if (data.ok) {
      // Count jobs before and after to show delta
      const before = document.getElementById('jobCount').textContent;
      await loadJobs();
      await loadJobCount();
      const after = document.getElementById('jobCount').textContent;
      const delta = parseInt(after) - parseInt(before);
      showToast(delta > 0 ? `Scraped ${delta} new job(s) — ${after} total` : `No new jobs found — ${after} total`);
    } else {
      showToast('Scrape failed: ' + (data.error || 'Unknown error'), true);
    }
  } catch (e) {
    showToast('Scrape failed: ' + e.message, true);
  }
  btn.disabled = false;
  btn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg> Scrape Now`;
}

/* ── Job Detail Modal ── */
function initModal() {
  const modal = document.getElementById('jobModal');
  modal.querySelector('.modal-close').addEventListener('click', closeModal);
  modal.querySelector('.modal-backdrop').addEventListener('click', closeModal);
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeModal();
  });
  // Prevent body scroll when modal is open (mobile)
  modal.addEventListener('touchmove', (e) => {
    if (!e.target.closest('.modal-container')) e.preventDefault();
  }, {passive: false});
}

async function openJobDetail(jobId) {
  currentJobId = jobId;
  const modal = document.getElementById('jobModal');
  modal.style.display = 'flex';
  document.body.style.overflow = 'hidden';
  const detail = document.getElementById('jobDetail');
  detail.innerHTML = '<div class="loading"><div class="spinner"></div>Loading...</div>';

  try {
    const r = await fetch(`${API}/jobs/${jobId}`);
    const j = await r.json();
    renderJobDetail(j);
  } catch (e) {
    detail.innerHTML = `<div class="empty-state"><h3>Error</h3><p>${e.message}</p></div>`;
  }
}

function closeModal() {
  document.getElementById('jobModal').style.display = 'none';
  document.body.style.overflow = '';
  currentJobId = null;
}

function renderJobDetail(j) {
  const detail = document.getElementById('jobDetail');
  let html = `
    <div class="job-detail-header">
      <h2>${escapeHtml(j.title)}</h2>
      <div class="company-name">${escapeHtml(j.company)}</div>
      <div class="job-detail-meta">
        <span class="job-tag tag-discipline">${disciplineLabel(j.discipline)}</span>
        ${j.location ? `<span class="job-tag tag-location">${escapeHtml(j.location)}</span>` : ''}
        ${j.salary_range ? `<span class="job-tag tag-salary">${escapeHtml(j.salary_range)}</span>` : ''}
        ${j.fresh_grad_friendly ? '<span class="job-tag tag-fresh">Graduate</span>' : ''}
        ${j.application_status ? `<span class="job-tag" style="background:${statusColor(j.application_status)}15;color:${statusColor(j.application_status)}">${j.application_status}</span>` : ''}
      </div>
    </div>`;

  if (j.description || j.requirements || j.description_html) {
    html += '<div class="detail-grid">';
    if (j.description_html) {
      // Rich HTML from original source or formatter
      html += `<div class="detail-section"><h3>Description</h3><div class="desc-content desc-html">${sanitizeDescriptionHtml(j.description_html)}</div></div>`;
    } else if (j.description) {
      html += `<div class="detail-section"><h3>Description</h3><div class="desc-content">${formatDescription(j.description)}</div></div>`;
    }
    if (j.requirements) html += `<div class="detail-section"><h3>Requirements</h3><div class="desc-content">${formatDescription(j.requirements)}</div></div>`;
    html += '</div>';
  }

  if (j.url) {
    html += `<div class="detail-section"><a href="${escapeHtml(j.url)}" target="_blank" rel="noopener noreferrer" class="source-link" onclick="event.stopPropagation(); window.open(this.href, '_blank'); return false;">${icon('external')} View original posting</a></div>`;
  }

  // Match panel
  if (j.match_score != null) {
    html += renderMatchPanel(j);
  }

  // Action buttons
  html += `<div class="action-buttons">
    <button class="btn btn-primary" onclick="runCVMatch(${j.id})">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
      ${j.match_score != null ? 'Re-run Match' : 'Match CV to This Job'}
    </button>
    <button class="btn btn-outline" onclick="researchCompany('${escapeAttr(j.company)}')">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><rect x="4" y="2" width="16" height="20" rx="2"/></svg>
      Research Company
    </button>
  </div>`;

  detail.innerHTML = html;
}

function renderMatchPanel(j) {
  const ms = j.match_score;
  const cls = ms >= 70 ? 'high' : ms >= 40 ? 'medium' : 'low';
  let html = `<div class="match-panel">
    <div class="match-header">
      <div class="match-score-large ${cls}">${ms}%</div>
      <div class="match-cta">
        <span style="font-size:.85rem;color:var(--color-text2)">Match Score</span>
      </div>
    </div>`;

  if (j.strengths) {
    const strengths = tryParseJSON(j.strengths);
    html += `<div class="match-detail-section"><h4>Strengths</h4><ul>${(Array.isArray(strengths)?strengths:[j.strengths]).map(s=>`<li>${escapeHtml(typeof s==='string'?s:JSON.stringify(s))}</li>`).join('')}</ul></div>`;
  }
  if (j.gaps) {
    const gaps = tryParseJSON(j.gaps);
    html += `<div class="match-detail-section"><h4>Gaps</h4><ul>${(Array.isArray(gaps)?gaps:[j.gaps]).map(g=>`<li>${escapeHtml(typeof g==='string'?g:JSON.stringify(g))}</li>`).join('')}</ul></div>`;
  }
  if (j.suggestions) {
    const suggestions = tryParseJSON(j.suggestions);
    html += `<div class="match-detail-section"><h4>CV Suggestions</h4><ul>${(Array.isArray(suggestions)?suggestions:[j.suggestions]).map(s=>`<li>${escapeHtml(typeof s==='string'?s:JSON.stringify(s))}</li>`).join('')}</ul></div>`;
  }

  html += '</div>'; // match-panel

  if (j.tailored_cv) {
    html += `<div class="content-block"><h4>Tailored CV Summary</h4><p>${escapeHtml(j.tailored_cv)}</p></div>`;
  }
  if (j.cover_letter) {
    html += `<div class="content-block"><h4>Cover Letter</h4><p>${escapeHtml(j.cover_letter)}</p></div>`;
  }
  if (j.interview_questions) {
    const iq = tryParseJSON(j.interview_questions);
    html += `<div class="content-block"><h4>Likely Interview Questions</h4><ul>${(Array.isArray(iq)?iq:[j.interview_questions]).map((q,i)=>`<li style="padding:4px 0;font-size:.85rem">${i+1}. ${escapeHtml(typeof q==='string'?q:JSON.stringify(q))}</li>`).join('')}</ul></div>`;
  }

  return html;
}

async function runCVMatch(jobId) {
  if (matchLoading) return;
  matchLoading = true;
  const detail = document.getElementById('jobDetail');

  // Store current job detail HTML so we can restore it with match results
  const currentDetailHTML = detail.innerHTML;
  detail.innerHTML += '<div class="loading"><div class="spinner"></div>Analyzing CV against this job...</div>';

  try {
    const r = await fetch(`${API}/cv/match/${jobId}`, {method:'POST'});
    if (!r.ok) {
      const err = await r.json();
      throw new Error(err.detail || 'Match failed');
    }
    const data = await r.json();
    // Re-render the full job detail (preserving header) and inject match results below
    // First, restore the original job detail, then overlay match data
    detail.innerHTML = currentDetailHTML;
    // Remove any existing match panel before appending new one
    const existingMatch = detail.querySelector('.match-panel');
    if (existingMatch) existingMatch.remove();
    // Render match panel using just the match data fields
    const matchHTML = renderMatchPanel({
      match_score: data.match_score,
      strengths: data.strengths,
      gaps: data.gaps,
      suggestions: data.suggestions,
      tailored_cv: data.tailored_cv,
      cover_letter: data.cover_letter,
      interview_questions: data.interview_questions,
    });
    detail.insertAdjacentHTML('beforeend', matchHTML);
    showToast(`Match complete — score: ${data.match_score}%`);
  } catch (e) {
    detail.innerHTML = currentDetailHTML;
    showToast(e.message, true);
  }
  matchLoading = false;
}

async function researchCompany(name) {
  const detail = document.getElementById('jobDetail');
  const loader = document.createElement('div');
  loader.className = 'loading';
  loader.innerHTML = '<div class="spinner"></div>Researching company via web search...</div>';
  loader.id = 'researchLoader';
  detail.appendChild(loader);
  try {
    const r = await fetch(`${API}/companies/${encodeURIComponent(name)}`);
    const ld = document.getElementById('researchLoader');
    if (ld) ld.remove();
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      throw new Error(err.detail || 'Company research failed');
    }
    const data = await r.json();
    renderCompanyResearch(data);
  } catch (e) {
    const ld = document.getElementById('researchLoader');
    if (ld) ld.remove();
    showToast(e.message, true);
  }
}

function renderCompanyResearch(data) {
  const detail = document.getElementById('jobDetail');
  let html = '<div class="company-research">';

  // Header with rating
  html += '<div class="cr-header">';
  html += `<h3>${escapeHtml(data.company_name || '')}</h3>`;
  if (data.glassdoor_rating) {
    const stars = 'Rating: ' + data.glassdoor_rating + '/5';
    html += `<div class="cr-rating"><span class="cr-stars">${stars}</span> <span class="cr-score">${data.glassdoor_rating}/5</span>`;
    if (data.glassdoor_review_count) html += ` <span class="cr-review-count">(${data.glassdoor_review_count} reviews)</span>`;
    html += '</div>';
  }
  html += '</div>';

  // Overview
  html += '<div class="cr-section">';
  html += '<h4>Overview</h4>';
  html += `<p>${escapeHtml(data.overview || 'No overview available')}</p>`;
  html += '<div class="cr-meta">';
  if (data.employee_count && data.employee_count !== 'Unknown') html += `<span class="cr-meta-item">${icon('users')} ${escapeHtml(data.employee_count)} employees</span>`;
  if (data.founded_year && data.founded_year !== 'Unknown') html += `<span class="cr-meta-item">${icon('calendar')} Founded ${escapeHtml(data.founded_year)}</span>`;
  if (data.headquarters && data.headquarters !== 'Unknown') html += `<span class="cr-meta-item">${icon('map-pin')} ${escapeHtml(data.headquarters)}</span>`;
  if (data.apc_training) html += '<span class="cr-meta-item cr-apc">' + icon('graduation-cap') + ' HKIS/RICS APC Training</span>';
  html += '</div>';
  html += '</div>';

  // Glassdoor pros/cons
  if (data.glassdoor_pros || data.glassdoor_cons) {
    html += '<div class="cr-grid">';
    if (data.glassdoor_pros) {
      const pros = Array.isArray(data.glassdoor_pros) ? data.glassdoor_pros : [data.glassdoor_pros];
      html += '<div class="cr-card cr-pros"><h4>' + icon('thumbs-up') + ' Pros</h4><ul>';
      pros.forEach(p => { html += `<li>${escapeHtml(typeof p === 'string' ? p : '')}</li>`; });
      html += '</ul></div>';
    }
    if (data.glassdoor_cons) {
      const cons = Array.isArray(data.glassdoor_cons) ? data.glassdoor_cons : [data.glassdoor_cons];
      html += '<div class="cr-card cr-cons"><h4>' + icon('thumbs-down') + ' Cons</h4><ul>';
      cons.forEach(c => { html += `<li>${escapeHtml(typeof c === 'string' ? c : '')}</li>`; });
      html += '</ul></div>';
    }
    html += '</div>';
  }

  // HK Government Contracts
  if (data.hk_government_contracts && Array.isArray(data.hk_government_contracts) && data.hk_government_contracts.length) {
    html += '<div class="cr-section"><h4>' + icon('hard-hat') + ' HK Government Contracts</h4>';
    data.hk_government_contracts.forEach(c => {
      html += `<div class="cr-contract">`;
      html += `<div class="cr-contract-name">${escapeHtml(c.project || '')}</div>`;
      html += `<div class="cr-contract-meta">${escapeHtml(c.client || '')}${c.value ? ' · ' + escapeHtml(c.value) : ''}</div>`;
      html += '</div>';
    });
    html += '</div>';
  }

  // Recent News
  if (data.recent_news && Array.isArray(data.recent_news) && data.recent_news.length) {
    html += '<div class="cr-section"><h4>' + icon('newspaper') + ' Recent News</h4>';
    data.recent_news.forEach(n => {
      html += '<div class="cr-news-item">';
      if (n.date) html += `<span class="cr-news-date">${escapeHtml(n.date)}</span>`;
      html += `<div class="cr-news-title">${escapeHtml(n.title || '')}</div>`;
      if (n.detail) html += `<div class="cr-news-detail">${escapeHtml(n.detail)}</div>`;
      html += '</div>';
    });
    html += '</div>';
  }

  // HK projects
  if (data.hk_projects && Array.isArray(data.hk_projects) && data.hk_projects.length) {
    html += '<div class="cr-section"><h4>' + icon('building') + ' HK Projects</h4>';
    data.hk_projects.forEach(p => {
      html += `<div class="cr-project-card">`;
      html += `<div class="cr-project-name">${escapeHtml(p.name || '')}</div>`;
      if (p.type) html += `<span class="cr-project-type">${escapeHtml(p.type)}</span>`;
      if (p.description) html += `<div class="cr-project-desc">${escapeHtml(p.description)}</div>`;
      html += '</div>';
    });
    html += '</div>';
  }

  // Competitor comparison
  if (data.competitor_comparison && data.competitor_comparison !== 'Unknown') {
    html += '<div class="cr-section"><h4>' + icon('shuffle') + ' vs Competitors</h4>';
    html += `<p>${escapeHtml(data.competitor_comparison)}</p>`;
    html += '</div>';
  }

  // Staff turnover
  if (data.staff_turnover_notes && data.staff_turnover_notes !== 'Unknown') {
    html += '<div class="cr-section"><h4>' + icon('alert-triangle') + ' Staff Signals</h4>';
    html += `<p>${escapeHtml(data.staff_turnover_notes)}</p>`;
    html += '</div>';
  }

  // Cache info
  if (data.last_researched) {
    html += `<div class="cr-footer">Researched ${escapeHtml(data.last_researched.slice(0, 10))} · cached 30 days</div>`;
  }

  html += '</div>'; // .company-research

  // Replace existing detail content with a fresh rendering
  // We need to re-render the full job detail with company research appended
  const jobTitle = detail.querySelector('.job-detail-header h2');
  const jobCompany = detail.querySelector('.job-detail-header .company-name');
  if (jobTitle && jobCompany) {
    // Insert research after existing job detail, before any existing research
    const existingResearch = detail.querySelector('.company-research');
    if (existingResearch) existingResearch.remove();
    detail.insertAdjacentHTML('beforeend', html);
  }
}

/* ── Applications Tab ── */
function initApplicationTab() {
  document.querySelectorAll('#appStatusTabs .status-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('#appStatusTabs .status-tab').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      loadApplications(tab.dataset.status);
    });
  });
}

async function loadApplications(status = '') {
  if (currentTab !== 'applications') return;
  const list = document.getElementById('appList');
  list.innerHTML = '<div class="loading"><div class="spinner"></div>Loading...</div>';

  let url = `${API}/applications`;
  if (status) url += `?status=${status}`;

  try {
    const r = await fetch(url);
    const data = await r.json();
    const apps = data.applications || [];
    if (!apps.length) {
      list.innerHTML = `<div class="empty-state"><h3>No applications</h3><p>Save jobs from the Jobs tab to track them here.</p></div>`;
      return;
    }
    list.innerHTML = apps.map(a => `
      <div class="job-card" data-job-id="${a.job_id}">
        <div class="job-info">
          <div class="job-title">${escapeHtml(a.job_title)}</div>
          <div class="job-company">${icon('building')} ${escapeHtml(a.job_company)}</div>
          <div class="job-meta">
            <span class="job-tag tag-discipline">${disciplineLabel(a.discipline)}</span>
            ${a.location ? `<span class="job-tag tag-location">${escapeHtml(a.location)}</span>` : ''}
            <span class="job-tag" style="background:${statusColor(a.status)}15;color:${statusColor(a.status)}">${a.status}</span>
            ${a.applied_date ? `<span style="font-size:.75rem;color:var(--color-text2)">Applied: ${a.applied_date}</span>` : ''}
          </div>
        </div>
        <div></div>
        <div class="status-cell">
          <select class="status-select" data-app-id="${a.id}" data-current="${a.status}">
            <option value="" ${!a.status?'selected':''}>Not applied</option>
            <option value="saved" ${a.status==='saved'?'selected':''}>Saved</option>
            <option value="applied" ${a.status==='applied'?'selected':''}>Applied</option>
            <option value="interview" ${a.status==='interview'?'selected':''}>Interview</option>
            <option value="offer" ${a.status==='offer'?'selected':''}>Offer</option>
            <option value="rejected" ${a.status==='rejected'?'selected':''}>Rejected</option>
            <option value="withdrawn" ${a.status==='withdrawn'?'selected':''}>Withdrawn</option>
          </select>
        </div>
      </div>
    `).join('');

    list.querySelectorAll('.job-card').forEach(card => {
      card.addEventListener('click', (e) => {
        if (e.target.closest('.status-select')) return;
        openJobDetail(parseInt(card.dataset.jobId));
      });
    });

    list.querySelectorAll('.status-select').forEach(sel => {
      sel.addEventListener('change', async (e) => {
        e.stopPropagation();
        const appId = sel.dataset.appId;
        const newStatus = sel.value;
        if (newStatus) {
          await fetch(`${API}/applications/id/${appId}`, {
            method: 'PATCH',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({status: newStatus})
          });
          showToast(`Status updated to ${newStatus}`);
        } else {
          // Clear status — need job_id to delete
          const jobId = sel.closest('.job-card')?.dataset.jobId;
          if (jobId) {
            await fetch(`${API}/applications/${jobId}`, { method: 'DELETE' });
            showToast('Application removed');
          }
        }
        // Reload with the current active status filter
        const activeTab = document.querySelector('#appStatusTabs .status-tab.active');
        const currentFilter = activeTab ? activeTab.dataset.status : '';
        loadApplications(currentFilter);
      });
    });
  } catch (e) {
    list.innerHTML = `<div class="empty-state"><h3>Error</h3><p>${e.message}</p></div>`;
  }
}

/* ── CV Tab ── */
function initCVTab() {
  document.getElementById('saveCvBtn').addEventListener('click', saveCV);
  document.getElementById('analyzeBtn').addEventListener('click', analyzeCV);
  document.getElementById('skillGapBtn').addEventListener('click', skillGapAnalysis);
  document.getElementById('matchAllBtn').addEventListener('click', matchAllJobs);
  initFileUpload();
}

function initFileUpload() {
  const dropZone = document.getElementById('cvDropZone');
  const fileInput = document.getElementById('cvFileInput');
  const progress = document.getElementById('cvUploadProgress');
  const prompt = dropZone.querySelector('.file-upload-prompt');

  // Click to browse
  dropZone.addEventListener('click', () => fileInput.click());
  prompt.querySelector('strong')?.addEventListener('click', (e) => {
    e.stopPropagation();
    fileInput.click();
  });

  // File selected via browse
  fileInput.addEventListener('change', () => {
    if (fileInput.files.length) handleFileUpload(fileInput.files[0]);
  });

  // Drag and drop
  dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('dragover');
  });
  dropZone.addEventListener('dragleave', () => {
    dropZone.classList.remove('dragover');
  });
  dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
    const file = e.dataTransfer.files[0];
    if (file) handleFileUpload(file);
  });
}

async function handleFileUpload(file) {
  const prompt = document.querySelector('#cvDropZone .file-upload-prompt');
  const progress = document.getElementById('cvUploadProgress');

  // Validate size (10MB)
  if (file.size > 10 * 1024 * 1024) {
    showToast('File too large — max 10MB', true);
    return;
  }

  // Show progress
  prompt.style.display = 'none';
  progress.style.display = 'flex';

  try {
    const formData = new FormData();
    formData.append('file', file);

    const r = await fetch(`${API}/cv/upload-file`, {
      method: 'POST',
      body: formData,
    });

    if (!r.ok) {
      const err = await r.json();
      throw new Error(err.detail || 'Upload failed');
    }

    const data = await r.json();
    // Fetch the full CV text and populate the textarea for review/editing
    const cvResp = await fetch(`${API}/cv`);
    if (cvResp.ok) {
      const cvData = await cvResp.json();
      document.getElementById('cvText').value = cvData.full_text || '';
    }
    showToast(`CV loaded — ${data.text_length.toLocaleString()} chars extracted from ${file.name}`);

    // Auto-analyze after successful upload
    setTimeout(() => analyzeCV(), 500);
  } catch (e) {
    showToast(e.message, true);
    prompt.style.display = '';
    progress.style.display = 'none';
  }
}

async function loadCV() {
  try {
    const r = await fetch(`${API}/cv`);
    if (r.ok) {
      const cv = await r.json();
      document.getElementById('cvText').value = cv.full_text || '';
      // CV exists — enable step 2
      document.getElementById('analyzeBtn').disabled = false;
      document.getElementById('flowStep2').classList.add('flow-step-ready');
      if (cv.parsed_sections) {
        renderCVAnalysis(cv);
        // Analysis exists — enable steps 3 and 4
        document.getElementById('matchAllBtn').disabled = false;
        document.getElementById('skillGapBtn').disabled = false;
        document.getElementById('flowStep3').classList.add('flow-step-ready');
        document.getElementById('flowStep4').classList.add('flow-step-ready');
      }
    }
  } catch (e) {
    // CV not uploaded yet — silently ignore
  }
}

async function saveCV() {
  const text = document.getElementById('cvText').value.trim();
  if (!text) { showToast('Please paste your CV first', true); return; }
  try {
    await fetch(`${API}/cv/upload`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({full_text: text})
    });
    showToast('CV saved');
    // Enable step 2
    document.getElementById('analyzeBtn').disabled = false;
    document.getElementById('flowStep2').classList.add('flow-step-ready');
  } catch (e) {
    showToast('Failed to save CV', true);
  }
}

async function analyzeCV() {
  const panel = document.getElementById('cvAnalysis');
  panel.innerHTML = '<div class="loading"><div class="spinner"></div>Analyzing CV with AI...</div>';

  try {
    // Save first
    const text = document.getElementById('cvText').value.trim();
    if (text) await saveCV();

    const r = await fetch(`${API}/cv/analyze`, {method:'POST'});
    if (!r.ok) throw new Error((await r.json()).detail || 'Analysis failed');
    const data = await r.json();
    renderCVAnalysis(data);
    showToast('CV analysis complete');
    // Enable steps 3 and 4
    document.getElementById('matchAllBtn').disabled = false;
    document.getElementById('skillGapBtn').disabled = false;
    document.getElementById('flowStep3').classList.add('flow-step-ready');
    document.getElementById('flowStep4').classList.add('flow-step-ready');
  } catch (e) {
    panel.innerHTML = `<div class="empty-state"><h3>Analysis Failed</h3><p>${e.message}</p></div>`;
  }
}

function renderCVAnalysis(data) {
  const panel = document.getElementById('cvAnalysis');
  let html = '<h3>CV Analysis</h3>';

  if (data.key_skills) {
    const skills = tryParseJSON(data.key_skills);
    html += `<h4>Key Skills</h4><div class="skill-tags">${(Array.isArray(skills)?skills:[]).map(s=>`<span class="skill-tag">${escapeHtml(typeof s==='string'?s:JSON.stringify(s))}</span>`).join('')}</div>`;
  }
  if (data.education) {
    const edu = tryParseJSON(data.education);
    html += '<h4>Education</h4><ul>';
    (Array.isArray(edu) ? edu : []).forEach(e => {
      const deg = typeof e === 'object' ? `${e.degree || ''} — ${e.institution || ''} (${e.year || ''})` : String(e);
      html += `<li>${escapeHtml(deg)}</li>`;
    });
    html += '</ul>';
  }
  if (data.experience_summary) html += `<h4>Experience Summary</h4><p>${escapeHtml(data.experience_summary)}</p>`;
  if (data.years_of_experience != null) html += `<h4>Years of Experience</h4><p>${data.years_of_experience} years (including internships)</p>`;
  if (data.languages) {
    const langs = tryParseJSON(data.languages);
    html += `<h4>Languages</h4><div class="skill-tags">${(Array.isArray(langs)?langs:[]).map(l=>`<span class="skill-tag">${escapeHtml(typeof l==='string'?l:JSON.stringify(l))}</span>`).join('')}</div>`;
  }
  if (data.certifications) {
    const certs = tryParseJSON(data.certifications);
    html += '<h4>Certifications</h4><ul>';
    (Array.isArray(certs)?certs:[]).forEach(c => html += `<li>${escapeHtml(typeof c==='string'?c:JSON.stringify(c))}</li>`);
    html += '</ul>';
  }
  if (data.hkis_eligible != null) {
    html += `<h4>HKIS Eligibility</h4><p style="color:${data.hkis_eligible?'var(--color-success)':'var(--color-destructive)'};font-weight:600">${data.hkis_eligible ? 'Degree appears HKIS-recognized' : 'Degree may not be HKIS-recognized — verify'}</p>`;
  }

  panel.innerHTML = html;
  panel.style.display = 'block';
}

async function skillGapAnalysis() {
  const panel = document.getElementById('skillGapResults');
  panel.style.display = 'block';
  panel.innerHTML = '<div class="loading"><div class="spinner"></div>Analyzing skill gaps across all jobs...</div>';

  try {
    const r = await fetch(`${API}/cv/skill-gaps`, {method:'POST'});
    if (!r.ok) throw new Error((await r.json()).detail || 'Skill gap analysis failed');
    const data = await r.json();
    renderSkillGaps(data);
  } catch (e) {
    panel.innerHTML = `<div class="empty-state"><h3>Analysis Failed</h3><p>${e.message}</p></div>`;
  }
}

function renderSkillGaps(data) {
  const panel = document.getElementById('skillGapResults');
  let html = '<h3>Skill Gap Analysis</h3>';

  if (data.overall_assessment) {
    html += `<p class="gap-assessment">${escapeHtml(data.overall_assessment)}</p>`;
  }

  if (data.missing_skills) {
    const skills = tryParseJSON(data.missing_skills);
    html += '<h4>Missing Skills (across all jobs)</h4>';
    if (Array.isArray(skills)) {
      skills.forEach(s => {
        const skillObj = typeof s === 'string' ? { skill: s } : s;
        const name = skillObj.skill || skillObj.name || '';
        const priority = skillObj.priority || '';
        const count = skillObj.jobs_requiring || skillObj.count || 0;
        const commonIn = skillObj.common_in || '';
        const priorityClass = priority === 'high' ? 'priority-high' : priority === 'medium' ? 'priority-medium' : '';
        html += `<div class="gap-item">
          <div class="gap-header">
            <span class="gap-name">${escapeHtml(name)}</span>
            ${priority ? `<span class="gap-priority ${priorityClass}">${priority}</span>` : ''}
          </div>
          <div class="gap-meta">
            ${count ? `<span>${count} jobs require this</span>` : ''}
            ${commonIn ? `<span>· ${escapeHtml(commonIn)}</span>` : ''}
          </div>
        </div>`;
      });
    }
  }

  if (data.recommended_courses) {
    const courses = tryParseJSON(data.recommended_courses);
    html += '<h4>Recommended Courses / Certifications</h4>';
    (Array.isArray(courses) ? courses : []).forEach(c => {
      const course = typeof c === 'string' ? { name: c } : c;
      html += `<div class="course-item">
        <div class="course-name">${escapeHtml(course.name || '')}</div>
        <div class="course-provider">${escapeHtml(course.provider || '')}</div>
        <div class="course-why">${escapeHtml(course.why || '')}</div>
        ${course.estimated_cost_hkd ? `<div class="course-cost">~HK$${Number(course.estimated_cost_hkd).toLocaleString()}</div>` : ''}
      </div>`;
    });
  }

  panel.innerHTML = html;
  panel.style.display = 'block';
}

/* ── Match All Jobs ── */
async function matchAllJobs() {
  const btn = document.getElementById('matchAllBtn');
  const progressDiv = document.getElementById('matchProgress');
  const fill = document.getElementById('matchProgressFill');
  const text = document.getElementById('matchProgressText');

  btn.disabled = true;
  btn.textContent = 'Matching...';
  progressDiv.style.display = 'block';
  fill.style.width = '0%';
  text.textContent = 'Starting...';

  // Poll for progress since the endpoint runs synchronously
  const pollInterval = setInterval(() => {
    const w = parseFloat(fill.style.width) || 0;
    if (w < 90) {
      fill.style.width = Math.min(w + 2, 90) + '%';
      text.textContent = `Matching jobs... ${Math.round(w)}%`;
    }
  }, 800);

  try {
    const r = await fetch(`${API}/cv/match-all`, { method: 'POST' });
    clearInterval(pollInterval);

    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      throw new Error(err.detail || 'Match failed');
    }

    const data = await r.json();
    fill.style.width = '100%';
    text.textContent = data.message;

    // Show top results
    if (data.results && data.results.length) {
      const top5 = data.results
        .sort((a, b) => (b.match_score || 0) - (a.match_score || 0))
        .slice(0, 5);

      let summary = `<div style="margin-top:12px;font-size:.82rem;color:var(--color-text)">`;
      summary += `<strong>Top matches:</strong><br>`;
      top5.forEach(j => {
        summary += `${j.match_score}% — ${escapeHtml(j.title)} @ ${escapeHtml(j.company)}<br>`;
      });
      if (data.results.length > 5) {
        summary += `<span style="color:var(--color-text2)">...and ${data.results.length - 5} more</span><br>`;
      }
      summary += `</div>`;
      text.insertAdjacentHTML('afterend', summary);
    }

    if (data.errors && data.errors.length) {
      const errDiv = document.createElement('div');
      errDiv.style.cssText = 'margin-top:8px;font-size:.78rem;color:var(--color-destructive)';
      errDiv.textContent = `${data.errors.length} jobs failed to match`;
      text.parentNode.appendChild(errDiv);
    }

    showToast(`Matched ${data.matched} jobs! Switch to Jobs tab → Match ranking to see sorted results.`);

    // Auto-switch to ranked view after 2s
    setTimeout(() => {
      document.querySelector('.sort-btn[data-sort="match"]')?.click();
      switchTab('jobs');
    }, 2000);

  } catch (e) {
    clearInterval(pollInterval);
    fill.style.width = '0%';
    text.textContent = 'Failed';
    showToast(e.message, true);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Match All Jobs';
    // Hide progress after 5s
    setTimeout(() => { progressDiv.style.display = 'none'; }, 5000);
  }
}

/* ── Analytics ── */
async function loadAnalytics() {
  if (currentTab !== 'analytics') return;
  const el = document.getElementById('analyticsContent');
  el.innerHTML = '<div class="loading"><div class="spinner"></div>Loading analytics...</div>';

  try {
    const r = await fetch(`${API}/analytics`);
    const d = await r.json();
    el.innerHTML = `
      <div class="stat-card">
        <h3>Total Jobs</h3>
        <div class="stat-value">${d.total_jobs}</div>
        <div class="stat-sub">all levels</div>
      </div>
      <div class="stat-card">
        <h3>Response Rate</h3>
        <div class="stat-value">${d.response_rate}%</div>
        <div class="stat-sub">applied → interview+</div>
      </div>
      <div class="stat-card">
        <h3>Avg Match Score</h3>
        <div class="stat-value">${d.avg_match_score}%</div>
        <div class="stat-sub">across matched jobs</div>
      </div>
      <div class="stat-card">
        <h3>By Discipline</h3>
        ${(() => {
          const vals = Object.values(d.by_discipline || {});
          const maxVal = vals.length ? Math.max(...vals) : 0;
          return Object.entries(d.by_discipline || {}).map(([k,v])=>{
            const pct = maxVal > 0 ? Math.max(v / maxVal * 100, 2) : 0;
            return `<div class="bar-row"><span class="bar-label">${disciplineLabel(k)}</span><div class="bar-track"><div class="bar-fill" style="width:${pct}%"></div></div><span class="bar-value">${v}</span></div>`;
          }).join('');
        })()}
      </div>
      <div class="stat-card">
        <h3>Application Status</h3>
        ${(() => {
          const vals = Object.values(d.by_status || {});
          const maxVal = vals.length ? Math.max(...vals) : 0;
          return Object.entries(d.by_status || {}).map(([k,v])=>{
            const pct = maxVal > 0 ? Math.max(v / maxVal * 100, 2) : 0;
            return `<div class="bar-row"><span class="bar-label">${k}</span><div class="bar-track"><div class="bar-fill" style="width:${pct}%;background:${statusColor(k)}"></div></div><span class="bar-value">${v}</span></div>`;
          }).join('');
        })()}
      </div>
      ${(d.by_discipline && Object.keys(d.by_discipline).length === 0) ? '<div class="empty-state"><p>No jobs matched</p></div>' : ''}
      ${d.salary_benchmarks && d.salary_benchmarks.length ? `
      <div class="stat-card" style="grid-column:span 2">
        <h3>Salary Benchmarks (HKD/month)</h3>
        <div class="table-scroll">
        <table>
          <thead><tr><td>Discipline / Level</td><td>P25</td><td>P50</td><td>P75</td></tr></thead>
          ${d.salary_benchmarks.map(s => `<tr><td>${disciplineLabel(s.discipline)} · ${s.experience_level}</td><td>${s.percentile_25?.toLocaleString()}</td><td>${s.percentile_50?.toLocaleString()}</td><td>${s.percentile_75?.toLocaleString()}</td></tr>`).join('')}
        </table>
        </div>
      </div>` : ''}
      ${d.recent_activity && d.recent_activity.length ? `
      <div class="stat-card" style="grid-column:span 2">
        <h3>Recent Activity</h3>
        ${d.recent_activity.map(a => `<div class="activity-item"><div class="activity-detail"><span style="color:${statusColor(a.status)};font-weight:500">${a.status}</span> — ${escapeHtml(a.title)} @ ${escapeHtml(a.company)}</div><div class="activity-time">${a.updated_at?.slice(0,10)}</div></div>`).join('')}
      </div>` : ''}
    `;
  } catch (e) {
    el.innerHTML = `<div class="empty-state"><h3>Error</h3><p>${e.message}</p></div>`;
  }
}

/* ── Pipeline (Kanban) ── */
const PIPELINE_STAGES = ['saved', 'applied', 'phone_screen', 'interview', 'assessment', 'offer', 'accepted', 'rejected', 'withdrawn'];
const STAGE_LABELS = { saved: 'Saved', applied: 'Applied', phone_screen: 'Phone Screen', interview: 'Interview', assessment: 'Assessment', offer: 'Offer', accepted: 'Accepted', rejected: 'Rejected', withdrawn: 'Withdrawn' };

async function loadPipeline() {
  const board = document.getElementById('kanbanBoard');
  const stats = document.getElementById('pipelineStats');
  board.innerHTML = '<div class="loading">Loading pipeline...</div>';

  try {
    const [pipelineR, statsR] = await Promise.all([
      fetch(`${API}/pipeline`),
      fetch(`${API}/pipeline/stats`)
    ]);
    const pipelineData = await pipelineR.json();
    const statsData = await statsR.json();

    // Render stats
    stats.innerHTML = `
      <div class="pipeline-stat"><div class="ps-value">${statsData.summary?.total_applied || 0}</div><div class="ps-label">Total Applied</div></div>
      <div class="pipeline-stat"><div class="ps-value">${statsData.summary?.interviews_secured || 0}</div><div class="ps-label">Interviews</div></div>
      <div class="pipeline-stat"><div class="ps-value">${statsData.summary?.offers_received || 0}</div><div class="ps-label">Offers</div></div>
      <div class="pipeline-stat"><div class="ps-value">${statsData.summary?.accepted || 0}</div><div class="ps-label">Accepted</div></div>
    `;

    // Render kanban
    const stages = pipelineData.stages || [];
    board.innerHTML = stages.map(s => {
      const items = s.items || [];
      return `<div class="kanban-column">
        <div class="kanban-column-header">
          <span class="kanban-column-title">${STAGE_LABELS[s.stage] || s.stage}</span>
          <span class="kanban-column-count">${s.count || 0}</span>
        </div>
        <div class="kanban-column-body">
          ${items.map(item => `
            <div class="kanban-card" data-app-id="${item.id}">
              <div class="kc-title" onclick="openJobDetail(${item.job_id})">${escapeHtml(item.job_title)}</div>
              <div class="kc-company">${escapeHtml(item.company)}</div>
              <div class="kc-meta">
                <span>${item.days_in_stage != null ? `${item.days_in_stage}d in stage` : 'New'}</span>
                ${item.applied_date ? `<span>${item.applied_date.slice(0,10)}</span>` : ''}
              </div>
              <select class="kanban-stage-select" data-app-id="${item.id}" data-current="${s.stage}">
                ${PIPELINE_STAGES.map(st => `<option value="${st}" ${st === s.stage ? 'selected' : ''}>${STAGE_LABELS[st]}</option>`).join('')}
              </select>
            </div>
          `).join('')}
          ${!items.length ? '<div class="empty-state" style="padding:20px;font-size:.78rem;color:var(--color-text2)">No applications</div>' : ''}
        </div>
      </div>`;
    }).join('');

    // Stage change handlers
    board.querySelectorAll('.kanban-stage-select').forEach(sel => {
      sel.addEventListener('change', async (e) => {
        e.stopPropagation();
        const appId = sel.dataset.appId;
        const newStage = sel.value;
        try {
          await fetch(`${API}/applications/${appId}/pipeline`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ stage: newStage })
          });
          showToast(`Moved to ${STAGE_LABELS[newStage]}`);
          loadPipeline();
        } catch (err) {
          showToast('Failed to move application');
          sel.value = sel.dataset.current;
        }
      });
    });

  } catch (e) {
    board.innerHTML = `<div class="empty-state"><h3>Error</h3><p>${e.message}</p></div>`;
  }
}

/* ── Graduate Schemes ── */
async function loadSchemes() {
  const grid = document.getElementById('schemesGrid');
  const stats = document.getElementById('schemesStats');
  grid.innerHTML = '<div class="loading">Loading schemes...</div>';

  try {
    const [schemesR, statsR] = await Promise.all([
      fetch(`${API}/graduate-schemes`),
      fetch(`${API}/graduate-schemes/stats`)
    ]);
    const schemes = await schemesR.json();
    const statsData = await statsR.json();

    stats.innerHTML = `
      <div class="scheme-stat urgent">${icon('alert-triangle')} Closing Soon: ${statsData.closing_soon || 0}</div>
      <div class="scheme-stat open">Open Now: ${statsData.open_now || 0}</div>
      <div class="scheme-stat upcoming">Upcoming: ${statsData.upcoming || 0}</div>
    `;

    const today = new Date().toISOString().slice(0, 10);
    const in30d = new Date(Date.now() + 30*86400000).toISOString().slice(0, 10);

    // Group by status
    const closingSoon = [];
    const openNow = [];
    const upcoming = [];

    (schemes.schemes || schemes).forEach(s => {
      const close = s.application_close;
      const open = s.application_open;
      if (close && close >= today && close <= in30d) closingSoon.push(s);
      else if (close && close >= today) openNow.push(s);
      else upcoming.push(s);
    });

    const renderSchemeCard = (s, daysLabel) => {
      const closeDate = s.application_close ? new Date(s.application_close) : null;
      const todayDate = new Date();
      const daysLeft = closeDate ? Math.ceil((closeDate - todayDate) / 86400000) : null;
      const period = s.application_open && s.application_close
        ? `${s.application_open.slice(5)} → ${s.application_close.slice(5)}`
        : 'TBC';

      return `<div class="scheme-card" onclick="this.classList.toggle('expanded')">
        <div class="scheme-card-header">
          <div>
            <div class="scheme-card-company">${escapeHtml(s.company_name)}</div>
            <div class="scheme-card-name">${escapeHtml(s.scheme_name)}</div>
          </div>
          ${daysLeft != null ? `<span class="scheme-card-days ${daysLabel}">${daysLeft}d left</span>` : ''}
        </div>
        <div class="scheme-card-period">${icon('calendar')} ${period} · Intake ${escapeHtml(s.intake_year || 'TBC')}</div>
        <div class="scheme-card-badges">
          <span class="scheme-badge">${disciplineLabel(s.discipline)}</span>
          ${s.url ? `<a href="${escapeHtml(s.url)}" target="_blank" class="scheme-badge" style="background:var(--color-primary);color:#fff;text-decoration:none" onclick="event.stopPropagation()">${icon('external')} Apply</a>` : ''}
        </div>
        <div class="scheme-card-details">
          ${s.notes ? `<p>${escapeHtml(s.notes)}</p>` : ''}
          <div class="scheme-card-actions">
            <button class="scheme-applied-toggle ${s._applied ? 'applied' : ''}" onclick="event.stopPropagation(); toggleSchemeApplied(${s.id}, this)">${s._applied ? 'Applied' : 'Mark Applied'}</button>
          </div>
        </div>
      </div>`;
    };

    grid.innerHTML = '';
    if (closingSoon.length) {
      grid.innerHTML += `<div class="scheme-section"><div class="scheme-section-header urgent">${icon('alert-triangle')} Closing Soon</div>${closingSoon.map(s => renderSchemeCard(s, 'urgent')).join('')}</div>`;
    }
    if (openNow.length) {
      grid.innerHTML += `<div class="scheme-section"><div class="scheme-section-header open">${icon('check-circle')} Open Now</div>${openNow.map(s => renderSchemeCard(s, 'open')).join('')}</div>`;
    }
    if (upcoming.length) {
      grid.innerHTML += `<div class="scheme-section"><div class="scheme-section-header upcoming">${icon('clipboard-list')} Upcoming</div>${upcoming.map(s => renderSchemeCard(s, '')).join('')}</div>`;
    }

    if (!closingSoon.length && !openNow.length && !upcoming.length) {
      grid.innerHTML = '<div class="empty-state"><h3>No schemes found</h3></div>';
    }

  } catch (e) {
    grid.innerHTML = `<div class="empty-state"><h3>Error</h3><p>${e.message}</p></div>`;
  }
}

async function toggleSchemeApplied(schemeId, btn) {
  const applied = btn.classList.contains('applied');
  try {
    await fetch(`${API}/graduate-schemes/${schemeId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ applied: !applied })
    });
    btn.classList.toggle('applied');
    btn.textContent = applied ? 'Mark Applied' : 'Applied';
    showToast(applied ? 'Marked as not applied' : 'Marked as applied!');
  } catch (e) {
    showToast('Failed to update');
  }
}

/* ── Helpers ── */
function escapeHtml(s) {
  if (!s) return '';
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function sanitizeDescriptionHtml(html) {
  if (!html) return '';
  // Safe: HTML comes from server-side formatter, not user input.
  // We strip scripts, event handlers, and dangerous tags as defense-in-depth.
  const div = document.createElement('div');
  div.innerHTML = html;
  // Remove any script, style, iframe, object, embed tags
  div.querySelectorAll('script, style, iframe, object, embed, link, meta').forEach(el => el.remove());
  // Remove event handlers and dangerous attributes
  div.querySelectorAll('*').forEach(el => {
    Array.from(el.attributes).forEach(attr => {
      if (attr.name.startsWith('on') || attr.name === 'formaction') {
        el.removeAttribute(attr.name);
      }
    });
  });
  return div.innerHTML;
}

function formatDescription(text) {
  if (!text) return '';
  // Escape HTML first
  let html = escapeHtml(text);
  // Convert double-newlines into paragraph breaks
  html = html.replace(/\n\n+/g, '</p><p>');
  // Convert single newlines to <br>
  html = html.replace(/\n/g, '<br>');
  // Format common bullet characters into styled bullets
  html = html.replace(/(?:<br>|^)([•\-\*])\s+/g, '<br><span class="desc-bullet">$1</span> ');
  // Wrap in a paragraph
  html = '<p>' + html + '</p>';
  // Clean up empty paragraphs
  html = html.replace(/<p><\/p>/g, '');
  html = html.replace(/<p><br><\/p>/g, '');
  // Fix duplicate <br> tags after bullet conversion
  html = html.replace(/<br><br>/g, '<br>');
  return html;
}

function escapeAttr(s) {
  if (!s) return '';
  return String(s).replace(/'/g,"\\'").replace(/"/g,'&quot;');
}

function tryParseJSON(v) {
  if (!v) return v;
  if (Array.isArray(v)) return v;
  if (typeof v === 'object') return v;
  try { return JSON.parse(v); } catch (e) { return v; }
}
