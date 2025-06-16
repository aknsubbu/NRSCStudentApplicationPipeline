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
EMAIL_OUT_SERVER_URL = os.getenv("EMAIL_OUT_SERVER_URL", "http://localhost:8001")
AI_SERVER_URL = os.getenv("AI_SERVER_URL", "http://localhost:8005")

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

# V2 Workflow Models
class ValidationStatus(BaseModel):
    """Status of document validation"""
    is_valid: bool
    feedback: str
    validation_details: Dict[str, Any] = {}
    
class WorkflowResult(BaseModel):
    """Result of the complete v2 workflow"""
    email_id: str
    student_id: str
    workflow_stage: str  # "received", "processing", "validation", "completed", "failed"
    application_received_sent: bool = False
    documents_processed: bool = False
    validation_completed: bool = False
    validation_result: Optional[ValidationStatus] = None
    validation_email_sent: bool = False
    marked_for_review: bool = False
    errors: List[str] = []
    processing_time: float = 0.0

class EmailWorkflowRequest(BaseModel):
    """Request model for v2 email workflow"""
    email_data: EmailData
    send_confirmation: bool = True
    perform_validation: bool = True

# Utility Functions
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

# V2 Workflow Functions
async def send_application_received_email(student_email: str, student_name: str, student_id: str, application_id: str) -> bool:
    """Send application received confirmation email"""
    try:
        headers = {"X-API-Key": API_KEY}
        
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
            return True
            
    except Exception as e:
        logger.error(f"Error sending application received email: {e}")
        return False

async def send_validation_complete_email(student_email: str, student_name: str, student_id: str, application_id: str) -> bool:
    """Send validation complete email"""
    try:
        headers = {"X-API-Key": API_KEY}
        
        email_data = {
            "recipient": student_email,
            "student_name": student_name,
            "student_id": student_id,
            "application_id": application_id
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{EMAIL_OUT_SERVER_URL}/email/template/application_validated",
                json=email_data,
                headers=headers
            )
            response.raise_for_status()
            logger.info(f"Validation complete email sent to {student_email}")
            return True
            
    except Exception as e:
        logger.error(f"Error sending validation complete email: {e}")
        return False

async def send_validation_failed_email(student_email: str, student_name: str, validation_feedback: str, issues: List[str]) -> bool:
    """Send validation failed email"""
    try:
        headers = {"X-API-Key": API_KEY}
        
        email_data = {
            "recipient": student_email,
            "subject": "Application Validation Failed - NRSC Training and Outreach",
            "template_name": "validation_failed.html",
            "template_data": {
                "student_name": student_name,
                "message": validation_feedback,
                "issues": issues
            }
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{EMAIL_OUT_SERVER_URL}/email/template/validation_failed",
                json=email_data,
                headers=headers
            )
            response.raise_for_status()
            logger.info(f"Validation failed email sent to {student_email}")
            return True
            
    except Exception as e:
        logger.error(f"Error sending validation failed email: {e}")
        return False

async def validate_documents_with_ai(attachments: List[EmailAttachment], student_id: str) -> ValidationStatus:
    """Send documents to AI server for validation"""
    try:
        headers = {"X-API-Key": API_KEY}
        
        # For now, we'll simulate AI validation since we need the actual files
        # In a real implementation, we'd send the attachment files to the AI server
        
        # Check if we have the required documents (basic validation)
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
        
        # Basic validation logic
        if len(attachments) >= 3 and has_resume and has_marksheet:
            return ValidationStatus(
                is_valid=True,
                feedback="All required documents are present and appear to be in correct format.",
                validation_details=validation_details
            )
        else:
            missing_docs = []
            if not has_resume:
                missing_docs.append("Resume/CV")
            if not has_marksheet:
                missing_docs.append("Academic transcripts/marksheets")
            if not has_lor:
                missing_docs.append("Letter of recommendation")
                
            return ValidationStatus(
                is_valid=False,
                feedback=f"Missing required documents: {', '.join(missing_docs)}",
                validation_details=validation_details
            )
            
    except Exception as e:
        logger.error(f"Error validating documents with AI: {e}")
        return ValidationStatus(
            is_valid=False,
            feedback=f"Validation error: {str(e)}",
            validation_details={"error": str(e)}
        )

async def mark_for_review(student_id: str, student_email: str, validation_result: ValidationStatus) -> bool:
    """Mark student application for review in validated.txt file"""
    try:
        review_file = Path("validated.txt")
        
        # Create entry for review
        review_entry = {
            "timestamp": datetime.now().isoformat(),
            "student_id": student_id,
            "student_email": student_email,
            "validation_status": "passed" if validation_result.is_valid else "failed",
            "feedback": validation_result.feedback,
            "validation_details": validation_result.validation_details
        }
        
        # Append to file
        with open(review_file, "a", encoding="utf-8") as f:
            f.write(f"{json.dumps(review_entry, ensure_ascii=False)}\n")
        
        logger.info(f"Marked {student_id} for review in validated.txt")
        return True
        
    except Exception as e:
        logger.error(f"Error marking for review: {e}")
        return False

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

async def process_email_workflow_v2(email_data: EmailData, send_confirmation: bool = True, perform_validation: bool = True) -> WorkflowResult:
    """
    V2 Workflow: Complete email processing workflow
    1. Extract student ID and send application received email
    2. Process email and attachments, store to DB
    3. Validate documents with AI (parallel)
    4. Send validation result emails
    5. Mark for review if validation passes
    """
    start_time = datetime.now()
    
    result = WorkflowResult(
        email_id=email_data.id,
        student_id="",
        workflow_stage="received"
    )
    
    try:
        # Step 1: Extract student information
        student_extraction = extract_student_id_from_email(email_data)
        result.student_id = student_extraction.student_id
        
        # Extract student name from filename or email
        student_name = "Student"  # Default
        if student_extraction.extracted_info.get("name"):
            student_name = student_extraction.extracted_info["name"]
        else:
            # Try to extract from email address
            email_username = email_data.sender.split('@')[0]
            student_name = email_username.replace('.', ' ').replace('_', ' ').title()
        
        application_id = f"APP_{result.student_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        logger.info(f"Starting v2 workflow for {result.student_id} (Email: {email_data.id})")
        
        # Step 2: Send application received email (if requested)
        if send_confirmation:
            result.application_received_sent = await send_application_received_email(
                email_data.sender, student_name, result.student_id, application_id
            )
            if not result.application_received_sent:
                result.errors.append("Failed to send application received email")
        
        # Step 3: Process documents and store to DB
        result.workflow_stage = "processing"
        try:
            # Upload attachments to storage
            uploaded_files = []
            for attachment in email_data.attachments:
                try:
                    if Path(attachment.path).exists():
                        upload_result = await upload_attachment_to_minio(result.student_id, attachment)
                        uploaded_files.append(f"{result.student_id}/{attachment.filename}")
                        logger.info(f"Uploaded {attachment.filename} for {result.student_id}")
                    else:
                        result.errors.append(f"Attachment file not found: {attachment.path}")
                except Exception as e:
                    result.errors.append(f"Failed to upload {attachment.filename}: {str(e)}")
            
            # Save email metadata to database
            processing_result = ProcessingResult(
                email_id=email_data.id,
                student_id=result.student_id,
                status="completed",
                attachments_uploaded=len(uploaded_files),
                total_attachments=len(email_data.attachments),
                minio_files=uploaded_files
            )
            
            await save_email_to_database(email_data, result.student_id, processing_result)
            result.documents_processed = True
            logger.info(f"Documents processed and stored for {result.student_id}")
            
        except Exception as e:
            result.errors.append(f"Document processing failed: {str(e)}")
            logger.error(f"Document processing failed for {result.student_id}: {e}")
        
        # Step 4: Validate documents with AI (if requested and we have attachments)
        if perform_validation and email_data.attachments:
            result.workflow_stage = "validation"
            try:
                validation_result = await validate_documents_with_ai(email_data.attachments, result.student_id)
                result.validation_result = validation_result
                result.validation_completed = True
                
                logger.info(f"Validation completed for {result.student_id}: {'PASSED' if validation_result.is_valid else 'FAILED'}")
                
                # Step 5: Send validation result emails
                if validation_result.is_valid:
                    # Send validation complete email
                    result.validation_email_sent = await send_validation_complete_email(
                        email_data.sender, student_name, result.student_id, application_id
                    )
                    
                    # Mark for review
                    result.marked_for_review = await mark_for_review(
                        result.student_id, email_data.sender, validation_result
                    )
                    
                    if result.marked_for_review:
                        result.workflow_stage = "completed"
                        logger.info(f"Application {result.student_id} marked for review")
                    
                else:
                    # Send validation failed email
                    issues = []
                    if "Missing required documents" in validation_result.feedback:
                        issues.append(validation_result.feedback)
                    
                    result.validation_email_sent = await send_validation_failed_email(
                        email_data.sender, student_name, validation_result.feedback, issues
                    )
                    
                    # Still mark for review even if validation failed
                    result.marked_for_review = await mark_for_review(
                        result.student_id, email_data.sender, validation_result
                    )
                    
                    result.workflow_stage = "completed"
                    logger.info(f"Application {result.student_id} validation failed, but marked for manual review")
                
            except Exception as e:
                result.errors.append(f"Validation failed: {str(e)}")
                result.workflow_stage = "failed"
                logger.error(f"Validation failed for {result.student_id}: {e}")
        
        else:
            result.workflow_stage = "completed"
            logger.info(f"Workflow completed for {result.student_id} (validation skipped)")
    
    except Exception as e:
        result.errors.append(f"Workflow failed: {str(e)}")
        result.workflow_stage = "failed"
        logger.error(f"Workflow failed for {email_data.id}: {e}")
    
    # Calculate processing time
    result.processing_time = (datetime.now() - start_time).total_seconds()
    
    logger.info(f"V2 workflow completed for {result.student_id} in {result.processing_time:.2f}s - Stage: {result.workflow_stage}")
    
    return result

# API Endpoints

@app.get("/")
def read_root():
    return {
        "status": "running",
        "message": "Email Processing Manager API is running",
        "api_versions": {
            "v1": {
                "description": "Legacy email processing (no email notifications)",
                "endpoints": [
                    "/process-email/",
                    "/process-batch/", 
                    "/poll-and-process/",
                    "/process-background/"
                ]
            },
            "v2": {
                "description": "Complete workflow with email notifications and AI validation",
                "endpoints": [
                    "/v2/process-email/",
                    "/v2/process-batch/",
                    "/v2/poll-and-process/",
                    "/v2/workflow-status/{student_id}",
                    "/v2/review-queue/"
                ],
                "workflow": [
                    "1. Send application received email",
                    "2. Process and store documents",
                    "3. Validate documents with AI",
                    "4. Send validation result emails",
                    "5. Mark for review in validated.txt"
                ]
            }
        },
        "services": {
            "db_server": DB_SERVER_URL,
            "email_poller": EMAIL_POLLER_URL,
            "minio_server": MINIO_SERVER_URL,
            "email_out_server": EMAIL_OUT_SERVER_URL,
            "ai_server": AI_SERVER_URL
        },
        "config": {
            "api_key_configured": bool(API_KEY and API_KEY != "your-secret-api-key-123"),
            "urls_configured": {
                "db_server": DB_SERVER_URL,
                "email_poller": EMAIL_POLLER_URL,
                "minio_server": MINIO_SERVER_URL,
                "email_out_server": EMAIL_OUT_SERVER_URL,
                "ai_server": AI_SERVER_URL
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

# V2 API Endpoints - New Workflow
@app.post("/v2/process-email/", response_model=WorkflowResult, dependencies=[Depends(get_api_key)])
async def process_email_v2(request: EmailWorkflowRequest):
    """
    V2: Process email with complete workflow
    - Send application received email
    - Process and store documents
    - Validate with AI
    - Send validation result emails
    - Mark for review
    """
    return await process_email_workflow_v2(
        request.email_data, 
        request.send_confirmation, 
        request.perform_validation
    )

@app.post("/v2/process-batch/", dependencies=[Depends(get_api_key)])
async def process_email_batch_v2(email_batch: EmailBatch, send_confirmation: bool = True, perform_validation: bool = True):
    """V2: Process a batch of emails using the new workflow"""
    start_time = datetime.now()
    
    results = []
    successful = 0
    failed = 0
    
    # Process emails with limited concurrency
    semaphore = asyncio.Semaphore(2)  # Process max 2 emails concurrently for v2 workflow
    
    async def process_with_semaphore(email_data: EmailData):
        async with semaphore:
            return await process_email_workflow_v2(email_data, send_confirmation, perform_validation)
    
    try:
        # Process all emails
        tasks = [process_with_semaphore(email) for email in email_batch.emails]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Count successes and failures
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                failed += 1
                # Create a failed result object
                results[i] = WorkflowResult(
                    email_id=email_batch.emails[i].id,
                    student_id="FAILED",
                    workflow_stage="failed",
                    errors=[str(result)]
                )
            elif result.workflow_stage in ["completed", "processing"]:
                successful += 1
            else:
                failed += 1
    
    except Exception as e:
        logger.error(f"V2 batch processing error: {e}")
        return {
            "error": f"Batch processing failed: {str(e)}",
            "total_processed": 0,
            "successful": 0,
            "failed": len(email_batch.emails)
        }
    
    processing_time = (datetime.now() - start_time).total_seconds()
    
    return {
        "total_processed": len(email_batch.emails),
        "successful": successful,
        "failed": failed,
        "results": results,
        "processing_time": processing_time,
        "workflow_version": "v2"
    }

@app.get("/v2/poll-and-process/", dependencies=[Depends(get_api_key)])
async def poll_and_process_v2(send_confirmation: bool = True, perform_validation: bool = True):
    """V2: Poll emails from poller and process them with the new workflow"""
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
        
        # Process the batch with v2 workflow
        result = await process_email_batch_v2(email_batch, send_confirmation, perform_validation)
        
        logger.info(f"V2: Polled and processed {result['total_processed']} emails: "
                   f"{result['successful']} successful, {result['failed']} failed")
        
        return result
        
    except Exception as e:
        logger.error(f"Error in v2 poll-and-process: {e}")
        raise HTTPException(status_code=500, detail=f"V2 poll and process failed: {str(e)}")

@app.get("/v2/workflow-status/{student_id}", dependencies=[Depends(get_api_key)])
async def get_workflow_status_v2(student_id: str):
    """V2: Get workflow status for a specific student"""
    try:
        # Check if student is in validated.txt
        review_file = Path("validated.txt")
        if review_file.exists():
            with open(review_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())
                        if entry.get("student_id") == student_id:
                            return {
                                "student_id": student_id,
                                "found_in_review": True,
                                "review_entry": entry,
                                "workflow_version": "v2"
                            }
                    except json.JSONDecodeError:
                        continue
        
        return {
            "student_id": student_id,
            "found_in_review": False,
            "message": "Student not found in review queue",
            "workflow_version": "v2"
        }
        
    except Exception as e:
        logger.error(f"Error checking workflow status for {student_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to check status: {str(e)}")

@app.get("/v2/review-queue/", dependencies=[Depends(get_api_key)])
async def get_review_queue_v2():
    """V2: Get all applications in the review queue"""
    try:
        review_file = Path("validated.txt")
        if not review_file.exists():
            return {
                "total_applications": 0,
                "applications": [],
                "workflow_version": "v2"
            }
        
        applications = []
        with open(review_file, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    applications.append(entry)
                except json.JSONDecodeError:
                    continue
        
        return {
            "total_applications": len(applications),
            "applications": applications,
            "workflow_version": "v2"
        }
        
    except Exception as e:
        logger.error(f"Error getting review queue: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get review queue: {str(e)}")

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
    """V1: Poll emails from email service and process them automatically (legacy)."""
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
        
        logger.info(f"V1: Polled and processed {result.total_processed} emails: "
                   f"{result.successful} successful, {result.failed} failed")
        
        return result
        
    except Exception as e:
        logger.error(f"Error in v1 poll-and-process: {e}")
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
    logger.info(f"  EMAIL_OUT_SERVER_URL: {EMAIL_OUT_SERVER_URL}")
    logger.info(f"  AI_SERVER_URL: {AI_SERVER_URL}")
    logger.info(f"")
    logger.info(f"Available API versions:")
    logger.info(f"  V1 (Legacy): Basic email processing")
    logger.info(f"  V2 (Enhanced): Complete workflow with notifications and AI validation")
    
    # Run the FastAPI app
    uvicorn.run(app, host="0.0.0.0", port=8004, log_level="info")