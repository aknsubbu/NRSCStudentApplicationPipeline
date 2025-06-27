import os
import email
import imaplib
import json
import base64
from email.header import decode_header
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, BackgroundTasks, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator
import uvicorn
from datetime import datetime
import logging
from dotenv import load_dotenv
from pathlib import Path
import re
import time
from contextlib import contextmanager
import hashlib
from datetime import datetime

#  TODO: Add a route to fetch the information required response and pass it to manager

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("email-poller")

app = FastAPI(title="Email Polling API", description="API for polling emails using IMAP with folder management")


# Configuration models
class EmailConfig(BaseModel):   
    imap_server: str
    username: str
    password: str
    folder: str = "INBOX"
    processed_folder: str = "Processed"  # Folder for processed emails
    # Keywords to identify application emails
    app_keywords: List[str] = Field(default_factory=lambda: ["application", "apply", "job", "position", "vacancy"])
    # Keywords to identify information required emails
    info_required_keywords: List[str] = Field(default_factory=lambda: ["information required", "info required", "additional information", "please provide", "documents needed", "missing information"])
    # Maximum number of emails to fetch
    max_emails: int = 10
    # If True, mark emails as read after processing
    mark_as_read: bool = False
    # If True, move processed emails to processed folder
    move_processed: bool = False
    # Directory to save attachments
    attachment_dir: str = "attachments"
    # Connection timeout
    timeout: int = 30
    # Include email body in base64 for complete backup
    include_raw_email: bool = False
    
    @validator('app_keywords')
    def validate_app_keywords(cls, v):
        return [keyword.strip().lower() for keyword in v if keyword.strip()]
    
    @validator('info_required_keywords')
    def validate_info_required_keywords(cls, v):
        return [keyword.strip().lower() for keyword in v if keyword.strip()]
    
    @validator('max_emails')
    def validate_max_emails(cls, v):
        if v < 1:
            raise ValueError('max_emails must be at least 1')
        return min(v, 100)  # Limit to prevent overload

# Default config (can be overridden)
DEFAULT_CONFIG = EmailConfig(
    imap_server=os.getenv("IMAP_SERVER", "imap.gmail.com"),
    username=os.getenv("EMAIL_USERNAME", ""),
    password=os.getenv("EMAIL_PASSWORD_IN", ""),
    folder=os.getenv("EMAIL_FOLDER", "INBOX"),
    processed_folder=os.getenv("PROCESSED_FOLDER", "Processed"),
    app_keywords=os.getenv("APP_KEYWORDS", "application,apply,job,position,vacancy").split(","),
    info_required_keywords=os.getenv("INFO_REQUIRED_KEYWORDS", "information required,info required,additional information,please provide,documents needed,missing information").split(","),
    max_emails=10,
    mark_as_read=os.getenv("MARK_AS_READ", "True").lower() == "true",
    move_processed=os.getenv("MOVE_PROCESSED", "True").lower() == "true",
    attachment_dir=os.getenv("ATTACHMENT_DIR", "attachments"),
    timeout=60,
    include_raw_email=os.getenv("INCLUDE_RAW_EMAIL", "False").lower() == "true"
)

# Store the current config
current_config = DEFAULT_CONFIG

class UpdateConfigRequest(BaseModel):
    imap_server: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    folder: Optional[str] = None
    processed_folder: Optional[str] = None
    app_keywords: Optional[List[str]] = None
    info_required_keywords: Optional[List[str]] = None
    max_emails: Optional[int] = None
    mark_as_read: Optional[bool] = None
    move_processed: Optional[bool] = None
    attachment_dir: Optional[str] = None
    timeout: Optional[int] = None
    include_raw_email: Optional[bool] = None

class Attachment(BaseModel):
    filename: str
    content_type: str
    path: str
    size: int
    content_base64: Optional[str] = None  # For API responses
    file_hash: Optional[str] = None  # For integrity verification

class EmailData(BaseModel):
    id: str
    student_id: str
    application_id: str
    subject: str
    sender: str
    sender_name: str
    recipient: Optional[str] = None
    date: str
    body_text: str
    body_html: Optional[str] = None
    is_application: bool
    is_info_required: bool
    app_keywords_found: List[str]
    info_required_keywords_found: List[str]
    attachments: List[Attachment] = []
    raw_email_base64: Optional[str] = None  # Complete email for backup
    processed_timestamp: str
    email_hash: str  # Unique identifier for deduplication

class EmailResponse(BaseModel):
    total_emails: int
    application_emails: int
    info_required_emails: int
    processed_emails: int
    moved_emails: int
    emails: List[EmailData]
    processing_time: float
    errors: List[str] = []

def get_config():
    return current_config


#utility functions
def extract_email_from_sender(sender: str) -> str:
    
    match = re.search(r'<([^<>]+@[^<>]+)>', sender)

    if match:
        email = match.group(1)
        return email
    else:
        return None
    

def extract_name(sender:str):
    # Split on '<' and take the first part
    parts = sender.split('<')
    if len(parts) > 1:
        return parts[0].strip()
    
    return None


@contextmanager
def imap_connection(config: EmailConfig):
    """Context manager for IMAP connections with proper cleanup."""
    mail = None
    try:
        mail = imaplib.IMAP4_SSL(config.imap_server, timeout=config.timeout)
        mail.login(config.username, config.password)
        yield mail
    except imaplib.IMAP4.error as e:
        logger.error(f"IMAP error: {e}")
        raise HTTPException(status_code=401, detail=f"IMAP authentication failed: {str(e)}")
    except Exception as e:
        logger.error(f"Connection error: {e}")
        raise HTTPException(status_code=500, detail=f"Connection error: {str(e)}")
    finally:
        if mail:
            try:
                mail.close()
                mail.logout()
            except Exception as e:
                logger.warning(f"Error closing IMAP connection: {e}")

def ensure_folder_exists(mail, folder_name: str) -> bool:
    """Ensure a folder exists, create it if it doesn't."""
    try:
        # List all folders
        result, folders = mail.list()
        if result != "OK":
            logger.error("Failed to list folders")
            return False
        
        # Check if folder exists
        folder_exists = False
        for folder in folders:
            folder_str = folder.decode() if isinstance(folder, bytes) else str(folder)
            if f'"{folder_name}"' in folder_str or f"'{folder_name}'" in folder_str:
                folder_exists = True
                break
        
        if not folder_exists:
            # Create the folder
            result, response = mail.create(folder_name)
            if result == "OK":
                logger.info(f"Created folder: {folder_name}")
                return True
            else:
                logger.error(f"Failed to create folder {folder_name}: {response}")
                return False
        else:
            logger.debug(f"Folder {folder_name} already exists")
            return True
            
    except Exception as e:
        logger.error(f"Error ensuring folder {folder_name} exists: {e}")
        return False

def move_email(mail, email_id: str, source_folder: str, dest_folder: str) -> bool:
    """Move an email from source folder to destination folder."""
    try:
        # Select source folder
        result, _ = mail.select(source_folder)
        if result != "OK":
            logger.error(f"Failed to select source folder: {source_folder}")
            return False
        
        # Convert email_id to bytes if needed
        if isinstance(email_id, str):
            email_id_bytes = email_id.encode()
        else:
            email_id_bytes = email_id
        
        # Copy email to destination folder
        result, response = mail.copy(email_id_bytes, dest_folder)
        if result != "OK":
            logger.error(f"Failed to copy email {email_id} to {dest_folder}: {response}")
            return False
        
        # Mark original email for deletion
        result, response = mail.store(email_id_bytes, '+FLAGS', '\\Deleted')
        if result != "OK":
            logger.error(f"Failed to mark email {email_id} for deletion: {response}")
            return False
        
        # Expunge to actually delete from source folder
        result, response = mail.expunge()
        if result != "OK":
            logger.error(f"Failed to expunge email {email_id}: {response}")
            return False
        
        logger.info(f"Successfully moved email {email_id} from {source_folder} to {dest_folder}")
        return True
        
    except Exception as e:
        logger.error(f"Error moving email {email_id}: {e}")
        return False


def calculate_email_hash(email_message) -> str:
    """Calculate a unique hash for the email to prevent duplicates."""
    # Use Message-ID if available, otherwise use combination of sender, subject, and date
    message_id = email_message.get("Message-ID", "")
    if message_id:
        return hashlib.md5(message_id.encode()).hexdigest()
    
    # Fallback to combination of headers
    sender = email_message.get("From", "")
    subject = email_message.get("Subject", "")
    date = email_message.get("Date", "")
    
    combined = f"{sender}{subject}{date}"
    return hashlib.md5(combined.encode()).hexdigest()

def check_email_categories(email_content: Dict[str, Any], config: EmailConfig) -> tuple[bool, List[str], bool, List[str]]:
    """Check if email is an application email and/or information required email based on keywords."""
    app_keywords_found = []
    info_required_keywords_found = []
    
    # Combine subject and body for searching
    search_text = f"{email_content.get('subject', '')} {email_content.get('body_text', '')}".lower()
    
    # Check for application keywords
    for keyword in config.app_keywords:
        pattern = r'\b' + re.escape(keyword.lower()) + r'\b'
        if re.search(pattern, search_text):
            app_keywords_found.append(keyword)
    
    # Check for information required keywords
    for keyword in config.info_required_keywords:
        # For multi-word phrases, don't require word boundaries
        if len(keyword.split()) > 1:
            if keyword.lower() in search_text:
                info_required_keywords_found.append(keyword)
        else:
            pattern = r'\b' + re.escape(keyword.lower()) + r'\b'
            if re.search(pattern, search_text):
                info_required_keywords_found.append(keyword)
    
    is_application = bool(app_keywords_found)
    is_info_required = bool(info_required_keywords_found)
    
    return is_application, app_keywords_found, is_info_required, info_required_keywords_found

def safe_decode_header(header_value: str) -> str:
    """Safely decode email headers."""
    if not header_value:
        return ""
    
    try:
        decoded_parts = decode_header(header_value)
        result = ""
        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                if encoding:
                    result += part.decode(encoding)
                else:
                    # Try common encodings
                    for enc in ['utf-8', 'latin-1', 'ascii']:
                        try:
                            result += part.decode(enc)
                            break
                        except UnicodeDecodeError:
                            continue
                    else:
                        result += part.decode('utf-8', errors='replace')
            else:
                result += str(part)
        return result
    except Exception as e:
        logger.warning(f"Error decoding header: {e}")
        return str(header_value)

def decode_email_part(part) -> tuple[Optional[str], Optional[str]]:
    """Decode an email part into text with better error handling."""
    content_type = part.get_content_type()
    try:
        body = part.get_payload(decode=True)
        if body:
            # Try to detect charset
            charset = part.get_content_charset()
            if not charset:
                # Try to detect from content-type
                content_type_header = part.get('Content-Type', '')
                charset_match = re.search(r'charset[=:]\s*([a-zA-Z0-9-]+)', content_type_header)
                if charset_match:
                    charset = charset_match.group(1)
                else:
                    charset = 'utf-8'
            
            # Try to decode with detected charset
            for encoding in [charset, 'utf-8', 'latin-1', 'ascii']:
                try:
                    return body.decode(encoding), content_type
                except (UnicodeDecodeError, LookupError):
                    continue
            
            # If all else fails, use utf-8 with error replacement
            return body.decode('utf-8', errors='replace'), content_type
    except Exception as e:
        logger.error(f"Error decoding email part: {e}")
    return None, content_type

def sanitize_filename(filename: str) -> str:
    """Sanitize filename for safe file system operations."""
    # Remove or replace unsafe characters
    unsafe_chars = '<>:"/\\|?*'
    for char in unsafe_chars:
        filename = filename.replace(char, '_')
    
    # Truncate if too long
    if len(filename) > 255:
        name, ext = os.path.splitext(filename)
        filename = name[:255-len(ext)] + ext
    
    return filename

def save_attachment(part, email_id: str, config: EmailConfig) -> Optional[Attachment]:
    """Save an attachment to disk and return its info with better error handling."""
    try:
        filename = part.get_filename()
        if filename:
            filename = safe_decode_header(filename)
            filename = sanitize_filename(filename)
            
            # Create attachments directory if it doesn't exist
            attachment_dir = Path(config.attachment_dir) / str(email_id)
            attachment_dir.mkdir(parents=True, exist_ok=True)
            
            filepath = attachment_dir / filename
            
            # Handle duplicate filenames
            counter = 1
            original_filepath = filepath
            while filepath.exists():
                name, ext = os.path.splitext(original_filepath)
                filepath = Path(f"{name}_{counter}{ext}")
                counter += 1
            
            payload = part.get_payload(decode=True)
            if payload:
                with open(filepath, 'wb') as f:
                    f.write(payload)
                
                # Calculate file hash for integrity
                file_hash = hashlib.md5(payload).hexdigest()
                
                # Encode to base64 for API response
                content_base64 = base64.b64encode(payload).decode('utf-8')
                
                return Attachment(
                    filename=filepath.name,
                    content_type=part.get_content_type(),
                    path=str(filepath),
                    size=len(payload),
                    content_base64=content_base64,
                    file_hash=file_hash
                )
    except Exception as e:
        logger.error(f"Error saving attachment: {e}")
    return None

def process_email(mail, email_id: str, config: EmailConfig) -> Dict[str, Any]:
    """Process a single email and extract its content with improved error handling."""
    try:
        # Convert email_id to appropriate format
        if isinstance(email_id, bytes):
            email_id_str = email_id.decode()
            email_id_bytes = email_id
        else:
            email_id_str = str(email_id)
            email_id_bytes = email_id.encode() if isinstance(email_id, str) else email_id
        
        # Fetch the email
        result, data = mail.fetch(email_id_bytes, "(RFC822)")
        if result != "OK" or not data or not data[0]:
            raise Exception(f"Error fetching email {email_id_str}")
        
        raw_email = data[0][1]
        email_message = email.message_from_bytes(raw_email)
        
        # Calculate unique hash for this email
        email_hash = calculate_email_hash(email_message)
        
        # Extract email headers with safe decoding
        subject = safe_decode_header(email_message.get("Subject", ""))
        sender = safe_decode_header(email_message.get("From", ""))
        recipient = safe_decode_header(email_message.get("To", ""))
        date = email_message.get("Date", "")
        sender_email = extract_email_from_sender(sender)
        current_year = datetime.now().year
        application_id = f"{current_year}/{sender_email}"
        student_id = hashlib.md5(sender_email.encode()).hexdigest()
        sender_name=extract_name(sender)
        
        
        # Extract email body and attachments
        body_text = ""
        body_html = ""
        attachments = []
        
        if email_message.is_multipart():
            for part in email_message.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition", ""))
                
                # Skip multipart containers
                if content_type.startswith("multipart/"):
                    continue
                
                # Handle attachments
                if "attachment" in content_disposition or part.get_filename():
                    attachment = save_attachment(part, student_id, config)
                    if attachment:
                        attachments.append(attachment)
                # Handle text parts
                elif content_type == "text/plain":
                    text, _ = decode_email_part(part)
                    if text:
                        body_text += text + "\n"
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
        
        # Prepare raw email in base64 if requested
        raw_email_base64 = None
        if config.include_raw_email:
            raw_email_base64 = base64.b64encode(raw_email).decode('utf-8')
        
        
        
        
        
        # Create email content dictionary
        email_content = {
            "id": email_id_str,
            "student_id": student_id,
            "application_id": application_id,
            "subject": subject,
            "sender": sender_email,
            "sender_name": sender_name,
            "recipient": recipient,
            "date": date,
            "body_text": body_text.strip(),
            "body_html": body_html,
            "processed_timestamp": datetime.now().isoformat(),
            "email_hash": email_hash,
            "raw_email_base64": raw_email_base64
        }
        
        # Check email categories
        is_application, app_keywords_found, is_info_required, info_required_keywords_found = check_email_categories(email_content, config)
        
        email_content["is_application"] = is_application
        email_content["is_info_required"] = is_info_required
        email_content["app_keywords_found"] = app_keywords_found
        email_content["info_required_keywords_found"] = info_required_keywords_found
        email_content["attachments"] = [attachment.dict() for attachment in attachments]
        
        # Mark as read if specified
        if config.mark_as_read:
            mail.store(email_id_bytes, '+FLAGS', '\\Seen')
        
        return email_content
    
    except Exception as e:
        logger.error(f"Error processing email {email_id}: {e}")
        # Return a minimal error entry instead of failing completely
        return {
            "id": str(email_id),
            "subject": "Error processing email",
            "student_id": None,
            "application_id": None,
            "sender": "Unknown",
            "sender_name": "Unknown",
            "recipient": None,
            "date": "",
            "body_text": f"Error: {str(e)}",
            "body_html": None,
            "is_application": False,
            "is_info_required": False,
            "app_keywords_found": [],
            "info_required_keywords_found": [],
            "attachments": [],
            "processed_timestamp": datetime.now().isoformat(),
            "email_hash": hashlib.md5(str(email_id).encode()).hexdigest(),
            "raw_email_base64": None
        }


def fetch_emails(config: EmailConfig) -> Dict[str, Any]:
    """Fetch emails from the specified IMAP server with improved error handling and folder management."""
    start_time = time.time()
    errors = []
    moved_emails = 0
    
    try:
        with imap_connection(config) as mail:
            # Ensure processed folder exists if moving is enabled
            if config.move_processed:
                if not ensure_folder_exists(mail, config.processed_folder):
                    errors.append(f"Failed to create processed folder: {config.processed_folder}")
                    config.move_processed = False  # Disable moving for this session
            
            # Select the source folder
            result, _ = mail.select(config.folder)
            if result != "OK":
                raise Exception(f"Error selecting folder: {config.folder}")
            
            # Search for all emails in the folder
            result, data = mail.search(None, "ALL")
            if result != "OK":
                raise Exception("Error searching for emails")
            
            if not data or not data[0]:
                logger.info("No emails found in folder")
                return {
                    "emails": [],
                    "processing_time": time.time() - start_time,
                    "moved_emails": 0,
                    "errors": errors
                }
            
            email_ids = data[0].split()
            # Process the most recent emails up to max_emails
            emails_to_process = email_ids[-config.max_emails:] if config.max_emails > 0 else email_ids
            
            emails = []
            processed_count = 0
            error_count = 0
            
            for email_id in reversed(emails_to_process):
                try:
                    email_content = process_email(mail, email_id, config)
                    emails.append(email_content)
                    processed_count += 1
                    
                    # Move email to processed folder if enabled and it's an application or info required email
                    if config.move_processed and (email_content.get("is_application", False) or email_content.get("is_info_required", False)):
                        # Re-select source folder before moving (processing might have changed selection)
                        mail.select(config.folder)
                        
                        if move_email(mail, email_id, config.folder, config.processed_folder):
                            moved_emails += 1
                        else:
                            errors.append(f"Failed to move email {email_id} to processed folder")
                    
                except Exception as e:
                    logger.error(f"Error processing email {email_id}: {e}")
                    errors.append(f"Error processing email {email_id}: {str(e)}")
                    error_count += 1
                    # Continue processing other emails
            
            processing_time = time.time() - start_time
            # logger.info(f"Processed {processed_count} emails in {processing_time:.2f}s, {error_count} errors, {moved_emails} moved")
            
            return {
                "emails": emails,
                "processing_time": processing_time,
                "moved_emails": moved_emails,
                "errors": errors
            }
            
    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        logger.error(f"Error fetching emails: {e}")
        raise HTTPException(status_code=500, detail=f"Error fetching emails: {str(e)}")

# API Endpoints
@app.get("/")
def read_root():
    return {"status": "running", "message": "Email Polling API with Folder Management is running"}

@app.get("/health")
def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.get("/config", response_model=EmailConfig)
def get_current_config():
    # Return config without sensitive password
    config_dict = current_config.dict()
    config_dict["password"] = "***" if config_dict["password"] else ""
    return config_dict

@app.post("/config", response_model=EmailConfig)
def update_config(config_request: UpdateConfigRequest):
    global current_config
    
    # Update only the provided fields
    update_data = config_request.dict(exclude_unset=True)
    current_config_dict = current_config.dict()
    current_config_dict.update(update_data)
    
    try:
        current_config = EmailConfig(**current_config_dict)
        logger.info("Configuration updated successfully")
        
        # Return config without sensitive password
        response_dict = current_config.dict()
        response_dict["password"] = "***" if response_dict["password"] else ""
        return response_dict
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid configuration: {str(e)}")

@app.get("/poll", response_model=EmailResponse)
def poll_emails(config: EmailConfig = Depends(get_config)):
    """Poll emails and return application emails."""
    if not config.username or not config.password:
        raise HTTPException(status_code=400, detail="Email credentials not configured")
    
    result = fetch_emails(config)
    emails = result["emails"]
    
    # Filter application emails
    application_emails = [email for email in emails if email.get("is_application", False)]
    info_required_emails = [email for email in emails if email.get("is_info_required", False)]
    
    response = {
        "total_emails": len(emails),
        "application_emails": len(application_emails),
        "info_required_emails": len(info_required_emails),
        "processed_emails": len(emails),
        "moved_emails": result["moved_emails"],
        "emails": application_emails if len(application_emails) > 0 else emails,
        "processing_time": round(result["processing_time"], 2),
        "errors": result["errors"]
    }
    
    return response

@app.post("/poll/save")
def poll_and_save(background_tasks: BackgroundTasks, config: EmailConfig = Depends(get_config)):
    """Poll emails and save results to a JSON file."""
    
    if not config.username or not config.password:
        raise HTTPException(status_code=400, detail="Email credentials not configured")
    
    def save_to_json():
        try:
            result = fetch_emails(config)
            emails = result["emails"]
            application_emails = [email for email in emails if email.get("is_application", False)]
            info_required_emails = [email for email in emails if email.get("is_info_required", False)]
            
            output_dir = Path("output")
            output_dir.mkdir(exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = output_dir / f"emails_{timestamp}.json"
            
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump({
                    "total_emails": len(emails),
                    "application_emails": len(application_emails),
                    "info_required_emails": len(info_required_emails),
                    "processed_emails": len(emails),
                    "moved_emails": result["moved_emails"],
                    "emails": application_emails if len(application_emails) > 0 else emails,
                    "processing_time": round(result["processing_time"], 2),
                    "timestamp": datetime.now().isoformat(),
                    "errors": result["errors"]
                }, f, indent=2, ensure_ascii=False)
            
            # logger.info(f"Saved emails to {output_file}")
        except Exception as e:
            logger.error(f"Error saving emails: {e}")
    
    background_tasks.add_task(save_to_json)
    return {"status": "Processing emails in the background", "timestamp": datetime.now().isoformat()}

@app.get("/application-emails", response_model=EmailResponse)
def get_application_emails(config: EmailConfig = Depends(get_config)):
    """Get only application emails."""
    if not config.username or not config.password:
        raise HTTPException(status_code=400, detail="Email credentials not configured")
    
    result = fetch_emails(config)
    emails = result["emails"]
    application_emails = [email for email in emails if email.get("is_application", False)]
    info_required_emails = [email for email in emails if email.get("is_info_required", False)]
    
    response = {
        "total_emails": len(emails),
        "application_emails": len(application_emails),
        "info_required_emails": len(info_required_emails),
        "processed_emails": len(emails),
        "moved_emails": result["moved_emails"],
        "emails": application_emails,
        "processing_time": round(result["processing_time"], 2),
        "errors": result["errors"]
    }
    
    return response

@app.get("/information-required-emails", response_model=EmailResponse)
def get_information_required_emails(config: EmailConfig = Depends(get_config)):
    """Get only information required emails."""
    if not config.username or not config.password:
        raise HTTPException(status_code=400, detail="Email credentials not configured")
    
    result = fetch_emails(config)
    emails = result["emails"]
    application_emails = [email for email in emails if True]
    info_required_emails = [email for email in emails if True]
    
    response = {
        "total_emails": len(emails),
        "application_emails": len(application_emails),
        "info_required_emails": len(info_required_emails),
        "processed_emails": len(emails),
        "moved_emails": result["moved_emails"],
        "emails": info_required_emails,
        "processing_time": round(result["processing_time"], 2),
        "errors": result["errors"]
    }
    
    return response

@app.get("/test-connection")
def test_connection(config: EmailConfig = Depends(get_config)):
    """Test IMAP connection without fetching emails."""
    if not config.username or not config.password:
        raise HTTPException(status_code=400, detail="Email credentials not configured")
    
    try:
        with imap_connection(config) as mail:
            result, folders = mail.list()
            if result == "OK":
                # Check if processed folder exists or can be created
                processed_folder_status = "exists"
                if config.move_processed:
                    if not ensure_folder_exists(mail, config.processed_folder):
                        processed_folder_status = "failed_to_create"
                    else:
                        processed_folder_status = "created/verified"
                
                return {
                    "status": "success", 
                    "message": "Successfully connected to email server",
                    "server": config.imap_server,
                    "username": config.username,
                    "source_folder": config.folder,
                    "processed_folder": config.processed_folder,
                    "processed_folder_status": processed_folder_status,
                    "move_processed_enabled": config.move_processed,
                    "folders_available": len(folders)
                }
            else:
                raise Exception("Failed to list folders")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Connection test failed: {str(e)}")

@app.get("/folders")
def list_folders(config: EmailConfig = Depends(get_config)):
    """List all available folders in the email account."""
    if not config.username or not config.password:
        raise HTTPException(status_code=400, detail="Email credentials not configured")
    
    try:
        with imap_connection(config) as mail:
            result, folders = mail.list()
            if result == "OK":
                folder_list = []
                for folder in folders:
                    folder_str = folder.decode() if isinstance(folder, bytes) else str(folder)
                    # Parse folder name from IMAP response
                    parts = folder_str.split('"')
                    if len(parts) >= 3:
                        folder_name = parts[-2]
                        folder_list.append(folder_name)
                
                return {
                    "status": "success",
                    "folders": folder_list,
                    "current_source_folder": config.folder,
                    "current_processed_folder": config.processed_folder
                }
            else:
                raise Exception("Failed to list folders")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing folders: {str(e)}")

if __name__ == "__main__":
    # Validate required environment variables
    if not DEFAULT_CONFIG.username or not DEFAULT_CONFIG.password:
        logger.warning("Email credentials not found in environment variables. Configure via API.")
    
    # Create directories
    Path(DEFAULT_CONFIG.attachment_dir).mkdir(exist_ok=True)
    Path("output").mkdir(exist_ok=True)
    
    # Run the FastAPI app
    uvicorn.run("main:app", host="0.0.0.0", port=8004, log_level="info")