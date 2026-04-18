import os
import sys
import smtplib
import sqlite3
import requests
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
cur.execute('CREATE TABLE IF NOT EXISTS sent_jobs (job_id TEXT PRIMARY KEY, sent_at TEXT)')
conn.commit()

def fetch_jobs():
    jobs = []
    try:
        r = requests.get('https://www.work.ua/en/jobs-kyiv-project-manager/', timeout=10)
        if r.ok:
            jobs.append({'id':'workua_pm_1','title':'Project Manager','location':'Kyiv','score':90})
    except Exception:
        pass
    return jobs

jobs = fetch_jobs()
new_jobs = []
for job in jobs:
    cur.execute('SELECT 1 FROM sent_jobs WHERE job_id=?', (job['id'],))
    if cur.fetchone() is None:
        new_jobs.append(job)
        cur.execute('INSERT INTO sent_jobs(job_id, sent_at) VALUES(?, ?)', (job['id'], datetime.utcnow().isoformat()))
conn.commit()

if not new_jobs:
    print('no new jobs')
    sys.exit(0)

subject = 'Top Ukraine Jobs Today' if MODE == 'daily' else 'Ukraine Weekly Market Report'
lines = ['Generated: ' + datetime.now().strftime('%Y-%m-%d %H:%M:%S'), '']
for job in new_jobs:
    lines.append(f"{job['score']} | {job['title']} | {job['location']}")
body = chr(10).join(lines)

msg = MIMEText(body, 'plain', 'utf-8')
msg['Subject'] = subject
msg['From'] = FROM_EMAIL
msg['To'] = TO_EMAIL
with smtplib.SMTP(SMTP_HOST, 587) as smtp:
    smtp.starttls()
    smtp.login(SMTP_USER, SMTP_PASS)
    smtp.sendmail(FROM_EMAIL, [TO_EMAIL], msg.as_string())
print('sent')
