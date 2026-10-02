#!/usr/bin/env python3
"""Main CLI Entry Point for the Nvoids Job Application Bot."""
import os
import sys
import re
import json
import argparse
from typing import Dict, Any

# Ensure local packages in src can be imported
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.bot import JobApplicationBot
from src.scraper import NvoidsScraper
from src.matcher import ResumeMatcher
from src.mailer import EmailSender
from src.tracker import ApplicationTracker

def load_env_file(env_path: str = ".env"):
    """Load simple key=value pairs from .env into os.environ."""
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            val = v.strip().strip("'").strip('"')
            if val:
                os.environ[k.strip()] = val

def load_config(config_path: str = "config/config.json") -> Dict[str, Any]:
    """Load JSON config and overlay any .env environment variables."""
    load_env_file(".env")
    load_env_file("config/.env")

    if not os.path.exists(config_path):
        print(f"[Error] Configuration file not found at {config_path}")
        sys.exit(1)

    with open(config_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    # Overlay environment variables onto smtp config
    smtp_cfg = cfg.setdefault("smtp", {})
    if os.environ.get("SMTP_HOST"):
        smtp_cfg["host"] = os.environ["SMTP_HOST"]
    if os.environ.get("SMTP_PORT"):
        smtp_cfg["port"] = int(os.environ["SMTP_PORT"])
    if os.environ.get("SMTP_USER"):
        smtp_cfg["username"] = os.environ["SMTP_USER"]
    if os.environ.get("SMTP_PASSWORD"):
        smtp_cfg["password"] = os.environ["SMTP_PASSWORD"]
    if os.environ.get("SENDER_EMAIL"):
        smtp_cfg["sender_email"] = os.environ["SENDER_EMAIL"]
    if os.environ.get("SENDER_NAME"):
        smtp_cfg["sender_name"] = os.environ["SENDER_NAME"]

    if os.environ.get("MIN_MATCH_PERCENTAGE"):
        cfg.setdefault("matching", {})["min_match_percentage"] = float(os.environ["MIN_MATCH_PERCENTAGE"])

    if os.environ.get("DAILY_SAFE_CAP"):
        cfg.setdefault("throttling", {})["daily_safe_cap"] = int(os.environ["DAILY_SAFE_CAP"])

    if os.environ.get("FULL_STACK_ONLY"):
        val = os.environ["FULL_STACK_ONLY"].lower() in ("true", "1", "yes")
        cfg.setdefault("search", {})["full_stack_only"] = val

    if os.environ.get("CC_EMAIL") or os.environ.get("MAILER_CC"):
        cc_val = os.environ.get("CC_EMAIL") or os.environ.get("MAILER_CC")
        cfg.setdefault("mailer", {})["cc_emails"] = [c.strip() for c in re.split(r'[,;\s]+', cc_val) if c.strip()]

    return cfg

def cmd_run(args):
    """Execute the bot."""
    cfg = load_config(args.config)

    # Determine dry-run status
    dry_run = True
    if args.live:
        dry_run = False
    elif args.dry_run:
        dry_run = True
    else:
        dry_run = cfg.get("mailer", {}).get("dry_run", True)

    if args.min_match:
        cfg.setdefault("matching", {})["min_match_percentage"] = args.min_match

    if args.interval:
        cfg.setdefault("monitoring", {})["check_interval_seconds"] = args.interval

    if args.days:
        cfg.setdefault("search", {})["days_back"] = args.days

    if hasattr(args, "full_stack_only") and args.full_stack_only is not None:
        cfg.setdefault("search", {})["full_stack_only"] = args.full_stack_only

    if getattr(args, "cc", None):
        cfg.setdefault("mailer", {})["cc_emails"] = [c.strip() for c in re.split(r'[,;\s]+', args.cc) if c.strip()]

    if getattr(args, "query", None):
        cfg.setdefault("search", {})["search_queries"] = [args.query.strip()]

    bot = JobApplicationBot(
        config=cfg,
        dry_run=dry_run,
        min_match=args.min_match
    )
    bot.run(once=args.once, max_jobs=args.max_jobs)


def cmd_scrape_only(args):
    """Inspect and list recent jobs matching criteria without applying."""
    cfg = load_config(args.config)
    scraper = NvoidsScraper()
    days_back = args.days or cfg.get("search", {}).get("days_back", 3)

    if hasattr(args, "full_stack_only") and args.full_stack_only is not None:
        full_stack_only = args.full_stack_only
    else:
        full_stack_only = cfg.get("search", {}).get("full_stack_only", True)

    mode_label = "Java Full Stack C2C" if full_stack_only else "Java / Full Stack C2C"
    print(f"\n[Scrape-Only] Searching Nvoids for {mode_label} jobs in the last {days_back} days...\n")
    queries = cfg.get("search", {}).get("search_queries", [
        "java full stack c2c",
        "java full stack developer c2c",
        "java fullstack c2c"
    ])
    found_count = 0

    for q in queries:
        print(f"--- Query: '{q}' ---")
        jobs = scraper.get_search_results(q, hotlist_filter=1)
        for job in jobs[:10]:
            details = scraper.parse_job_details(job["url"])
            if not details:
                continue
            is_valid_role = scraper.is_java_developer_role(details["title"], details["description"], full_stack_only=full_stack_only)
            is_c2c = scraper.is_c2c_and_usa(details["title"], details["location"], details["description"])
            in_window = scraper.is_within_days_window(details["posted_date"], days_back=days_back)
            if in_window and is_c2c and is_valid_role:
                found_count += 1
                print(f"[{job['job_id']}] {details['title']}")
                print(f"  Date: {details['posted_date_str']} | Location: {details['location']}")
                print(f"  Recruiter: {details['recruiter_name']} <{details['recruiter_email']}>")
                print(f"  URL: {job['url']}\n")

    print(f"[Done] Found {found_count} matching C2C postings in the last {days_back} days.")

def cmd_match_check(args):
    """Test resume matching algorithm against a job description or sample job."""
    cfg = load_config(args.config)
    min_match = args.min_match or cfg.get("matching", {}).get("min_match_percentage", 85.0)
    matcher = ResumeMatcher(
        resumes_dir=cfg.get("matching", {}).get("resumes_dir", "resumes"),
        min_match_percentage=min_match,
        short_jd_match_percentage=cfg.get("matching", {}).get("short_jd_match_percentage", min_match)
    )

    print(f"\n[Match-Check] Loaded {len(matcher.get_loaded_resumes())} candidate resumes from '{matcher.resumes_dir}/'")

    scraper = NvoidsScraper()
    target_url = args.url or "https://www.nvoids.com/job_details.jsp?id=3678923&uid=9e8ecdf532304898951628aa12aa9c3e"
    print(f"\nFetching job from: {target_url}...")
    details = scraper.parse_job_details(target_url)
    if not details:
        print("[Error] Failed to fetch job details.")
        return

    print(f"\nJob Title: {details['title']}")
    print(f"Location:  {details['location']}")
    result = matcher.select_best_resume(details["title"], details["description"], job_location=details.get("location", ""))

    print("\n" + "=" * 65)
    print(f"  Best Resume:        {result['filename']}")
    print(f"  Match Percentage:   {result['match_percentage']}%")
    print(f"  Threshold:          >= {result['min_threshold']}%")
    print(f"  Action Decision:    {'✅ SELECT & UPLOAD' if result['is_match'] else '❌ REJECT JOB (All < 90%)'}")
    print(f"  Total Evaluated:    All {result.get('total_evaluated', len(matcher.catalog.get_all_resumes()))} resumes in portfolio")
    print(f"  AI Keywords ({len(result.get('extracted_keywords', []))}): {', '.join(result.get('extracted_keywords', []))}")
    print(f"  Matched Keywords:   {', '.join(result['matched_skills'])}")
    print(f"  Missing Keywords:   {', '.join(result['missing_skills']) if result['missing_skills'] else 'None'}")
    print(f"  Top 5 Ranked Resumes:")
    for idx, cand in enumerate(result.get('top_candidates', [])[:5], 1):
        print(f"    {idx}. {cand['score']}% | {cand['filename']} ({cand['specialization']} - {cand['matched_count']}/{cand['total_keywords']} tech terms)")
    print("=" * 65 + "\n")

def cmd_stats(args):
    """Display statistics and history from SQLite database."""
    cfg = load_config(args.config)
    db_path = cfg.get("database", {}).get("path", "data/applied_jobs.db")
    tracker = ApplicationTracker(db_path)

    metrics = tracker.get_dashboard_metrics()

    print("\n" + "=" * 65)
    print("   📊 NVOIDS BOT DASHBOARD & APPLICATION SUMMARY")
    print("=" * 65)
    print(f"  📅 Jobs Applied Today:         {metrics['applied_today']} positions (Date: {metrics['date_today']})")
    print(f"  📅 Jobs Applied Yesterday:     {metrics['applied_yesterday']} positions (Date: {metrics['date_yesterday']})")
    cutoff = cfg.get('matching', {}).get('min_match_percentage', 85.0)
    print(f"  🎯 Average Match Score:        {metrics['avg_match_percentage']}% (Cutoff: ≥ {cutoff}%)")
    print(f"  🛡️  Skipped Today:              {metrics['skipped_today']} (Threshold < {cutoff}%: {metrics['skipped_threshold_today']})")
    print("-" * 65)

    if metrics.get("resumes_breakdown"):
        print("  📄 Resumes Selected by Bot:")
        for item in metrics["resumes_breakdown"]:
            short_name = item["resume"].replace("sample_", "")
            print(f"     • {short_name:<42}: {item['count']} applied")
        print("-" * 65)

    recent = tracker.get_recent_applications(limit=10)
    if recent:
        print("  📋 Recent Log Entries (Applied Today & Recent):")
        for r in recent:
            status_tag = f"[{r['status'].upper()}]"
            short_title = (r['job_title'][:38] + '..') if len(r['job_title']) > 40 else r['job_title']
            time_str = r['applied_at'][11:16] if 'T' in r['applied_at'] else r['applied_at'][:10]
            print(f"     {time_str} {status_tag:<14} {short_title:<40} | {r['match_percentage']}% | To: {r['vendor_email']}")
    print("=" * 65)
    print("  Tip: Run 'python3 main.py dashboard' for the live interactive browser UI!\n")


def cmd_test_email(args):
    """Send a verification test email via configured SMTP."""
    cfg = load_config(args.config)
    smtp_cfg = cfg.get("smtp", {})
    recipient = args.to or smtp_cfg.get("sender_email")

    if not recipient:
        print("[Error] Specify recipient with --to <email>")
        return

    if getattr(args, "cc", None):
        cfg.setdefault("mailer", {})["cc_emails"] = [c.strip() for c in re.split(r'[,;\s]+', args.cc) if c.strip()]

    cc_info = f" (CC: {', '.join(cfg.get('mailer', {}).get('cc_emails', []))})" if cfg.get('mailer', {}).get('cc_emails') else ""
    print(f"[Test Email] Sending test email to {recipient}{cc_info} via {smtp_cfg.get('host')}:{smtp_cfg.get('port')}...")
    sender = EmailSender(cfg, smtp_cfg, dry_run=False)

    fake_job = {
        "title": "Java Full Stack Developer (Test Email)",
        "location": "Remote, USA",
        "recruiter_name": "Test Recruiter",
        "vendor_company": "Nvoids Bot"
    }
    fake_match = {
        "match_percentage": 98.5,
        "matched_skills": ["Java 17", "Spring Boot", "Microservices", "React", "Kafka"],
        "resume_path": None
    }
    res = sender.send_application(recipient, fake_job, fake_match)
    if res.get("success"):
        print(f"✅ Success! Test email delivered to {recipient}.")
    else:
        print(f"❌ Failed: {res.get('error')}")

def main():
    parser = argparse.ArgumentParser(
        description="Automated Nvoids C2C Java Developer & Java Full Stack Job Applier"
    )
    parser.add_argument(
        "--config", default="config/config.json",
        help="Path to config.json (default: config/config.json)"
    )

    subparsers = parser.add_subparsers(dest="command")

    # Command: run
    run_parser = subparsers.add_parser("run", help="Run the bot (scan last 3 days + monitor)")
    run_parser.add_argument("--dry-run", action="store_true", help="Simulate without sending real emails (default)")
    run_parser.add_argument("--live", action="store_true", help="Send actual emails using SMTP credentials")
    run_parser.add_argument("--once", action="store_true", help="Run scan once and exit (no continuous monitoring)")
    run_parser.add_argument("--min-match", type=float, default=None, help="Minimum match score percentage (default: from config, 80.0)")
    run_parser.add_argument("--interval", type=int, help="Polling interval in seconds (default: 180)")
    run_parser.add_argument("--days", type=int, default=3, help="Days back to scan (default: 3: today, yesterday, day before)")
    run_parser.add_argument("--max-jobs", type=int, default=None, help="Limit number of jobs to process during initial scan")
    run_parser.add_argument("--full-stack-only", dest="full_stack_only", action="store_true", default=None, help="Filter strictly for Java Full Stack roles (default: True)")
    run_parser.add_argument("--all-java", dest="full_stack_only", action="store_false", help="Allow backend-only Java roles as well")
    run_parser.add_argument("--cc", type=str, default=None, help="Comma-separated email addresses to CC on applications")
    run_parser.add_argument("--query", type=str, default=None, help="Custom search query (e.g. 'java full stack')")


    # Command: scrape-only
    scrape_parser = subparsers.add_parser("scrape-only", help="Preview matching jobs on Nvoids")
    scrape_parser.add_argument("--days", type=int, default=3, help="Days back to inspect")
    scrape_parser.add_argument("--full-stack-only", dest="full_stack_only", action="store_true", default=None, help="Filter strictly for Java Full Stack roles")
    scrape_parser.add_argument("--all-java", dest="full_stack_only", action="store_false", help="Allow backend-only Java roles as well")

    # Command: match-check
    match_parser = subparsers.add_parser("match-check", help="Test resume matching on a job URL")
    match_parser.add_argument("--url", help="URL of the Nvoids job to test against")
    match_parser.add_argument("--min-match", type=float, default=None)

    # Command: stats
    subparsers.add_parser("stats", help="Show SQLite database statistics")

    # Command: clear-dry-runs
    subparsers.add_parser("clear-dry-runs", help="Clear simulated dry_run records, keeping real applied records")

    # Command: reset-db
    subparsers.add_parser("reset-db", help="Completely reset the applications tracker database")

    # Command: dashboard
    dash_parser = subparsers.add_parser("dashboard", help="Launch live web dashboard (shows jobs applied today, stats, and log)")
    dash_parser.add_argument("--port", type=int, default=8080, help="Port to listen on (default: 8080)")

    # Command: test-email
    test_mail_parser = subparsers.add_parser("test-email", help="Verify SMTP setup with a test email")
    test_mail_parser.add_argument("--to", required=True, help="Destination email address")
    test_mail_parser.add_argument("--cc", type=str, default=None, help="Comma-separated email addresses to CC on test email")

    args = parser.parse_args()

    if not args.command or args.command == "run":
        if not hasattr(args, "live"):
            # Set defaults when invoked without subcommands e.g. `python main.py`
            args.live = False
            args.dry_run = True
            args.once = False
            args.min_match = None
            args.interval = None
            args.days = 3
        cmd_run(args)
    elif args.command == "scrape-only":
        cmd_scrape_only(args)
    elif args.command == "match-check":
        cmd_match_check(args)
    elif args.command == "stats":
        cmd_stats(args)
    elif args.command == "dashboard":
        from src.dashboard_server import run_dashboard_server
        cfg = load_config(args.config)
        db_path = cfg.get("database", {}).get("path", "data/applied_jobs.db")
        run_dashboard_server(db_path=db_path, port=args.port)
    elif args.command == "clear-dry-runs":
        cfg = load_config(args.config)
        tracker = ApplicationTracker(cfg.get("database", {}).get("path", "data/applied_jobs.db"))
        removed = tracker.clear_dry_runs()
        print(f"✅ Cleared {removed} simulated dry_run records. Real applied records preserved.")
    elif args.command == "reset-db":
        cfg = load_config(args.config)
        tracker = ApplicationTracker(cfg.get("database", {}).get("path", "data/applied_jobs.db"))
        tracker.reset_all()
        print("✅ Applications database completely reset.")
    elif args.command == "test-email":
        cmd_test_email(args)



if __name__ == "__main__":
    main()
