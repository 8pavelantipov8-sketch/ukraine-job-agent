import os, sys, smtplib
from email.mime.text import MIMEText
from datetime import datetime

TO_EMAIL = os.getenv('TO_EMAIL')
FROM_EMAIL = os.getenv('FROM_EMAIL')
SMTP_HOST = os.getenv('SMTP_HOST', 'smtp.gmail.com')
SMTP_USER = os.getenv('SMTP_USER')
SMTP_PASS = os.getenv('SMTP_PASS')

MODE = 'daily'
if len(sys.argv) > 1:
    MODE = sys.argv[1].replace('--', '')

jobs = [
    ('Project Manager - Reconstruction', 'Kyiv', 92),
    ('IT Delivery Lead', 'Lviv', 88),
    ('Operations Manager', 'Remote', 84),
]

subject = 'Top Ukraine Jobs Today' if MODE == 'daily' else 'Ukraine Weekly Market Report'
body = 'Generated: ' + str(datetime.now()) + '

'
for t, loc, score in jobs:
    body += f'{score} | {t} | {loc}
'

msg = MIMEText(body)
msg['Subject'] = subject
msg['From'] = FROM_EMAIL
msg['To'] = TO_EMAIL

with smtplib.SMTP(SMTP_HOST, 587) as s:
    s.starttls()
    s.login(SMTP_USER, SMTP_PASS)
    s.send_message(msg)

print('sent')
