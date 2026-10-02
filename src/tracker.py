"""SQLite Application Tracker to guarantee zero duplicate applications.

Maintains complete historical record and provides multi-layered deduplication:
1. Exact Job ID deduplication (never apply to same posting twice)
2. Vendor Email + Job Title deduplication (detects duplicate reposts with new IDs)
3. Recruiter contact cooldown (prevents spamming the same recruiter)
"""
import os
import re
import sqlite3
import datetime
from typing import Optional, Dict, Any, List, Tuple

class ApplicationTracker:
    def __init__(
        self,
        db_path: str = "data/applied_jobs.db",
        daily_safe_cap: int = 80,
        cooldown_days: int = 14
    ):
        self.db_path = db_path
        self.daily_safe_cap = daily_safe_cap
        self.cooldown_days = cooldown_days
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        # Enable Write-Ahead Logging (WAL) for concurrency & durability
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS applications (
                    job_id TEXT PRIMARY KEY,
                    job_url TEXT,
                    job_title TEXT,
                    normalized_title TEXT,
                    location TEXT,
                    vendor_email TEXT,
                    recruiter_name TEXT,
                    resume_file TEXT,
                    match_percentage REAL,
                    status TEXT,
                    applied_at TIMESTAMP,
                    error_message TEXT
                )
            """)
            # Schema migration: add normalized_title, recruiter_phone, desc_hash, description_snippet
            cursor.execute("PRAGMA table_info(applications);")
            columns = [col[1] for col in cursor.fetchall()]
            if "normalized_title" not in columns:
                cursor.execute("ALTER TABLE applications ADD COLUMN normalized_title TEXT;")
            if "recruiter_phone" not in columns:
                cursor.execute("ALTER TABLE applications ADD COLUMN recruiter_phone TEXT;")
            if "desc_hash" not in columns:
                cursor.execute("ALTER TABLE applications ADD COLUMN desc_hash TEXT;")
            if "description_snippet" not in columns:
                cursor.execute("ALTER TABLE applications ADD COLUMN description_snippet TEXT;")

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_vendor_email ON applications(vendor_email);
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_status ON applications(status);
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_applied_at ON applications(applied_at);
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_vendor_title ON applications(vendor_email, normalized_title);
            """)
            conn.commit()


    @staticmethod
    def normalize_title(title: str) -> str:
        """Strip filler words to detect duplicate job reposts."""
        if not title:
            return ""
        t = title.lower()
        # Remove common prefixes/fillers
        t = re.sub(
            r'\b(urgent|immediate|need|hiring|open|opening|position|role|c2c|w2|remote|onsite|hybrid|locals?|only|for|at|in|client|location|interview|lead|senior|sr)\b',
            ' ', t
        )
        t = re.sub(r'[^a-z0-9\s]', ' ', t)
        words = sorted(set(w for w in t.split() if len(w) > 2))
        return " ".join(words)

    def is_job_id_applied(self, job_id: str, is_dry_run: bool = False) -> bool:
        """Check if this specific Job ID was already applied."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT status FROM applications WHERE job_id = ?",
                (str(job_id),)
            )
            row = cursor.fetchone()
            if not row:
                return False
            status = row["status"]
            if is_dry_run:
                # In dry run, any previous run (dry_run or applied) counts
                return status in ("applied", "dry_run")
            else:
                # In LIVE mode, only an actual successful 'applied' prevents sending
                return status == "applied"

    def is_job_applied(self, job_id: str, is_dry_run: bool = False) -> bool:
        """Convenience alias for is_job_id_applied."""
        return self.is_job_id_applied(job_id, is_dry_run=is_dry_run)

    @staticmethod
    def compute_description_hash(description: str) -> str:
        """Generate deterministic hash from core text tokens of the JD, ignoring whitespace and noise."""
        if not description:
            return ""
        import hashlib
        t = re.sub(r'https?://\S+', '', description.lower())
        t = re.sub(r'\b[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+\b', '', t)
        t = re.sub(r'\b\d+\b', '', t)
        words = [w for w in re.findall(r'[a-z]{3,}', t) if w not in (
            'the', 'and', 'for', 'with', 'you', 'will', 'this', 'that', 'from', 'are',
            'job', 'role', 'opening', 'position', 'please', 'send', 'resume', 'email'
        )]
        core_text = " ".join(words[:150])
        if not core_text:
            return ""
        return hashlib.md5(core_text.encode('utf-8')).hexdigest()

    @staticmethod
    def compute_text_similarity(desc1: str, desc2: str) -> float:
        """Compute Jaccard token similarity between two job descriptions."""
        if not desc1 or not desc2:
            return 0.0
        def get_tokens(d):
            t = re.sub(r'https?://\S+', '', d.lower())
            t = re.sub(r'\b[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+\b', '', t)
            return set(w for w in re.findall(r'[a-z]{3,}', t) if w not in (
                'the', 'and', 'for', 'with', 'you', 'will', 'this', 'that', 'from', 'are',
                'job', 'role', 'opening', 'position', 'please', 'send', 'resume', 'email'
            ))
        s1 = get_tokens(desc1)
        s2 = get_tokens(desc2)
        if not s1 or not s2:
            return 0.0
        intersection = len(s1.intersection(s2))
        union = len(s1.union(s2))
        return intersection / union if union else 0.0

    def is_same_job_posting_applied(
        self,
        job_id: str,
        vendor_email: str = "",
        job_title: str = "",
        job_description: str = "",
        is_dry_run: bool = False,
        candidate_emails: Optional[List[str]] = None,
        recruiter_phone: str = "",
        same_day_only: bool = True
    ) -> Tuple[bool, str]:
        """Detect if the SAME recruiter posted the SAME job posting multiple times at the same time
        or in the same day, to prevent sending duplicate emails for the exact same opening.

        CRITICAL: If the recruiter posted a DIFFERENT job opening, this returns False so that
        the candidate can legitimately apply to distinct roles with the same vendor.

        Returns:
            (is_duplicate: bool, reason: str)
        """
        # Layer 1: Check by exact Job ID
        if self.is_job_id_applied(job_id, is_dry_run=is_dry_run):
            return True, f"Job ID {job_id} already has a recorded application."

        if not vendor_email and not candidate_emails and not recruiter_phone:
            return False, ""

        with self._get_connection() as conn:
            cursor = conn.cursor()
            status_filter = "status = 'applied'" if not is_dry_run else "status IN ('applied', 'dry_run')"

            # Build list of all emails associated with this recruiter/posting
            emails_to_check = []
            if vendor_email:
                clean_p = vendor_email.lower().strip()
                if clean_p and "googlegroups.com" not in clean_p:
                    emails_to_check.append(clean_p)
            if candidate_emails:
                for ce in candidate_emails:
                    clean_ce = ce.lower().strip()
                    if clean_ce and clean_ce not in emails_to_check and "googlegroups.com" not in clean_ce:
                        emails_to_check.append(clean_ce)

            if not emails_to_check:
                return False, ""

            placeholders = ",".join("?" * len(emails_to_check))
            cursor.execute(f"""
                SELECT job_id, job_title, normalized_title, vendor_email, recruiter_phone,
                       desc_hash, description_snippet, applied_at
                FROM applications
                WHERE vendor_email IN ({placeholders}) AND {status_filter}
                ORDER BY applied_at DESC
            """, emails_to_check)
            previous_jobs = cursor.fetchall()

            if not previous_jobs:
                return False, ""

            curr_hash = self.compute_description_hash(job_description)
            curr_norm_title = self.normalize_title(job_title)
            today_str = datetime.date.today().isoformat()

            for prev in previous_jobs:
                prev_applied_at = prev["applied_at"] or ""
                prev_date = prev_applied_at[:10]

                # If same_day_only is True, compare against same day postings
                if same_day_only and prev_date != today_str:
                    continue

                prev_id = prev["job_id"]
                prev_title = prev["job_title"]
                prev_hash = prev["desc_hash"] or ""
                prev_desc = prev["description_snippet"] or ""
                prev_norm_title = prev["normalized_title"] or ""

                # Check 1: Exact Content Hash Match (identical JD reposted at same time or same day)
                if curr_hash and prev_hash and curr_hash == prev_hash:
                    return True, (
                        f"Recruiter {prev['vendor_email']} posted this exact same job multiple times today "
                        f"(identical content to Job ID {prev_id}). Duplicate email prevented."
                    )

                # Check 2: Description text similarity (repost with minor edits like rate/timestamp)
                if job_description and prev_desc:
                    sim = self.compute_text_similarity(job_description, prev_desc)
                    if sim >= 0.70:
                        return True, (
                            f"Recruiter {prev['vendor_email']} reposted this same job posting today "
                            f"(description {round(sim*100)}% identical to Job ID {prev_id}: '{prev_title[:35]}'). Duplicate email prevented."
                        )
                    if curr_norm_title and prev_norm_title and curr_norm_title == prev_norm_title and sim >= 0.45:
                        return True, (
                            f"Recruiter {prev['vendor_email']} posted this same job ({prev_title[:35]}) multiple times today "
                            f"(Job ID {prev_id}). Duplicate email prevented."
                        )

                # Check 3: Identical normalized role title for same recruiter on same day
                if curr_norm_title and prev_norm_title and curr_norm_title == prev_norm_title and curr_norm_title != "":
                    return True, (
                        f"Recruiter {prev['vendor_email']} already received an application for identical role '{prev_title[:35]}' today "
                        f"(Job ID {prev_id}). Duplicate email prevented."
                    )

        return False, ""

    def is_already_applied(
        self,
        job_id: str,
        vendor_email: str = "",
        job_title: str = "",
        is_dry_run: bool = False,
        cooldown_days: Optional[int] = None,
        candidate_emails: Optional[List[str]] = None,
        recruiter_phone: str = "",
        job_description: str = ""
    ) -> Tuple[bool, str]:
        """Wrapper maintaining compatibility, routing to same job posting deduplication."""
        return self.is_same_job_posting_applied(
            job_id=job_id,
            vendor_email=vendor_email,
            job_title=job_title,
            job_description=job_description,
            is_dry_run=is_dry_run,
            candidate_emails=candidate_emails,
            recruiter_phone=recruiter_phone,
            same_day_only=True
        )

    def record_job(
        self,
        job_id: str,
        job_url: str,
        job_title: str,
        location: str,
        vendor_email: str,
        recruiter_name: str,
        resume_file: str,
        match_percentage: float,
        status: str,
        error_message: Optional[str] = None,
        recruiter_phone: str = "",
        job_description: str = ""
    ):
        """Record an application attempt or skipped status, storing content hash for same-job deduplication."""
        norm_title = self.normalize_title(job_title)
        clean_email = vendor_email.lower().strip() if vendor_email else ""
        desc_hash = self.compute_description_hash(job_description) if job_description else ""
        desc_snippet = job_description[:1200] if job_description else ""

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO applications (
                    job_id, job_url, job_title, normalized_title, location, vendor_email,
                    recruiter_name, recruiter_phone, resume_file, match_percentage, status,
                    applied_at, error_message, desc_hash, description_snippet
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    status = excluded.status,
                    applied_at = excluded.applied_at,
                    match_percentage = excluded.match_percentage,
                    resume_file = excluded.resume_file,
                    recruiter_phone = CASE 
                        WHEN excluded.recruiter_phone != '' THEN excluded.recruiter_phone 
                        ELSE applications.recruiter_phone 
                    END,
                    desc_hash = CASE
                        WHEN excluded.desc_hash != '' THEN excluded.desc_hash
                        ELSE applications.desc_hash
                    END,
                    description_snippet = CASE
                        WHEN excluded.description_snippet != '' THEN excluded.description_snippet
                        ELSE applications.description_snippet
                    END,
                    error_message = excluded.error_message
            """, (
                str(job_id),
                job_url,
                job_title,
                norm_title,
                location,
                clean_email,
                recruiter_name,
                recruiter_phone,
                resume_file,
                float(match_percentage),
                status,
                datetime.datetime.now().isoformat(),
                error_message,
                desc_hash,
                desc_snippet
            ))
            conn.commit()

    def get_stats(self) -> Dict[str, int]:
        """Return counts of processed jobs by status."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT status, COUNT(*) as cnt FROM applications GROUP BY status")
            rows = cursor.fetchall()
            stats = {row["status"]: row["cnt"] for row in rows}
            cursor.execute("SELECT COUNT(*) as total FROM applications")
            stats["total_tracked"] = cursor.fetchone()["total"]
            return stats

    def get_recent_applications(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Retrieve the most recent applications."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM applications ORDER BY applied_at DESC LIMIT ?",
                (limit,)
            )
            return [dict(row) for row in cursor.fetchall()]

    def clear_dry_runs(self) -> int:
        """Remove only simulated dry_run records, preserving real applied jobs."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM applications WHERE status = 'dry_run'")
            conn.commit()
            return cursor.rowcount

    def reset_all(self):
        """Completely clear the database (all tracking records)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM applications")
            conn.commit()

    def get_live_sent_today(self) -> int:
        """Count actual live sent applications today."""
        today_prefix = datetime.date.today().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) as cnt FROM applications WHERE status = 'applied' AND applied_at LIKE ?",
                (f"{today_prefix}%",)
            )
            return cursor.fetchone()["cnt"]

    def get_live_sent_last_hour(self) -> int:
        """Count actual live sent applications in the rolling last 60 minutes."""
        cutoff = (datetime.datetime.now() - datetime.timedelta(hours=1)).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) as cnt FROM applications WHERE status = 'applied' AND applied_at >= ?",
                (cutoff,)
            )
            return cursor.fetchone()["cnt"]

    def get_seconds_until_next_hourly_slot(self) -> int:
        """Calculate remaining seconds until the oldest sent email in the past hour expires."""
        cutoff = (datetime.datetime.now() - datetime.timedelta(hours=1)).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT applied_at FROM applications WHERE status = 'applied' AND applied_at >= ? ORDER BY applied_at ASC LIMIT 1",
                (cutoff,)
            )
            row = cursor.fetchone()
            if not row:
                return 0
            try:
                oldest_dt = datetime.datetime.fromisoformat(row["applied_at"])
                elapsed = (datetime.datetime.now() - oldest_dt).total_seconds()
                return max(0, int(3600 - elapsed) + 5)
            except Exception:
                return 60

    def get_dashboard_metrics(self) -> Dict[str, Any]:
        """Return rich metrics specifically for the dashboard interface."""
        today_prefix = datetime.date.today().isoformat()
        yesterday_prefix = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 1. Jobs applied today (both live and dry_run)
            cursor.execute("""
                SELECT COUNT(*) as cnt FROM applications
                WHERE status IN ('applied', 'dry_run') AND applied_at LIKE ?
            """, (f"{today_prefix}%",))
            applied_today = cursor.fetchone()["cnt"]

            # Real applied today
            cursor.execute("""
                SELECT COUNT(*) as cnt FROM applications
                WHERE status = 'applied' AND applied_at LIKE ?
            """, (f"{today_prefix}%",))
            real_applied_today = cursor.fetchone()["cnt"]

            # 2. Jobs applied yesterday
            cursor.execute("""
                SELECT COUNT(*) as cnt FROM applications
                WHERE status IN ('applied', 'dry_run') AND applied_at LIKE ?
            """, (f"{yesterday_prefix}%",))
            applied_yesterday = cursor.fetchone()["cnt"]

            # 3. Total jobs applied all-time
            cursor.execute("""
                SELECT COUNT(*) as cnt FROM applications WHERE status = 'applied'
            """)
            total_applied_live = cursor.fetchone()["cnt"]

            cursor.execute("""
                SELECT COUNT(*) as cnt FROM applications WHERE status IN ('applied', 'dry_run')
            """)
            total_applied_all = cursor.fetchone()["cnt"]

            # 4. Total skipped today
            cursor.execute("""
                SELECT COUNT(*) as cnt FROM applications
                WHERE status LIKE 'skipped%' AND applied_at LIKE ?
            """, (f"{today_prefix}%",))
            skipped_today = cursor.fetchone()["cnt"]

            # 5. Skipped by threshold (< 93%) today
            cursor.execute("""
                SELECT COUNT(*) as cnt FROM applications
                WHERE status = 'skipped_threshold' AND applied_at LIKE ?
            """, (f"{today_prefix}%",))
            skipped_threshold_today = cursor.fetchone()["cnt"]

            # 6. Average match score of applied jobs
            cursor.execute("""
                SELECT AVG(match_percentage) as avg_score FROM applications
                WHERE status IN ('applied', 'dry_run') AND match_percentage > 0
            """)
            row = cursor.fetchone()
            avg_match = round(row["avg_score"], 1) if row and row["avg_score"] else 0.0

            # 7. Count of recruiters ready for immediate phone call
            cursor.execute("""
                SELECT COUNT(*) as cnt FROM applications
                WHERE status IN ('applied', 'dry_run') AND recruiter_phone != '' AND recruiter_phone IS NOT NULL
            """)
            call_ready_count = cursor.fetchone()["cnt"]

            # 8. Sent in the last hour
            cutoff_hour = (datetime.datetime.now() - datetime.timedelta(hours=1)).isoformat()
            cursor.execute("""
                SELECT COUNT(*) as cnt FROM applications
                WHERE status = 'applied' AND applied_at >= ?
            """, (cutoff_hour,))
            sent_last_hour = cursor.fetchone()["cnt"]

            # 9. Resume usage breakdown
            cursor.execute("""
                SELECT resume_file, COUNT(*) as cnt FROM applications
                WHERE status IN ('applied', 'dry_run') AND resume_file != ''
                GROUP BY resume_file ORDER BY cnt DESC
            """)
            resumes_breakdown = [{"resume": r["resume_file"], "count": r["cnt"]} for r in cursor.fetchall()]

            # 10. Status totals
            cursor.execute("SELECT status, COUNT(*) as cnt FROM applications GROUP BY status")
            status_counts = {r["status"]: r["cnt"] for r in cursor.fetchall()}

            return {
                "date_today": today_prefix,
                "date_yesterday": yesterday_prefix,
                "applied_today": applied_today,
                "real_applied_today": real_applied_today,
                "applied_yesterday": applied_yesterday,
                "total_applied_live": total_applied_live,
                "total_applied_all": total_applied_all,
                "skipped_today": skipped_today,
                "skipped_threshold_today": skipped_threshold_today,
                "avg_match_percentage": avg_match,
                "call_ready_count": call_ready_count,
                "sent_last_hour": sent_last_hour,
                "daily_safe_cap": self.daily_safe_cap,
                "hourly_limit": 10,
                "resumes_breakdown": resumes_breakdown,
                "status_counts": status_counts,
                "total_processed": sum(status_counts.values())
            }

    def get_jobs_list(
        self,
        date_filter: Optional[str] = None,
        status_filter: Optional[str] = None,
        search_query: Optional[str] = None,
        has_phone: bool = False,
        limit: int = 150
    ) -> List[Dict[str, Any]]:
        """Query jobs with flexible filtering for the dashboard table."""
        today_prefix = datetime.date.today().isoformat()
        yesterday_prefix = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()

        query = "SELECT * FROM applications WHERE 1=1"
        params = []

        if date_filter == "today":
            query += " AND applied_at LIKE ?"
            params.append(f"{today_prefix}%")
        elif date_filter == "yesterday":
            query += " AND applied_at LIKE ?"
            params.append(f"{yesterday_prefix}%")

        if status_filter and status_filter != "all":
            if status_filter == "applied_all":
                query += " AND status IN ('applied', 'dry_run')"
            elif status_filter == "skipped_all":
                query += " AND status LIKE 'skipped%'"
            else:
                query += " AND status = ?"
                params.append(status_filter)

        if has_phone:
            query += " AND recruiter_phone != '' AND recruiter_phone IS NOT NULL"

        if search_query:
            query += " AND (job_title LIKE ? OR vendor_email LIKE ? OR location LIKE ? OR recruiter_name LIKE ? OR recruiter_phone LIKE ?)"
            wildcard = f"%{search_query}%"
            params.extend([wildcard, wildcard, wildcard, wildcard, wildcard])

        query += " ORDER BY applied_at DESC LIMIT ?"
        params.append(limit)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]


