from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum

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