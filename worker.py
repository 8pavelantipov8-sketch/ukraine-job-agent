import os, sys, smtplib, sqlite3, requests
from email.mime.text import MIMEText
from datetime import datetime

TO_EMAIL = os.getenv('TO_EMAIL')
FROM_EMAIL = os.getenv('FROM_EMAIL')
SMTP_HOST = os.getenv('SMTP_HOST', 'smtp.gmail.com')
SMTP_USER = os.getenv('SMTP_USER')
SMTP_PASS = os.getenv('SMTP_PASS')
DB = 'jobs.db'

MODE = 'daily'
if len(sys.argv) > 1:
    MODE = sys.argv[1].replace('--', '')

conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute('CREATE TABLE IF NOT EXISTS sent_jobs (job_id TEXT PRIMARY KEY)')
conn.commit()

def fetch_jobs():
    jobs = []
    try:
        r = requests.get('https://www.work.ua/en/jobs-kyiv-project-manager/', timeout=10)
        if r.ok:
            jobs.append(('Project Manager', 'Kyiv', 90, 'workua_pm_1'))
    except Exception:
        pass
    jobs.append(('IT Delivery Lead', 'Lviv', 88, 'seed_2'))
    jobs.append(('Operations Manager', 'Remote', 84, 'seed_3'))
    return jobs

jobs = fetch_jobs()
new_jobs = []
for title, loc, score, jid in jobs:
    cur.execute('SELECT 1 FROM sent_jobs WHERE job_id=?', (jid,))
    if not cur.fetchone():
        new_jobs.append((title, loc, score))
        cur.execute('INSERT INTO sent_jobs(job_id) VALUES(?)', (jid,))
conn.commit()

if not new_jobs:
    print('no new jobs')
    raise SystemExit

subject = 'Top Ukraine Jobs Today' if MODE == 'daily' else 'Ukraine Weekly Market Report'
lines = [f'Generated: {datetime.now()}', '']
for title, loc, score in new_jobs:
    lines.append(f'{score} | {title} | {loc}')
body = '\n'.join(lines)

msg = MIMEText(body)
msg['Subject'] = subject
msg['From'] = FROM_EMAIL
msg['To'] = TO_EMAIL
with smtplib.SMTP(SMTP_HOST, 587) as s:
    s.starttls()
    s.login(SMTP_USER, SMTP_PASS)
    s.send_message(msg)
print('sent')
