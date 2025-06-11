from fastapi import FastAPI, HTTPException, Depends, Security, BackgroundTasks
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import httpx
import os
import json
import logging
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
import re
import hashlib
import asyncio

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("email-manager")

app = FastAPI(
    title="Email Processing Manager API", 
    description="Orchestrates email processing between polling, database, and MinIO storage"
)

# Configuration
API_KEY = os.getenv("API_KEY", "your-secret-api-key-123")
DB_SERVER_URL = os.getenv("DB_SERVER_URL", "http://localhost:8000")
EMAIL_POLLER_URL = os.getenv("EMAIL_POLLER_URL", "http://localhost:8002")
MINIO_SERVER_URL = os.getenv("MINIO_SERVER_URL", "http://localhost:8000")

# API Key Authentication
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def get_api_key(api_key: str = Security(api_key_header)):
    if api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API Key")
    return api_key

# Models
class EmailAttachment(BaseModel):
    filename: str
    content_type: str
    path: str
    size: int
    content_base64: Optional[str] = None
    file_hash: Optional[str] = None

class EmailData(BaseModel):
    id: str
    subject: str
    sender: str
    recipient: Optional[str] = None
    date: str
    body_text: str
    body_html: Optional[str] = None
    is_application: bool
    keywords_found: List[str]
    attachments: List[EmailAttachment] = []
    raw_email_base64: Optional[str] = None
    processed_timestamp: str
    email_hash: str

class EmailBatch(BaseModel):
    total_emails: int
    application_emails: int
    processed_emails: int
    moved_emails: int
    emails: List[EmailData]
    processing_time: float
    errors: List[str] = []

class ProcessingResult(BaseModel):
    email_id: str
    student_id: Optional[str] = None
    status: str
    database_saved: bool = False
    attachments_uploaded: int = 0
    total_attachments: int = 0
    errors: List[str] = []
    minio_files: List[str] = []

class BatchProcessingResult(BaseModel):
    total_processed: int
    successful: int
    failed: int
    results: List[ProcessingResult]
    processing_time: float
    errors: List[str] = []

class StudentExtractionResult(BaseModel):
    student_id: str
    confidence: float
    method: str  # "email", "name", "manual", "generated"
    extracted_info: Dict[str, Any]

# Utility Functions
# def extract_student_id_from_email(email_data: EmailData) -> StudentExtractionResult:
#     """Extract student ID from email content using various methods."""
    
#     # Method 1: Look for student ID patterns in email body
#     text_to_search = f"{email_data.subject} {email_data.body_text} {email_data.sender}"
    
#     # Common student ID patterns
#     patterns = [
#         r'\b\d{2}[A-Z]{2,3}\d{4,6}\b',  # Format: 20CS1234, 22AI5678
#         r'\b[A-Z]{2,4}\d{4,8}\b',       # Format: CSE2022001, AIML20220045
#         r'\b\d{4}[A-Z]{2,4}\d{3,4}\b', # Format: 2022CS001, 2023AI045
#         r'\bRoll\s*No[:\s]*([A-Z0-9]+)\b',  # Roll No: ABC123
#         r'\bStudent\s*ID[:\s]*([A-Z0-9]+)\b', # Student ID: ABC123
#         r'\bReg\s*No[:\s]*([A-Z0-9]+)\b',    # Reg No: ABC123
#     ]
    
#     for pattern in patterns:
#         matches = re.findall(pattern, text_to_search, re.IGNORECASE)
#         if matches:
#             student_id = matches[0] if isinstance(matches[0], str) else matches[0]
#             return StudentExtractionResult(
#                 student_id=student_id,
#                 confidence=0.8,
#                 method="pattern_match",
#                 extracted_info={"pattern": pattern, "match": student_id}
#             )
    
#     # Method 2: Extract from email address
#     email_match = re.search(r'([a-zA-Z0-9]+)@', email_data.sender)
#     if email_match:
#         potential_id = email_match.group(1)
#         # Check if it looks like a student ID
#         if re.match(r'^[a-zA-Z]*\d{4,}[a-zA-Z]*\d*$', potential_id):
#             return StudentExtractionResult(
#                 student_id=potential_id,
#                 confidence=0.6,
#                 method="email_username",
#                 extracted_info={"email": email_data.sender, "username": potential_id}
#             )
    
#     # Method 3: Extract name and generate ID
#     name_patterns = [
#         r'My name is ([A-Za-z\s]+)',
#         r'I am ([A-Za-z\s]+)',
#         r'Sincerely,\s*([A-Za-z\s]+)',
#         r'From[:\s]*([A-Za-z\s]+)',
#     ]
    
#     for pattern in name_patterns:
#         match = re.search(pattern, email_data.body_text, re.IGNORECASE)
#         if match:
#             name = match.group(1).strip()
#             # Generate student ID from name
#             name_parts = name.split()
#             if len(name_parts) >= 2:
#                 generated_id = f"{name_parts[0][:4]}{name_parts[-1][:4]}_{datetime.now().strftime('%Y%m')}"
#                 return StudentExtractionResult(
#                     student_id=generated_id.upper(),
#                     confidence=0.4,
#                     method="name_generated",
#                     extracted_info={"name": name, "generated_from": "name_pattern"}
#                 )
    
#     # Method 4: Generate from email hash (fallback)
#     email_hash_short = email_data.email_hash[:8]
#     timestamp = datetime.now().strftime('%m%d')
#     generated_id = f"STU_{email_hash_short}_{timestamp}"
    
#     return StudentExtractionResult(
#         student_id=generated_id,
#         confidence=0.2,
#         method="hash_generated",
#         extracted_info={"email_hash": email_data.email_hash, "method": "fallback"}
#     )

def extract_student_id_from_email(email_data: EmailData) -> StudentExtractionResult:
    """Extract student ID from email content using attachment filename pattern: clg_name_branch.pdf"""
    
    # Method 1: Extract from attachment filenames (PRIMARY METHOD)
    # Pattern: clg_name_branch.pdf
    if email_data.attachments:
        for attachment in email_data.attachments:
            filename = attachment.filename
            logger.info(f"Analyzing attachment filename: {filename}")
            
            # Remove file extension (.pdf, .doc, etc.)
            filename_without_ext = filename.rsplit('.', 1)[0] if '.' in filename else filename
            
            # Look for pattern: clg_name_branch
            # Split by underscore
            parts = filename_without_ext.split('_')
            
            # We expect exactly 3 parts: college_name_branch
            if len(parts) >= 3:
                college = parts[0]
                name = parts[1] 
                branch = '_'.join(parts[2:])  # Join remaining parts in case branch has underscores
                
                # Basic validation - ensure parts aren't empty and have reasonable lengths
                if (college and name and branch and 
                    1 <= len(college) <= 20 and 
                    1 <= len(name) <= 30 and 
                    1 <= len(branch) <= 50):
                    
                    # Create student ID by combining all parts
                    student_id = f"{college}_{name}_{branch}".upper()
                    
                    logger.info(f"Successfully extracted from filename '{filename}': {student_id}")
                    
                    return StudentExtractionResult(
                        student_id=student_id,
                        confidence=0.9,
                        method="attachment_filename",
                        extracted_info={
                            "college": college,
                            "name": name,
                            "branch": branch,
                            "source_filename": filename,
                            "pattern": "clg_name_branch"
                        }
                    )
    
    # Fallback: Generate from email hash if no attachments or pattern doesn't match
    email_hash_short = email_data.email_hash[:8] if email_data.email_hash else "UNKNOWN"
    timestamp = datetime.now().strftime('%m%d%H%M')
    generated_id = f"STU_{email_hash_short}_{timestamp}"
    
    logger.info(f"Using fallback method, generated ID: {generated_id}")
    
    return StudentExtractionResult(
        student_id=generated_id,
        confidence=0.2,
        method="hash_generated",
        extracted_info={"email_hash": email_data.email_hash, "method": "fallback"}
    )

@app.get("/test-filename-extraction/", dependencies=[Depends(get_api_key)])
async def test_filename_extraction(filename: str):
    """Test student ID extraction from attachment filename."""
    
    # Create a test attachment
    test_attachment = EmailAttachment(
        filename=filename,
        content_type="application/pdf",
        path="/test/path",
        size=1000
    )
    
    # Create a minimal email object for testing
    test_email = EmailData(
        id="test",
        subject="Test Application",
        sender="test@example.com",
        date="",
        body_text="Test email body",
        is_application=True,
        keywords_found=["application"],
        attachments=[test_attachment],
        processed_timestamp=datetime.now().isoformat(),
        email_hash="test_hash"
    )
    
    result = extract_student_id_from_email(test_email)
    
    return {
        "test_filename": filename,
        "extraction_result": result,
        "would_create_folder": result.student_id,
        "extraction_method": result.method,
        "confidence": result.confidence,
        "extracted_info": result.extracted_info
    }

async def upload_attachment_to_minio(student_id: str, attachment: EmailAttachment) -> Dict[str, Any]:
    """Upload a single attachment to MinIO."""
    try:
        headers = {"X-API-Key": API_KEY}
        
        # Prepare upload data
        upload_data = {
            "student_id": student_id,
            "object_name": attachment.filename,
            "file_path": attachment.path
        }
        
        # Ensure URL is properly formatted
        upload_url = f"{MINIO_SERVER_URL}/objects/upload/"
        logger.info(f"Uploading to URL: {upload_url}")
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                upload_url,
                json=upload_data,
                headers=headers
            )
            response.raise_for_status()
            return response.json()
            
    except Exception as e:
        logger.error(f"Error uploading attachment {attachment.filename}: {e}")
        raise

async def save_email_to_database(email_data: EmailData, student_id: str, processing_result: ProcessingResult) -> Dict[str, Any]:
    """Save email data to database using objects upload endpoint."""
    try:
        headers = {"X-API-Key": API_KEY}
        
        # Prepare email data for storage
        db_data = {
            "email_id": email_data.id,
            "student_id": student_id,
            "subject": email_data.subject,
            "sender": email_data.sender,
            "recipient": email_data.recipient,
            "date": email_data.date,
            "body_text": email_data.body_text,
            "body_html": email_data.body_html,
            "is_application": email_data.is_application,
            "keywords_found": email_data.keywords_found,
            "email_hash": email_data.email_hash,
            "processed_timestamp": email_data.processed_timestamp,
            "attachments_count": len(email_data.attachments),
            "processing_status": processing_result.status,
            "minio_files": processing_result.minio_files,
            "raw_email_base64": email_data.raw_email_base64,
            "created_at": datetime.now().isoformat()
        }
        
        # Create temporary file for email metadata
        temp_dir = Path("temp_email_data")
        temp_dir.mkdir(exist_ok=True)
        
        email_filename = f"email_metadata_{email_data.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        temp_file_path = temp_dir / email_filename
        
        # Write JSON data to temporary file
        with open(temp_file_path, "w", encoding="utf-8") as f:
            json.dump(db_data, f, indent=2, ensure_ascii=False)
        
        # Upload email metadata using objects upload endpoint
        upload_data = {
            "student_id": student_id,
            "object_name": f"_metadata/{email_filename}",  # Special metadata folder
            "file_path": str(temp_file_path)
        }
        
        upload_url = f"{MINIO_SERVER_URL}/objects/upload/"
        logger.info(f"Saving email metadata to URL: {upload_url}")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                upload_url,
                json=upload_data,
                headers=headers
            )
            response.raise_for_status()
            result = response.json()
            
            # Clean up temporary file
            temp_file_path.unlink()
            
            logger.info(f"Saved email metadata for {student_id} to MinIO: {email_filename}")
            return result
            
    except Exception as e:
        # Clean up temporary file if it exists
        if 'temp_file_path' in locals() and temp_file_path.exists():
            temp_file_path.unlink()
        logger.error(f"Error saving email to database: {e}")
        raise

async def process_single_email(email_data: EmailData) -> ProcessingResult:
    """Process a single email: extract student ID, upload attachments, save to DB."""
    result = ProcessingResult(
        email_id=email_data.id,
        status="processing",
        total_attachments=len(email_data.attachments)
    )
    
    try:
        # Step 1: Extract student ID
        student_extraction = extract_student_id_from_email(email_data)
        result.student_id = student_extraction.student_id
        
        logger.info(f"Extracted student ID '{student_extraction.student_id}' for email {email_data.id} "
                   f"using method '{student_extraction.method}' with confidence {student_extraction.confidence}")
        
        # Step 2: Upload attachments to MinIO
        uploaded_files = []
        for attachment in email_data.attachments:
            try:
                # Check if file exists
                if not Path(attachment.path).exists():
                    result.errors.append(f"Attachment file not found: {attachment.path}")
                    continue
                
                upload_result = await upload_attachment_to_minio(student_extraction.student_id, attachment)
                uploaded_files.append(f"{student_extraction.student_id}/{attachment.filename}")
                result.attachments_uploaded += 1
                
                logger.info(f"Uploaded attachment {attachment.filename} for student {student_extraction.student_id}")
                
            except Exception as e:
                error_msg = f"Failed to upload {attachment.filename}: {str(e)}"
                result.errors.append(error_msg)
                logger.error(error_msg)
        
        result.minio_files = uploaded_files
        
        # Step 3: Save email data to database
        try:
            db_result = await save_email_to_database(email_data, student_extraction.student_id, result)
            result.database_saved = True
            logger.info(f"Saved email {email_data.id} to database for student {student_extraction.student_id}")
            
        except Exception as e:
            error_msg = f"Failed to save to database: {str(e)}"
            result.errors.append(error_msg)
            logger.error(error_msg)
        
        # Determine final status
        if result.database_saved and result.attachments_uploaded == result.total_attachments:
            result.status = "completed"
        elif result.database_saved or result.attachments_uploaded > 0:
            result.status = "partial"
        else:
            result.status = "failed"
            
    except Exception as e:
        result.status = "failed"
        result.errors.append(f"Processing failed: {str(e)}")
        logger.error(f"Error processing email {email_data.id}: {e}")
    
    return result

# API Endpoints

@app.get("/")
def read_root():
    return {
        "status": "running",
        "message": "Email Processing Manager API is running",
        "services": {
            "db_server": DB_SERVER_URL,
            "email_poller": EMAIL_POLLER_URL,
            "minio_server": MINIO_SERVER_URL
        },
        "config": {
            "api_key_configured": bool(API_KEY and API_KEY != "your-secret-api-key-123"),
            "urls_configured": {
                "db_server": DB_SERVER_URL,
                "email_poller": EMAIL_POLLER_URL,
                "minio_server": MINIO_SERVER_URL
            }
        }
    }

@app.get("/extract-student-id/", dependencies=[Depends(get_api_key)])
async def extract_student_id_endpoint(email_text: str):
    """Test student ID extraction from email text."""
    # Create a minimal email object for testing
    test_email = EmailData(
        id="test",
        subject="",
        sender="test@example.com",
        date="",
        body_text=email_text,
        is_application=True,
        keywords_found=[],
        processed_timestamp=datetime.now().isoformat(),
        email_hash="test"
    )
    
    result = extract_student_id_from_email(test_email)
    return result

@app.get("/health")
async def health_check():
    """Check health of all connected services."""
    health_status = {
        "manager": "healthy",
        "timestamp": datetime.now().isoformat(),
        "services": {}
    }
    
    # Check each service
    services = {
        "db_server": DB_SERVER_URL,
        "email_poller": EMAIL_POLLER_URL,
        # "minio_server": MINIO_SERVER_URL
    }
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        for service_name, url in services.items():
            try:
                response = await client.get(f"{url}/health" if "health" not in url else url)
                health_status["services"][service_name] = {
                    "status": "healthy" if response.status_code == 200 else "unhealthy",
                    "url": url,
                    "response_time": response.elapsed.total_seconds()
                }
            except Exception as e:
                health_status["services"][service_name] = {
                    "status": "unhealthy",
                    "url": url,
                    "error": str(e)
                }
    
    return health_status

@app.post("/process-email/", response_model=ProcessingResult, dependencies=[Depends(get_api_key)])
async def process_email(email_data: EmailData):
    """Process a single email: extract student info, upload attachments, save to DB."""
    return await process_single_email(email_data)

@app.post("/process-batch/", response_model=BatchProcessingResult, dependencies=[Depends(get_api_key)])
async def process_email_batch(email_batch: EmailBatch):
    """Process a batch of emails from the email poller."""
    start_time = datetime.now()
    
    results = []
    successful = 0
    failed = 0
    errors = []
    
    # Process emails concurrently (but limit concurrency to avoid overwhelming services)
    semaphore = asyncio.Semaphore(3)  # Process max 3 emails concurrently
    
    async def process_with_semaphore(email_data: EmailData):
        async with semaphore:
            return await process_single_email(email_data)
    
    try:
        # Process all emails
        tasks = [process_with_semaphore(email) for email in email_batch.emails]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Count successes and failures
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                failed += 1
                errors.append(f"Email {email_batch.emails[i].id}: {str(result)}")
                # Create a failed result object
                results[i] = ProcessingResult(
                    email_id=email_batch.emails[i].id,
                    status="failed",
                    errors=[str(result)]
                )
            elif result.status == "completed":
                successful += 1
            else:
                failed += 1
    
    except Exception as e:
        errors.append(f"Batch processing error: {str(e)}")
        logger.error(f"Batch processing error: {e}")
    
    processing_time = (datetime.now() - start_time).total_seconds()
    
    return BatchProcessingResult(
        total_processed=len(email_batch.emails),
        successful=successful,
        failed=failed,
        results=results,
        processing_time=processing_time,
        errors=errors
    )

@app.get("/poll-and-process/", response_model=BatchProcessingResult, dependencies=[Depends(get_api_key)])
async def poll_and_process():
    """Poll emails from email service and process them automatically."""
    try:
        headers = {"X-API-Key": API_KEY}
        
        # Get emails from poller
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(
                f"{EMAIL_POLLER_URL}/application-emails",
                headers=headers
            )
            response.raise_for_status()
            email_data = response.json()
        
        # Convert to EmailBatch model
        email_batch = EmailBatch(**email_data)
        
        # Process the batch
        result = await process_email_batch(email_batch)
        
        logger.info(f"Polled and processed {result.total_processed} emails: "
                   f"{result.successful} successful, {result.failed} failed")
        
        return result
        
    except Exception as e:
        logger.error(f"Error in poll-and-process: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to poll and process: {str(e)}")

@app.post("/process-background/", dependencies=[Depends(get_api_key)])
async def process_emails_background(background_tasks: BackgroundTasks, email_batch: EmailBatch):
    """Process emails in the background and save results to file."""
    
    async def process_and_save():
        try:
            result = await process_email_batch(email_batch)
            
            # Save results to file
            output_dir = Path("processing_results")
            output_dir.mkdir(exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = output_dir / f"processing_result_{timestamp}.json"
            
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(result.dict(), f, indent=2, ensure_ascii=False)
            
            logger.info(f"Background processing completed. Results saved to {output_file}")
            
        except Exception as e:
            logger.error(f"Background processing failed: {e}")
    
    background_tasks.add_task(process_and_save)
    
    return {
        "status": "Background processing started",
        "message": f"Processing {len(email_batch.emails)} emails in background",
        "timestamp": datetime.now().isoformat()
    }

@app.get("/debug/config", dependencies=[Depends(get_api_key)])
async def debug_config():
    """Debug endpoint to check configuration and test URLs."""
    config_info = {
        "environment_variables": {
            "API_KEY": "***" if API_KEY else "NOT SET",
            "DB_SERVER_URL": DB_SERVER_URL,
            "EMAIL_POLLER_URL": EMAIL_POLLER_URL, 
            "MINIO_SERVER_URL": MINIO_SERVER_URL
        },
        "constructed_urls": {
            "minio_upload": f"{MINIO_SERVER_URL}/objects/upload/",
            "email_poller": f"{EMAIL_POLLER_URL}/application-emails",
            "db_health": f"{DB_SERVER_URL}/health"
        },
        "url_validation": {}
    }
    
    # Test URL construction
    for name, url in config_info["constructed_urls"].items():
        try:
            # Basic URL validation
            if url.startswith(("http://", "https://")):
                config_info["url_validation"][name] = "valid_protocol"
            else:
                config_info["url_validation"][name] = "missing_protocol"
        except Exception as e:
            config_info["url_validation"][name] = f"error: {str(e)}"
    
    return config_info

@app.get("/debug/test-upload", dependencies=[Depends(get_api_key)])
async def debug_test_upload():
    """Test endpoint to debug upload URL construction."""
    test_data = {
        "student_id": "TEST_STUDENT",
        "object_name": "test_file.txt",
        "file_path": "/tmp/nonexistent.txt"
    }
    
    upload_url = f"{MINIO_SERVER_URL}/objects/upload/"
    
    return {
        "test_upload_data": test_data,
        "constructed_url": upload_url,
        "minio_server_url": MINIO_SERVER_URL,
        "url_has_protocol": upload_url.startswith(("http://", "https://")),
        "environment_check": {
            "MINIO_SERVER_URL": os.getenv("MINIO_SERVER_URL"),
            "DB_SERVER_URL": os.getenv("DB_SERVER_URL")
        }
    }

if __name__ == "__main__":
    import uvicorn
    
    # Create necessary directories
    Path("processing_results").mkdir(exist_ok=True)
    Path("temp_email_data").mkdir(exist_ok=True)
    
    # Debug configuration
    logger.info(f"Configuration:")
    logger.info(f"  API_KEY: {'***' if API_KEY else 'NOT SET'}")
    logger.info(f"  DB_SERVER_URL: {DB_SERVER_URL}")
    logger.info(f"  EMAIL_POLLER_URL: {EMAIL_POLLER_URL}")
    logger.info(f"  MINIO_SERVER_URL: {MINIO_SERVER_URL}")
    
    # Run the FastAPI app
    uvicorn.run(app, host="0.0.0.0", port=8003, log_level="info")