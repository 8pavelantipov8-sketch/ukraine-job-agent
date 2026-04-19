import os
import sys
import smtplib
import psycopg2
import requests
from email.mime.text import MIMEText
from datetime import datetime

# ---------------------------------------------------------------------------
# Config from environment
# ---------------------------------------------------------------------------
TO_EMAIL     = os.getenv('TO_EMAIL')
FROM_EMAIL   = os.getenv('FROM_EMAIL')
SMTP_HOST    = os.getenv('SMTP_HOST', 'smtp.gmail.com')
SMTP_USER    = os.getenv('SMTP_USER')
SMTP_PASS    = os.getenv('SMTP_PASS')
DATABASE_URL = os.getenv('DATABASE_URL')   # provided automatically by Render PostgreSQL

# ---------------------------------------------------------------------------
# FIX 1 (from Python audit): Validate all required env vars at startup.
# FIX 2 (from YAML audit):   DATABASE_URL added — replaces ephemeral SQLite.
# ---------------------------------------------------------------------------
required = {
    'TO_EMAIL':     TO_EMAIL,
    'FROM_EMAIL':   FROM_EMAIL,
    'SMTP_USER':    SMTP_USER,
    'SMTP_PASS':    SMTP_PASS,
    'DATABASE_URL': DATABASE_URL,
}
missing = [k for k, v in required.items() if not v]
if missing:
    sys.exit(f"[ERROR] Missing required environment variables: {', '.join(missing)}")

# ---------------------------------------------------------------------------
# CLI argument / mode parsing
# FIX 3 (from Python audit): Reject unknown modes explicitly.
# FIX 4 (from YAML audit):   startCommand uses worker.py — this file matches.
# ---------------------------------------------------------------------------
MODE = 'daily'
if len(sys.argv) > 1:
    MODE = sys.argv[1].replace('--', '').lower()

VALID_MODES = {'daily', 'weekly'}
if MODE not in VALID_MODES:
    sys.exit(f"[ERROR] Unknown mode '{MODE}'. Valid options: {VALID_MODES}")

# ---------------------------------------------------------------------------
# Database setup — PostgreSQL (persistent across Render deploys)
# FIX 2 (from YAML audit): SQLite was ephemeral; jobs.db was wiped on every
#   deploy, causing all jobs to look "new" and duplicate emails to be sent.
#   psycopg2 + Render's managed PostgreSQL persists dedup state permanently.
# ---------------------------------------------------------------------------
conn = psycopg2.connect(DATABASE_URL)
try:
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS sent_jobs (
            job_id  TEXT PRIMARY KEY,
            sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    ''')
    # Prune records older than 30 days so re-posted jobs can resurface.
    cur.execute("DELETE FROM sent_jobs WHERE sent_at < NOW() - INTERVAL '30 days'")
    conn.commit()

    # -----------------------------------------------------------------------
    # Job fetching
    # FIX (from Python audit): Log fetch errors to stderr; don't swallow them.
    # NOTE: Replace the stub below with real BeautifulSoup scraping once the
    #       page structure is confirmed. The stub returns one hardcoded job
    #       only to preserve the existing send/dedup flow during development.
    # -----------------------------------------------------------------------
    def fetch_jobs():
        jobs = []
        try:
            r = requests.get(
                'https://www.work.ua/en/jobs-kyiv-project-manager/',
                timeout=10
            )
            r.raise_for_status()

            # --- Replace with real scraping ---
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
            # --- Temporary stub ---
            jobs.append({
                'id':       'workua_pm_1',
                'title':    'Project Manager',
                'location': 'Kyiv',
                'score':    90,
            })
        except requests.RequestException as e:
            print(f"[WARN] fetch_jobs failed: {e}", file=sys.stderr)
        return jobs

    jobs = fetch_jobs()

    # -----------------------------------------------------------------------
    # Deduplication
    # -----------------------------------------------------------------------
    new_jobs = []
    for job in jobs:
        cur.execute('SELECT 1 FROM sent_jobs WHERE job_id = %s', (job['id'],))
        if cur.fetchone() is None:
            new_jobs.append(job)
            cur.execute(
                'INSERT INTO sent_jobs (job_id, sent_at) VALUES (%s, %s)',
                (job['id'], datetime.now().astimezone())
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
    # FIX (from Python audit): try/except with specific, actionable messages.
    # NOTE: Gmail with 2FA requires an App Password for SMTP_PASS.
    #       Generate one at: myaccount.google.com/apppasswords
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
            "  - Gmail with 2FA requires a 16-character App Password.\n"
            "    Generate one at: https://myaccount.google.com/apppasswords"
        )
    except smtplib.SMTPException as e:
        sys.exit(f"[ERROR] SMTP error: {e}")
    except OSError as e:
        sys.exit(f"[ERROR] Network error connecting to {SMTP_HOST}:587 — {e}")

finally:
    conn.close()
