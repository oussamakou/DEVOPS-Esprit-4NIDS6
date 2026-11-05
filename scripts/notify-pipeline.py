"""Send only run status, per-job outcomes and a link via authenticated SMTP.

The message never contains credentials, report contents or job outputs (such as
image digests): JOB_RESULTS is the workflow's `needs` JSON and only each job's
name and result are read from it. Certificates are validated (STARTTLS).
"""
from email.message import EmailMessage
import json
import os
import smtplib
import ssl

REQUIRED = ["SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD", "MAIL_FROM", "MAIL_TO", "RUN_URL", "RUN_RESULT"]


def build_message(env):
    missing = [name for name in REQUIRED if not env.get(name)]
    if missing:
        raise SystemExit("Missing notification configuration: " + ", ".join(missing))
    workflow = env.get("WORKFLOW_NAME") or "pipeline"
    message = EmailMessage()
    message["Subject"] = f"DevSecOps {workflow}: {env['RUN_RESULT']}"
    message["From"] = env["MAIL_FROM"]
    message["To"] = env["MAIL_TO"]
    lines = [f"Workflow: {workflow}", f"Pipeline status: {env['RUN_RESULT']}"]
    jobs = json.loads(env.get("JOB_RESULTS") or "{}")
    if jobs:
        lines += ["", "Stage results:"] + [f"  {name}: {value.get('result', 'unknown')}" for name, value in jobs.items()]
    lines += ["", f"Run and reports: {env['RUN_URL']}"]
    message.set_content("\n".join(lines) + "\n")
    return message


def send(env):
    message = build_message(env)
    with smtplib.SMTP(env["SMTP_HOST"], int(env.get("SMTP_PORT") or "587"), timeout=30) as smtp:
        smtp.starttls(context=ssl.create_default_context())
        smtp.login(env["SMTP_USERNAME"], env["SMTP_PASSWORD"])
        smtp.send_message(message)
    print("Pipeline notification accepted by SMTP server.")


if __name__ == "__main__":
    send(os.environ)
