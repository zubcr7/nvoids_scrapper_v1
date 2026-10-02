"""Nvoids Job Portal Scraper.

Fetches Java Developer and Java Full Stack Developer job postings,
decodes Cloudflare protected emails, verifies USA & C2C suitability,
and extracts recruiter contact details.
"""
import re
import ssl
import time
import datetime
import urllib.request
import urllib.parse
from html.parser import HTMLParser
from typing import List, Dict, Any, Optional, Set

class NvoidsScraper:
    BASE_URL = "https://www.nvoids.com"
    SEARCH_URL = "https://www.nvoids.com/search_sph.jsp"
    INDEX_URL = "https://www.nvoids.com/index.jsp"

    IGNORE_EMAIL_DOMAINS = {
        "nvoids.com", "jobs.nvoids.com", "yandex.ru", "google.com", "clarity.ms"
    }
    IGNORE_EMAIL_PREFIXES = {
        "admin@", "support@", "noreply@", "no-reply@", "post@", "kill@", "job_kill@"
    }

    def __init__(self, headers: Optional[Dict[str, str]] = None):
        self.headers = headers or {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        # Create unverified SSL context for environments missing macOS root certs
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE

    def _fetch_url(self, url: str, post_data: Optional[Dict[str, str]] = None, timeout: int = 35, retries: int = 2) -> str:
        """Fetch URL content via urllib with custom headers, SSL handling, and retry logic."""
        data_bytes = None
        if post_data:
            data_bytes = urllib.parse.urlencode(post_data).encode("utf-8")
        req = urllib.request.Request(url, data=data_bytes, headers=self.headers)
        
        for attempt in range(1, retries + 1):
            try:
                with urllib.request.urlopen(req, context=self.ssl_context, timeout=timeout) as response:
                    return response.read().decode("utf-8", errors="ignore")
            except Exception as e:
                if attempt < retries:
                    time.sleep(2)
                    continue
                print(f"[Scraper] Error fetching {url} (attempt {attempt}/{retries}): {e}")
                return ""
        return ""


    @staticmethod
    def decode_cloudflare_email(cf_hex: str) -> str:
        """Decode Cloudflare XOR-obfuscated email address."""
        if not cf_hex or len(cf_hex) < 4:
            return ""
        try:
            k = int(cf_hex[:2], 16)
            email = "".join(
                chr(int(cf_hex[i:i+2], 16) ^ k)
                for i in range(2, len(cf_hex), 2)
            )
            return email.strip()
        except Exception:
            return ""

    def get_search_results(self, search_val: str, hotlist_filter: int = 1) -> List[Dict[str, str]]:
        """Query Nvoids search_sph.jsp and return list of job link references."""
        post_data = {
            "search_val": search_val,
            "hotlist": str(hotlist_filter)  # 1 = Exclude Hotlists
        }
        html = self._fetch_url(self.SEARCH_URL, post_data=post_data)
        if not html:
            return []

        # Find all job_details links and titles: <a href="job_details.jsp?id=3678923&uid=... ">Title</a>
        pattern = re.compile(
            r'<a\s+href=[\'"](job_details\.jsp\?id=(\d+)&(?:amp;)?uid=([a-f0-9]+))[\'"][^>]*>(.*?)</a>',
            re.DOTALL | re.IGNORECASE
        )
        matches = pattern.findall(html)
        jobs = []
        seen_ids = set()

        for match in matches:
            full_link = match[0].replace("&amp;", "&")
            job_id = match[1]
            uid = match[2]
            raw_title = re.sub(r'<[^>]+>', ' ', match[3]).strip()
            if job_id and job_id not in seen_ids:
                seen_ids.add(job_id)
                jobs.append({
                    "job_id": job_id,
                    "uid": uid,
                    "url": f"{self.BASE_URL}/{full_link}",
                    "title": raw_title
                })

        if not jobs:
            # Fallback regex if link tag formatting varies
            fallback_pat = re.compile(r'href=[\'"](job_details\.jsp\?id=(\d+)&amp;uid=([a-f0-9]+)|job_details\.jsp\?id=(\d+)&uid=([a-f0-9]+))[\'"]')
            for match in fallback_pat.findall(html):
                full_link = match[0].replace("&amp;", "&")
                job_id = match[1] or match[3]
                uid = match[2] or match[4]
                if job_id and job_id not in seen_ids:
                    seen_ids.add(job_id)
                    jobs.append({
                        "job_id": job_id,
                        "uid": uid,
                        "url": f"{self.BASE_URL}/{full_link}",
                        "title": ""
                    })
        return jobs

    def get_latest_stream_jobs(self, max_pages: int = 2) -> List[Dict[str, str]]:
        """Fetch the latest jobs directly from the home feed (index.jsp) for real-time monitoring."""
        jobs = []
        seen_ids = set()
        for p in range(max_pages):
            url = f"{self.INDEX_URL}?p={p}" if p > 0 else self.INDEX_URL
            html = self._fetch_url(url)
            if not html:
                break
            pattern = re.compile(
                r'<a\s+href=[\'"](job_details\.jsp\?id=(\d+)&(?:amp;)?uid=([a-f0-9]+))[\'"][^>]*>(.*?)</a>',
                re.DOTALL | re.IGNORECASE
            )
            for match in pattern.findall(html):
                full_link = match[0].replace("&amp;", "&")
                job_id = match[1]
                uid = match[2]
                raw_title = re.sub(r'<[^>]+>', ' ', match[3]).strip()
                if job_id and job_id not in seen_ids:
                    seen_ids.add(job_id)
                    jobs.append({
                        "job_id": job_id,
                        "uid": uid,
                        "url": f"{self.BASE_URL}/{full_link}",
                        "title": raw_title
                    })
            if not jobs:
                # Fallback
                simple_pattern = re.compile(r'href=[\'"](job_details\.jsp\?id=(\d+)&amp;uid=([a-f0-9]+)|job_details\.jsp\?id=(\d+)&uid=([a-f0-9]+))[\'"]')
                for match in simple_pattern.findall(html):
                    full_link = match[0].replace("&amp;", "&")
                    job_id = match[1] or match[3]
                    uid = match[2] or match[4]
                    if job_id and job_id not in seen_ids:
                        seen_ids.add(job_id)
                        jobs.append({
                            "job_id": job_id,
                            "uid": uid,
                            "url": f"{self.BASE_URL}/{full_link}",
                            "title": ""
                        })
        return jobs

    def parse_job_details(self, job_url: str) -> Optional[Dict[str, Any]]:
        """Fetch and parse a job detail page to extract all metadata and body."""
        html = self._fetch_url(job_url)
        if not html:
            return None

        # 1. Decode all Cloudflare emails found in HTML
        cf_emails = []
        for m in re.finditer(r'data-cfemail=[\'"]([a-f0-9]+)[\'"]', html):
            decoded = self.decode_cloudflare_email(m.group(1))
            if decoded:
                cf_emails.append(decoded)
        for m in re.finditer(r'/cdn-cgi/l/email-protection#([a-f0-9]+)', html):
            decoded = self.decode_cloudflare_email(m.group(1))
            if decoded:
                cf_emails.append(decoded)

        # 2. Extract plain email from job_email.jsp?email=...
        url_emails = []
        for m in re.finditer(r'job_email\.jsp\?email=([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)', html):
            url_emails.append(m.group(1))

        # 3. Extract table rows containing the title, body, and timestamp
        # The structure is:
        # <table border="1">
        #   <tr><td>Title at Location</td></tr>
        #   <tr><td>Email: ...</td></tr>
        #   <tr><td>Full Description Body...</td></tr>
        #   <tr><td>... View All</td></tr>
        #   <tr><td> 01:00 AM 12-Sep-26 </td></tr>
        # </table>
        table_content = ""
        table_match = re.search(r'<table[^>]*>(.*?)</table>', html, re.DOTALL | re.IGNORECASE)
        if table_match:
            table_content = table_match.group(1)

        td_pattern = re.compile(r'<td[^>]*>(.*?)</td>', re.DOTALL | re.IGNORECASE)
        td_cells = [m.group(1).strip() for m in td_pattern.finditer(table_content)]

        title_location_raw = td_cells[0] if len(td_cells) > 0 else ""
        # Strip HTML tags
        title_location_clean = re.sub(r'<[^>]+>', ' ', title_location_raw).strip()

        # Separate Title and Location
        title = title_location_clean
        raw_location = "USA"
        if " at " in title_location_clean:
            parts = title_location_clean.rsplit(" at ", 1)
            title = parts[0].strip()
            raw_location = parts[1].strip()

        # Job description body is typically the largest <td> cell
        description_raw = ""
        for cell in td_cells:
            if len(cell) > len(description_raw):
                description_raw = cell

        # Clean description text: replace <br />, <br>, <p> with newlines, then remove HTML tags
        cleaned_desc = re.sub(r'<(?:br|p)[^>]*>', '\n', description_raw, flags=re.IGNORECASE)
        cleaned_desc = re.sub(r'<[^>]+>', ' ', cleaned_desc)
        # Normalize whitespace while preserving line breaks
        cleaned_desc = '\n'.join(' '.join(line.split()) for line in cleaned_desc.split('\n') if line.strip())

        # 4. Extract timestamp from table
        posted_date = None
        date_str = ""
        time_match = re.search(r'(\d{1,2}:\d{2}\s+(?:AM|PM)\s+\d{1,2}-[A-Za-z]{3}-\d{2,4})', table_content)
        if time_match:
            date_str = time_match.group(1)
            posted_date = self._parse_nvoids_timestamp(date_str)

        # 5. Extract all candidate emails from description text
        regex_emails = re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', cleaned_desc)

        # Combine all found emails in priority order: URL emails -> CF emails -> body emails
        all_emails = url_emails + cf_emails + regex_emails
        valid_emails = []
        for e in all_emails:
            e_lower = e.lower().strip()
            domain = e_lower.split('@')[-1] if '@' in e_lower else ''
            if domain in self.IGNORE_EMAIL_DOMAINS:
                continue
            if any(e_lower.startswith(pfx) for pfx in self.IGNORE_EMAIL_PREFIXES):
                continue
            if any(e_lower.endswith(ext) for ext in ('.png', '.jpg', '.jpeg', '.gif', '.js', '.css')):
                continue
            if e_lower not in [v.lower() for v in valid_emails]:
                valid_emails.append(e.strip())

        # Select primary recruiter email: prefer personal/corporate email over mailing list
        recruiter_email = ""
        for email_candidate in valid_emails:
            if "googlegroups.com" not in email_candidate.lower():
                recruiter_email = email_candidate
                break
        if not recruiter_email and valid_emails:
            recruiter_email = valid_emails[0]

        # Extract explicit CC emails if mentioned in the JD text (e.g. "cc: hr@company.com", "cc to: ...")
        cc_matches = re.findall(
            r'(?:cc|copy)\s*(?:to)?\s*[:\-]?\s*([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)',
            cleaned_desc,
            re.IGNORECASE
        )
        recruiter_cc_emails = []
        for cc_cand in cc_matches:
            cc_lower = cc_cand.lower().strip()
            domain = cc_lower.split('@')[-1] if '@' in cc_lower else ''
            if domain in self.IGNORE_EMAIL_DOMAINS:
                continue
            if any(cc_lower.startswith(pfx) for pfx in self.IGNORE_EMAIL_PREFIXES):
                continue
            if cc_lower != recruiter_email.lower() and cc_lower not in [c.lower() for c in recruiter_cc_emails]:
                recruiter_cc_emails.append(cc_cand.strip())

        # 6. Extract Recruiter Name
        recruiter_name = self._extract_recruiter_name(cleaned_desc, recruiter_email)

        # 7. Extract Recruiter Phone Number
        recruiter_phone = self._extract_recruiter_phone(cleaned_desc)

        # 8. Extract Refined Location (e.g. Philadelphia, PA or Remote)
        location = self._extract_location(title, cleaned_desc, raw_location)

        # 9. Extract Vendor / Company
        vendor_company = self._extract_company_name(cleaned_desc)

        # 10. Extract clean professional role title (strip recruiter fluff and locations)
        clean_title = self.clean_job_title(title)

        return {
            "title": title,
            "clean_title": clean_title,
            "location": location,
            "description": cleaned_desc,
            "recruiter_email": recruiter_email,
            "all_emails": valid_emails,
            "cc_emails": recruiter_cc_emails,
            "recruiter_name": recruiter_name,
            "recruiter_phone": recruiter_phone,
            "vendor_company": vendor_company,
            "posted_date": posted_date,
            "posted_date_str": date_str,
            "raw_html": html
        }

    @classmethod
    def clean_job_title(cls, raw_title: str, description: str = "") -> str:
        """Extract clean, canonical professional role name from noisy job post title.
        Example: 'We currently have 50 Full Stack openings across Engineer and Lead levels,
                  Open Positions : 30 Full Stack Developers & 20 Lead Full Stack Developers'
                 -> 'Full Stack Developer'
        Example: 'We are Looking for a Lead AWS Java Developer - Philadelphia, PA Locals only'
                 -> 'Lead AWS Java Developer'
        """
        if not raw_title or not raw_title.strip():
            return "Java Full Stack Developer"

        t = raw_title.strip()

        # 1. Clean HTML, brackets, and parentheses
        t = re.sub(r'<[^>]+>', ' ', t)
        t = re.sub(r'\([^)]*\)', ' ', t)
        t = re.sub(r'\[[^\]]*\]', ' ', t)

        # 2. Strip common recruiter preambles & announcement sentences
        preamble_patterns = [
            r'^.*?(?:openings\s+across|open\s+positions\s*:)\s*',
            r'^.*?(?:we\s+(?:currently\s+)?have\s+\d+\s+.*?(?:openings|positions).*?:)\s*',
            r'^(?:we\s+are\s+looking\s+for\s+(?:a|an)?|looking\s+for\s+(?:a|an)?)\s*',
            r'^(?:hiring\s+(?:for)?\s*(?:a|an)?)\s*[-:]?\s*',
            r'^(?:urgent\s+(?:need|job\s+opening|opening|requirement|role)\s*(?:for|on|:|\|)?)\s*',
            r'^(?:immediate\s+(?:need|opening|requirement)\s*(?:for|on|:|\|)?)\s*',
            r'^(?:local\s+need\s*(?:for|\|)?)\s*',
            r'^(?:direct\s+client\s+(?:need|requirement|opening)\s*(?:for|:)?)\s*',
            r'^(?:hotlist\s*:\s*(?:need|multiple)?\s*)',
            r'^(?:requirement\s+for\s*(?:a|an)?)\s*',
            r'^(?:top\s+qualified\s+.*?\s+for\s+)',
            r'^(?:100%\s+remote\s*[-–:]?\s*)',
            r'^(?:c2c\s+urgent\s+requirement\s*:\s*)'
        ]
        for p in preamble_patterns:
            t = re.sub(p, '', t, flags=re.IGNORECASE).strip(' -:|')

        # 3. If delimiters like ||, //, |, - exist, inspect segments
        for sep in [r'\s*\|\|\s*', r'\s*//\s*', r'\s*\|\s*']:
            if re.search(sep, t):
                parts = re.split(sep, t)
                for part in parts:
                    p_clean = part.strip(' -:|;')
                    if re.search(r'\b(java|developer|engineer|lead|architect|full\s*stack|backend)\b', p_clean, re.I):
                        if not re.search(r'^(?:c2c|need\s+resumes|local\s+need|\d+\s*years?|w2|remote|onsite|[A-Z\s]+,\s*[A-Z]{2})$', p_clean, re.I):
                            t = p_clean
                            break

        # 4. If quantities like '30 Full Stack Developers & 20 Lead Full Stack Developers' exist,
        # isolate the primary canonical role
        if re.search(r'\b\d+\s+(?:lead\s+)?full\s*stack\s+developers?\b', t, re.I):
            t = "Full Stack Developer"

        # 5. Regex for valid role noun phrases
        role_pattern = re.compile(
            r'\b('
            r'(?:Senior|Sr\.?|Lead|Principal|Staff|Technical|Tech)?\s*'
            r'(?:AWS\s+|Cloud\s+|Azure\s+|GCP\s+|Core\s+)?'
            r'(?:Java\s+)?'
            r'(?:Full\s*Stack|Backend|Frontend)?\s*'
            r'(?:Java\s+)?'
            r'(?:Developer|Engineer|Architect|Tech\s*Lead|Technical\s*Lead|Lead|Consultant|Specialist)s?'
            r'(?:\s+with\s+(?:Gen\s*AI|GenAI|AI|AWS|React|Angular|Kafka|Microservices|Multithreading|[A-Za-z0-9]+))?'
            r')\b',
            re.IGNORECASE
        )

        # Strip locations and work modes from t
        t = re.sub(r'\s*[-–,]\s*[A-Z][a-zA-Z\s]+,\s*[A-Z]{2}.*$', '', t, flags=re.I)
        t = re.sub(r'\s*[-–,]\s*(?:remote|onsite|hybrid|only\s+locals|in\s+person|locals?\s+only|c2c|w2|tcs|nyc|irving|chicago|dallas|austin|wilmington|philadelphia|charlotte).*$', '', t, flags=re.I)
        t = re.sub(r'\s+in\s+[A-Z][a-zA-Z\s,]+.*$', '', t, flags=re.I)
        t = re.sub(r'\s*[-–]\s*\d+\+?\s*years?.*$', '', t, flags=re.I)
        t = re.sub(r'^\d+\+?\s*years?\s+(?:of\s+experience\s+)?', '', t, flags=re.I)
        t = t.strip(' -–|:;,')

        # Check if t is already a concise role (2-6 words, no sentence words)
        sentence_words = {'have', 'has', 'we', 'are', 'is', 'openings', 'positions', 'across', 'levels', 'needed', 'wanted'}
        words = t.split()
        if 2 <= len(words) <= 6 and not any(w.lower() in sentence_words for w in words):
            if any(w.lower() in ('developer', 'engineer', 'lead', 'architect', 'specialist', 'consultant') for w in words):
                return cls._format_clean_title(t)

        # Otherwise extract candidate matching role_pattern
        matches = [m.group(1).strip() for m in role_pattern.finditer(t)]
        if matches:
            cands = []
            for m in matches:
                c = ' '.join(m.split())
                if len(c.split()) == 1 and c.lower() in ('engineer', 'developer', 'lead', 'architect'):
                    continue
                cands.append(c)
            if cands:
                return cls._format_clean_title(cands[0])

        # Fallback to description inspection or default
        if 'full stack' in t.lower() or 'fullstack' in t.lower() or 'full stack' in description.lower():
            return "Java Full Stack Developer"
        return "Java Developer"

    @staticmethod
    def _format_clean_title(title: str) -> str:
        """Format role title casing and acronyms."""
        t = title.strip(' -–|:;,')
        t = re.sub(r'^\d+\+?\s*years?\s+(?:of\s+experience\s+)?', '', t, flags=re.I)
        t = re.sub(r'\bDevelopers\b', 'Developer', t, flags=re.I)
        t = re.sub(r'\bEngineers\b', 'Engineer', t, flags=re.I)
        t = re.sub(r'\bLeads\b', 'Lead', t, flags=re.I)
        if t.lower() in ('lead java', 'java lead'):
            t = 'Lead Java Developer'
        elif t.lower() in ('full stack', 'fullstack'):
            t = 'Full Stack Developer'
        elif t.lower() == 'java':
            t = 'Java Developer'

        words = t.split()
        caps = []
        for w in words:
            if w.upper() in ('AWS', 'GCP', 'AI', 'J2EE', 'API', 'UI', 'REST', 'GENAI'):
                caps.append(w.upper())
            elif w.lower() == 'gen':
                caps.append('Gen')
            elif w.lower() == 'with':
                caps.append('with')
            elif w.lower() == 'for':
                caps.append('for')
            else:
                caps.append(w.capitalize())
        return ' '.join(caps)


    def _parse_nvoids_timestamp(self, ts_str: str) -> Optional[datetime.datetime]:
        """Parse Nvoids timestamp format (e.g., '01:00 AM 12-Sep-26')."""
        ts_str = ts_str.strip()
        for fmt in ("%I:%M %p %d-%b-%y", "%I:%M %p %d-%b-%Y"):
            try:
                return datetime.datetime.strptime(ts_str, fmt)
            except ValueError:
                pass
        return None

    def _extract_recruiter_name(self, text: str, email: str) -> str:
        """Attempt to extract recruiter's first name from signatures or email username."""
        def _clean_name(name_candidate: str) -> Optional[str]:
            if not name_candidate:
                return None
            n = re.sub(r'(?:linkedin|recruiter|hr|staffing|corp)$', '', name_candidate, flags=re.IGNORECASE).strip()
            if len(n) >= 3 and n.isalpha() and n.lower() not in ("team", "hiring", "dear", "best", "regards", "thanks"):
                return n.capitalize()
            return None

        # 1. Look for 'From:\s*([A-Za-z]+)'
        m = re.search(r'From:\s*([A-Z][a-z]+)', text)
        if m:
            clean = _clean_name(m.group(1).strip())
            if clean:
                return clean

        # 2. Look for 'My name is ([A-Z][a-z]+)'
        m = re.search(r'My name is\s+([A-Z][a-z]+)', text, re.IGNORECASE)
        if m:
            clean = _clean_name(m.group(1).strip())
            if clean:
                return clean

        # 3. Look for 'Thanks & Regards,\s*([A-Z][a-z]+)' or 'Best Regards,\s*([A-Z][a-z]+)'
        m = re.search(r'(?:Thanks\s+(?:&|and)\s+Regards|Best\s+Regards)[\s,:]+([A-Z][a-z]+)', text, re.IGNORECASE)
        if m:
            clean = _clean_name(m.group(1).strip())
            if clean:
                return clean

        # 4. Infer from email username (e.g. pinki.p@testingxperts.com -> Pinki, vickylinkedin@... -> Vicky)
        if email and "@" in email:
            uname = email.split("@")[0]
            name_part = re.split(r'[\._0-9]', uname)[0]
            clean = _clean_name(name_part)
            if clean:
                return clean

        return "Hiring Team"

    def _extract_recruiter_phone(self, text: str) -> str:
        """Extract US recruiter phone number from text or signatures."""
        if not text:
            return ""

        # 1. Look for explicit keyword labels: Phone: ..., Direct: ..., Desk: ..., Cell: ...
        labeled_pattern = re.compile(
            r'(?:phone|ph|tel|cell|mobile|direct|desk|call|reach\s+me\s+at)[\s.:#-]*'
            r'(\+?1?[\s.-]?\(?[2-9]\d{2}\)?[\s.-]?\d{3}[\s.-]?\d{4}(?:\s*(?:ext|x|extension)[\s.:]*\d{1,5})?)',
            re.IGNORECASE
        )
        match = labeled_pattern.search(text)
        if match:
            raw_phone = match.group(1).strip()
            # Verify it's not candidate's own number
            digits = re.sub(r'\D', '', raw_phone)
            if digits and not digits.endswith("3123584463") and len(digits) >= 10:
                return raw_phone

        # 2. Look for standalone phone format in the signature or bottom portion
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        tail_text = " \n ".join(lines[-15:]) if len(lines) > 15 else text

        general_pattern = re.compile(
            r'(?:\+?1[\s.-]?)?\(?([2-9]\d{2})\)?[\s.-]?([2-9]\d{2})[\s.-]?(\d{4})'
        )
        for m in general_pattern.finditer(tail_text):
            digits = m.group(1) + m.group(2) + m.group(3)
            if digits != "3123584463":
                return f"({m.group(1)}) {m.group(2)}-{m.group(3)}"

        return ""

    def _extract_location(self, title: str, text: str, raw_loc: str) -> str:
        """Refine job location from title, description keywords, and raw location."""
        # 1. If raw_loc already contains specific city/state, use it
        if raw_loc and raw_loc.strip() != "USA" and len(raw_loc.strip()) > 2:
            clean = raw_loc.strip(' -:|;')
            if re.search(r'[A-Z][a-zA-Z\s]+,\s*[A-Z]{2}', clean):
                return clean

        # 2. Check title for location patterns (e.g. "// Philadelphia, PA" or "- Dallas, TX")
        title_loc = re.search(r'[-–/|]\s*([A-Z][a-zA-Z\s]+,\s*[A-Z]{2})\b', title)
        if title_loc:
            return title_loc.group(1).strip()

        # 3. Check description for explicit 'Location:' fields
        desc_loc = re.search(
            r'(?:job\s+location|work\s+location|location)[\s:–-]+([A-Z][a-zA-Z\s]+,\s*[A-Z]{2}|Remote|Hybrid[^\n\r,.]*)',
            text, re.IGNORECASE
        )
        if desc_loc:
            cand = desc_loc.group(1).strip(' -:|;')
            if len(cand) <= 40 and not any(w in cand.lower() for w in ('experience', 'candidate', 'developer', 'require')):
                return cand

        # 4. Check for Remote / Hybrid indicators
        text_lower = text.lower()
        title_lower = title.lower()
        if "100% remote" in title_lower or "100% remote" in text_lower:
            return "Remote (USA)"
        if "remote" in title_lower or "remote" in text_lower[:200]:
            return "Remote"
        if "hybrid" in title_lower or "hybrid" in text_lower[:200]:
            return "Hybrid (USA)"

        return raw_loc.strip() if raw_loc else "USA"

    def _extract_company_name(self, text: str) -> str:
        """Extract staffing agency or vendor company name if present."""
        m = re.search(r'(?:at|with)\s+([A-Z][A-Za-z0-9\s&]{2,25}(?:Inc|LLC|Solutions|Technologies|Corp|Staffing|Systems|Consulting))', text)
        if m:
            return m.group(1).strip()
        m2 = re.search(r'From:[\s\S]*?\n\s*([A-Z][A-Za-z0-9\s&]{2,25}(?:Inc|LLC|Solutions|Technologies|Corp|Staffing|Systems|Consulting))', text)
        if m2:
            return m2.group(1).strip()
        return "Staffing Partner"

    def is_within_days_window(self, post_dt: Optional[datetime.datetime], days_back: int = 3) -> bool:
        """Check if posting date is within today, yesterday, and day before yesterday.
        Accounts for Nvoids server timezone (UTC/IST) which is up to +1 day ahead of US timezones.
        """
        if not post_dt:
            # If timestamp could not be parsed, keep by default or inspect text
            return True

        # Use current date (or reference date)
        now = datetime.datetime.now()
        # Include tomorrow's date (+1 day) to absorb timezone offsets (e.g. IST UTC+5:30 vs US EDT UTC-4)
        target_dates: Set[datetime.date] = {
            (now + datetime.timedelta(days=1)).date(),
            *{(now - datetime.timedelta(days=d)).date() for d in range(days_back)}
        }
        return post_dt.date() in target_dates

    def is_c2c_and_usa(self, title: str, location: str, description: str) -> bool:
        """Verify that the role is suitable for C2C in the USA, and NOT a bench marketing post."""
        combined = f"{title} {location} {description}".lower()
        title_lower = title.lower()

        # Filter out candidate/bench marketing in title
        if title_lower.startswith("interested in") or "-resume-" in title_lower or "resume-" in title_lower:
            return False

        # 1. Filter out candidate/bench marketing / hotlists that slipped through
        bench_indicators = [
            "available for new opportunities",
            "consultants are available",
            "candidate highlights:",
            "lead bench sales recruiter",
            "on our bench",
            "on the bench",
            "available on the bench",
            "marketing my consultant",
            "hotlist",
            "we have consultants available",
            "top qualified and interview ready consultants",
            "looking for c2c",
            "looking for new role",
            "available for c2c",
            "marketing consultant"
        ]
        if any(ind in combined for ind in bench_indicators):
            return False

        # 2. Strict W2 Only exclusion (e.g. "W2 only", "no c2c", "no 1099")
        w2_only_indicators = [
            "w2 only",
            "w-2 only",
            "no c2c",
            "no c-to-c",
            "no corp-to-corp",
            "no corp to corp",
            "no 1099",
            "strictly w2",
            "only w2",
            "w2 candidates only",
            "citizenship required w2"
        ]
        if any(ind in combined for ind in w2_only_indicators):
            return False

        # 3. Verify USA location
        # If location is explicitly specified as non-USA (e.g., India, UK, Canada only), skip
        if "india" in location.lower() and "usa" not in location.lower():
            return False

        # 4. C2C suitability:
        # On Nvoids, requirements are almost exclusively C2C unless stated W2 only.
        # Check for explicit C2C mentions or general contracting openings
        c2c_positive = [
            "c2c", "corp to corp", "corp-to-corp", "c-to-c", "corp2corp",
            "1099", "contract", "hourly rate", "$/hr", "/hr", "c2h"
        ]
        has_c2c_term = any(term in combined for term in c2c_positive)

        # As long as it's not W2 only and not a bench post, C2C is applicable
        return has_c2c_term or ("w2" not in combined)

    FRONTEND_PATTERNS = [
        re.compile(r'\bfull[- ]?stack\b', re.IGNORECASE),
        re.compile(r'\bfullstack\b', re.IGNORECASE),
        re.compile(r'\bfsd\b', re.IGNORECASE),
        re.compile(r'\bfront[- ]?end\b', re.IGNORECASE),
        re.compile(r'\b(react|reactjs|react\.js)\b', re.IGNORECASE),
        re.compile(r'\b(angular|angularjs)\b', re.IGNORECASE),
        re.compile(r'\b(vue|vuejs|vue\.js)\b', re.IGNORECASE),
        re.compile(r'\b(next|nextjs|next\.js)\b', re.IGNORECASE),
        re.compile(r'\btypescript\b', re.IGNORECASE),
        re.compile(r'\bjavascript\b', re.IGNORECASE),
        re.compile(r'\bredux\b', re.IGNORECASE),
        re.compile(r'\brx(?:js)?\b', re.IGNORECASE),
        re.compile(r'\bhtml5?\b', re.IGNORECASE),
        re.compile(r'\bcss3?\b', re.IGNORECASE),
        re.compile(r'\bsvelte\b', re.IGNORECASE),
        re.compile(r'\btailwind\b', re.IGNORECASE),
        re.compile(r'\bbootstrap\b', re.IGNORECASE),
        re.compile(r'\bui developer\b', re.IGNORECASE),
        re.compile(r'\bweb application development\b', re.IGNORECASE),
        re.compile(r'\bclient[- ]side\b', re.IGNORECASE)
    ]

    BACKEND_ONLY_TITLE_TERMS = [
        "backend", "back-end", "back end", "core java", "server-side", "server side"
    ]

    EXCLUDED_NICHE_PLATFORM_PATTERNS = [
        # BPM & Workflow Engines
        re.compile(r'\bcamunda\b', re.IGNORECASE),
        re.compile(r'\bbpmn\b', re.IGNORECASE),
        re.compile(r'\bjbpm\b', re.IGNORECASE),
        re.compile(r'\bflowable\b', re.IGNORECASE),
        re.compile(r'\bactiviti\b', re.IGNORECASE),
        re.compile(r'\bpega\b', re.IGNORECASE),
        re.compile(r'\bappian\b', re.IGNORECASE),

        # Enterprise Packaged Apps / ERP / Insurance Suites
        re.compile(r'\bguidewire\b', re.IGNORECASE),
        re.compile(r'\bclaimcenter\b', re.IGNORECASE),
        re.compile(r'\bpolicycenter\b', re.IGNORECASE),
        re.compile(r'\bbillingcenter\b', re.IGNORECASE),
        re.compile(r'\bsalesforce\b', re.IGNORECASE),
        re.compile(r'\bsfdc\b', re.IGNORECASE),
        re.compile(r'\bapex\b', re.IGNORECASE),
        re.compile(r'\bservicenow\b', re.IGNORECASE),
        re.compile(r'\bworkday\b', re.IGNORECASE),
        re.compile(r'\bpeoplesoft\b', re.IGNORECASE),
        re.compile(r'\bsap\b', re.IGNORECASE),
        re.compile(r'\babap\b', re.IGNORECASE),
        re.compile(r'\bhana\b', re.IGNORECASE),
        re.compile(r'\bfiori\b', re.IGNORECASE),
        re.compile(r'\bsiebel\b', re.IGNORECASE),

        # Integration / ESB / Middleware
        re.compile(r'\bmulesoft\b', re.IGNORECASE),
        re.compile(r'\bmule\b', re.IGNORECASE),
        re.compile(r'\btibco\b', re.IGNORECASE),
        re.compile(r'\bbiztalk\b', re.IGNORECASE),
        re.compile(r'\bboomi\b', re.IGNORECASE),
        re.compile(r'\bdell\s+boomi\b', re.IGNORECASE),
        re.compile(r'\bwebmethods\b', re.IGNORECASE),

        # Telephony / Contact Center
        re.compile(r'\bamazon\s+connect\b', re.IGNORECASE),
        re.compile(r'\bgenesys\b', re.IGNORECASE),
        re.compile(r'\bavaya\b', re.IGNORECASE),
        re.compile(r'\bfive9\b', re.IGNORECASE),

        # CMS / Portals
        re.compile(r'\baem\b', re.IGNORECASE),
        re.compile(r'\badobe\s+experience\s+manager\b', re.IGNORECASE),
        re.compile(r'\bsitecore\b', re.IGNORECASE),
        re.compile(r'\bdrupal\b', re.IGNORECASE),
        re.compile(r'\bwordpress\b', re.IGNORECASE),

        # Data Warehousing / Dedicated BI / ETL (when primary title)
        re.compile(r'\bsnowflake\s+architect\b', re.IGNORECASE),
        re.compile(r'\bsnowflake\s+developer\b', re.IGNORECASE),
        re.compile(r'\bdatabricks\b', re.IGNORECASE),
        re.compile(r'\binformatica\b', re.IGNORECASE),
        re.compile(r'\bdatastage\b', re.IGNORECASE),
        re.compile(r'\btalend\b', re.IGNORECASE),
        re.compile(r'\bpower\s*bi\b', re.IGNORECASE),
        re.compile(r'\btableau\b', re.IGNORECASE),
        re.compile(r'\bcognos\b', re.IGNORECASE),
        re.compile(r'\bteradata\b', re.IGNORECASE),

        # Legacy Systems
        re.compile(r'\bmainframe\b', re.IGNORECASE),
        re.compile(r'\bcobol\b', re.IGNORECASE),
        re.compile(r'\bpl/1\b', re.IGNORECASE),
        re.compile(r'\bas400\b', re.IGNORECASE),
        re.compile(r'\brpg\b', re.IGNORECASE),
        re.compile(r'\bpowerbuilder\b', re.IGNORECASE),
        re.compile(r'\bfilenet\b', re.IGNORECASE),

        # Identity & Security
        re.compile(r'\bsailpoint\b', re.IGNORECASE),
        re.compile(r'\bcyberark\b', re.IGNORECASE),
        re.compile(r'\bping\s+identity\b', re.IGNORECASE),
        re.compile(r'\bforgerock\b', re.IGNORECASE),

        # RPA
        re.compile(r'\buipath\b', re.IGNORECASE),
        re.compile(r'\bautomation\s+anywhere\b', re.IGNORECASE),
        re.compile(r'\bblue\s+prism\b', re.IGNORECASE)
    ]

    NON_JAVA_OR_NON_DEV_PATTERNS = [
        # Other primary programming languages
        re.compile(r'\.\s*net\b', re.IGNORECASE),
        re.compile(r'\basp\.?\s*net\b', re.IGNORECASE),
        re.compile(r'\bc#\b', re.IGNORECASE),
        re.compile(r'\bdotnet\b', re.IGNORECASE),
        re.compile(r'\bpython\b', re.IGNORECASE),
        re.compile(r'\bgolang\b', re.IGNORECASE),
        re.compile(r'\bruby\b', re.IGNORECASE),
        re.compile(r'\bphp\b', re.IGNORECASE),
        re.compile(r'\bios\b', re.IGNORECASE),
        re.compile(r'\bandroid\b', re.IGNORECASE),
        re.compile(r'\bflutter\b', re.IGNORECASE),

        # Management & Business Analysis
        re.compile(r'\bproject manager\b', re.IGNORECASE),
        re.compile(r'\bprogram manager\b', re.IGNORECASE),
        re.compile(r'\bproduct manager\b', re.IGNORECASE),
        re.compile(r'\bproduct owner\b', re.IGNORECASE),
        re.compile(r'\bscrum master\b', re.IGNORECASE),
        re.compile(r'\bagile coach\b', re.IGNORECASE),
        re.compile(r'\bbusiness analyst\b', re.IGNORECASE),
        re.compile(r'\bdata analyst\b', re.IGNORECASE),
        re.compile(r'\bsystems? analyst\b', re.IGNORECASE),

        # QA & Testing
        re.compile(r'\bqa\b', re.IGNORECASE),
        re.compile(r'\bsdet\b', re.IGNORECASE),
        re.compile(r'\bquality assurance\b', re.IGNORECASE),
        re.compile(r'\bautomation tester\b', re.IGNORECASE),
        re.compile(r'\bmanual tester\b', re.IGNORECASE),
        re.compile(r'\bmobile automation\b', re.IGNORECASE),
        re.compile(r'\bpenetration tester\b', re.IGNORECASE),
        re.compile(r'\bpen\s+tester\b', re.IGNORECASE),

        # Data & Database Admin
        re.compile(r'\bdata engineer\b', re.IGNORECASE),
        re.compile(r'\bdatabase administrator\b', re.IGNORECASE),
        re.compile(r'\bdba\b', re.IGNORECASE),

        # Infrastructure & Networking
        re.compile(r'\binfrastructure\b', re.IGNORECASE),
        re.compile(r'\bnetwork engineer\b', re.IGNORECASE),
        re.compile(r'\bnetwork administrator\b', re.IGNORECASE),
        re.compile(r'\bnetwork analyst\b', re.IGNORECASE),
        re.compile(r'\bstorage engineer\b', re.IGNORECASE),
        re.compile(r'\bstorage administrator\b', re.IGNORECASE),

        # Systems & OS Administration
        re.compile(r'\bsys(?:tem)?s?\s+admin(?:istrator)?\b', re.IGNORECASE),
        re.compile(r'\blinux\s+admin(?:istrator)?\b', re.IGNORECASE),
        re.compile(r'\bunix\s+admin(?:istrator)?\b', re.IGNORECASE),
        re.compile(r'\bwindows\s+admin(?:istrator)?\b', re.IGNORECASE),

        # Architecture roles that are NOT hands-on developer roles
        re.compile(r'\bsolutions?\s+architect\b', re.IGNORECASE),
        re.compile(r'\benterprise\s+architect\b', re.IGNORECASE),
        re.compile(r'\bsecurity\s+architect\b', re.IGNORECASE),
        re.compile(r'\bnetwork\s+architect\b', re.IGNORECASE),
        re.compile(r'\bcloud\s+architect\b', re.IGNORECASE),
        re.compile(r'\bdata\s+architect\b', re.IGNORECASE),
        re.compile(r'\bstorage\s+architect\b', re.IGNORECASE),
        re.compile(r'\bsystems?\s+architect\b', re.IGNORECASE),
        re.compile(r'\bcloud\s+solutions?\b', re.IGNORECASE),

        # Support, Incident, SRE & Operations
        re.compile(r'\bdesktop\s+support\b', re.IGNORECASE),
        re.compile(r'\bhelpdesk\b', re.IGNORECASE),
        re.compile(r'\btechnical\s+support\b', re.IGNORECASE),
        re.compile(r'\bit\s+support\b', re.IGNORECASE),
        re.compile(r'\bproduction\s+support\b', re.IGNORECASE),
        re.compile(r'\bsite\s+reliability\b', re.IGNORECASE),
        re.compile(r'\bsre\b', re.IGNORECASE),
        re.compile(r'\brelease\s+(?:manager|engineer)\b', re.IGNORECASE),
        re.compile(r'\bincident\s+(?:manager|engineer)\b', re.IGNORECASE),
        re.compile(r'\bforensics\b', re.IGNORECASE),
        re.compile(r'\bcyber\s*security\b', re.IGNORECASE),
        re.compile(r'\binformation\s+security\b', re.IGNORECASE),
        re.compile(r'\bsoc\s+analyst\b', re.IGNORECASE)
    ]

    def is_java_developer_role(self, title: str, description: str, full_stack_only: bool = True) -> bool:
        """Ensure the role is indeed Java Developer or strictly Java Full Stack Developer if full_stack_only is True."""
        title_lower = title.lower()
        desc_lower = description.lower()

        # 0. STRICT FILTER: Disqualify any role whose title specifies an excluded niche platform/tool
        # (Camunda, Guidewire, MuleSoft, Salesforce, Pega, Amazon Connect, Snowflake, etc.)
        # Even if Java is mentioned in the title (e.g. "Sr. Java FSD - Camunda 7" or "Guidewire Java Integration"),
        # these roles require dedicated proprietary suite experience and MUST be excluded.
        for p in self.EXCLUDED_NICHE_PLATFORM_PATTERNS:
            if p.search(title_lower):
                return False

        # 1. Non-Java primary programming languages & non-developer roles
        for p in self.NON_JAVA_OR_NON_DEV_PATTERNS:
            if p.search(title_lower):
                return False

        has_java_in_title = bool(re.search(r'\b(?:java|j2ee)\b', title_lower))

        # 2. Generic Engineering Title Scope Check when Java is not in title:
        # If Java is NOT in the title, the title MUST explicitly be a recognized software engineering title:
        # e.g. "Full Stack Developer", "Software Engineer", "Application Developer", "Backend Developer", "Technical Lead"
        # Otherwise reject (e.g. "Cloud Consultant", "Integration Architect", "Platform Specialist")
        if not has_java_in_title:
            accepted_generic_dev_pattern = re.compile(
                r'\b(?:full[- ]?stack|fullstack|fsd|software\s*(?:engineer|developer)|application\s*developer|backend\s*(?:engineer|developer)|lead\s*(?:developer|engineer)|technical\s*lead)\b',
                re.IGNORECASE
            )
            if not accepted_generic_dev_pattern.search(title_lower):
                return False

        # 3. Java / Full Stack Backend Presence Check
        has_fs_in_title = any(fs in title_lower for fs in ["full stack", "fullstack", "full-stack", "fsd"])
        java_in_desc = bool(re.search(r'\b(?:java|j2ee)\b', desc_lower))
        spring_in_desc = bool(re.search(r'\b(?:spring|spring\s*boot)\b', desc_lower))

        # Must have genuine Java/Spring presence
        if not (has_java_in_title or java_in_desc or spring_in_desc):
            return False

        # If full_stack_only is False, accept general Java Developer roles
        if not full_stack_only:
            return True

        # 4. Full Stack Enforcement:
        # Reject explicit backend-only titles (e.g. "Java Backend Developer", "Core Java Developer")
        if any(b in title_lower for b in self.BACKEND_ONLY_TITLE_TERMS) and not has_fs_in_title:
            return False

        # Positive match if title indicates fullstack or frontend
        title_has_fe = has_fs_in_title or any(fe in title_lower for fe in ["react", "angular", "vue", "frontend", "front-end", "ui"])
        if title_has_fe:
            return True

        # If title is general Java Developer / Software Engineer, check description for frontend requirements
        has_fe_in_desc = any(p.search(desc_lower) for p in self.FRONTEND_PATTERNS)
        return has_fe_in_desc

    def is_java_full_stack_role(self, title: str, description: str) -> bool:
        """Convenience method to check specifically for Java Full Stack Developer openings."""
        return self.is_java_developer_role(title, description, full_stack_only=True)

