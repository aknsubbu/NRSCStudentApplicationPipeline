import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import asyncio
from dotenv import load_dotenv
import logging
from jinja2 import Environment, FileSystemLoader
from typing import List, Optional
from .retry import retry

load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def validate_email_config():
    """Validate that required email configuration is present."""
    required_vars = ['EMAIL_SENDER', 'EMAIL_PASSWORD_IN', 'SMTP_HOST', 'SMTP_PORT']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")
    
    logger.info(f"Email configuration validated for {os.getenv('EMAIL_SENDER')}")

@retry(max_attempts=3, delay_seconds=2)
def send_email(recipient: str, subject: str, body: str, is_html: bool = False, 
               file_list: Optional[List[str]] = None, 
               minio_url: Optional[str] = None):
    """Send an email with optional file list and MinIO presigned URL."""
    
    logger.info(f"Attempting to send email to {recipient}")
    
    # Validate configuration first
    try:
        validate_email_config()
    except Exception as e:
        logger.error(f"Email configuration validation failed: {str(e)}")
        raise
    
    # Create message
    msg = MIMEMultipart('alternative')
    from_email = os.getenv("EMAIL_SENDER")
    msg['From'] = from_email
    msg['To'] = recipient
    msg['Subject'] = subject

    # Create the email body
    email_body = body
    
    # # Add file list to body if provided
    # if file_list and len(file_list) > 0:
    #     logger.info(f"Adding {len(file_list)} files to email body")
    #     if is_html:
    #         file_list_html = "<br><strong>Referenced Files:</strong><ul>"
    #         for filename in file_list:
    #             file_list_html += f"<li>{filename}</li>"
    #         file_list_html += "</ul>"
    #         email_body = f"{body}<br><br>{file_list_html}"
    #     else:
    #         file_list_text = "\n\nReferenced Files:\n"
    #         for i, filename in enumerate(file_list, 1):
    #             file_list_text += f"{i}. {filename}\n"
    #         email_body = f"{body}{file_list_text}"
    
    # Add MinIO URL to body if provided
    if minio_url:
        logger.info("Adding MinIO download link to email")
        if is_html:
            download_link = f'<p><strong>Download your file:</strong> <a href="{minio_url}" target="_blank">Click here to download</a></p>'
            email_body = f"{email_body}<br><br>{download_link}"
        else:
            download_text = f"\n\nDownload your file: {minio_url}"
            email_body = f"{email_body}{download_text}"

    # Attach body
    if is_html:
        msg.attach(MIMEText(email_body, 'html'))
    else:
        msg.attach(MIMEText(email_body, 'plain'))

    # Send email
    try:
        # Get configuration
        smtp_host = os.getenv("SMTP_HOST")
        smtp_port = int(os.getenv("SMTP_PORT"))
        email_sender = os.getenv("EMAIL_SENDER")
        email_password = os.getenv("EMAIL_PASSWORD_IN")
        
        logger.info(f"Connecting to {smtp_host}:{smtp_port}")
        
        # Create secure SSL context
        context = ssl.create_default_context()
        
        # Connect to Gmail SMTP server
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            logger.info("Connected to SMTP server")
            
            server.starttls(context=context)  # Enable encryption
            logger.info("TLS encryption enabled")
            
            server.login(email_sender, email_password)
            logger.info("Authentication successful")
            
            # Send email
            text = msg.as_string()
            server.sendmail(email_sender, recipient, text)
            logger.info("Email sent successfully")
            
        logger.info(f"Email successfully sent to {recipient}")
        return {
            "message": f"Email sent to {recipient}",
            "status": "success",
            "recipient": recipient,
            "subject": subject,
            "files_referenced": len(file_list) if file_list else 0,
            "minio_url_included": bool(minio_url)
        }
        
    except smtplib.SMTPAuthenticationError as e:
        error_msg = f"Gmail authentication failed. Check your email and app password: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg)
    
    except smtplib.SMTPConnectError as e:
        error_msg = f"Cannot connect to SMTP server: {str(e)} - Check network and firewall settings"
        logger.error(error_msg)
        raise Exception(error_msg)
    
    except smtplib.SMTPRecipientsRefused as e:
        error_msg = f"Recipient email address rejected: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg)
    
    except smtplib.SMTPDataError as e:
        error_msg = f"SMTP data error: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg)
        
    except smtplib.SMTPServerDisconnected as e:
        error_msg = f"SMTP server disconnected: {str(e)} - Network issue"
        logger.error(error_msg)
        raise Exception(error_msg)
    
    except Exception as e:
        error_msg = f"Failed to send email to {recipient}: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg)

@retry(max_attempts=3, delay_seconds=2)
async def send_email_async(recipient: str, subject: str, body: str, is_html: bool = False, 
                          file_list: Optional[List[str]] = None, 
                          minio_url: Optional[str] = None):
    """Asynchronous version of send_email function."""
    loop = asyncio.get_running_loop()
    
    result = await loop.run_in_executor(
        None,
        lambda: send_email(recipient, subject, body, is_html, file_list, minio_url)
    )
    return result

def render_template(template_name: str, **kwargs):
    """Render an HTML email template with provided data."""
    try:
        # Determine the correct templates directory
        # Check if we're running from the email service directory
        # if os.path.exists('templates'):
        #     templates_dir = 'templates'
        # # Check if we're running from project root
        if os.path.exists('servers/emails/out/templates'):
            templates_dir = 'servers/emails/out/templates'
        # else:
        #     # Create templates directory in current location
        #     templates_dir = 'templates'
        #     if not os.path.exists(templates_dir):
        #         os.makedirs(templates_dir)
        #         logger.info(f"Created templates directory: {templates_dir}")
        
        logger.info(f"Using templates directory: {templates_dir}")
        logger.info(f"Attempting to render template: {template_name}")
        logger.info(f"Template data: {kwargs}")
        
        env = Environment(loader=FileSystemLoader(templates_dir))
        
        # List available templates
        available_templates = env.list_templates()
        logger.info(f"Available templates: {available_templates}")
        
        template = env.get_template(template_name)
        rendered = template.render(**kwargs)
        
        logger.info(f"Template {template_name} rendered successfully")
        return rendered
        
    except Exception as e:
        logger.error(f"Template rendering error for {template_name}: {str(e)}")
        logger.error(f"Template directory contents: {os.listdir('templates') if os.path.exists('templates') else 'Directory does not exist'}")
        
        # Fall back to a simple message if template fails
        message = kwargs.get('message', 'Important notification')
        file_url = kwargs.get('file_url', '')
        file_list = kwargs.get('file_list', [])
        recipient_name = kwargs.get('recipient_name', 'User')
        
        # Create file list HTML
        file_list_html = ""
        if file_list and len(file_list) > 0:
            file_list_html = "<h3>Referenced Files:</h3><ul>"
            for filename in file_list:
                file_list_html += f"<li>{filename}</li>"
            file_list_html += "</ul>"
        
        fallback_html = f"""
        <!DOCTYPE html>
        <html>
        <body>
            <h2>Hello {recipient_name},</h2>
            <p>{message}</p>
            {file_list_html}
            {f'<p><strong>Download your file:</strong> <a href="{file_url}" target="_blank">Click here to download</a></p>' if file_url else ''}
            <p><em>Note: This is a fallback email as the template "{template_name}" could not be loaded.</em></p>
            <p>Best regards,<br>NRSC Student Program</p>
        </body>
        </html>
        """
        
        logger.info("Using fallback template")
        return fallback_html

async def render_template_async(template_name: str, **kwargs):
    """Asynchronous version of render_template function."""
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: render_template(template_name, **kwargs)
    )
    return result

def test_email_connection():
    """Test the email connection and configuration with detailed logging."""
    try:
        logger.info("Starting email connection test...")
        
        # Check environment variables
        smtp_host = os.getenv("SMTP_HOST")
        smtp_port = os.getenv("SMTP_PORT")
        email_sender = os.getenv("EMAIL_SENDER")
        email_password = os.getenv("EMAIL_PASSWORD_IN")
        
        logger.info(f"SMTP Host: {smtp_host}")
        logger.info(f"SMTP Port: {smtp_port}")
        logger.info(f"Email Sender: {email_sender}")
        logger.info(f"Password configured: {'Yes' if email_password else 'No'}")
        
        validate_email_config()
        
        smtp_port = int(smtp_port)
        context = ssl.create_default_context()
        
        logger.info("Attempting to connect to SMTP server...")
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            logger.info("Connected to SMTP server")
            
            logger.info("Starting TLS...")
            server.starttls(context=context)
            logger.info("TLS started successfully")
            
            logger.info("Attempting login...")
            server.login(email_sender, email_password)
            logger.info("Login successful")
            
        logger.info("Email connection test successful!")
        return {
            "status": "success", 
            "message": "Email connection verified",
            "config": {
                "smtp_host": smtp_host,
                "smtp_port": smtp_port,
                "email_sender": email_sender
            }
        }
        
    except smtplib.SMTPAuthenticationError as e:
        error_msg = f"Authentication failed: {str(e)} - Check your email and app password"
        logger.error(error_msg)
        return {"status": "error", "message": error_msg, "type": "authentication"}
        
    except smtplib.SMTPConnectError as e:
        error_msg = f"Cannot connect to SMTP server: {str(e)} - Check host/port and network"
        logger.error(error_msg)
        return {"status": "error", "message": error_msg, "type": "connection"}
        
    except smtplib.SMTPServerDisconnected as e:
        error_msg = f"Server disconnected: {str(e)} - Network issue or server problem"
        logger.error(error_msg)
        return {"status": "error", "message": error_msg, "type": "disconnected"}
        
    except Exception as e:
        error_msg = f"Email connection test failed: {str(e)}"
        logger.error(error_msg)
        return {"status": "error", "message": error_msg, "type": "unknown"}