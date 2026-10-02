"""Email Dispatcher and Template Engine.

Renders personalized C2C job application emails, attaches candidate resumes,
and sends them via SMTP (Gmail, Outlook, Custom) with safe dry-run preview mode.
"""
import os
import re
import time
import random
import datetime
import json
import urllib.request
import mimetypes
import smtplib
import email.utils
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from typing import Dict, Any, Optional, Tuple

from src.pdf_converter import InMemoryPdfConverter

class EmailSender:
    def __init__(self, config: Dict[str, Any], smtp_config: Dict[str, Any], dry_run: bool = True):
        self.mailer_config = config.get("mailer", {})
        self.candidate_info = self.mailer_config.get("candidate", {})
        self.smtp_config = smtp_config
        self.dry_run = dry_run
        self.send_delay = self.mailer_config.get("send_delay_seconds", 15)
        self.use_ai_humanizer = self.mailer_config.get("use_ai_humanizer", True)

        # CC Recipients Configuration (string or list)
        raw_cc = self.mailer_config.get("cc_emails") or self.mailer_config.get("cc") or []
        if isinstance(raw_cc, str):
            self.configured_cc_emails = [c.strip() for c in re.split(r'[,;\s]+', raw_cc) if c.strip()]
        elif isinstance(raw_cc, list):
            self.configured_cc_emails = [str(c).strip() for c in raw_cc if str(c).strip()]
        else:
            self.configured_cc_emails = []

        # Gmail Volume & Throttling Protection
        self.throttling_config = config.get("throttling", {})
        self.daily_safe_cap = self.throttling_config.get("daily_safe_cap", 80)
        self.hourly_limit = self.throttling_config.get("hourly_limit", 10)
        self.min_jitter = float(self.throttling_config.get("min_jitter_seconds", 25.0))
        self.max_jitter = float(self.throttling_config.get("max_jitter_seconds", 55.0))
        self.consecutive_sends = 0

        # Load templates
        txt_path = self.mailer_config.get("template_txt", "templates/email_template.txt")
        html_path = self.mailer_config.get("template_html", "templates/email_template.html")

        self.template_txt = self._read_file(txt_path)
        self.template_html = self._read_file(html_path)
        self.subject_template = self.mailer_config.get(
            "subject_template",
            "Nithin's Resume for {{job_title}} role"
        )

    def _read_file(self, path: str) -> str:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception as e:
                print(f"[Mailer] Error reading template {path}: {e}")
        return ""

    def render_template(self, template_str: str, context: Dict[str, Any]) -> str:
        """Render template with placeholders and simple conditional blocks."""
        rendered = template_str

        # 1. Handle conditional blocks {{#key}}...{{/key}}
        def replace_conditional(match):
            key = match.group(1).strip()
            content = match.group(2)
            val = context.get(key)
            if val and str(val).strip():
                # Value is present, render inner content
                return content
            return ""

        rendered = re.sub(r'\{\{#([a-zA-Z0-9_]+)\}\}([\s\S]*?)\{\{/\1\}\}', replace_conditional, rendered)

        # 2. Replace placeholders {{key}}
        for k, v in context.items():
            placeholder = f"{{{{{k}}}}}"
            rendered = rendered.replace(placeholder, str(v) if v is not None else "")

        # Clean remaining unmatched {{...}} placeholders
        rendered = re.sub(r'\{\{[a-zA-Z0-9_]+\}\}', '', rendered)
        return rendered

    def build_context(
        self,
        job_details: Dict[str, Any],
        matching_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Combine candidate info and job details into email context dictionary."""
        skills_str = ", ".join(matching_result.get("matched_skills", []))
        if not skills_str:
            skills_str = "Java, Spring Boot, Microservices, REST APIs, SQL"

        recruiter_name = job_details.get("recruiter_name") or "Hiring Team"
        if recruiter_name.lower() in ("hiring team", "hiring manager", "team"):
            recruiter_name = "Hiring Team"

        # Use clean professional role name (e.g. 'Lead AWS Java Developer') instead of raw recruiter headline
        clean_role = job_details.get("clean_title") or job_details.get("title", "Java Full Stack Developer")

        return {
            "recruiter_name": recruiter_name,
            "job_title": clean_role,
            "raw_job_title": job_details.get("title", clean_role),
            "location": job_details.get("location", "Remote, USA"),
            "vendor_company": job_details.get("vendor_company", "Staffing Team"),
            "match_percentage": matching_result.get("match_percentage", 95.0),
            "matched_skills": skills_str,

            "candidate_name": self.candidate_info.get("name", "Candidate Name"),
            "candidate_email": self.candidate_info.get("email", "candidate@example.com"),
            "candidate_phone": self.candidate_info.get("phone", "+1 (555) 123-4567"),
            "candidate_linkedin": self.candidate_info.get("linkedin", ""),
            "candidate_experience": self.candidate_info.get("experience_years", "9+ years"),
            "rate": self.candidate_info.get("c2c_rate", "$75/hr C2C"),
            "work_authorization": self.candidate_info.get("work_authorization", "C2C / Corp-to-Corp"),
            "candidate_summary": self.candidate_info.get("summary", "")
        }

    def compose_human_email(
        self, context: Dict[str, Any], matching_result: Optional[Dict[str, Any]] = None
    ) -> Tuple[str, str]:
        """Compose a 100% natural, human-written email tailored to the role and recruiter.
        Returns: (plain_text_body, gmail_styled_html_body)
        """
        recruiter_name = context.get("recruiter_name") or "there"
        clean_role = context.get("job_title") or "Java Full Stack Developer"
        skills = (matching_result.get("matched_skills") if matching_result else []) or []

        # 1. Optional LLM Compose if API key available
        gemini_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if gemini_key:
            llm_text = self._compose_with_gemini(recruiter_name, clean_role, skills, gemini_key)
            if llm_text:
                return llm_text, self._text_to_gmail_html(llm_text)

        # 2. Intelligent AI Combinatorial Human Engine
        return self._compose_natural_human_email(recruiter_name, clean_role, skills)

    def _compose_with_gemini(
        self, recruiter_name: str, clean_role: str, matched_skills: list, api_key: str
    ) -> Optional[str]:
        """Optionally call Google Gemini API for real-time human email drafting."""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
        top_skills = [s for s in matched_skills if s.lower() not in ('agile', 'unit testing', 'ci/cd', 'domain')][:3]
        skills_phrase = ", ".join(top_skills) if top_skills else "Java, Spring Boot, and Microservices"

        prompt = (
            f"Write a short, natural email from senior software engineer Nithin Chiguru to recruiter '{recruiter_name}' "
            f"applying for the '{clean_role}' role. "
            f"Requirements:\n"
            f"- Sound 100% like a genuine human engineer writing directly from personal Gmail.\n"
            f"- Naturally mention 10+ years of experience with {skills_phrase}.\n"
            f"- State that resume is attached for review.\n"
            f"- Include these exact details at the bottom:\n"
            f"Experience: 10+ years\n"
            f"Visa: H1B from 2024-2027\n\n"
            f"Best regards,\nNithin Chiguru\nPhone: +1 (312) 358-4463\nEmail: nithin.chiguru9@gmail.com\nLinkedIn: https://www.linkedin.com/in/nithinch/\n"
            f"- Strictly NO robotic headers, NO bulleted tables, NO mention of match scores or AI. Output ONLY the email body."
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 300}
        }
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=4) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                candidates = data.get("candidates", [])
                if candidates:
                    text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
                    if text and "Nithin Chiguru" in text:
                        return text
        except Exception:
            pass
        return None

    def _compose_natural_human_email(
        self, recruiter_name: str, clean_role: str, matched_skills: list
    ) -> Tuple[str, str]:
        """Generate an authentic human email with realistic phrasing variations."""
        def _format_tech_name(tech: str) -> str:
            t = tech.strip()
            mapping = {
                'ai & genai': 'Generative AI',
                'aws': 'AWS',
                'gcp': 'GCP',
                'restful apis': 'REST APIs',
                'html / css': 'HTML/CSS',
                'ci/cd': 'CI/CD',
                'selenium / automation': 'Selenium automation',
                'relational database': 'SQL/RDBMS',
                'nosql database': 'NoSQL',
                'batch processing': 'Spring Batch'
            }
            return mapping.get(t.lower(), t)

        tech_candidates = [
            _format_tech_name(s) for s in matched_skills 
            if s.lower() not in ('agile', 'unit testing', 'ci/cd', 'version control', 'relational database', 'nosql database', 'build tools', 'domain')
        ]
        if not tech_candidates:
            tech_candidates = ['Java', 'Spring Boot', 'Microservices']

        selected_tech = tech_candidates[:3]
        if len(selected_tech) == 1:
            tech_str = selected_tech[0]
        elif len(selected_tech) == 2:
            tech_str = f"{selected_tech[0]} and {selected_tech[1]}"
        else:
            tech_str = f"{selected_tech[0]}, {selected_tech[1]}, and {selected_tech[2]}"

        # Natural Greetings
        if recruiter_name and recruiter_name.lower() not in ('hiring team', 'team', 'hiring manager', 'there'):
            greetings = [
                f"Hi {recruiter_name},",
                f"Hello {recruiter_name},",
                f"Hi {recruiter_name}, hope you are doing well.",
                f"Hi {recruiter_name}, hope you are having a great week."
            ]
        else:
            greetings = [
                "Hi there,",
                "Hello,",
                "Hi, hope you are doing well."
            ]
        greeting = random.choice(greetings)

        # Natural Openings
        openings = [
            f"I recently came across the {clean_role} position you posted and wanted to reach out directly.",
            f"I saw your posting for the {clean_role} role and thought my background would be a strong match.",
            f"I noticed your requirement for the {clean_role} role and wanted to share my profile with you.",
            f"I am writing to express my interest in the {clean_role} opportunity you are currently hiring for."
        ]
        opening = random.choice(openings)

        # Natural Technical Context
        contexts = [
            f"I have 10+ years of extensive hands-on experience in enterprise software engineering, with a deep focus on {tech_str}. Throughout my career, I have designed and delivered scalable backend microservices, modern cloud solutions, and resilient distributed architectures.",
            f"I bring over 10 years of technical experience specializing in {tech_str}. I have a consistent track record of leading complex technical implementations, optimizing high-performance applications, and collaborating effectively with cross-functional teams.",
            f"Over the past decade, my work has centered heavily around {tech_str}. I have extensive experience building mission-critical services and driving cloud modernization initiatives from concept to production."
        ]
        context_para = random.choice(contexts)

        # Natural Call to Action
        closings = [
            "Please review my attached resume and let me know if my profile aligns with your requirements. I would welcome the opportunity to discuss how I can contribute.",
            "I have attached my resume for your review. Please feel free to reach out by phone or email if you would like to connect for a brief discussion.",
            "Please take a look at my attached resume. If this aligns with what your client is looking for, I would be glad to set up a quick call."
        ]
        closing = random.choice(closings)

        plain_text = f"""{greeting}

{opening} {context_para}

{closing}

Experience: 10+ years
Visa: H1B from 2024-2027

Best regards,
Nithin Chiguru
Phone: +1 (312) 358-4463
Email: nithin.chiguru9@gmail.com
LinkedIn: https://www.linkedin.com/in/nithinch/"""

        html = f"""<div dir="ltr" style="font-family: Arial, Helvetica, sans-serif; font-size: 13.33px; color: #222222; line-height: 1.55;">
  <p>{greeting}</p>
  <p>{opening} {context_para}</p>
  <p>{closing}</p>
  <p style="margin-top: 16px;">
    <strong>Experience:</strong> 10+ years<br>
    <strong>Visa:</strong> H1B from 2024-2027
  </p>
  <p style="margin-top: 16px;">
    Best regards,<br>
    <strong>Nithin Chiguru</strong><br>
    Phone: +1 (312) 358-4463<br>
    Email: <a href="mailto:nithin.chiguru9@gmail.com" style="color: #1155cc;">nithin.chiguru9@gmail.com</a><br>
    LinkedIn: <a href="https://www.linkedin.com/in/nithinch/" style="color: #1155cc;">https://www.linkedin.com/in/nithinch/</a>
  </p>
</div>"""

        return plain_text, html

    def _text_to_gmail_html(self, text: str) -> str:
        """Convert plain text to clean Gmail web compose styled HTML."""
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        html_paras = []
        for p in paragraphs:
            lines = p.split("\n")
            para_html = "<br>".join(lines)
            para_html = re.sub(r'(https?://[^\s]+)', r'<a href="\1" style="color: #1155cc;">\1</a>', para_html)
            para_html = re.sub(r'([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)', r'<a href="mailto:\1" style="color: #1155cc;">\1</a>', para_html)
            html_paras.append(f"<p>{para_html}</p>")

        return f"""<div dir="ltr" style="font-family: Arial, Helvetica, sans-serif; font-size: 13.33px; color: #222222; line-height: 1.55;">
{''.join(html_paras)}
</div>"""

    def prepare_email_message(
        self,
        recipient_email: str,
        context: Dict[str, Any],
        resume_attachment_path: Optional[str] = None,
        matching_result: Optional[Dict[str, Any]] = None,
        extra_cc_emails: Optional[list] = None
    ) -> Tuple[MIMEMultipart, str]:
        """Create a full MIME email with body and attachment styled authentically as human-composed.
        Returns: (MIMEMultipart message, dynamic_attachment_filename)
        """
        msg = MIMEMultipart("mixed")
        sender_addr = self.smtp_config.get("sender_email") or self.candidate_info.get("email")
        sender_name = self.smtp_config.get("sender_name") or self.candidate_info.get("name")

        msg["From"] = f"{sender_name} <{sender_addr}>" if sender_name else sender_addr
        msg["To"] = recipient_email
        msg["Subject"] = self.render_template(self.subject_template, context)

        # Handle CC recipients (configured global CCs + any extra job-specific CCs)
        all_cc = list(self.configured_cc_emails)
        if extra_cc_emails:
            all_cc.extend(extra_cc_emails)

        valid_cc = []
        recip_lower = recipient_email.lower().strip()

        for c in all_cc:
            clean_c = str(c).strip()
            c_lower = clean_c.lower()
            if re.match(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$', c_lower):
                if c_lower != recip_lower and c_lower not in [v.lower() for v in valid_cc]:
                    valid_cc.append(clean_c)

        if valid_cc:
            msg["Cc"] = ", ".join(valid_cc)

        # Authentic RFC 2822 Headers matching real personal email clients
        msg["Date"] = email.utils.formatdate(localtime=True)
        msg["Message-ID"] = email.utils.make_msgid(domain="gmail.com")

        # Create alternative part for text / html
        alt_part = MIMEMultipart("alternative")
        if self.use_ai_humanizer:
            body_txt, body_html = self.compose_human_email(context, matching_result)
        else:
            body_txt = self.render_template(self.template_txt, context) if self.template_txt else ""
            body_html = self.render_template(self.template_html, context) if self.template_html else ""

        if body_txt:
            alt_part.attach(MIMEText(body_txt, "plain", "utf-8"))
        if body_html:
            alt_part.attach(MIMEText(body_html, "html", "utf-8"))

        msg.attach(alt_part)

        # Attach resume using in-memory bytes OR disk file with zero-disk conversion
        dynamic_filename = ""
        resume_bytes = matching_result.get("resume_bytes") if matching_result else None
        custom_filename = matching_result.get("filename") if matching_result else None

        if resume_bytes:
            dynamic_filename = custom_filename or f"Nithin_Chiguru_{context.get('job_title', 'Java_Developer')}_Resume.docx"
            dynamic_filename = re.sub(r'[^a-zA-Z0-9_.-]', '_', dynamic_filename)
            try:
                part = MIMEBase("application", "vnd.openxmlformats-officedocument.wordprocessingml.document")
                part.set_payload(resume_bytes)
                encoders.encode_base64(part)
                part.add_header("Content-Disposition", f'attachment; filename="{dynamic_filename}"')
                msg.attach(part)
            except Exception as e:
                print(f"[Mailer] Warning attaching in-memory resume: {e}")
        elif resume_attachment_path and os.path.exists(resume_attachment_path):
            attachment_name = custom_filename or os.path.basename(resume_attachment_path)
            attachment_name = re.sub(r'[^a-zA-Z0-9_.-]', '_', attachment_name)
            try:
                with open(resume_attachment_path, "rb") as f:
                    file_bytes = f.read()

                ext = os.path.splitext(attachment_name)[1].lower()
                if ext == ".pdf":
                    mime_main, mime_sub = "application", "pdf"
                elif ext == ".docx":
                    mime_main, mime_sub = "application", "vnd.openxmlformats-officedocument.wordprocessingml.document"
                else:
                    mime_main, mime_sub = "application", "octet-stream"

                part = MIMEBase(mime_main, mime_sub)
                part.set_payload(file_bytes)
                encoders.encode_base64(part)
                part.add_header("Content-Disposition", f'attachment; filename="{attachment_name}"')
                msg.attach(part)
                dynamic_filename = attachment_name
            except Exception as e:
                print(f"[Mailer] Warning attaching resume {resume_attachment_path}: {e}")

        return msg, dynamic_filename

    def send_application(
        self,
        recipient_email: str,
        job_details: Dict[str, Any],
        matching_result: Dict[str, Any],
        tracker: Optional[Any] = None
    ) -> Dict[str, Any]:
        """Dispatch application email (or simulate in dry_run mode) with Gmail volume protection."""
        context = self.build_context(job_details, matching_result)
        resume_path = matching_result.get("resume_path")

        # Pass any recruiter CC emails extracted from job details
        extra_cc = job_details.get("cc_emails") or []
        msg, dynamic_attachment = self.prepare_email_message(
            recipient_email, context, resume_path, matching_result, extra_cc_emails=extra_cc
        )

        # Extract CC recipients from msg header for SMTP envelope and logs
        cc_header = msg.get("Cc", "")
        cc_addrs = [c.strip() for c in cc_header.split(",") if c.strip()] if cc_header else []
        envelope_recipients = [recipient_email] + cc_addrs

        if self.dry_run:
            print("\n" + "=" * 70)
            print(f"  [DRY RUN PREVIEW] - Authentic Human Email to: {recipient_email}")
            if cc_addrs:
                print(f"  Cc: {', '.join(cc_addrs)}")
            print(f"  Subject: {msg['Subject']}")
            print(f"  Resume Attached: {dynamic_attachment or 'None'} (Dynamic Professional Format - 100% Original Layout)")
            print(f"  Technology Match: {matching_result.get('match_percentage')}%")
            print("-" * 70)
            if self.use_ai_humanizer:
                preview_body, _ = self.compose_human_email(context, matching_result)
            else:
                preview_body = self.render_template(self.template_txt, context)
            for line in preview_body.split("\n"):
                print(f"  | {line}")
            print("=" * 70 + "\n")
            return {
                "success": True,
                "status": "dry_run",
                "recipient": recipient_email,
                "cc": cc_addrs,
                "subject": msg["Subject"],
                "resume": dynamic_attachment or (os.path.basename(resume_path) if resume_path else "")
            }

        # LIVE SENDING VIA SMTP - GMAIL VOLUME & THROTTLING PROTECTION
        if tracker:
            # Pre-flight guard: ensure the same recruiter has not already received an email for this same job posting today
            if not self.dry_run:
                is_dup, dup_reason = tracker.is_same_job_posting_applied(
                    job_details.get("job_id", ""),
                    vendor_email=recipient_email,
                    job_title=job_details.get("title", ""),
                    job_description=job_details.get("description", ""),
                    is_dry_run=False,
                    candidate_emails=job_details.get("all_emails", []),
                    recruiter_phone=job_details.get("recruiter_phone", ""),
                    same_day_only=True
                )
                if is_dup:
                    print(f"\n  🛑 MAILER PRE-FLIGHT DUPLICATE GUARD: Blocked send to {recipient_email}: {dup_reason}")
                    return {
                        "success": False,
                        "status": "already_applied",
                        "error": dup_reason
                    }

            sent_today = tracker.get_live_sent_today()
            if sent_today >= self.daily_safe_cap:
                msg_err = f"Daily safe sending limit ({sent_today}/{self.daily_safe_cap}) reached today."
                print(f"\n  🛑 GMAIL REPUTATION GUARD: {msg_err}")
                print(f"     Pausing live sends to guarantee zero Gmail restrictions or spam detection.")
                return {
                    "success": False,
                    "status": "throttled_daily_cap",
                    "error": msg_err
                }

            sent_hour = tracker.get_live_sent_last_hour()
            if sent_hour >= self.hourly_limit:
                wait_secs = tracker.get_seconds_until_next_hourly_slot()
                print(f"\n  ⏳ GMAIL BURST GUARD: Hourly limit ({sent_hour}/{self.hourly_limit}) reached.")
                print(f"     Holding sending for {wait_secs}s to maintain natural human cadence...")
                if 0 < wait_secs <= 120:
                    time.sleep(wait_secs)

        host = str(self.smtp_config.get("host") or "").strip()
        port = int(self.smtp_config.get("port", 587))
        user = str(self.smtp_config.get("username") or self.smtp_config.get("sender_email") or "").strip()
        raw_password = str(self.smtp_config.get("password") or "").strip()
        password = raw_password.replace(" ", "")
        use_tls = bool(self.smtp_config.get("use_tls", True))

        if not host or not user or not password:
            err = "SMTP configuration incomplete. Host, user, or password missing."
            print(f"[Mailer] Error: {err}")
            return {"success": False, "status": "failed", "error": err}

        try:
            cc_str = f" (CC: {', '.join(cc_addrs)})" if cc_addrs else ""
            print(f"[Mailer] Connecting to {host}:{port} to send application to {recipient_email}{cc_str}...")
            server = smtplib.SMTP(host, port, timeout=25)
            server.ehlo()
            if use_tls:
                server.starttls()
                server.ehlo()
            server.login(user, password)
            server.sendmail(user, envelope_recipients, msg.as_string())
            server.quit()
            print(f"[Mailer] Successfully sent application with '{dynamic_attachment}' to {recipient_email}{cc_str}!")

            # Natural human pacing delay with randomized jitter
            self.consecutive_sends += 1
            jitter = random.uniform(self.min_jitter, self.max_jitter)
            if self.consecutive_sends % 5 == 0:
                extra = random.uniform(20.0, 40.0)
                jitter += extra
                print(f"[Mailer] Natural human reading break after 5 sends: {round(jitter, 1)}s pause...")
            else:
                print(f"[Mailer] Natural human delay before next application: {round(jitter, 1)}s...")
            time.sleep(jitter)

            return {
                "success": True,
                "status": "applied",
                "recipient": recipient_email,
                "cc": cc_addrs,
                "subject": msg["Subject"],
                "resume": dynamic_attachment or (os.path.basename(resume_path) if resume_path else "")
            }
        except smtplib.SMTPResponseException as e:
            err_text = f"SMTP {e.smtp_code}: {e.smtp_error.decode('utf-8', 'ignore') if isinstance(e.smtp_error, bytes) else e.smtp_error}"
            print(f"[Mailer] SMTP error sending to {recipient_email}: {err_text}")
            if e.smtp_code in (421, 550):
                print(f"  ⚠️ Google SMTP Rate Limit reached. Pausing...")
            return {"success": False, "status": "failed", "error": err_text}
        except Exception as e:
            print(f"[Mailer] Failed to send email to {recipient_email}: {e}")
            return {"success": False, "status": "failed", "error": str(e)}
