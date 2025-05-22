import os
import email
import imaplib
import json
import base64
from email.header import decode_header
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, BackgroundTasks, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import uvicorn
from datetime import datetime
import logging
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("email-poller")

app = FastAPI(title="Email Polling API", description="API for polling emails using IMAP")

# Configuration models
class EmailConfig(BaseModel):
    imap_server: str
    username: str
    password: str
    folder: str = "INBOX"
    # Keywords to identify application emails
    app_keywords: List[str] = Field(default_factory=lambda: ["application", "apply", "job", "position", "vacancy"])
    # Maximum number of emails to fetch
    max_emails: int = 10
    # If True, mark emails as read after processing
    mark_as_read: bool = False
    # Directory to save attachments
    attachment_dir: str = "attachments"

# Default config (can be overridden)
DEFAULT_CONFIG = EmailConfig(
    imap_server=os.getenv("IMAP_SERVER", ""),
    username=os.getenv("EMAIL_USERNAME", ""),
    password=os.getenv("EMAIL_PASSWORD", ""),
    folder=os.getenv("EMAIL_FOLDER", "INBOX"),
    app_keywords=os.getenv("APP_KEYWORDS", "application,apply,job,position,vacancy").split(","),
    max_emails=int(os.getenv("MAX_EMAILS", "10")),
    mark_as_read=os.getenv("MARK_AS_READ", "False").lower() == "true",
    attachment_dir=os.getenv("ATTACHMENT_DIR", "attachments")
)

# Store the current config
current_config = DEFAULT_CONFIG

class UpdateConfigRequest(BaseModel):
    imap_server: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    folder: Optional[str] = None
    app_keywords: Optional[List[str]] = None
    max_emails: Optional[int] = None
    mark_as_read: Optional[bool] = None
    attachment_dir: Optional[str] = None

class Attachment(BaseModel):
    filename: str
    content_type: str
    path: str
    size: int

class EmailData(BaseModel):
    id: str
    subject: str
    sender: str
    date: str
    body_text: str
    body_html: Optional[str] = None
    is_application: bool
    keywords_found: List[str]
    attachments: List[Attachment] = []

class EmailResponse(BaseModel):
    total_emails: int
    application_emails: int
    emails: List[EmailData]

def get_config():
    return current_config

def check_if_application_email(email_content: Dict[str, Any], config: EmailConfig) -> tuple[bool, List[str]]:
    """Check if email is an application email based on keywords."""
    keywords_found = []
    
    # Check subject
    subject = email_content.get("subject", "").lower()
    for keyword in config.app_keywords:
        if keyword.lower() in subject:
            keywords_found.append(keyword)
    
    # Check body text
    body_text = email_content.get("body_text", "").lower()
    for keyword in config.app_keywords:
        if keyword.lower() in body_text and keyword not in keywords_found:
            keywords_found.append(keyword)
    
    return bool(keywords_found), keywords_found

def decode_email_part(part) -> tuple[Optional[str], Optional[str]]:
    """Decode an email part into text."""
    content_type = part.get_content_type()
    try:
        body = part.get_payload(decode=True)
        if body:
            charset = part.get_content_charset() or 'utf-8'
            try:
                body = body.decode(charset)
            except UnicodeDecodeError:
                body = body.decode('latin-1')  # Fallback encoding
            return body, content_type
    except Exception as e:
        logger.error(f"Error decoding email part: {e}")
    return None, content_type

def save_attachment(part, email_id: str, config: EmailConfig) -> Optional[Attachment]:
    """Save an attachment to disk and return its info."""
    try:
        filename = part.get_filename()
        if filename:
            # Decode filename if needed
            decoded_header = decode_header(filename)[0]
            if decoded_header[1] is not None:
                filename = decoded_header[0].decode(decoded_header[1])
            elif isinstance(decoded_header[0], bytes):
                filename = decoded_header[0].decode('utf-8')
            else:
                filename = decoded_header[0]
            
            # Create attachments directory if it doesn't exist
            attachment_dir = Path(config.attachment_dir) / str(email_id)
            attachment_dir.mkdir(parents=True, exist_ok=True)
            
            filepath = attachment_dir / filename
            
            with open(filepath, 'wb') as f:
                f.write(part.get_payload(decode=True))
            
            return Attachment(
                filename=filename,
                content_type=part.get_content_type(),
                path=str(filepath),
                size=os.path.getsize(filepath)
            )
    except Exception as e:
        logger.error(f"Error saving attachment: {e}")
    return None

def process_email(mail, email_id: str, config: EmailConfig) -> Dict[str, Any]:
    """Process a single email and extract its content."""
    # Convert email_id to string if it's bytes
    if isinstance(email_id, bytes):
        email_id_str = email_id.decode()
        email_id_bytes = email_id
    else:
        email_id_str = str(email_id)
        email_id_bytes = email_id.encode() if isinstance(email_id, str) else email_id
    
    # Fetch the email
    result, data = mail.fetch(email_id_bytes, "(RFC822)")
    if result != "OK":
        raise Exception(f"Error fetching email {email_id_str}")
    
    raw_email = data[0][1]
    email_message = email.message_from_bytes(raw_email)
    
    # Extract email headers
    subject, encoding = decode_header(email_message["Subject"])[0]
    if isinstance(subject, bytes):
        subject = subject.decode(encoding or "utf-8")
    
    sender, encoding = decode_header(email_message["From"])[0]
    if isinstance(sender, bytes):
        sender = sender.decode(encoding or "utf-8")
    
    date = email_message["Date"]
    
    # Extract email body and attachments
    body_text = ""
    body_html = ""
    attachments = []
    
    if email_message.is_multipart():
        for part in email_message.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition"))
            
            # Skip multipart container
            if content_type == "multipart/alternative":
                continue
            
            # Handle attachments
            if "attachment" in content_disposition:
                attachment = save_attachment(part, email_id_str, config)
                if attachment:
                    attachments.append(attachment)
            # Handle text parts
            elif content_type == "text/plain":
                text, _ = decode_email_part(part)
                if text:
                    body_text += text
            elif content_type == "text/html":
                html, _ = decode_email_part(part)
                if html:
                    body_html += html
    else:
        # Handle non-multipart emails
        body, content_type = decode_email_part(email_message)
        if body:
            if content_type == "text/plain":
                body_text = body
            elif content_type == "text/html":
                body_html = body
    
    # Create email content dictionary
    email_content = {
        "id": email_id_str,
        "subject": subject,
        "sender": sender,
        "date": date,
        "body_text": body_text,
        "body_html": body_html,
    }
    
    # Check if it's an application email
    is_application, keywords_found = check_if_application_email(email_content, config)
    
    email_content["is_application"] = is_application
    email_content["keywords_found"] = keywords_found
    email_content["attachments"] = [attachment.dict() for attachment in attachments]
    
    # Mark as read if specified
    if config.mark_as_read:
        mail.store(email_id_bytes, '+FLAGS', '\\Seen')
    
    return email_content

def fetch_emails(config: EmailConfig) -> List[Dict[str, Any]]:
    """Fetch emails from the specified IMAP server."""
    try:
        # Connect to the IMAP server
        mail = imaplib.IMAP4_SSL(config.imap_server)
        mail.login(config.username, config.password)
        mail.select(config.folder)
        
        # Search for all emails in the folder
        result, data = mail.search(None, "ALL")
        if result != "OK":
            raise Exception("Error searching for emails")
        
        email_ids = data[0].split()
        # Process the most recent emails up to max_emails
        emails_to_process = email_ids[-config.max_emails:] if config.max_emails > 0 else email_ids
        
        emails = []
        for email_id in reversed(emails_to_process):
            try:
                email_content = process_email(mail, email_id, config)
                emails.append(email_content)
            except Exception as e:
                logger.error(f"Error processing email {email_id}: {e}")
        
        mail.close()
        mail.logout()
        
        return emails
    except Exception as e:
        logger.error(f"Error fetching emails: {e}")
        raise HTTPException(status_code=500, detail=f"Error fetching emails: {str(e)}")

@app.get("/")
def read_root():
    return {"status": "running", "message": "Email Polling API is running"}

@app.get("/config", response_model=EmailConfig)
def get_current_config():
    return current_config

@app.post("/config", response_model=EmailConfig)
def update_config(config_request: UpdateConfigRequest):
    global current_config
    
    # Update only the provided fields
    update_data = config_request.dict(exclude_unset=True)
    current_config_dict = current_config.dict()
    current_config_dict.update(update_data)
    
    current_config = EmailConfig(**current_config_dict)
    return current_config

@app.get("/poll", response_model=EmailResponse)
def poll_emails(config: EmailConfig = Depends(get_config)):
    """Poll emails and return application emails."""
    emails = fetch_emails(config)
    
    # Filter application emails
    application_emails = [email for email in emails if email["is_application"]]
    
    response = {
        "total_emails": len(emails),
        "application_emails": len(application_emails),
        "emails": application_emails if len(application_emails) > 0 else emails
    }
    
    return response

@app.post("/poll/save")
def poll_and_save(background_tasks: BackgroundTasks, config: EmailConfig = Depends(get_config)):
    """Poll emails and save results to a JSON file."""
    
    def save_to_json():
        try:
            emails = fetch_emails(config)
            application_emails = [email for email in emails if email["is_application"]]
            
            output_dir = Path("output")
            output_dir.mkdir(exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = output_dir / f"emails_{timestamp}.json"
            
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump({
                    "total_emails": len(emails),
                    "application_emails": len(application_emails),
                    "emails": application_emails if len(application_emails) > 0 else emails
                }, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Saved emails to {output_file}")
        except Exception as e:
            logger.error(f"Error saving emails: {e}")
    
    background_tasks.add_task(save_to_json)
    return {"status": "Processing emails in the background"}

@app.get("/application-emails", response_model=EmailResponse)
def get_application_emails(config: EmailConfig = Depends(get_config)):
    """Get only application emails."""
    emails = fetch_emails(config)
    application_emails = [email for email in emails if email["is_application"]]
    
    response = {
        "total_emails": len(emails),
        "application_emails": len(application_emails),
        "emails": application_emails
    }
    
    return response

if __name__ == "__main__":
    # Create attachments directory if it doesn't exist
    Path(DEFAULT_CONFIG.attachment_dir).mkdir(exist_ok=True)
    
    # Run the FastAPI app
    uvicorn.run(app, host="0.0.0.0", port=8000)