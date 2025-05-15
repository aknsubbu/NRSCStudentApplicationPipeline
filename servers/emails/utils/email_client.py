import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import os
from dotenv import load_dotenv
import logging
from jinja2 import Environment, FileSystemLoader

load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def send_email(recipient: str, subject: str, body: str, is_html: bool = False, attachments: list = None, minio_url: str = None):
    """Send an email with optional attachments and MinIO presigned URL."""
    msg = MIMEMultipart()
    msg['From'] = os.getenv("EMAIL_SENDER")
    msg['To'] = recipient
    msg['Subject'] = subject

    # Attach body
    if is_html:
        msg.attach(MIMEText(body, 'html'))
    else:
        msg.attach(MIMEText(body, 'plain'))

    # Attach MinIO presigned URL if provided
    if minio_url:
        body_part = msg.get_payload()[0]
        current_body = body_part.get_payload()
        body_part.set_payload(f"{current_body}\n\nDownload file: {minio_url}")
        msg.replace_payload([body_part])

    # Attach files
    if attachments:
        for attachment in attachments:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(attachment['content'])
            encoders.encode_base64(part)
            part.add_header(
                'Content-Disposition',
                f'attachment; filename={attachment["filename"]}'
            )
            msg.attach(part)

    # Send email
    try:
        server = smtplib.SMTP(os.getenv("SMTP_HOST", "smtp.gmail.com"), int(os.getenv("SMTP_PORT", 587)))
        server.starttls()
        server.login(os.getenv("EMAIL_SENDER"), os.getenv("EMAIL_PASSWORD"))
        server.sendmail(msg['From'], msg['To'], msg.as_string())
        server.quit()
        logger.info(f"Email sent to {recipient}")
        return {"message": f"Email sent to {recipient}"}
    except Exception as e:
        logger.error(f"Failed to send email to {recipient}: {str(e)}")
        raise Exception(f"Failed to send email: {str(e)}")

def render_template(template_name: str, **kwargs):
    """Render an HTML email template with provided data."""
    env = Environment(loader=FileSystemLoader('templates'))
    template = env.get_template(template_name)
    return template.render(**kwargs)