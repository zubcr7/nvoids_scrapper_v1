# Nvoids C2C Job Application Bot
### Automated Java Developer & Java Full Stack Developer Job Applier

An automated bot engineered to discover, filter, match, and apply for recent **Java Developer** and **Java Full Stack Developer** C2C (Corp-to-Corp) positions in the USA on [Nvoids](https://www.nvoids.com).

---

## Key Features

1. **Targeted Roles**: Specifically targets **Java Developer** and **Java Full Stack Developer** positions.
2. **Date Window (Last 3 Days)**: Scrapes and processes all positions posted on **today, yesterday, and the day before yesterday**.
3. **Continuous Real-Time Monitoring**: After the initial 3-day scan, the bot enters a continuous loop polling the Nvoids live stream for new postings every 3 minutes until manually stopped (Ctrl+C).
4. **Strict Match Cutoff (>= 93%)**: Evaluates all candidate resumes against job descriptions. If a job has **less than 93% match**, it is automatically skipped.
5. **Best Resume Selection**: Evaluates all resumes in `resumes/` (supporting `.pdf`, `.docx`, and `.txt`) and picks the candidate profile with the highest alignment score (targeting 95–99% match).
6. **Automatic Email & Contact Extraction**:
   - Decodes Cloudflare email protection (`data-cfemail` XOR cipher).
   - Extracts recruiter emails from URLs, headers, and description text.
   - Filters out spam traps, mailing lists, and system emails.
7. **Email Templating & Dispatch**:
   - Custom template (`templates/email_template.txt` and `templates/email_template.html`).
   - Replaces placeholders: `{{recruiter_name}}`, `{{job_title}}`, `{{location}}`, `{{match_percentage}}`, `{{matched_skills}}`, `{{candidate_name}}`, etc.
   - Attaches the selected resume (PDF or DOCX).
   - Rate limiting delay to protect your sender reputation.
8. **Safe Dry-Run Mode**: Defaults to preview mode (`--dry-run`) so you can inspect rendered emails and matched scores before enabling live email dispatch.
9. **Zero-Duplicate Tracker (3-Layer Protection)**: Built-in SQLite database (`data/applied_jobs.db`) provides ironclad deduplication:
   - **Layer 1 (Job ID)**: Never applies to the same job posting ID twice.
   - **Layer 2 (Recruiter + Job Repost)**: Detects when recruiters repost the same requirement under a new job ID and skips the duplicate.
   - **Layer 3 (Recruiter Cooldown)**: Prevents sending multiple emails to the same recruiter contact within a 7-day window.


---

## Directory Structure

```
nvoids-job-applier/
├── config/
│   ├── config.json               # Search terms, thresholds, candidate info, SMTP config
│   └── .env.example              # Environment variables template for email credentials
├── templates/
│   ├── email_template.txt        # Plain text template for outgoing applications
│   └── email_template.html       # HTML formatted template with skills table
├── resumes/                      # Drop your candidate resumes here (.pdf, .docx, .txt)
│   ├── sample_senior_java_fullstack_resume.txt
│   └── sample_java_backend_developer_resume.txt
├── src/
│   ├── scraper.py                # Nvoids scraper & Cloudflare email decoder
│   ├── matcher.py                # Resume parser & keyword matching engine
│   ├── mailer.py                 # SMTP email dispatcher & template renderer
│   ├── tracker.py                # SQLite deduplication & stats database
│   └── bot.py                    # Orchestrator & continuous monitoring loop
├── main.py                       # CLI entry point
├── setup.sh                      # Setup script
└── requirements.txt              # Optional dependencies (pure Python fallback included)
```

---

## Running in Visual Studio Code (VS Code)

The project includes preconfigured **VS Code 1-Click Debug Profiles** and **Tasks** in `.vscode/`.

### 1. Open the Project in VS Code
Run this command in your Mac Terminal:
```bash
open -a "Visual Studio Code" /Users/nithinchiguru/.gemini/antigravity/scratch/nvoids-job-applier
```
*(Or open VS Code, go to **File > Open Folder...**, and select `nvoids-job-applier`).*

### 2. Run via VS Code "Run & Debug" (1-Click)
1. Press `Cmd + Shift + D` (or click the **Run & Debug** play icon on the left sidebar).
2. At the top dropdown, select any configuration:
   - **`🤖 1. Run Bot (Safe Dry-Run Preview)`** (recommended first run)
   - **`🚀 2. Run Bot (LIVE - Sends Real Emails)`** (continuous live mode)
   - **`🌐 3. Launch Web Dashboard (Browser UI)`** (starts dashboard on port 8080)
   - **`⚡ 4. Run Single Scan Once (No Loop)`**
   - **`📊 5. View Application Stats`**
   - **`🎯 6. Test Resume Matching Score`**
3. Click the green **Play (▷)** button or press `F5`!

### 3. Run via VS Code Integrated Terminal
Press `` Ctrl + ` `` to open the built-in terminal in VS Code, and run:
```bash
python3 main.py run --live
```


### 1. Place Your Resumes
Copy your candidate resumes into the `resumes/` directory:
```bash
cp /path/to/Your_Resume.pdf resumes/
cp /path/to/Another_Resume.docx resumes/
```
The bot will evaluate every file in `resumes/` and automatically pick the best matching resume for each specific job posting.

### 2. Configure Your Candidate Profile & Settings
Edit `config/config.json`:
- `mailer.candidate.name`: Your full name.
- `mailer.candidate.email`: Your contact email.
- `mailer.candidate.phone`: Your phone number.
- `mailer.candidate.linkedin`: Your LinkedIn profile URL.
- `mailer.candidate.c2c_rate`: Your target rate (e.g. `$75/hr C2C`).
- `matching.min_match_percentage`: Set to `93.0` (jobs below 93% match are skipped).

### 3. Configure Email Permissions (SMTP)
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Edit `.env` with your credentials:

#### For Gmail:
1. Go to your Google Account: **Security** -> **2-Step Verification** -> **App Passwords**.
2. Generate a 16-character App Password (e.g. `abcd efgh ijkl mnop`).
3. Set in `.env`:
```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USE_TLS=true
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-16-char-app-password
SENDER_EMAIL=your-email@gmail.com
SENDER_NAME=Your Full Name
```

#### For Microsoft Outlook / Office 365:
```env
SMTP_HOST=smtp.office365.com
SMTP_PORT=587
SMTP_USE_TLS=true
SMTP_USER=your-email@outlook.com
SMTP_PASSWORD=your-password
SENDER_EMAIL=your-email@outlook.com
SENDER_NAME=Your Full Name
```

---

## Usage Commands

### 1. Test Resume Matching on a Job
Test how your resumes score against a real Nvoids job:
```bash
python3 main.py match-check
```

### 2. Preview Matching Jobs on Nvoids (Scrape Only)
Preview currently active C2C jobs from the last 3 days:
```bash
python3 main.py scrape-only --days 3
```

### 3. Safe Dry-Run (Initial Scan + Continuous Monitor)
Runs the initial scan of the last 3 days and enters continuous monitoring, simulating applications without sending real emails:
```bash
python3 main.py run --dry-run
```

### 4. Run Single Scan Once (No Infinite Loop)
Scans today, yesterday, and day before yesterday, then exits:
```bash
python3 main.py run --dry-run --once
```

### 5. Live Application Mode (Sends Real Emails)
Once you have verified the dry-run output and configured your email credentials, run the live bot:
```bash
python3 main.py run --live
```
The bot will:
1. Scan and apply to all qualifying jobs (>= 93% match) posted today, yesterday, and day before yesterday.
2. Enter real-time continuous polling to immediately catch and apply to any new job posted on Nvoids.
3. Keep running until you press `Ctrl+C`.

### 6. View Live Web Dashboard (Browser Interface)
Launch the interactive web dashboard to view live statistics, jobs applied today vs yesterday, match breakdown, and search/filter through all evaluations:
```bash
python3 main.py dashboard
```
Open your browser to: **`http://127.0.0.1:8080`**

### 7. View Terminal Application Statistics
Check terminal summary of jobs applied today, yesterday, match scores, and resume distribution:
```bash
python3 main.py stats
```


### 7. Test Email Connection
Verify your SMTP credentials by sending a test message:
```bash
python3 main.py test-email --to your-email@gmail.com
```

---

## Customizing the Email Template
You can customize the outgoing email template anytime by editing `templates/email_template.txt` or `templates/email_template.html`.

Available dynamic placeholders:
- `{{recruiter_name}}`: Recruiter's first name (or "Hiring Team").
- `{{job_title}}`: Full job title from the posting.
- `{{location}}`: Job location (e.g. Remote, City, State).
- `{{vendor_company}}`: Vendor / staffing agency name.
- `{{match_percentage}}`: Calculated match score (e.g. 96.2%).
- `{{matched_skills}}`: List of overlapping technical skills.
- `{{candidate_name}}`: Your name from config.
- `{{candidate_email}}`: Your email.
- `{{candidate_phone}}`: Your phone.
- `{{candidate_linkedin}}`: Your LinkedIn URL.
- `{{candidate_experience}}`: Years of experience.
- `{{rate}}`: Target C2C rate.
- `{{work_authorization}}`: Work authorization status.
- `{{candidate_summary}}`: Professional summary.
