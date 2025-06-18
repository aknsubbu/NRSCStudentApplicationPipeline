from fastapi import FastAPI, HTTPException, Depends, Security, BackgroundTasks
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Tuple
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
from enum import Enum

# Load environment variables
load_dotenv(dotenv_path=Path(__file__).parent.parent / '.env')

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("email-manager")

app = FastAPI(
    title="Email Processing Manager API", 
    description="Orchestrates email processing with notifications and AI validation"
)

#  TODO: Add a route to store student details in a DB when received
#  TODO: Add a route to fetch student details from the DB when the information required response is received
#  TODO: Add a route to store the information required response in the DB
#  TODO: Add a route to pass the documents from the Doc Store and the details from the DB to the AI server for validation
#  TODO: Add a route to store the validation result in the DB
#  TODO: Add a route to store student profile in the DB which is from the AI Server
#  TODO: Add a route to send a email to admin for screening
#  TODO: Add the DB control fns to the manager
#  TODO: Complete the flow of the application

# Configuration
API_KEY = os.getenv("API_KEY", "your-secret-api-key-123")
DB_SERVER_URL = os.getenv("DB_SERVER_URL", "http://localhost:8000")
EMAIL_POLLER_URL = os.getenv("EMAIL_POLLER_URL", "http://localhost:8002")
MINIO_SERVER_URL = os.getenv("MINIO_SERVER_URL", "http://localhost:8000")
EMAIL_OUT_SERVER_URL = os.getenv("EMAIL_OUT_SERVER_URL", "http://localhost:8001")
AI_SERVER_URL = os.getenv("AI_SERVER_URL", "http://localhost:8005")

# Feature flags
ENABLE_EMAIL_NOTIFICATIONS = os.getenv("ENABLE_EMAIL_NOTIFICATIONS", "true").lower() == "true"
ENABLE_AI_VALIDATION = os.getenv("ENABLE_AI_VALIDATION", "true").lower() == "true"

# File paths
VALIDATED_APPLICATIONS_FILE = Path("validated_applications.txt")

# API Key Authentication
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def get_api_key(api_key: str = Security(api_key_header)):
    if api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API Key")
    return api_key

# Enums
class ValidationStatus(str, Enum):
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"

class ProcessingStage(str, Enum):
    RECEIVED = "received"
    PROCESSING = "processing"
    STORAGE_COMPLETE = "storage_complete"
    VALIDATION_COMPLETE = "validation_complete"
    NOTIFICATION_SENT = "notification_sent"
    COMPLETED = "completed"
    FAILED = "failed"

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

class StudentExtractionResult(BaseModel):
    student_id: str
    student_name: str
    college: str
    branch: str
    confidence: float
    method: str
    extracted_info: Dict[str, Any]

class StorageResult(BaseModel):
    success: bool
    uploaded_files: List[str] = []
    database_saved: bool = False
    errors: List[str] = []

class AIValidationResult(BaseModel):
    status: ValidationStatus
    feedback: str
    missing_documents: List[str] = []
    validation_details: Dict[str, Any] = {}
    processing_time: float = 0.0

class EmailNotificationResult(BaseModel):
    sent: bool
    email_type: str
    recipient: str
    error: Optional[str] = None

class ApplicationProcessingResult(BaseModel):
    email_id: str
    student_id: str
    student_name: str
    processing_stage: ProcessingStage
    storage_result: Optional[StorageResult] = None
    validation_result: Optional[AIValidationResult] = None
    notifications_sent: Dict[str, bool] = {}
    logged_to_file: bool = False
    errors: List[str] = []
    warnings: List[str] = []
    processing_time: float = 0.0

class BatchProcessingReport(BaseModel):
    total_processed: int
    successful: int
    failed: int
    validation_passed: int
    validation_failed: int
    notifications_sent: int
    results: List[ApplicationProcessingResult]
    processing_time: float
    errors: List[str] = []

# Utility Functions
def extract_student_info_from_email(email_data: EmailData) -> StudentExtractionResult:
    """Extract student information from email using attachment filename pattern: clg_name_branch.pdf"""
    
    # Primary method: Extract from attachment filenames
    if email_data.attachments:
        for attachment in email_data.attachments:
            filename = attachment.filename
            logger.info(f"Analyzing attachment filename: {filename}")
            
            # Remove file extension
            filename_without_ext = filename.rsplit('.', 1)[0] if '.' in filename else filename
            
            # Look for pattern: clg_name_branch
            parts = filename_without_ext.split('_')
            
            if len(parts) >= 3:
                college = parts[0]
                name = parts[1] 
                branch = '_'.join(parts[2:])  # Join remaining parts
                
                # Basic validation
                if (college and name and branch and 
                    1 <= len(college) <= 20 and 
                    1 <= len(name) <= 30 and 
                    1 <= len(branch) <= 50):
                    
                    student_id = f"{college}_{name}_{branch}".upper()
                    
                    logger.info(f"Successfully extracted from filename '{filename}': {student_id}")
                    
                    return StudentExtractionResult(
                        student_id=student_id,
                        student_name=name.replace('_', ' ').title(),
                        college=college.upper(),
                        branch=branch.replace('_', ' ').title(),
                        confidence=0.9,
                        method="attachment_filename",
                        extracted_info={
                            "source_filename": filename,
                            "pattern": "clg_name_branch"
                        }
                    )
    
    # Fallback: Generate from email hash
    email_hash_short = email_data.email_hash[:8] if email_data.email_hash else "UNKNOWN"
    timestamp = datetime.now().strftime('%m%d%H%M')
    generated_id = f"STU_{email_hash_short}_{timestamp}"
    
    # Try to extract name from email address
    email_username = email_data.sender.split('@')[0]
    student_name = email_username.replace('.', ' ').replace('_', ' ').title()
    
    logger.info(f"Using fallback method, generated ID: {generated_id}")
    
    return StudentExtractionResult(
        student_id=generated_id,
        student_name=student_name,
        college="UNKNOWN",
        branch="UNKNOWN",
        confidence=0.2,
        method="hash_generated",
        extracted_info={"email_hash": email_data.email_hash, "method": "fallback"}
    )

# Core Processing Functions
async def upload_attachments_to_minio(student_id: str, attachments: List[EmailAttachment]) -> Tuple[List[str], List[str]]:
    """Upload attachments to MinIO. Returns (uploaded_files, errors)"""
    uploaded_files = []
    errors = []
    
    headers = {"X-API-Key": API_KEY}
    upload_url = f"{MINIO_SERVER_URL}/objects/upload/"
    
    for attachment in attachments:
        try:
            # Check if file exists
            if not Path(attachment.path).exists():
                errors.append(f"File not found: {attachment.path}")
                continue
            
            upload_data = {
                "student_id": student_id,
                "object_name": attachment.filename,
                "file_path": attachment.path
            }
            
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(upload_url, json=upload_data, headers=headers)
                response.raise_for_status()
                
                uploaded_files.append(f"{student_id}/{attachment.filename}")
                logger.info(f"Uploaded {attachment.filename} for {student_id}")
                
        except Exception as e:
            error_msg = f"Failed to upload {attachment.filename}: {str(e)}"
            errors.append(error_msg)
            logger.error(error_msg)
    
    return uploaded_files, errors

async def save_email_metadata(email_data: EmailData, student_id: str, uploaded_files: List[str]) -> bool:
    """Save email metadata to database via MinIO"""
    try:
        headers = {"X-API-Key": API_KEY}
        
        # Prepare metadata
        metadata = {
            "email_id": email_data.id,
            "student_id": student_id,
            "subject": email_data.subject,
            "sender": email_data.sender,
            "date": email_data.date,
            "body_text": email_data.body_text,
            "is_application": email_data.is_application,
            "keywords_found": email_data.keywords_found,
            "email_hash": email_data.email_hash,
            "processed_timestamp": email_data.processed_timestamp,
            "attachments_count": len(email_data.attachments),
            "uploaded_files": uploaded_files,
            "created_at": datetime.now().isoformat()
        }
        
        # Save as temporary file
        temp_dir = Path("temp_email_data")
        temp_dir.mkdir(exist_ok=True)
        
        filename = f"email_metadata_{email_data.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        temp_path = temp_dir / filename
        
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        
        # Upload to MinIO
        upload_data = {
            "student_id": student_id,
            "object_name": f"_metadata/{filename}",
            "file_path": str(temp_path)
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{MINIO_SERVER_URL}/objects/upload/",
                json=upload_data,
                headers=headers
            )
            response.raise_for_status()
        
        # Clean up
        temp_path.unlink()
        logger.info(f"Saved email metadata for {student_id}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to save email metadata: {e}")
        if 'temp_path' in locals() and temp_path.exists():
            temp_path.unlink()
        return False

async def store_email_and_attachments(email_data: EmailData, student_id: str) -> StorageResult:
    """Handle storage of email and attachments"""
    result = StorageResult(success=False)
    
    try:
        # Upload attachments
        uploaded_files, upload_errors = await upload_attachments_to_minio(student_id, email_data.attachments)
        result.uploaded_files = uploaded_files
        result.errors.extend(upload_errors)
        
        # Save email metadata
        result.database_saved = await save_email_metadata(email_data, student_id, uploaded_files)
        
        # Determine success
        result.success = result.database_saved and len(uploaded_files) > 0
        
    except Exception as e:
        result.errors.append(f"Storage error: {str(e)}")
        logger.error(f"Storage failed for {student_id}: {e}")
    
    return result

# AI Validation Functions
async def validate_documents_with_ai(attachments: List[EmailAttachment], student_id: str) -> AIValidationResult:
    """Validate documents using AI service"""
    start_time = datetime.now()
    
    try:
        if not ENABLE_AI_VALIDATION:
            return AIValidationResult(
                status=ValidationStatus.PASSED,
                feedback="AI validation disabled - auto-passed",
                processing_time=0.0
            )
        
        # Analyze attachment types
        attachment_names = [att.filename.lower() for att in attachments]
        
        has_resume = any('resume' in name or 'cv' in name for name in attachment_names)
        has_marksheet = any('marksheet' in name or 'grade' in name or 'transcript' in name for name in attachment_names)
        has_lor = any('recommendation' in name or 'lor' in name or 'letter' in name for name in attachment_names)
        
        validation_details = {
            "documents_found": {
                "resume": has_resume,
                "marksheet": has_marksheet,
                "letter_of_recommendation": has_lor
            },
            "total_attachments": len(attachments),
            "attachment_filenames": [att.filename for att in attachments]
        }
        
        # Determine validation result
        missing_docs = []
        if not has_resume:
            missing_docs.append("Resume/CV")
        if not has_marksheet:
            missing_docs.append("Academic transcripts/marksheets")
        if not has_lor:
            missing_docs.append("Letter of recommendation")
        
        if len(attachments) >= 3 and has_resume and has_marksheet:
            status = ValidationStatus.PASSED
            feedback = "All required documents are present and appear to be in correct format."
        else:
            status = ValidationStatus.FAILED
            feedback = f"Missing required documents: {', '.join(missing_docs)}" if missing_docs else "Insufficient documents provided"
        
        processing_time = (datetime.now() - start_time).total_seconds()
        
        return AIValidationResult(
            status=status,
            feedback=feedback,
            missing_documents=missing_docs,
            validation_details=validation_details,
            processing_time=processing_time
        )
        
    except Exception as e:
        logger.error(f"AI validation error for {student_id}: {e}")
        return AIValidationResult(
            status=ValidationStatus.ERROR,
            feedback=f"Validation error: {str(e)}",
            validation_details={"error": str(e)},
            processing_time=(datetime.now() - start_time).total_seconds()
        )

# Email Notification Functions
async def send_application_received_email(student_email: str, student_name: str, student_id: str) -> EmailNotificationResult:
    """Send application received confirmation email"""
    if not ENABLE_EMAIL_NOTIFICATIONS:
        return EmailNotificationResult(sent=False, email_type="application_received", recipient=student_email, error="Notifications disabled")
    
    try:
        headers = {"X-API-Key": API_KEY}
        application_id = f"APP_{student_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        email_data = {
            "recipient": student_email,
            "student_name": student_name,
            "student_id": student_id,
            "application_id": application_id
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{EMAIL_OUT_SERVER_URL}/email/template/application_received",
                json=email_data,
                headers=headers
            )
            response.raise_for_status()
            
        logger.info(f"Application received email sent to {student_email}")
        return EmailNotificationResult(sent=True, email_type="application_received", recipient=student_email)
        
    except Exception as e:
        error_msg = f"Failed to send application received email: {str(e)}"
        logger.error(error_msg)
        return EmailNotificationResult(sent=False, email_type="application_received", recipient=student_email, error=error_msg)

async def send_validation_result_email(student_email: str, student_name: str, student_id: str, validation_result: AIValidationResult) -> EmailNotificationResult:
    """Send validation result email (passed or failed)"""
    if not ENABLE_EMAIL_NOTIFICATIONS:
        return EmailNotificationResult(sent=False, email_type="validation_result", recipient=student_email, error="Notifications disabled")
    
    try:
        headers = {"X-API-Key": API_KEY}
        
        if validation_result.status == ValidationStatus.PASSED:
            # Send validation passed email
            email_data = {
                "recipient": student_email,
                "student_name": student_name,
                "student_id": student_id,
                "application_id": f"APP_{student_id}"
            }
            
            endpoint = f"{EMAIL_OUT_SERVER_URL}/email/template/application_validated"
            email_type = "validation_passed"
            
        else:
            # Send validation failed email
            email_data = {
                "recipient": student_email,
                "subject": "Application Validation Failed - Action Required",
                "template_name": "validation_failed.html",
                "template_data": {
                    "student_name": student_name,
                    "message": validation_result.feedback,
                    "issues": validation_result.missing_documents
                }
            }
            
            endpoint = f"{EMAIL_OUT_SERVER_URL}/email/template/validation_failed"
            email_type = "validation_failed"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(endpoint, json=email_data, headers=headers)
            response.raise_for_status()
        
        logger.info(f"{email_type} email sent to {student_email}")
        return EmailNotificationResult(sent=True, email_type=email_type, recipient=student_email)
        
    except Exception as e:
        error_msg = f"Failed to send validation result email: {str(e)}"
        logger.error(error_msg)
        return EmailNotificationResult(sent=False, email_type="validation_result", recipient=student_email, error=error_msg)

async def send_information_required_email(student_email: str, student_name: str, student_id: str) -> EmailNotificationResult:
    """Send information required email"""
    if not ENABLE_EMAIL_NOTIFICATIONS:
        return EmailNotificationResult(sent=False, email_type="information_required", recipient=student_email, error="Notifications disabled")
    
    try:
        headers = {"X-API-Key": API_KEY}
        
        email_data = {
            "recipient": student_email,
            "student_name": student_name,
            "student_id": student_id,
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{EMAIL_OUT_SERVER_URL}/email/template/information_required",
                json=email_data,
                headers=headers
            )
            response.raise_for_status()
            
        logger.info(f"Information required email sent to {student_email}")
        return EmailNotificationResult(sent=True, email_type="information_required", recipient=student_email)
        
    except Exception as e:
        error_msg = f"Failed to send information required email: {str(e)}"
        logger.error(error_msg)
        return EmailNotificationResult(sent=False, email_type="information_required", recipient=student_email, error=error_msg)
    
    
# Application Logging
async def log_application_to_file(result: ApplicationProcessingResult) -> bool:
    """Log application details to validated_applications.txt"""
    try:
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "email_id": result.email_id,
            "student_id": result.student_id,
            "student_name": result.student_name,
            "sender_email": result.notifications_sent.get("recipient", "unknown"),
            "validation_status": result.validation_result.status if result.validation_result else "not_validated",
            "validation_feedback": result.validation_result.feedback if result.validation_result else "",
            "storage_success": result.storage_result.success if result.storage_result else False,
            "uploaded_files": result.storage_result.uploaded_files if result.storage_result else [],
            "notifications_sent": result.notifications_sent,
            "processing_stage": result.processing_stage,
            "errors": result.errors,
            "processing_time": result.processing_time
        }
        
        # Append to file
        with open(VALIDATED_APPLICATIONS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
        
        logger.info(f"Logged application {result.student_id} to file")
        return True
        
    except Exception as e:
        logger.error(f"Failed to log application to file: {e}")
        return False

# Main Processing Function
async def process_application_email(email_data: EmailData) -> ApplicationProcessingResult:
    """Process a single application email through the complete workflow"""
    start_time = datetime.now()
    
    # Initialize result
    result = ApplicationProcessingResult(
        email_id=email_data.id,
        student_id="",
        student_name="",
        processing_stage=ProcessingStage.RECEIVED
    )
    
    try:
        # Step 1: Extract student information
        student_info = extract_student_info_from_email(email_data)
        result.student_id = student_info.student_id
        result.student_name = student_info.student_name
        
        logger.info(f"Processing application from {result.student_name} ({result.student_id})")
        
        # Step 2: Send application received email (non-blocking)
        notification_task = asyncio.create_task(
            send_application_received_email(email_data.sender, student_info.student_name, student_info.student_id)
        )
        
        result.processing_stage = ProcessingStage.PROCESSING
        
        # Step 3: Parallel processing of storage and validation
        storage_task = asyncio.create_task(
            store_email_and_attachments(email_data, student_info.student_id)
        )
        
        validation_task = asyncio.create_task(
            validate_documents_with_ai(email_data.attachments, student_info.student_id)
        )
        
        # Wait for parallel tasks
        storage_result, validation_result = await asyncio.gather(storage_task, validation_task)
        result.storage_result = storage_result
        result.validation_result = validation_result
        
        # Wait for initial notification
        notification_result = await notification_task
        result.notifications_sent[email_data.sender] = notification_result.sent
        
        if storage_result.success:
            result.processing_stage = ProcessingStage.STORAGE_COMPLETE
        
        # Step 4: Send validation result email
        if validation_result.status != ValidationStatus.ERROR:
            result.processing_stage = ProcessingStage.VALIDATION_COMPLETE
            
            validation_email_result = await send_validation_result_email(
                email_data.sender, 
                student_info.student_name, 
                student_info.student_id, 
                validation_result
            )
            
            result.notifications_sent[f"{email_data.sender}_validation"] = validation_email_result.sent
            
            if validation_email_result.sent:
                result.processing_stage = ProcessingStage.NOTIFICATION_SENT
        
        # Step 5: Log application to file
        result.logged_to_file = await log_application_to_file(result)
        
        # Determine final status
        if result.storage_result.success and result.logged_to_file:
            result.processing_stage = ProcessingStage.COMPLETED
        elif result.storage_result.success:
            result.processing_stage = ProcessingStage.STORAGE_COMPLETE
        else:
            result.processing_stage = ProcessingStage.FAILED
        
        # Collect errors and warnings
        if result.storage_result:
            result.errors.extend(result.storage_result.errors)
        
        if not notification_result.sent:
            result.warnings.append("Failed to send application received email")
        
        if result.validation_result.status == ValidationStatus.ERROR:
            result.warnings.append("AI validation encountered an error")
        
    except Exception as e:
        result.processing_stage = ProcessingStage.FAILED
        result.errors.append(f"Processing failed: {str(e)}")
        logger.error(f"Failed to process application {email_data.id}: {e}")
    
    result.processing_time = (datetime.now() - start_time).total_seconds()
    
    logger.info(f"Completed processing {result.student_id} in {result.processing_time:.2f}s - Stage: {result.processing_stage}")
    
    return result

# Batch Processing
async def process_application_batch(email_batch: EmailBatch) -> BatchProcessingReport:
    """Process a batch of application emails"""
    start_time = datetime.now()
    
    results = []
    successful = 0
    failed = 0
    validation_passed = 0
    validation_failed = 0
    notifications_sent = 0
    
    # Process with limited concurrency
    semaphore = asyncio.Semaphore(3)
    
    async def process_with_semaphore(email_data: EmailData):
        async with semaphore:
            return await process_application_email(email_data)
    
    try:
        # Process all emails
        tasks = [process_with_semaphore(email) for email in email_batch.emails]
        results = await asyncio.gather(*tasks, return_exceptions=False)
        
        # Analyze results
        for result in results:
            if result.processing_stage == ProcessingStage.COMPLETED:
                successful += 1
            else:
                failed += 1
            
            if result.validation_result:
                if result.validation_result.status == ValidationStatus.PASSED:
                    validation_passed += 1
                elif result.validation_result.status == ValidationStatus.FAILED:
                    validation_failed += 1
            
            notifications_sent += len([v for v in result.notifications_sent.values() if v])
    
    except Exception as e:
        logger.error(f"Batch processing error: {e}")
        return BatchProcessingReport(
            total_processed=0,
            successful=0,
            failed=len(email_batch.emails),
            validation_passed=0,
            validation_failed=0,
            notifications_sent=0,
            results=[],
            processing_time=0.0,
            errors=[str(e)]
        )
    
    processing_time = (datetime.now() - start_time).total_seconds()
    
    return BatchProcessingReport(
        total_processed=len(results),
        successful=successful,
        failed=failed,
        validation_passed=validation_passed,
        validation_failed=validation_failed,
        notifications_sent=notifications_sent,
        results=results,
        processing_time=processing_time
    )

# API Endpoints
@app.get("/")
def read_root():
    return {
        "status": "running",
        "message": "Email Processing Manager API with AI Validation and Notifications",
        "version": "2.0",
        "features": {
            "email_notifications": ENABLE_EMAIL_NOTIFICATIONS,
            "ai_validation": ENABLE_AI_VALIDATION
        },
        "services": {
            "email_poller": EMAIL_POLLER_URL,
            "minio_storage": MINIO_SERVER_URL,
            "email_notifications": EMAIL_OUT_SERVER_URL,
            "ai_validation": AI_SERVER_URL
        },
        "workflow": [
            "1. Poll application emails",
            "2. Send application received notification",
            "3. Process documents and validate in parallel",
            "4. Send validation result notification",
            "5. Log applications to file"
        ]
    }

@app.get("/health")
async def health_check():
    """Check health of all connected services"""
    health_status = {
        "manager": "healthy",
        "timestamp": datetime.now().isoformat(),
        "services": {}
    }
    
    services = {
        "email_poller": EMAIL_POLLER_URL,
        "minio_storage": MINIO_SERVER_URL,
        "email_notifications": EMAIL_OUT_SERVER_URL if ENABLE_EMAIL_NOTIFICATIONS else None,
        "ai_validation": AI_SERVER_URL if ENABLE_AI_VALIDATION else None
    }
    
    async with httpx.AsyncClient(timeout=5.0) as client:
        for service_name, url in services.items():
            if url is None:
                health_status["services"][service_name] = {"status": "disabled"}
                continue
                
            try:
                response = await client.get(f"{url}/health")
                health_status["services"][service_name] = {
                    "status": "healthy" if response.status_code == 200 else "unhealthy",
                    "url": url
                }
            except Exception as e:
                health_status["services"][service_name] = {
                    "status": "unhealthy",
                    "url": url,
                    "error": str(e)
                }
    
    return health_status

# @app.post("/process-email/", response_model=ApplicationProcessingResult, dependencies=[Depends(get_api_key)])
# async def process_email(email_data: EmailData):
#     """Process a single application email"""
#     return await process_application_email(email_data)

# @app.post("/process-batch/", response_model=BatchProcessingReport, dependencies=[Depends(get_api_key)])
# async def process_batch(email_batch: EmailBatch):
#     """Process a batch of application emails"""
#     return await process_application_batch(email_batch)

# @app.get("/poll-and-process/", response_model=BatchProcessingReport, dependencies=[Depends(get_api_key)])
# async def poll_and_process():
#     """Poll emails from email service and process them"""
#     try:
#         headers = {"X-API-Key": API_KEY}
        
#         # Get emails from poller
#         async with httpx.AsyncClient(timeout=60.0) as client:
#             response = await client.get(
#                 f"{EMAIL_POLLER_URL}/application-emails",
#                 headers=headers
#             )
#             response.raise_for_status()
#             email_data = response.json()
        
#         # Convert to EmailBatch model
#         email_batch = EmailBatch(**email_data)
        
#         logger.info(f"Polled {email_batch.total_emails} emails, {email_batch.application_emails} are applications")
        
#         # Process the batch
#         result = await process_application_batch(email_batch)
        
#         logger.info(
#             f"Processed {result.total_processed} emails: "
#             f"{result.successful} successful, {result.failed} failed, "
#             f"{result.validation_passed} passed validation, {result.validation_failed} failed validation"
#         )
        
#         return result
        
#     except Exception as e:
#         logger.error(f"Error in poll-and-process: {e}")
#         raise HTTPException(status_code=500, detail=f"Failed to poll and process: {str(e)}")

# @app.get("/applications/", dependencies=[Depends(get_api_key)])
# async def get_applications(status: Optional[ValidationStatus] = None, limit: int = 100):
#     """Get logged applications from file"""
#     try:
#         if not VALIDATED_APPLICATIONS_FILE.exists():
#             return {"applications": [], "total": 0}
        
#         applications = []
#         with open(VALIDATED_APPLICATIONS_FILE, "r", encoding="utf-8") as f:
#             for line in f:
#                 try:
#                     app = json.loads(line.strip())
#                     if status is None or app.get("validation_status") == status:
#                         applications.append(app)
#                 except json.JSONDecodeError:
#                     continue
        
#         # Sort by timestamp (newest first)
#         applications.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        
#         return {
#             "applications": applications[:limit],
#             "total": len(applications),
#             "filtered_by": status
#         }
        
#     except Exception as e:
#         logger.error(f"Error reading applications: {e}")
#         raise HTTPException(status_code=500, detail=f"Failed to read applications: {str(e)}")

# @app.get("/applications/{student_id}", dependencies=[Depends(get_api_key)])
# async def get_application_by_student_id(student_id: str):
#     """Get specific application by student ID"""
#     try:
#         if not VALIDATED_APPLICATIONS_FILE.exists():
#             raise HTTPException(status_code=404, detail="Application not found")
        
#         with open(VALIDATED_APPLICATIONS_FILE, "r", encoding="utf-8") as f:
#             for line in f:
#                 try:
#                     app = json.loads(line.strip())
#                     if app.get("student_id") == student_id:
#                         return app
#                 except json.JSONDecodeError:
#                     continue
        
#         raise HTTPException(status_code=404, detail="Application not found")
        
#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.error(f"Error reading application: {e}")
#         raise HTTPException(status_code=500, detail=f"Failed to read application: {str(e)}")

# @app.get("/stats/", dependencies=[Depends(get_api_key)])
# async def get_processing_stats():
#     """Get processing statistics"""
#     try:
#         stats = {
#             "total_applications": 0,
#             "validation_passed": 0,
#             "validation_failed": 0,
#             "validation_error": 0,
#             "storage_success": 0,
#             "notifications_sent": 0,
#             "average_processing_time": 0.0
#         }
        
#         if not VALIDATED_APPLICATIONS_FILE.exists():
#             return stats
        
#         processing_times = []
        
#         with open(VALIDATED_APPLICATIONS_FILE, "r", encoding="utf-8") as f:
#             for line in f:
#                 try:
#                     app = json.loads(line.strip())
#                     stats["total_applications"] += 1
                    
#                     validation_status = app.get("validation_status")
#                     if validation_status == "passed":
#                         stats["validation_passed"] += 1
#                     elif validation_status == "failed":
#                         stats["validation_failed"] += 1
#                     elif validation_status == "error":
#                         stats["validation_error"] += 1
                    
#                     if app.get("storage_success"):
#                         stats["storage_success"] += 1
                    
#                     notifications = app.get("notifications_sent", {})
#                     stats["notifications_sent"] += len([v for v in notifications.values() if v])
                    
#                     if app.get("processing_time"):
#                         processing_times.append(app["processing_time"])
                        
#                 except json.JSONDecodeError:
#                     continue
        
#         if processing_times:
#             stats["average_processing_time"] = sum(processing_times) / len(processing_times)
        
#         return stats
        
#     except Exception as e:
#         logger.error(f"Error calculating stats: {e}")
#         raise HTTPException(status_code=500, detail=f"Failed to calculate stats: {str(e)}")

# if __name__ == "__main__":
#     import uvicorn
    
#     # Create necessary directories
#     Path("temp_email_data").mkdir(exist_ok=True)
    
#     # Log configuration
#     logger.info("=" * 60)
#     logger.info("Email Processing Manager Starting")
#     logger.info("=" * 60)
#     logger.info(f"Configuration:")
#     logger.info(f"  API_KEY: {'***' if API_KEY else 'NOT SET'}")
#     logger.info(f"  Email Poller URL: {EMAIL_POLLER_URL}")
#     logger.info(f"  MinIO Storage URL: {MINIO_SERVER_URL}")
#     logger.info(f"  Email Notifications: {'ENABLED' if ENABLE_EMAIL_NOTIFICATIONS else 'DISABLED'}")
#     logger.info(f"  AI Validation: {'ENABLED' if ENABLE_AI_VALIDATION else 'DISABLED'}")
#     logger.info(f"  Applications Log File: {VALIDATED_APPLICATIONS_FILE}")
#     logger.info("=" * 60)
    
#     # Run the FastAPI app
#     uvicorn.run("main:app", host="0.0.0.0", port=8004, log_level="info",reload=True)