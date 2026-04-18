import os
import sys
import smtplib
import sqlite3
import requests
from email.mime.text import MIMEText
from datetime import datetime

# ---------------------------------------------------------------------------
# Config from environment
# ---------------------------------------------------------------------------
TO_EMAIL  = os.getenv('TO_EMAIL')
FROM_EMAIL = os.getenv('FROM_EMAIL')
SMTP_HOST  = os.getenv('SMTP_HOST', 'smtp.gmail.com')
SMTP_USER  = os.getenv('SMTP_USER')
SMTP_PASS  = os.getenv('SMTP_PASS')
DB = 'jobs.db'

# ---------------------------------------------------------------------------
# FIX 1: Validate all required env vars at startup — fail fast with a clear
#         message instead of crashing deep inside smtplib with a TypeError.
# ---------------------------------------------------------------------------
required = {
    'TO_EMAIL':   TO_EMAIL,
    'FROM_EMAIL': FROM_EMAIL,
    'SMTP_USER':  SMTP_USER,
    'SMTP_PASS':  SMTP_PASS,
}
missing = [k for k, v in required.items() if not v]
if missing:
    sys.exit(f"[ERROR] Missing required environment variables: {', '.join(missing)}")

# ---------------------------------------------------------------------------
# CLI argument / mode parsing
# ---------------------------------------------------------------------------
MODE = 'daily'
if len(sys.argv) > 1:
    MODE = sys.argv[1].replace('--', '').lower()

# FIX 6 (minor): Reject unknown modes instead of silently accepting them.
VALID_MODES = {'daily', 'weekly'}
if MODE not in VALID_MODES:
    sys.exit(f"[ERROR] Unknown mode '{MODE}'. Valid options: {VALID_MODES}")

# ---------------------------------------------------------------------------
# Database setup
# FIX 2: Wrap all DB work in try/finally so the connection is always closed,
#         even if the script exits early. Also prune stale rows (>30 days)
#         so re-posted jobs are not permanently suppressed.
# ---------------------------------------------------------------------------
conn = sqlite3.connect(DB)
try:
    cur = conn.cursor()
    cur.execute(
        'CREATE TABLE IF NOT EXISTS sent_jobs (job_id TEXT PRIMARY KEY, sent_at TEXT)'
    )
    # Prune records older than 30 days to allow re-posted jobs to resurface.
    cur.execute("DELETE FROM sent_jobs WHERE sent_at < datetime('now', '-30 days')")
    conn.commit()

    # -----------------------------------------------------------------------
    # Job fetching
    # FIX 3: Log fetch errors to stderr instead of silently swallowing them.
    #         An empty list no longer masks a network or parsing failure.
    # NOTE:   The hardcoded mock job below should be replaced with real HTML
    #         parsing (e.g. BeautifulSoup) once the page structure is known.
    #         Example stub is included but commented out.
    # -----------------------------------------------------------------------
    def fetch_jobs():
        jobs = []
        try:
            r = requests.get(
                'https://www.work.ua/en/jobs-kyiv-project-manager/',
                timeout=10
            )
            r.raise_for_status()

            # --- Replace the block below with real scraping ---
            # from bs4 import BeautifulSoup
            # soup = BeautifulSoup(r.text, 'html.parser')
            # for card in soup.select('.job-link'):
            #     job_id = card.get('data-id') or card['href']
            #     jobs.append({
            #         'id':       job_id,
            #         'title':    card.text.strip(),
            #         'location': 'Kyiv',
            #         'score':    90,
            #     })
            # --- Temporary stub (single hardcoded job for structure only) ---
            jobs.append({
                'id':       'workua_pm_1',
                'title':    'Project Manager',
                'location': 'Kyiv',
                'score':    90,
            })
        except requests.RequestException as e:
            # FIX 3: Surface the error; don't swallow it silently.
            print(f"[WARN] fetch_jobs failed: {e}", file=sys.stderr)
        return jobs

    jobs = fetch_jobs()

    # -----------------------------------------------------------------------
    # Deduplication
    # -----------------------------------------------------------------------
    new_jobs = []
    for job in jobs:
        cur.execute('SELECT 1 FROM sent_jobs WHERE job_id = ?', (job['id'],))
        if cur.fetchone() is None:
            new_jobs.append(job)
            cur.execute(
                'INSERT INTO sent_jobs(job_id, sent_at) VALUES (?, ?)',
                (job['id'], datetime.now().astimezone().isoformat())
            )
    conn.commit()

    if not new_jobs:
        print('no new jobs')
        sys.exit(0)

    # -----------------------------------------------------------------------
    # Build email
    # -----------------------------------------------------------------------
    subject = (
        'Top Ukraine Jobs Today'
        if MODE == 'daily'
        else 'Ukraine Weekly Market Report'
    )
    lines = ['Generated: ' + datetime.now().strftime('%Y-%m-%d %H:%M:%S'), '']
    for job in new_jobs:
        lines.append(f"{job['score']} | {job['title']} | {job['location']}")
    body = '\n'.join(lines)

    msg = MIMEText(body, 'plain', 'utf-8')
    msg['Subject'] = subject
    msg['From']    = FROM_EMAIL
    msg['To']      = TO_EMAIL

    # -----------------------------------------------------------------------
    # Send email
    # FIX 4: Wrap the SMTP block in try/except with specific, actionable error
    #         messages instead of crashing with a raw traceback.
    # NOTE:   Gmail with 2FA requires an App Password for SMTP_PASS.
    #         Generate one at: myaccount.google.com/apppasswords
    # -----------------------------------------------------------------------
    try:
        with smtplib.SMTP(SMTP_HOST, 587) as smtp:
            smtp.starttls()
            smtp.login(SMTP_USER, SMTP_PASS)
            smtp.sendmail(FROM_EMAIL, [TO_EMAIL], msg.as_string())
        print('sent')
    except smtplib.SMTPAuthenticationError:
        sys.exit(
            "[ERROR] SMTP authentication failed.\n"
            "  - Check SMTP_USER and SMTP_PASS.\n"
            "  - If using Gmail with 2FA, SMTP_PASS must be a 16-character App Password.\n"
            "    Generate one at: https://myaccount.google.com/apppasswords"
        )
    except smtplib.SMTPException as e:
        sys.exit(f"[ERROR] SMTP error: {e}")
    except OSError as e:
        sys.exit(f"[ERROR] Network error connecting to {SMTP_HOST}:587 — {e}")

finally:
    # FIX 2: Always close the DB connection.
    conn.close()
