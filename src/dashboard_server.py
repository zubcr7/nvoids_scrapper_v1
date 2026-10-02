"""Lightweight Built-In Web Dashboard Server.

Provides a responsive real-time web interface displaying:
- Number of jobs applied today vs yesterday vs all-time
- Direct recruiter phone numbers with click-to-call action buttons
- Prominently displayed job locations (e.g. Philadelphia, PA, Remote)
- Gmail Quota & Throttling Safety Monitor (60/day safe limit, 10/hr cadence)
- Real-time instant updates every 2.5 seconds with live sync indicator
- Search and filtering (by Date, Status, Recruiter, Role, Phone)
"""
import os
import json
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Dict, Any

from src.tracker import ApplicationTracker

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Nvoids Bot Live Dashboard - Java & Full Stack C2C</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    body { font-family: 'Inter', sans-serif; }
    .btn-call {
      transition: all 0.2s ease-in-out;
    }
    .btn-call:hover {
      transform: translateY(-1px);
      box-shadow: 0 4px 12px rgba(16, 185, 129, 0.25);
    }
  </style>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen">

  <!-- Header Navbar -->
  <nav class="bg-slate-900 border-b border-slate-800 sticky top-0 z-30 shadow-md">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3.5 flex items-center justify-between">
      <div class="flex items-center space-x-3.5">
        <div class="w-10 h-10 rounded-xl bg-indigo-600 flex items-center justify-center text-white text-lg shadow-lg shadow-indigo-500/20">
          <i class="fa-solid fa-robot"></i>
        </div>
        <div>
          <div class="flex items-center space-x-2">
            <h1 class="text-base font-bold text-white tracking-tight leading-tight">Nvoids C2C Application Dashboard</h1>
            <span class="px-2 py-0.5 rounded-full text-[10px] font-bold bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">NITHIN CHIGURU</span>
          </div>
          <p class="text-xs text-slate-400">Targeting Java & Full Stack C2C Roles • Calibrated Cutoffs: ≥ 85.0%</p>
        </div>
      </div>
      <div class="flex items-center space-x-3.5">
        <!-- Live Sync Status Indicator -->
        <div class="flex items-center space-x-2 bg-slate-800/90 px-3 py-1.5 rounded-full border border-slate-700/80 text-xs text-slate-300 shadow-inner">
          <span class="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse" id="live-pulse"></span>
          <span id="live-sync-text" class="font-medium">Live Sync (2.5s)</span>
        </div>
        <button onclick="fetchData()" class="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-xs font-semibold flex items-center space-x-1.5 shadow-sm transition">
          <i class="fa-solid fa-rotate text-xs" id="refresh-icon"></i>
          <span>Refresh</span>
        </button>
      </div>
    </div>
  </nav>

  <!-- Main Container -->
  <main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-7 space-y-6">

    <!-- KPI Metric Cards Grid -->
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      
      <!-- Card 1: Applied Today -->
      <div class="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-sm hover:border-slate-700 transition">
        <div class="flex justify-between items-start">
          <div>
            <p class="text-xs font-bold uppercase tracking-wider text-emerald-400">Applied Today</p>
            <h2 id="metric-applied-today" class="text-3xl font-black text-white mt-1">0</h2>
            <p id="metric-applied-today-sub" class="text-xs text-slate-400 mt-1">Date: --</p>
          </div>
          <div class="w-11 h-11 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400 text-lg">
            <i class="fa-solid fa-paper-plane"></i>
          </div>
        </div>
        <div class="mt-4 pt-3 border-t border-slate-800 flex items-center justify-between text-xs text-slate-400">
          <span>Yesterday: <strong id="metric-applied-yesterday" class="text-slate-200">0</strong></span>
          <span class="text-emerald-400 font-semibold">Priority Queue</span>
        </div>
      </div>

      <!-- Card 2: Recruiters Ready for Call -->
      <div class="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-sm hover:border-slate-700 transition">
        <div class="flex justify-between items-start">
          <div>
            <p class="text-xs font-bold uppercase tracking-wider text-teal-400">Ready to Call 📞</p>
            <h2 id="metric-call-ready" class="text-3xl font-black text-white mt-1">0</h2>
            <p class="text-xs text-slate-400 mt-1">Direct Phone Available</p>
          </div>
          <div class="w-11 h-11 rounded-xl bg-teal-500/10 border border-teal-500/20 flex items-center justify-center text-teal-400 text-lg">
            <i class="fa-solid fa-phone-volume"></i>
          </div>
        </div>
        <div class="mt-4 pt-3 border-t border-slate-800 flex items-center justify-between text-xs text-slate-400">
          <span>Action:</span>
          <span class="text-teal-300 font-semibold">5x Higher Callback</span>
        </div>
      </div>

      <!-- Card 3: Gmail Protection Guard -->
      <div class="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-sm hover:border-slate-700 transition">
        <div class="flex justify-between items-start">
          <div>
            <p class="text-xs font-bold uppercase tracking-wider text-blue-400">Gmail Safe Guard</p>
            <div class="flex items-baseline space-x-2 mt-1">
              <h2 id="metric-gmail-sent" class="text-3xl font-black text-white">0</h2>
              <span id="metric-gmail-cap" class="text-sm font-semibold text-slate-400">/ 60 cap</span>
            </div>
            <p id="metric-gmail-hourly" class="text-xs text-slate-400 mt-1">Hourly: 0 / 10 limit</p>
          </div>
          <div class="w-11 h-11 rounded-xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-blue-400 text-lg">
            <i class="fa-solid fa-shield-check"></i>
          </div>
        </div>
        <div class="mt-4 pt-3 border-t border-slate-800 flex items-center justify-between text-xs text-slate-400">
          <span>Sender Status:</span>
          <span class="text-emerald-400 font-semibold">🟢 100% Protected</span>
        </div>
      </div>

      <!-- Card 4: Avg Match Score -->
      <div class="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-sm hover:border-slate-700 transition">
        <div class="flex justify-between items-start">
          <div>
            <p class="text-xs font-bold uppercase tracking-wider text-amber-400">Average Match</p>
            <h2 id="metric-avg-match" class="text-3xl font-black text-white mt-1">--%</h2>
            <p class="text-xs text-slate-400 mt-1">Cutoffs: <strong class="text-amber-300 font-bold">≥ 88% / 93%</strong></p>
          </div>
          <div class="w-11 h-11 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-400 text-lg">
            <i class="fa-solid fa-bullseye"></i>
          </div>
        </div>
        <div class="mt-4 pt-3 border-t border-slate-800 flex items-center justify-between text-xs text-slate-400">
          <span>Skipped &lt; Cutoff: <strong id="metric-skipped-threshold" class="text-amber-400">0</strong></span>
          <span class="text-slate-400">Target: 95%+</span>
        </div>
      </div>

    </div>

    <!-- Pro-Tip Call Strategy Banner -->
    <div class="bg-gradient-to-r from-emerald-950/70 via-slate-900 to-indigo-950/70 border border-emerald-500/30 rounded-2xl p-4 flex flex-col md:flex-row items-start md:items-center justify-between gap-3 shadow-sm">
      <div class="flex items-center space-x-3">
        <div class="w-9 h-9 rounded-lg bg-emerald-500/20 border border-emerald-500/30 flex items-center justify-center text-emerald-400 flex-shrink-0">
          <i class="fa-solid fa-lightbulb"></i>
        </div>
        <div>
          <h4 class="text-xs font-bold text-white uppercase tracking-wider">Recruiter Callback Pro-Tip</h4>
          <p class="text-xs text-slate-300">Nvoids staffing recruiters receive 100+ emails per role. Calling the direct phone number below within 5–15 minutes moves your resume to the top of their client submission list.</p>
        </div>
      </div>
      <div class="flex items-center space-x-2 flex-shrink-0">
        <span class="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-900/60 text-emerald-300 border border-emerald-700/60">
          <i class="fa-solid fa-brain mr-1 text-[10px]"></i> AI ATS Matching (32-Tech Multi-Pillar)
        </span>
        <span class="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold bg-blue-900/60 text-blue-300 border border-blue-700/60">
          <i class="fa-solid fa-signature mr-1 text-[10px]"></i> Dynamic Renaming
        </span>
      </div>
    </div>

    <!-- Main Data Table Container -->
    <div class="bg-slate-900 border border-slate-800 rounded-2xl shadow-sm overflow-hidden">
      
      <!-- Table Header & Controls -->
      <div class="p-5 border-b border-slate-800 flex flex-col lg:flex-row lg:items-center justify-between gap-4">
        <div>
          <h3 class="text-base font-bold text-white flex items-center space-x-2">
            <i class="fa-solid fa-list-check text-indigo-400"></i>
            <span>Live Job Stream & Applications</span>
          </h3>
          <p class="text-xs text-slate-400 mt-0.5">Chronologically ordered (newest & freshest postings processed first)</p>
        </div>

        <div class="flex flex-wrap items-center gap-3">
          <!-- Date Filter -->
          <select id="filter-date" onchange="fetchData()" class="bg-slate-950 border border-slate-700 text-xs text-slate-200 rounded-lg px-3 py-2 focus:ring-1 focus:ring-indigo-500 font-medium">
            <option value="today" selected>📅 Applied Today</option>
            <option value="yesterday">📅 Applied Yesterday</option>
            <option value="all">🌐 All Time</option>
          </select>

          <!-- Status Filter -->
          <select id="filter-status" onchange="fetchData()" class="bg-slate-950 border border-slate-700 text-xs text-slate-200 rounded-lg px-3 py-2 focus:ring-1 focus:ring-indigo-500 font-medium">
            <option value="all" selected>All Statuses</option>
            <option value="applied_all">Applied &amp; Sent Only</option>
            <option value="skipped_threshold">Skipped (&lt; Cutoff: 90%)</option>
            <option value="skipped_not_c2c">Skipped (Not C2C / W2)</option>
            <option value="already_applied">Duplicates Prevented</option>
          </select>

          <!-- Phone Toggle Filter -->
          <button id="btn-phone-filter" onclick="togglePhoneFilter()" class="px-3 py-2 bg-slate-950 hover:bg-slate-800 text-slate-300 border border-slate-700 rounded-lg text-xs font-semibold flex items-center space-x-1.5 transition">
            <i class="fa-solid fa-phone text-emerald-400 text-xs"></i>
            <span id="phone-filter-label">Has Phone Only</span>
          </button>

          <!-- Search Bar -->
          <div class="relative">
            <i class="fa-solid fa-magnifying-glass absolute left-3 top-2.5 text-xs text-slate-500"></i>
            <input type="text" id="search-input" onkeyup="debounceSearch()" placeholder="Search role, location, recruiter, phone..." class="bg-slate-950 border border-slate-700 text-xs text-slate-200 rounded-lg pl-8 pr-3 py-2 w-60 focus:ring-1 focus:ring-indigo-500">
          </div>
        </div>
      </div>

      <!-- Table Content -->
      <div class="overflow-x-auto">
        <table class="w-full text-left text-xs text-slate-300">
          <thead class="bg-slate-950 text-slate-400 uppercase font-bold text-[11px] border-b border-slate-800 tracking-wider">
            <tr>
              <th scope="col" class="px-5 py-3.5">Status</th>
              <th scope="col" class="px-5 py-3.5">Role &amp; Nvoids ID</th>
              <th scope="col" class="px-5 py-3.5">📍 Location</th>
              <th scope="col" class="px-5 py-3.5">📞 Direct Phone (Call Now)</th>
              <th scope="col" class="px-5 py-3.5">Recruiter Contact</th>
              <th scope="col" class="px-5 py-3.5">Attached Resume</th>
              <th scope="col" class="px-5 py-3.5 text-center">Match %</th>
              <th scope="col" class="px-5 py-3.5">Timestamp</th>
            </tr>
          </thead>
          <tbody id="jobs-table-body" class="divide-y divide-slate-800/80">
            <tr>
              <td colspan="8" class="px-5 py-10 text-center text-slate-500">
                <i class="fa-solid fa-spinner fa-spin mr-2 text-indigo-400"></i> Loading live applications...
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Table Footer -->
      <div class="p-4 border-t border-slate-800 bg-slate-950/60 flex items-center justify-between text-xs text-slate-400">
        <span id="table-showing-count">Showing 0 jobs</span>
        <div class="flex items-center space-x-2 text-[11px] text-slate-500">
          <span>Synced with SQLite Database (WAL Mode)</span>
        </div>
      </div>

    </div>

  </main>

  <script>
    let searchTimeout = null;
    let onlyPhoneFilter = false;

    function debounceSearch() {
      clearTimeout(searchTimeout);
      searchTimeout = setTimeout(fetchData, 250);
    }

    function togglePhoneFilter() {
      onlyPhoneFilter = !onlyPhoneFilter;
      const btn = document.getElementById('btn-phone-filter');
      const label = document.getElementById('phone-filter-label');
      if (onlyPhoneFilter) {
        btn.classList.add('bg-emerald-950', 'border-emerald-500', 'text-emerald-300');
        btn.classList.remove('bg-slate-950', 'text-slate-300', 'border-slate-700');
        label.textContent = 'Showing Phone Only ✓';
      } else {
        btn.classList.remove('bg-emerald-950', 'border-emerald-500', 'text-emerald-300');
        btn.classList.add('bg-slate-950', 'text-slate-300', 'border-slate-700');
        label.textContent = 'Has Phone Only';
      }
      fetchData();
    }

    function formatStatusBadge(status) {
      if (status === 'applied') {
        return '<span class="inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-bold bg-emerald-950 text-emerald-300 border border-emerald-700"><i class="fa-solid fa-check mr-1 text-[10px]"></i> Sent</span>';
      } else if (status === 'dry_run') {
        return '<span class="inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-bold bg-blue-950 text-blue-300 border border-blue-700"><i class="fa-solid fa-eye mr-1 text-[10px]"></i> Dry Run</span>';
      } else if (status === 'skipped_threshold') {
        return '<span class="inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-bold bg-amber-950 text-amber-300 border border-amber-700"><i class="fa-solid fa-triangle-exclamation mr-1 text-[10px]"></i> &lt; Threshold</span>';
      } else if (status === 'skipped_not_c2c') {
        return '<span class="inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-bold bg-slate-900 text-slate-400 border border-slate-700"><i class="fa-solid fa-ban mr-1 text-[10px]"></i> Not C2C</span>';
      } else if (status === 'already_applied') {
        return '<span class="inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-bold bg-purple-950 text-purple-300 border border-purple-700"><i class="fa-solid fa-clone mr-1 text-[10px]"></i> Duplicate</span>';
      } else if (status === 'throttled_daily_cap') {
        return '<span class="inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-bold bg-rose-950 text-rose-300 border border-rose-700"><i class="fa-solid fa-shield-halved mr-1 text-[10px]"></i> Daily Cap</span>';
      } else {
        return `<span class="inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-bold bg-slate-900 text-slate-400 border border-slate-700">${status}</span>`;
      }
    }

    function formatScoreBadge(score) {
      if (!score || score === 0) return '<span class="text-slate-600">--</span>';
      let colorClass = 'text-slate-300';
      if (score >= 85.0) {
        colorClass = 'text-emerald-400 font-black';
      } else if (score >= 80.0) {
        colorClass = 'text-blue-400 font-bold';
      } else {
        colorClass = 'text-amber-400 font-semibold';
      }
      return `<span class="${colorClass}">${score.toFixed(1)}%</span>`;
    }

    async function fetchData() {
      const refreshIcon = document.getElementById('refresh-icon');
      if (refreshIcon) refreshIcon.classList.add('fa-spin');

      try {
        // 1. Fetch Stats
        const statsRes = await fetch('/api/stats');
        if (statsRes.ok) {
          const stats = await statsRes.json();
          renderStats(stats);
        }

        // 2. Fetch Jobs List
        const dateFilter = document.getElementById('filter-date').value;
        const statusFilter = document.getElementById('filter-status').value;
        const searchQuery = document.getElementById('search-input').value;

        const params = new URLSearchParams({
          date: dateFilter,
          status: statusFilter,
          q: searchQuery,
          has_phone: onlyPhoneFilter ? "1" : "0"
        });

        const jobsRes = await fetch('/api/jobs?' + params.toString());
        if (jobsRes.ok) {
          const jobs = await jobsRes.json();
          renderJobsTable(jobs);
        }
      } catch (err) {
        console.error('Error updating dashboard:', err);
      } finally {
        if (refreshIcon) refreshIcon.classList.remove('fa-spin');
      }
    }

    function renderStats(stats) {
      document.getElementById('metric-applied-today').textContent = stats.applied_today || 0;
      document.getElementById('metric-applied-today-sub').textContent = 'Date: ' + (stats.date_today || '--');
      document.getElementById('metric-applied-yesterday').textContent = stats.applied_yesterday || 0;
      
      document.getElementById('metric-call-ready').textContent = stats.call_ready_count || 0;
      
      const realToday = stats.real_applied_today || 0;
      const dailyCap = stats.daily_safe_cap || 80;
      document.getElementById('metric-gmail-sent').textContent = realToday;
      document.getElementById('metric-gmail-cap').textContent = `/ ${dailyCap} cap`;
      document.getElementById('metric-gmail-hourly').textContent = `Hourly: ${stats.sent_last_hour || 0} / ${stats.hourly_limit || 10} limit`;

      document.getElementById('metric-avg-match').textContent = stats.avg_match_percentage ? stats.avg_match_percentage + '%' : '--%';
      document.getElementById('metric-skipped-threshold').textContent = stats.status_counts?.skipped_threshold || 0;
    }

    function renderJobsTable(jobs) {
      const tbody = document.getElementById('jobs-table-body');
      const countSpan = document.getElementById('table-showing-count');

      if (!jobs || jobs.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" class="px-5 py-10 text-center text-slate-500">No jobs match current filter criteria.</td></tr>';
        countSpan.textContent = 'Showing 0 jobs';
        return;
      }

      countSpan.textContent = `Showing ${jobs.length} jobs`;
      let rows = '';

      jobs.forEach(job => {
        const dateStr = job.applied_at ? job.applied_at.replace('T', ' ').substring(0, 16) : '--';
        const resumeName = job.resume_file || '--';
        const recruiter = job.recruiter_name || 'Hiring Team';
        const email = job.vendor_email || '<span class="text-slate-600">None</span>';
        const location = job.location || 'USA';
        const phone = job.recruiter_phone;

        let phoneHtml = '';
        if (phone && phone.trim()) {
          phoneHtml = `
            <a href="tel:${phone}" class="btn-call inline-flex items-center px-2.5 py-1 rounded-lg text-xs font-bold bg-emerald-500/15 text-emerald-300 hover:bg-emerald-500/25 border border-emerald-500/30">
              <i class="fa-solid fa-phone mr-1.5 text-[10px]"></i>
              <span>${phone}</span>
            </a>
          `;
        } else {
          phoneHtml = '<span class="text-slate-500 text-[11px] font-mono">Email only</span>';
        }

        rows += `
          <tr class="hover:bg-slate-800/40 transition">
            <td class="px-5 py-3 whitespace-nowrap">${formatStatusBadge(job.status)}</td>
            <td class="px-5 py-3 max-w-xs">
              <div class="font-bold text-white truncate" title="${job.job_title}">${job.job_title}</div>
              <a href="${job.job_url}" target="_blank" class="text-[11px] text-indigo-400 hover:text-indigo-300 hover:underline inline-flex items-center space-x-1 mt-0.5">
                <span>Job #${job.job_id} on Nvoids</span>
                <i class="fa-solid fa-arrow-up-right-from-square text-[9px]"></i>
              </a>
            </td>
            <td class="px-5 py-3 whitespace-nowrap">
              <span class="inline-flex items-center px-2 py-0.5 rounded-md text-xs bg-slate-800 text-slate-200 border border-slate-700">
                <i class="fa-solid fa-location-dot text-rose-400 mr-1.5 text-[10px]"></i>
                <span class="font-medium">${location}</span>
              </span>
            </td>
            <td class="px-5 py-3 whitespace-nowrap">
              ${phoneHtml}
            </td>
            <td class="px-5 py-3 whitespace-nowrap">
              <div class="font-medium text-slate-200">${recruiter}</div>
              <div class="text-[11px] text-slate-400">${email}</div>
            </td>
            <td class="px-5 py-3 whitespace-nowrap">
              <span class="text-slate-300 font-mono text-[11px] bg-slate-800/80 px-2 py-1 rounded border border-slate-700/60">${resumeName}</span>
            </td>
            <td class="px-5 py-3 whitespace-nowrap text-center">
              ${formatScoreBadge(job.match_percentage)}
            </td>
            <td class="px-5 py-3 whitespace-nowrap text-slate-400 text-[11px] font-mono">
              ${dateStr}
            </td>
          </tr>
        `;
      });

      tbody.innerHTML = rows;
    }

    // Auto-refresh every 2.5 seconds for instant updates
    setInterval(fetchData, 2500);
    // Initial fetch
    fetchData();
  </script>
</body>
</html>
"""

class DashboardRequestHandler(BaseHTTPRequestHandler):
    tracker: ApplicationTracker = None

    def log_message(self, format, *args):
        # Silence standard HTTP access logging to keep terminal clean
        return

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        params = urllib.parse.parse_qs(parsed.query)

        if path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(DASHBOARD_HTML.encode("utf-8"))

        elif path == "/api/stats":
            metrics = self.tracker.get_dashboard_metrics()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(metrics).encode("utf-8"))

        elif path == "/api/jobs":
            date_filter = params.get("date", ["today"])[0]
            status_filter = params.get("status", ["all"])[0]
            search_query = params.get("q", [""])[0]
            has_phone = params.get("has_phone", ["0"])[0] == "1"

            jobs = self.tracker.get_jobs_list(
                date_filter=date_filter,
                status_filter=status_filter,
                search_query=search_query,
                has_phone=has_phone,
                limit=150
            )
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(jobs).encode("utf-8"))

        else:
            self.send_response(404)
            self.end_headers()

def run_dashboard_server(db_path: str = "data/applied_jobs.db", port: int = 8080):
    """Start local web dashboard server."""
    tracker = ApplicationTracker(db_path)
    DashboardRequestHandler.tracker = tracker

    server_address = ("127.0.0.1", port)
    try:
        httpd = HTTPServer(server_address, DashboardRequestHandler)
        print("=" * 70)
        print("   🌐 NVOIDS BOT LIVE WEB DASHBOARD")
        print("=" * 70)
        print(f"  Dashboard running at: http://127.0.0.1:{port}")
        print(f"  Database connected:   {db_path}")
        print("  Features:")
        print("    - Instant live updates (every 2.5 seconds)")
        print("    - Direct recruiter phone click-to-call action")
        print("    - Prominent job location display (e.g. Philadelphia, PA)")
        print("    - Gmail Quota & Throttling Safety Monitor (60/day cap)")
        print("  Press Ctrl+C to stop the dashboard server.")
        print("=" * 70 + "\n")
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[Dashboard] Server stopped.")
    except Exception as e:
        print(f"[Dashboard] Error: {e}")
