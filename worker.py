import os
import sys
import smtplib
import requests
import redis
from email.mime.text import MIMEText
from datetime import datetime

# ---------------------------------------------------------------------------
# Config from environment
# ---------------------------------------------------------------------------
TO_EMAIL   = os.getenv('TO_EMAIL')
FROM_EMAIL = os.getenv('FROM_EMAIL')
SMTP_HOST  = os.getenv('SMTP_HOST', 'smtp.gmail.com')
SMTP_USER  = os.getenv('SMTP_USER')
SMTP_PASS  = os.getenv('SMTP_PASS')
REDIS_URL  = os.getenv('REDIS_URL')   # from Upstash dashboard

# ---------------------------------------------------------------------------
# Validate all required env vars at startup
# ---------------------------------------------------------------------------
required = {
    'TO_EMAIL':   TO_EMAIL,
    'FROM_EMAIL': FROM_EMAIL,
    'SMTP_USER':  SMTP_USER,
    'SMTP_PASS':  SMTP_PASS,
    'REDIS_URL':  REDIS_URL,
}
missing = [k for k, v in required.items() if not v]
if missing:
    sys.exit(f"[ERROR] Missing required environment variables: {', '.join(missing)}")

# ---------------------------------------------------------------------------
# CLI mode parsing
# ---------------------------------------------------------------------------
MODE = 'daily'
if len(sys.argv) > 1:
    MODE = sys.argv[1].replace('--', '').lower()

VALID_MODES = {'daily', 'weekly'}
if MODE not in VALID_MODES:
    sys.exit(f"[ERROR] Unknown mode '{MODE}'. Valid options: {VALID_MODES}")

# ---------------------------------------------------------------------------
# Redis connection (Upstash — persistent, free tier, TLS required)
# Each job_id stored as its own key with a 30-day TTL — no schema needed.
# ---------------------------------------------------------------------------
try:
    r = redis.from_url(REDIS_URL, decode_responses=True, ssl_cert_reqs=None)
    r.ping()
except redis.RedisError as e:
    sys.exit(f"[ERROR] Could not connect to Redis: {e}")

SEEN_KEY_PREFIX = 'sent_job:'
TTL_SECONDS     = 30 * 24 * 60 * 60   # 30 days

def is_seen(job_id: str) -> bool:
    return r.exists(f"{SEEN_KEY_PREFIX}{job_id}") == 1

def mark_seen(job_id: str) -> None:
    r.setex(f"{SEEN_KEY_PREFIX}{job_id}", TTL_SECONDS, '1')

# ---------------------------------------------------------------------------
# Job fetching
# ---------------------------------------------------------------------------
def fetch_jobs():
    jobs = []
    try:
        response = requests.get(
            'https://www.work.ua/en/jobs-kyiv-project-manager/',
            timeout=10
        )
        response.raise_for_status()

        # --- Replace with real scraping once page structure is confirmed ---
        # from bs4 import BeautifulSoup
        # soup = BeautifulSoup(response.text, 'html.parser')
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

# ---------------------------------------------------------------------------
# Deduplication — filter out jobs already seen in the last 30 days
# ---------------------------------------------------------------------------
jobs     = fetch_jobs()
new_jobs = [job for job in jobs if not is_seen(job['id'])]

if not new_jobs:
    print('no new jobs')
    sys.exit(0)

# Mark all new jobs as seen before sending (prevents re-send on partial
# failure — swap order if you'd rather guarantee delivery over dedup)
for job in new_jobs:
    mark_seen(job['id'])

# ---------------------------------------------------------------------------
# Build email
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# Send email
# NOTE: Gmail with 2FA requires an App Password for SMTP_PASS.
#       Generate one at: myaccount.google.com/apppasswords
# ---------------------------------------------------------------------------
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
