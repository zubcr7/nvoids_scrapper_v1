import unittest
from unittest.mock import MagicMock, patch
from collections import deque

from src.bot import JobApplicationBot

class TestBotPriorityAndImmediateLoop(unittest.TestCase):
    def setUp(self):
        self.dummy_config = {
            "search": {
                "roles": ["Java Full Stack Developer"],
                "search_queries": ["java full stack c2c"],
                "full_stack_only": True,
                "days_back": 3,
                "excluded_title_keywords": ["camunda", "guidewire", "mulesoft"]
            },
            "matching": {
                "min_match_percentage": 85.0,
                "short_jd_match_percentage": 85.0,
                "short_jd_word_limit": 120,
                "resumes_dir": "resumes"
            },
            "monitoring": {
                "interval_seconds": 30,
                "live_poll_interval_seconds": 15
            },
            "throttling": {
                "daily_safe_cap": 80,
                "recruiter_cooldown_days": 14
            },
            "mailer": {
                "dry_run": True,
                "candidate": {
                    "name": "Nithin Chiguru",
                    "email": "nithin@example.com",
                    "phone": "312-358-4463"
                }
            },
            "database": {
                "path": ":memory:"
            }
        }
        with patch("src.bot.NvoidsScraper"), \
             patch("src.bot.ResumeMatcher"), \
             patch("src.bot.EmailSender"):
            self.bot = JobApplicationBot(self.dummy_config, dry_run=True)

    def test_job_recency_priority_key_ordering(self):
        """Ensure Java jobs get top preference and are ordered strictly newest to oldest."""
        jobs = [
            {"job_id": "3700010", "title": "Python Developer"},
            {"job_id": "3700005", "title": "Camunda Developer"},
            {"job_id": "3700001", "title": "Software Engineer"},
            {"job_id": "3699800", "title": "Java Developer"},
            {"job_id": "3700000", "title": "Java Developer"},
            {"job_id": "3699500", "title": "Java Full Stack Developer"},
            {"job_id": "3700050", "title": "Java Full Stack Developer"},
            {"job_id": "3700060", "title": "Sr. Java FSD Developer - Camunda 7"},  # Niche platform excluded
            {"job_id": "3700070", "title": "Guidewire Java Integration Specialist"},  # Niche platform excluded
        ]

        # Sort descending by priority key
        sorted_jobs = sorted(jobs, key=self.bot._job_recency_priority_key, reverse=True)
        sorted_ids = [j["job_id"] for j in sorted_jobs]

        # Top 2 should be Java Full Stack (newest: 3700050, older: 3699500)
        self.assertEqual(sorted_ids[0], "3700050")
        self.assertEqual(sorted_ids[1], "3699500")

        # Next 2 should be Java Developer (newest: 3700000, older: 3699800)
        self.assertEqual(sorted_ids[2], "3700000")
        self.assertEqual(sorted_ids[3], "3699800")

        # Generic Software Engineer should be next
        self.assertEqual(sorted_ids[4], "3700001")

        # Excluded niche platforms & non-java roles must be at the very bottom
        bottom_ids = sorted_ids[5:]
        self.assertIn("3700010", bottom_ids)  # Python
        self.assertIn("3700005", bottom_ids)  # Camunda
        self.assertIn("3700060", bottom_ids)  # Java with Camunda
        self.assertIn("3700070", bottom_ids)  # Java with Guidewire

    def test_immediate_post_application_recheck_and_loop(self):
        """Test that immediately after applying to a job, newly posted jobs are detected,
        prepended to the front of the queue, evaluated next, and the loop continues."""
        initial_job = {"job_id": "3700100", "title": "Java Full Stack Developer", "url": "https://nvoids.com/job1"}
        brand_new_job = {"job_id": "3700200", "title": "Lead Java Full Stack Developer", "url": "https://nvoids.com/job2"}

        processed_order = []

        def mock_process_job(job_ref):
            jid = job_ref["job_id"]
            processed_order.append(jid)
            return {"status": "applied", "job_id": jid}

        self.bot.process_job = MagicMock(side_effect=mock_process_job)

        # First call to _poll_live_stream_for_new_jobs before execution -> returns []
        # Immediately after initial_job is applied, the force=True call returns [brand_new_job]
        # Subsequent calls return []
        poll_call_count = [0]
        def mock_poll(force=False, max_pages=1):
            poll_call_count[0] += 1
            if force and poll_call_count[0] == 2:
                # This is the immediate check triggered after initial_job is applied
                return [brand_new_job]
            return []

        self.bot._poll_live_stream_for_new_jobs = MagicMock(side_effect=mock_poll)

        # Simulate execution queue with initial_job and a lower priority background job
        background_job = {"job_id": "3699000", "title": "Java Developer", "url": "https://nvoids.com/job3"}
        job_queue = deque([initial_job, background_job])

        # Run simulated scan loop (same logic as in run_initial_scan)
        while job_queue and self.bot._running:
            fresh_incoming = self.bot._poll_live_stream_for_new_jobs()
            if fresh_incoming:
                fresh_incoming.sort(key=self.bot._job_recency_priority_key, reverse=True)
                for fj in reversed(fresh_incoming):
                    job_queue.appendleft(fj)

            job_ref = job_queue.popleft()
            outcome = self.bot.process_job(job_ref)
            if outcome.get("status") in ("applied", "dry_run"):
                post_send_fresh = self.bot._poll_live_stream_for_new_jobs(force=True, max_pages=1)
                if post_send_fresh:
                    post_send_fresh.sort(key=self.bot._job_recency_priority_key, reverse=True)
                    for fj in reversed(post_send_fresh):
                        job_queue.appendleft(fj)

        # Verification:
        # 1. initial_job (3700100) was processed first.
        # 2. Immediately after applying 3700100, brand_new_job (3700200) was detected and pushed to FRONT.
        # 3. Next processed was brand_new_job (3700200), preempting background_job (3699000).
        # 4. Finally background_job (3699000) was processed.
        self.assertEqual(processed_order, ["3700100", "3700200", "3699000"])

if __name__ == "__main__":
    unittest.main()
