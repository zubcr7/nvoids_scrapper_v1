"""Central Bot Orchestrator for Nvoids Job Application.

Coordinates scraping, date filtering (today, yesterday, day before yesterday),
resume matching with strict threshold (>= 93%), duplicate tracking,
and continuous monitoring until manually stopped.
"""
import os
import sys
import time
import signal
import datetime
import re
from collections import deque
from typing import Dict, Any, Optional, Set, List, Tuple

from src.scraper import NvoidsScraper
from src.matcher import ResumeMatcher
from src.mailer import EmailSender
from src.tracker import ApplicationTracker

class JobApplicationBot:
    def __init__(
        self,
        config: Dict[str, Any],
        dry_run: Optional[bool] = None,
        min_match: Optional[float] = None
    ):
        self.config = config
        self.search_cfg = config.get("search", {})
        self.match_cfg = config.get("matching", {})
        self.monitor_cfg = config.get("monitoring", {})
        self.smtp_cfg = config.get("smtp", {})

        # Overrides from CLI or environment
        if dry_run is not None:
            self.dry_run = dry_run
        else:
            self.dry_run = config.get("mailer", {}).get("dry_run", True)

        self.min_match_percentage = min_match if min_match is not None else self.match_cfg.get("min_match_percentage", 85.0)
        self.days_back = self.search_cfg.get("days_back", 2)
        self.full_stack_only = self.search_cfg.get("full_stack_only", True)
        self.batch_delay = self.monitor_cfg.get("interval_seconds", 30)
        self.check_interval = self.batch_delay
        self.live_poll_interval = 15.0
        self._last_live_poll_time = 0.0
        self._seen_job_ids: Set[str] = set()
        self._max_seen_job_id: int = 0

        # Initialize components
        daily_cap = config.get("throttling", {}).get("daily_safe_cap", 80)
        cooldown_days = config.get("throttling", {}).get("recruiter_cooldown_days", 14)

        self.scraper = NvoidsScraper()
        self.matcher = ResumeMatcher(
            resumes_dir=self.match_cfg.get("resumes_dir", "resumes"),
            min_match_percentage=self.min_match_percentage,
            short_jd_match_percentage=self.match_cfg.get("short_jd_match_percentage", 85.0),
            short_jd_word_limit=self.match_cfg.get("short_jd_word_limit", 120)
        )
        self.mailer = EmailSender(config, self.smtp_cfg, dry_run=self.dry_run)
        self.tracker = ApplicationTracker(
            config.get("database", {}).get("path", "data/applied_jobs.db"),
            daily_safe_cap=daily_cap,
            cooldown_days=cooldown_days
        )

        # Session lock to guarantee that if a recruiter reposts the same job multiple times
        # at the same time or same day, only ONE email is sent
        self._session_applied_job_signatures: Set[str] = set()
        self._preload_session_history()

        self._running = True
        self._setup_signal_handlers()

    def _job_recency_priority_key(self, job_dict: Dict[str, Any]) -> Tuple[int, int]:
        """Sort key for job prioritization:
        1. Java preference tier:
           Tier 2: Java Full Stack (both Java and Full Stack/Frontend keywords)
           Tier 1: Java Developer (Java/J2EE/Spring keywords) or generic Full Stack
           Tier 0: Generic software engineering roles
           Tier -1: Explicitly excluded niche platforms (Camunda, Guidewire, etc.) or non-dev/non-Java roles
        2. Recency: higher Job ID = more recently posted.
        When sorted with reverse=True, the newest Java postings are strictly prioritized first.
        """
        title = (job_dict.get("title") or "").strip()
        title_lower = title.lower()

        try:
            jid = int(job_dict.get("job_id", 0))
        except Exception:
            jid = 0

        # Check for excluded niche platforms (Camunda, Guidewire, MuleSoft, Salesforce, etc.)
        for p in NvoidsScraper.EXCLUDED_NICHE_PLATFORM_PATTERNS:
            if p.search(title_lower):
                return (-1, jid)

        # Check for non-Java or non-dev roles (Python, C#, QA, PM, etc.)
        for p in NvoidsScraper.NON_JAVA_OR_NON_DEV_PATTERNS:
            if p.search(title_lower):
                return (-1, jid)

        has_java = bool(re.search(r'\b(?:java|j2ee|jvm|spring)\b', title_lower))
        has_fs = any(fs in title_lower for fs in ["full stack", "fullstack", "full-stack", "fsd"]) or any(
            fe in title_lower for fe in ["react", "angular", "vue", "frontend", "front-end", "ui"]
        )

        if has_java and has_fs:
            tier = 2
        elif has_java or has_fs:
            tier = 1
        else:
            tier = 0

        return (tier, jid)

    def _poll_live_stream_for_new_jobs(self, force: bool = False, max_pages: int = 1) -> List[Dict[str, str]]:
        """Poll Nvoids live stream (index.jsp) for brand new jobs posted since execution started.

        If newly posted jobs are detected:
        1. Logs real-time detection alert.
        2. Preemptively prioritizes them at the front of the queue by Java preference and recency
           so they are applied to immediately.
        """
        now = time.time()
        if not force and (now - self._last_live_poll_time < self.live_poll_interval):
            return []
        self._last_live_poll_time = now

        try:
            live_jobs = self.scraper.get_latest_stream_jobs(max_pages=max_pages)
            brand_new_jobs = []
            for j in live_jobs:
                jid = str(j.get("job_id", "")).strip()
                if not jid:
                    continue
                try:
                    jid_int = int(jid)
                except ValueError:
                    jid_int = 0

                if jid not in self._seen_job_ids:
                    self._seen_job_ids.add(jid)
                    if not self.tracker.is_job_applied(jid, is_dry_run=self.dry_run):
                        brand_new_jobs.append(j)

                if jid_int > self._max_seen_job_id:
                    self._max_seen_job_id = jid_int

            if brand_new_jobs:
                brand_new_jobs.sort(key=self._job_recency_priority_key, reverse=True)
                print("\n" + "⚡" * 38)
                print(f"  ⚡ [REAL-TIME LIVE POSTING] Recruiter posted {len(brand_new_jobs)} NEW job(s) during execution!")
                for bj in brand_new_jobs[:5]:
                    btitle = bj.get("title") or "New Posting"
                    print(f"     -> Job #{bj['job_id']}: {btitle[:65]}")
                if len(brand_new_jobs) > 5:
                    print(f"     ... and {len(brand_new_jobs) - 5} more newly posted jobs")
                print(f"  ⚡ [PREEMPTION] Prioritized at FRONT of queue (Java + Recency) - evaluating immediately!")
                print("⚡" * 38 + "\n")
            return brand_new_jobs
        except Exception:
            return []

    def _preload_session_history(self):
        """Preload today's applied job signatures for each recruiter to prevent duplicate reposts."""
        try:
            with self.tracker._get_connection() as conn:
                cursor = conn.cursor()
                status_filter = "status = 'applied'" if not self.dry_run else "status IN ('applied', 'dry_run')"
                cursor.execute(f"SELECT vendor_email, normalized_title, desc_hash, applied_at FROM applications WHERE {status_filter}")
                today_str = datetime.date.today().isoformat()
                for row in cursor.fetchall():
                    applied_at = row["applied_at"] or ""
                    if applied_at[:10] == today_str:
                        ve = (row["vendor_email"] or "").lower().strip()
                        dh = row["desc_hash"] or ""
                        nt = row["normalized_title"] or ""
                        if ve and dh:
                            self._session_applied_job_signatures.add(f"{ve}::{dh}")
                        if ve and nt:
                            self._session_applied_job_signatures.add(f"{ve}::{nt}")
        except Exception as e:
            print(f"[Bot] Notice loading session deduplication history: {e}")

    def _setup_signal_handlers(self):
        """Catch Ctrl+C (SIGINT) and SIGTERM for graceful shutdown."""
        def handle_signal(sig, frame):
            print("\n\n[Bot] Termination signal received. Finishing current task and shutting down gracefully...")
            self._running = False
        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)

    def print_banner(self):
        mode_str = "DRY-RUN (Simulated - Safe)" if self.dry_run else "LIVE SENDING (Emails will be sent!)"
        short_th = self.match_cfg.get("short_jd_match_percentage", 85.0)
        daily_cap = self.tracker.daily_safe_cap
        cooldown = self.tracker.cooldown_days
        print("=" * 75)
        print("   🤖 NVOIDS JAVA & JAVA FULL STACK C2C JOB APPLICATION BOT")
        print("=" * 75)
        print(f"  Mode:                {mode_str}")
        print(f"  Target Roles:        Java Developer & Java Full Stack Developer")
        print(f"  Position Type:       C2C (Corp-to-Corp) in USA")
        print(f"  Date Window:         Today, Yesterday, Day Before Yesterday ({self.days_back} days)")
        print(f"  Smart Threshold:     >= {short_th}% (Short JDs) | >= {self.min_match_percentage}% (Detailed JDs)")
        print(f"  Throttling & Cap:    {daily_cap}/day safe cap | {cooldown}-day Recruiter Lock: ACTIVE")
        print(f"  AI Matching Engine:  32-Category Multi-Pillar ATS (Specialization & Stack Alignment)")
        print(f"  Attachment Mode:     Direct Native Document (Zero Popups, 100% Original Layout)")
        print(f"  Check Interval:      Every {self.check_interval} seconds")
        print(f"  Live Ingestion:      ACTIVE (Interleaved polling every {self.live_poll_interval}s with immediate preemption)")
        loaded_resumes = self.matcher.get_loaded_resumes()
        print(f"  Resumes Indexed:     {len(loaded_resumes)} specialized candidate profiles indexed")
        sample_profiles = [os.path.basename(r) for r in loaded_resumes[:5]]
        for p in sample_profiles:
            print(f"    • {p}")
        if len(loaded_resumes) > 5:
            print(f"    ... and {len(loaded_resumes) - 5} additional specialized profiles")
        print("=" * 75)

    def process_job(self, job_ref: Dict[str, str]) -> Dict[str, Any]:
        """Process an individual job candidate: fetch, inspect, match, and apply."""
        job_id = job_ref["job_id"]
        job_url = job_ref["url"]

        # Layer 1: Fast check by Job ID before making network call
        if self.tracker.is_job_id_applied(job_id, is_dry_run=self.dry_run):
            print(f"\n[Job {job_id}] 🚫 DUPLICATE SKIPPED: Job ID {job_id} already applied/processed in database.")
            return {"status": "already_applied", "job_id": job_id}

        # Fetch job detail
        details = self.scraper.parse_job_details(job_url)
        if not details:
            return {"status": "fetch_error", "job_id": job_id}

        title = details["title"]
        location = details["location"]
        desc = details["description"]
        recruiter_email = details["recruiter_email"]
        recruiter_name = details["recruiter_name"]
        recruiter_phone = details.get("recruiter_phone", "")
        all_emails = details.get("all_emails", [])
        posted_dt = details["posted_date"]
        posted_str = details["posted_date_str"]

        print(f"\n[Job {job_id}] {title[:70]}...")
        print(f"  Location: {location} | Date: {posted_str}")

        clean_email = recruiter_email.lower().strip() if recruiter_email else ""
        content_hash = self.tracker.compute_description_hash(desc)
        norm_title = self.tracker.normalize_title(title)
        job_sig = f"{clean_email}::{content_hash}" if (clean_email and content_hash) else ""
        title_sig = f"{clean_email}::{norm_title}" if (clean_email and norm_title) else ""

        # Instant in-memory session lock: only block if this SAME job posting was already applied to today
        if job_sig and job_sig in self._session_applied_job_signatures:
            dup_msg = f"Recruiter {clean_email} posted this exact job posting multiple times today. Multiple email sends prevented."
            print(f"  🚫 DUPLICATE REPOST PREVENTED (Session Lock): {dup_msg}")
            self.tracker.record_job(
                job_id, job_url, title, location, recruiter_email, recruiter_name,
                "", 0.0, "already_applied", error_message=dup_msg, recruiter_phone=recruiter_phone,
                job_description=desc
            )
            return {"status": "already_applied", "job_id": job_id, "reason": dup_msg}

        # Multi-layer SQLite deduplication check:
        # Detects if same recruiter posted the same job posting multiple times today (without blocking different jobs)
        is_dup, dup_reason = self.tracker.is_same_job_posting_applied(
            job_id,
            vendor_email=recruiter_email,
            job_title=title,
            job_description=desc,
            is_dry_run=self.dry_run,
            candidate_emails=all_emails,
            recruiter_phone=recruiter_phone,
            same_day_only=True
        )
        if is_dup:
            print(f"  🚫 DUPLICATE REPOST PREVENTED: {dup_reason}")
            self.tracker.record_job(
                job_id, job_url, title, location, recruiter_email, recruiter_name,
                "", 0.0, "already_applied", error_message=dup_reason, recruiter_phone=recruiter_phone,
                job_description=desc
            )
            return {"status": "already_applied", "job_id": job_id, "reason": dup_reason}

        # 1. Role Check
        if not self.scraper.is_java_developer_role(title, desc, full_stack_only=self.full_stack_only):
            skip_msg = "Not a Java Full Stack Developer opening (Full Stack only mode active)." if self.full_stack_only else "Not a primary Java Developer opening."
            status_code = "skipped_not_fullstack" if self.full_stack_only else "skipped_non_java"
            print(f"  -> Skipped: {skip_msg}")
            self.tracker.record_job(job_id, job_url, title, location, recruiter_email, recruiter_name, "", 0.0, status_code)
            return {"status": status_code, "job_id": job_id}

        # 2. Date Window Check (Today, Yesterday, Day before yesterday)
        if not self.scraper.is_within_days_window(posted_dt, days_back=self.days_back):
            print(f"  -> Skipped: Posted outside the last {self.days_back} days window ({posted_str}).")
            self.tracker.record_job(job_id, job_url, title, location, recruiter_email, recruiter_name, "", 0.0, "skipped_date_window")
            return {"status": "skipped_date_window", "job_id": job_id}

        # 3. C2C & USA Check
        if not self.scraper.is_c2c_and_usa(title, location, desc):
            print(f"  -> Skipped: Not eligible for C2C in USA (or W2 only / bench post).")
            self.tracker.record_job(job_id, job_url, title, location, recruiter_email, recruiter_name, "", 0.0, "skipped_not_c2c")
            return {"status": "skipped_not_c2c", "job_id": job_id}

        # 4. Vendor Email Check
        if not recruiter_email:
            print(f"  -> Skipped: No valid recruiter email could be extracted.")
            self.tracker.record_job(job_id, job_url, title, location, "", recruiter_name, "", 0.0, "skipped_no_email")
            return {"status": "skipped_no_email", "job_id": job_id}

        recruiter_phone = details.get("recruiter_phone", "")
        phone_info = f" | Phone: {recruiter_phone}" if recruiter_phone else ""
        print(f"  Recruiter Contact: {recruiter_name} <{recruiter_email}>{phone_info}")

        # 5. Extract all technical keywords using AI and match against all resumes
        match_result = self.matcher.select_best_resume(title, desc, job_location=location)
        match_score = match_result["match_percentage"]
        best_resume = match_result["filename"]
        best_resume_path = match_result.get("resume_path")
        effective_threshold = match_result.get("min_threshold", self.min_match_percentage)
        decision = match_result.get("decision", "Select")
        extracted_kws = match_result.get("extracted_keywords", [])
        matched_kws = match_result.get("matched_skills", [])
        missing_kws = match_result.get("missing_skills", [])
        total_evaluated = match_result.get("total_evaluated", len(self.matcher.catalog.get_all_resumes()))
        top_candidates = match_result.get("top_candidates", [])

        print(f"  🔍 AI-Extracted Technical Keywords ({len(extracted_kws)}): {', '.join(extracted_kws[:12])}{'...' if len(extracted_kws) > 12 else ''}")
        print(f"  📋 Accessing and evaluating ALL {total_evaluated} candidate resumes in portfolio...")
        print(f"  📊 Top Matching Candidate Resumes:")
        for idx, cand in enumerate(top_candidates[:5], 1):
            spec_str = f" | {cand['specialization']}" if cand.get('specialization') else ""
            print(f"     {idx}. {cand['filename']} -> {cand['score']}% ({cand['matched_count']}/{cand['total_keywords']} tech terms{spec_str})")
        print(f"  🏆 Highest Scoring Resume Selected: '{best_resume}' -> {match_score}%")

        # 6. Candidate Ground-Truth Eligibility Check
        if match_result.get("eligibility", {}).get("has_confirmed_conflict"):
            conflict_msg = match_result.get("decision_reason", "Candidate ineligible")
            print(f"  ❌ REJECTED: {conflict_msg}")
            self.tracker.record_job(
                job_id, job_url, title, location, recruiter_email, recruiter_name,
                best_resume or "", match_score, "skipped_ineligible", error_message=conflict_msg, recruiter_phone=recruiter_phone
            )
            return {"status": "skipped_ineligible", "job_id": job_id, "score": match_score}

        # 7. Strict Cutoff Gate: If all resumes secured less than threshold match (>= 85%), reject that job
        if match_score < effective_threshold:
            reject_msg = f"All {total_evaluated} resumes secured less than {effective_threshold}% match (Highest: '{best_resume}' with {match_score}%). Job rejected."
            print(f"  ❌ REJECTED: {reject_msg}")
            self.tracker.record_job(
                job_id, job_url, title, location, recruiter_email, recruiter_name,
                best_resume or "", match_score, "skipped_threshold", error_message=reject_msg, recruiter_phone=recruiter_phone
            )
            return {"status": "skipped_threshold", "job_id": job_id, "score": match_score}

        # 8. Highest Score Resume Upload & Dispatch
        print(f"  📄 Uploading Resume: '{best_resume}' (Highest match: {match_score}% >= {effective_threshold}%, 100% authentic portfolio document)")
        print(f"  ✅ QUALIFIED ({match_score}% >= {effective_threshold}%). Dispatching application...")
        send_result = self.mailer.send_application(recruiter_email, details, match_result, tracker=self.tracker)

        app_status = send_result.get("status", "applied")
        err_msg = send_result.get("error")

        self.tracker.record_job(
            job_id, job_url, title, location, recruiter_email, recruiter_name,
            best_resume, match_score, app_status, err_msg, recruiter_phone=recruiter_phone,
            job_description=desc
        )

        # Update in-memory session lock: prevent sending to this exact same job posting if seen again today
        if app_status in ("applied", "dry_run"):
            if job_sig:
                self._session_applied_job_signatures.add(job_sig)
            if title_sig:
                self._session_applied_job_signatures.add(title_sig)

        # 8. Instant Phone Call Notification Alert
        if app_status in ("applied", "dry_run") and recruiter_phone:
            clean_role = details.get("clean_title") or title
            print("\n" + "=" * 75)
            print("  📞 HOT RECRUITER CALL ALERT (5x-10x CALLBACK ADVANTAGE):")
            print(f"     Recruiter:  {recruiter_name} ({recruiter_email})")
            print(f"     Phone:      {recruiter_phone}")
            print(f"     Role:       {clean_role} (Match: {match_score}%)")
            print(f"     ACTION:     Call recruiter now: 'Hi {recruiter_name}, I just emailed my resume for {clean_role}!'")
            print("=" * 75 + "\n")

        return {"status": app_status, "job_id": job_id, "score": match_score, "email": recruiter_email}

    def run_initial_scan(self, max_jobs: Optional[int] = None):
        """Execute unified scan:
        1. Ingest real-time live stream from homepage (0s lag, latest postings).
        2. Query historical search queries across days_back window.
        3. Merge into priority queue sorted descending by Job ID.
        4. Interleaved live polling: continuously check for new postings during execution,
           preempting older jobs whenever a recruiter posts a new job!
        """
        print("\n" + "#" * 75)
        print(f"  🔍 PHASE 1: Real-Time Live Stream + Historical Scan ({self.days_back} Days Window)")
        print("#" * 75)

        # Step 1: Immediately ingest freshest live stream from index.jsp (0s indexing lag)
        print("\n[Live Feed] Pulling absolute latest live postings from Nvoids homepage...")
        initial_live_jobs = self.scraper.get_latest_stream_jobs(max_pages=2)
        print(f"  -> Ingested {len(initial_live_jobs)} fresh live stream postings.")

        all_jobs_found = []
        for j in initial_live_jobs:
            jid = str(j.get("job_id", "")).strip()
            if jid and jid not in self._seen_job_ids:
                self._seen_job_ids.add(jid)
                all_jobs_found.append(j)
                try:
                    self._max_seen_job_id = max(self._max_seen_job_id, int(jid))
                except ValueError:
                    pass

        # Step 2: Query historical keyword searches
        queries = self.search_cfg.get("search_queries", [
            "java full stack c2c",
            "java full stack developer c2c",
            "java fullstack c2c"
        ])

        for q in queries:
            if not self._running:
                break
            print(f"\n[Search] Searching Nvoids for query: '{q}'...")
            results = self.scraper.get_search_results(q, hotlist_filter=1)
            new_count = 0
            for r in results:
                jid = str(r.get("job_id", "")).strip()
                if jid and jid not in self._seen_job_ids:
                    self._seen_job_ids.add(jid)
                    all_jobs_found.append(r)
                    new_count += 1
                    try:
                        self._max_seen_job_id = max(self._max_seen_job_id, int(jid))
                    except ValueError:
                        pass
            print(f"  -> Found {len(results)} search results ({new_count} new distinct jobs added).")

        # Step 3: Priority Sort - Always give preference to Java jobs which are most recently posted
        all_jobs_found.sort(key=self._job_recency_priority_key, reverse=True)
        print(f"\n  [Priority Queue] Ordered {len(all_jobs_found)} jobs with Java preference & recency (Newest Java postings first).")

        if max_jobs and len(all_jobs_found) > max_jobs:
            print(f"[Notice] Limiting evaluation to first {max_jobs} jobs (--max-jobs set).")
            all_jobs_found = all_jobs_found[:max_jobs]

        # Convert to dynamic queue (deque) for O(1) push-front / pop-left
        job_queue = deque(all_jobs_found)
        print(f"\n[Execution Plan] Dynamic Queue active with {len(job_queue)} jobs.")
        print(f"  ⚡ Live Ingestion: ACTIVE (checks for new postings every {self.live_poll_interval}s during execution)")

        applied_count = 0
        skipped_threshold = 0
        evaluated_count = 0

        while job_queue and self._running:
            # Check for brand new postings arrived during execution (before next candidate)
            fresh_incoming = self._poll_live_stream_for_new_jobs()
            if fresh_incoming:
                for fj in fresh_incoming:
                    job_queue.append(fj)
                reordered = sorted(list(job_queue), key=self._job_recency_priority_key, reverse=True)
                job_queue = deque(reordered)

            job_ref = job_queue.popleft()
            evaluated_count += 1
            remaining = len(job_queue)

            print(f"\n--- Progress: [Evaluated: {evaluated_count} | Queue Remaining: {remaining}] ---")
            outcome = self.process_job(job_ref)
            if outcome.get("status") in ("applied", "dry_run"):
                applied_count += 1
                # User Requirement: Immediately after applying a job, check if any new job is posted,
                # if yes apply to that job and continue the loop
                print(f"\n⚡ [IMMEDIATE RE-CHECK] Application dispatched for Job #{job_ref.get('job_id')}! Immediately checking live stream for newly posted jobs...")
                post_send_fresh = self._poll_live_stream_for_new_jobs(force=True, max_pages=1)
                if post_send_fresh:
                    for fj in post_send_fresh:
                        job_queue.append(fj)
                    reordered = sorted(list(job_queue), key=self._job_recency_priority_key, reverse=True)
                    job_queue = deque(reordered)
                    print(f"⚡ [IMMEDIATE PREEMPTION] Recruiter just posted {len(post_send_fresh)} new job(s)! Queue updated with newest Java job at the front to apply immediately.")
                    print(f"⚡ Continuing loop immediately to evaluate and apply to newly posted job(s)...")
            elif outcome.get("status") == "skipped_threshold":
                skipped_threshold += 1

            time.sleep(0.3)

        print("\n" + "=" * 75)
        print(f"  Phase 1 Scan Complete: Evaluated: {evaluated_count} | Applied/Simulated: {applied_count} | Skipped (< {self.min_match_percentage}%): {skipped_threshold}")
        print("=" * 75)

    def run_continuous_monitor(self):
        """Continuously monitor Nvoids live stream for new job postings until stopped.

        Real-time Reactive Architecture:
        1. Always prioritizes Java / Java Full Stack roles sorted newest-to-oldest.
        2. Immediately after applying to any job, checks the live stream for newly posted jobs.
        3. If new postings are found, prioritizes and applies to them immediately, continuing the loop.
        4. Only sleeps when all pending unapplied jobs have been processed.
        """
        print("\n" + "#" * 75)
        print(f"  🔄 PHASE 2: Continuous Real-Time Monitoring Loop")
        print(f"  ⚡ Preference: Always prioritizes Java roles which are most recently posted")
        print(f"  ⚡ Immediate Re-check: Instant zero-delay poll after every applied job")
        print(f"  Listening for new postings every {self.check_interval} seconds...")
        print(f"  Press Ctrl+C at any time to safely stop the bot.")
        print("#" * 75 + "\n")

        monitor_queue: deque = deque()
        iteration = 1

        while self._running:
            now_str = datetime.datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
            print(f"[{now_str}] Polling live feed (Cycle #{iteration})...")

            # Reload resumes in case user dropped new resumes into the folder
            self.matcher.reload_resumes()

            # Poll latest stream jobs
            latest_jobs = self.scraper.get_latest_stream_jobs(max_pages=2)
            fresh_jobs = []
            for j in latest_jobs:
                jid = str(j.get("job_id", "")).strip()
                if not jid:
                    continue
                try:
                    jid_int = int(jid)
                except ValueError:
                    jid_int = 0
                if jid_int > self._max_seen_job_id:
                    self._max_seen_job_id = jid_int

                if jid not in self._seen_job_ids:
                    self._seen_job_ids.add(jid)
                    if not self.tracker.is_job_applied(jid, is_dry_run=self.dry_run):
                        fresh_jobs.append(j)

            if fresh_jobs:
                # Always sort: Java jobs first, most recently posted first!
                fresh_jobs.sort(key=self._job_recency_priority_key, reverse=True)
                for j in fresh_jobs:
                    monitor_queue.append(j)
                print(f"  -> Discovered {len(fresh_jobs)} new unapplied job(s). Queue total: {len(monitor_queue)}.")
            else:
                if not monitor_queue:
                    print(f"  No new unapplied jobs detected in this cycle.")

            # Process all jobs in monitor queue with immediate post-application re-checking
            while monitor_queue and self._running:
                # Maintain strict Java recency priority across the queue
                if len(monitor_queue) > 1:
                    reordered = sorted(list(monitor_queue), key=self._job_recency_priority_key, reverse=True)
                    monitor_queue = deque(reordered)

                job_ref = monitor_queue.popleft()
                jid = str(job_ref.get("job_id", "")).strip()
                outcome = self.process_job(job_ref)

                # Immediately after applying a job, check if any new job is posted, if yes apply and continue loop
                if outcome.get("status") in ("applied", "dry_run"):
                    print(f"\n⚡ [IMMEDIATE RE-CHECK] Application dispatched for Job #{jid}! Checking live stream immediately for new postings...")
                    post_send_fresh = self._poll_live_stream_for_new_jobs(force=True, max_pages=1)
                    if post_send_fresh:
                        for nj in post_send_fresh:
                            monitor_queue.append(nj)
                        reordered = sorted(list(monitor_queue), key=self._job_recency_priority_key, reverse=True)
                        monitor_queue = deque(reordered)
                        print(f"⚡ [IMMEDIATE PREEMPTION] Found {len(post_send_fresh)} brand new job(s) posted immediately after application!")
                        for nj in post_send_fresh[:3]:
                            print(f"   -> Prioritizing: Job #{nj.get('job_id')} - {(nj.get('title') or '')[:60]}")
                        print(f"⚡ Continuing loop immediately to evaluate and apply to newly posted job(s)...")

                time.sleep(0.3)

            iteration += 1

            # Only sleep when queue is empty
            if self._running and not monitor_queue:
                for _ in range(self.check_interval):
                    if not self._running:
                        break
                    time.sleep(1)

        print("\n[Bot] Monitoring stopped.")

    def run(self, once: bool = False, max_jobs: Optional[int] = None):
        """Main execution entry point."""
        self.print_banner()

        # Step 1: Scan last 3 days
        self.run_initial_scan(max_jobs=max_jobs)

        # Step 2: Continuous real-time monitor if not in single-run mode
        if not once and self._running:
            self.run_continuous_monitor()

        # Summary
        self.print_summary()


    def print_summary(self):
        """Display overall statistics from tracker database."""
        stats = self.tracker.get_stats()
        print("\n" + "=" * 75)
        print("   📊 BOT EXECUTION SUMMARY")
        print("=" * 75)
        for status, count in sorted(stats.items()):
            print(f"  {status.replace('_', ' ').title():<25}: {count}")
        print("=" * 75 + "\n")
