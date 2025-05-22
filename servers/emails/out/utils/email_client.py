import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import os
import asyncio
from dotenv import load_dotenv
import logging
from jinja2 import Environment, FileSystemLoader
from typing import List, Dict, Any, Optional, Union, cast
from .retry import retry

load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@retry(max_attempts=3, delay_seconds=2)
def send_email(recipient: str, subject: str, body: str, is_html: bool = False, attachments: Optional[List[Dict[str, Any]]] = None, minio_url: Optional[str] = None):
    """Send an email with optional attachments and MinIO presigned URL."""
    msg = MIMEMultipart()
    from_email = os.getenv("EMAIL_SENDER", "noreply@example.com")  # Provide default
    msg['From'] = from_email
    msg['To'] = recipient
    msg['Subject'] = subject

    # Attach body
    if is_html:
        msg.attach(MIMEText(body, 'html'))
    else:
        msg.attach(MIMEText(body, 'plain'))

    # Attach MinIO presigned URL if provided
    if minio_url is not None and minio_url != "":
        # Simply add another text part with the download link
        download_text = f"\n\nDownload file: {minio_url}"
        if is_html:
            download_html = f'<p><a href="{minio_url}" target="_blank">Download file</a></p>'
            msg.attach(MIMEText(download_html, 'html'))
        else:
            msg.attach(MIMEText(download_text, 'plain'))

    # Attach files
    if attachments is not None and len(attachments) > 0:
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
        
        # Get email credentials with defaults to avoid None issues
        email_sender = os.getenv("EMAIL_SENDER", "")
        email_password = os.getenv("EMAIL_PASSWORD", "")
        
        if not email_sender or not email_password:
            raise ValueError("EMAIL_SENDER and EMAIL_PASSWORD environment variables must be set")
        
        # Ensure we have strings for login
        email_sender_str = str(email_sender)
        email_password_str = str(email_password)
            
        server.login(email_sender_str, email_password_str)
        server.sendmail(msg['From'], msg['To'], msg.as_string())
        server.quit()
        logger.info(f"Email sent to {recipient}")
        return {"message": f"Email sent to {recipient}"}
    except Exception as e:
        logger.error(f"Failed to send email to {recipient}: {str(e)}")
        raise Exception(f"Failed to send email: {str(e)}")

@retry(max_attempts=3, delay_seconds=2)
async def send_email_async(recipient: str, subject: str, body: str, is_html: bool = False, 
                          attachments: Optional[List[Dict[str, Any]]] = None, 
                          minio_url: Optional[str] = None):
    """Asynchronous version of send_email function."""
    # Use the synchronous version but run it in a thread pool to make it non-blocking
    loop = asyncio.get_running_loop()
    
    # Ensure attachments is properly handled as None or a list
    safe_attachments = [] if attachments is None else attachments
    # Ensure minio_url is properly handled as None or a string
    safe_minio_url = "" if minio_url is None else minio_url
    
    result = await loop.run_in_executor(
        None,
        lambda: send_email(recipient, subject, body, is_html, safe_attachments, safe_minio_url)
    )
    return result

def render_template(template_name: str, **kwargs):
    """Render an HTML email template with provided data."""
    try:
        env = Environment(loader=FileSystemLoader('templates'))
        template = env.get_template(template_name)
        return template.render(**kwargs)
    except Exception as e:
        logger.error(f"Template rendering error for {template_name}: {str(e)}")
        # Fall back to a simple message if template fails
        return f"<html><body><p>An important message from NRSC Student Program.</p><p>{kwargs.get('message', '')}</p></body></html>"
        
async def render_template_async(template_name: str, **kwargs):
    """Asynchronous version of render_template function."""
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: render_template(template_name, **kwargs)
    )
    return result