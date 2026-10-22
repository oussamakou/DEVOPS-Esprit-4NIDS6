"""Send only a run status/link via authenticated SMTP with certificate validation."""
from email.message import EmailMessage
import os
import smtplib
import ssl

required = ["SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD", "MAIL_FROM", "MAIL_TO", "RUN_URL", "RUN_RESULT"]
missing = [name for name in required if not os.environ.get(name)]
if missing:
    raise SystemExit("Missing notification configuration: " + ", ".join(missing))
message = EmailMessage()
message["Subject"] = f"DevSecOps pipeline: {os.environ['RUN_RESULT']}"
message["From"] = os.environ["MAIL_FROM"]
message["To"] = os.environ["MAIL_TO"]
message.set_content(f"Pipeline status: {os.environ['RUN_RESULT']}\nRun and reports: {os.environ['RUN_URL']}\n")
with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.environ.get("SMTP_PORT", "587")), timeout=30) as smtp:
    smtp.starttls(context=ssl.create_default_context())
    smtp.login(os.environ["SMTP_USERNAME"], os.environ["SMTP_PASSWORD"])
    smtp.send_message(message)
print("Pipeline notification accepted by SMTP server.")
