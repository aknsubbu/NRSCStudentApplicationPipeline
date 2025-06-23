"""
Enhanced Application Management System
Production-ready orchestration system with persistence, resilience, and monitoring
"""

import asyncio
import json
import logging
import hashlib
import re
import aioredis
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any, Set
from dataclasses import dataclass, asdict, field
from enum import Enum
import httpx
import uuid
from pathlib import Path
import base64
from contextlib import asynccontextmanager
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import aiofiles
from pydantic_settings import BaseSettings
from pydantic import  validator
import asyncpg
from concurrent.futures import ThreadPoolExecutor
import signal
import sys
from functools import wraps
import time
from collections import defaultdict
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
import uvicorn

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)

# Utility functions
def extract_email_from_sender(sender: str) -> str:
    """Extract email address from sender string (e.g., 'Name <email@domain.com>' -> 'email@domain.com')"""
    import re
    match = re.search(r'<([^<>]+@[^<>]+)>', sender)
    if match:
        return match.group(1)
    else:
        # If no angle brackets, assume the whole string is the email
        return sender.strip()

class ApplicationStatus(Enum):
    """Application status states"""
    INITIAL_EMAIL_RECEIVED = "initial_email_received"
    INFORMATION_REQUESTED = "information_requested"
    DOCUMENTS_RECEIVED = "documents_received"
    VALIDATION_IN_PROGRESS = "validation_in_progress"
    VALIDATION_SUCCESSFUL = "validation_successful"
    VALIDATION_FAILED = "validation_failed"
    APPLICATION_PROCESSED = "application_processed"
    VALIDATION_TIMEOUT = "validation_timeout"
    ERROR_STATE = "error_state"

class StudentStatus(Enum):
    """Student status states"""
    ACTIVE = "active"
    PENDING_DOCUMENTS = "pending_documents"
    UNDER_REVIEW = "under_review"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    BLOCKED = "blocked"

class Priority(Enum):
    """Processing priority levels"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4


class Settings(BaseSettings):
    """Simplified configuration settings"""
    
    # Server URLs
    email_polling_url: str = "http://localhost:8004"
    database_minio_url: str = "http://localhost:8000"
    ai_validation_url: str = "http://localhost:8003"
    outgoing_email_url: str = "http://localhost:8001"
    
    # Security
    api_key: str
    encryption_key: Optional[str] = None
    
    # Redis Configuration
    redis_url: str = "redis://localhost:6379"
    redis_password: Optional[str] = None
    
    # Database Configuration
    postgres_url: Optional[str] = None
    
    # MinIO Configuration
    bucket_name: str = "applicationdocs"
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str
    minio_secret_key: str
    minio_server_url: str = "http://localhost:8000"
    
    # AI Configuration
    gemini_api_key: str
    
    # Email Configuration - Incoming (IMAP)
    imap_server: str = "imap.gmail.com"
    email_username: str
    email_password_in: str
    email_folder: str = "INBOX"
    processed_folder: str = "Processed"
    attachment_dir: str = "attachments"
    imap_timeout: int = 30
    include_raw_email: bool = False
    mark_as_read: bool = False
    move_processed: bool = False
    
    # Email Configuration - Outgoing (SMTP)
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    email_sender: str
    email_password_out: str
    
    # Processing Configuration
    email_poll_interval: int = 30
    validation_timeout: int = 300
    max_concurrent_validations: int = 5
    retry_attempts: int = 3
    max_emails: int = 50
    
    # Application Keywords (as string)
    app_keywords: str = "application,apply,job,position,interview,offer,candidate"
    
    # File Configuration
    temp_dir: str = "/tmp/app-manager"
    max_file_size: int = 50 * 1024 * 1024  # 50MB
    allowed_file_types: str = "pdf,doc,docx,jpg,jpeg,png"
    
    # Monitoring
    metrics_enabled: bool = True
    log_level: str = "INFO"
    
    model_config = {
        "env_file": ".env",
        "case_sensitive": False,
        "extra": "allow"
    }
    
    # Helper methods to parse the string fields when needed
    def get_app_keywords_list(self):
        """Get app keywords as a list"""
        return [keyword.strip() for keyword in self.app_keywords.split(',')]
    
    def get_allowed_file_types_set(self):
        """Get allowed file types as a set"""
        return set(ext.strip() for ext in self.allowed_file_types.split(','))


@dataclass
class StudentInfo:
    """Enhanced student information with validation"""
    name: str
    email: str
    phone: str
    student_id: str
    priority: Priority = Priority.NORMAL
    additional_info: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    
    def __post_init__(self):
        # Validate email format
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', self.email):
            raise ValueError(f"Invalid email format: {self.email}")

@dataclass
class ApplicationInfo:
    """Enhanced application information with tracking"""
    application_id: str
    student_id: str
    status: ApplicationStatus
    initial_email_id: str
    priority: Priority = Priority.NORMAL
    documents_email_id: Optional[str] = None
    validation_result: Optional[Dict] = None
    retry_count: int = 0
    error_history: List[Dict] = field(default_factory=list)
    processing_metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def add_error(self, error: str, context: Dict = None):
        """Add error to history with timestamp"""
        self.error_history.append({
            'timestamp': datetime.now().isoformat(),
            'error': error,
            'context': context or {},
            'retry_count': self.retry_count
        })
        self.updated_at = datetime.now()

class CircuitBreaker:
    """Circuit breaker pattern implementation"""
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
    
    def call(self, func):
        """Decorator for circuit breaker"""
        @wraps(func)
        async def wrapper(*args, **kwargs):
            if self.state == "OPEN":
                if time.time() - self.last_failure_time > self.recovery_timeout:
                    self.state = "HALF_OPEN"
                    logger.info("Circuit breaker transitioning to HALF_OPEN")
                else:
                    raise Exception("Circuit breaker is OPEN")
            
            try:
                result = await func(*args, **kwargs)
                if self.state == "HALF_OPEN":
                    self.state = "CLOSED"
                    self.failure_count = 0
                    logger.info("Circuit breaker transitioning to CLOSED")
                return result
            except Exception as e:
                self.failure_count += 1
                self.last_failure_time = time.time()
                
                if self.failure_count >= self.failure_threshold:
                    self.state = "OPEN"
                    logger.error("Circuit breaker transitioning to OPEN")
                
                raise e
        return wrapper

class MetricsCollector:
    """Simple metrics collection"""
    def __init__(self):
        self.counters = defaultdict(int)
        self.timers = defaultdict(list)
        self.gauges = defaultdict(float)
    
    def increment(self, metric: str, value: int = 1):
        self.counters[metric] += value
    
    def timer(self, metric: str):
        @asynccontextmanager
        async def timer_context():
            start_time = time.time()
            try:
                yield
            finally:
                duration = time.time() - start_time
                self.timers[metric].append(duration)
        return timer_context()
    
    def set_gauge(self, metric: str, value: float):
        self.gauges[metric] = value
    
    def get_metrics(self) -> Dict:
        return {
            'counters': dict(self.counters),
            'timers': {k: {
                'count': len(v),
                'avg': sum(v) / len(v) if v else 0,
                'max': max(v) if v else 0,
                'min': min(v) if v else 0
            } for k, v in self.timers.items()},
            'gauges': dict(self.gauges)
        }

class StateManager:
    """Redis-based state management with fallback to in-memory"""
    def __init__(self, redis_url: str, password: str = None):
        self.redis_url = redis_url
        self.password = password
        self.redis = None
        self.memory_fallback = {}
        self.connected = False
    
    async def connect(self):
        """Connect to Redis with fallback"""
        try:
            self.redis = await aioredis.from_url(
                self.redis_url,
                password=self.password,
                encoding="utf-8",
                decode_responses=True
            )
            await self.redis.ping()
            self.connected = True
            logger.info("Connected to Redis for state management")
        except Exception as e:
            logger.warning(f"Redis connection failed, using memory fallback: {e}")
            self.connected = False
    
    async def set_state(self, key: str, value: Any, ttl: int = None):
        """Set state with optional TTL"""
        serialized = json.dumps(value, default=str)
        
        if self.connected:
            try:
                if ttl:
                    await self.redis.setex(key, ttl, serialized)
                else:
                    await self.redis.set(key, serialized)
                return
            except Exception as e:
                logger.error(f"Redis set failed: {e}")
        
        # Fallback to memory
        self.memory_fallback[key] = {
            'value': serialized,
            'expires': datetime.now() + timedelta(seconds=ttl) if ttl else None
        }
    
    async def get_state(self, key: str) -> Optional[Any]:
        """Get state from Redis or memory"""
        if self.connected:
            try:
                value = await self.redis.get(key)
                if value:
                    return json.loads(value)
            except Exception as e:
                logger.error(f"Redis get failed: {e}")
        
        # Fallback to memory
        if key in self.memory_fallback:
            entry = self.memory_fallback[key]
            if entry['expires'] is None or datetime.now() < entry['expires']:
                return json.loads(entry['value'])
            else:
                del self.memory_fallback[key]
        
        return None
    
    async def delete_state(self, key: str):
        """Delete state"""
        if self.connected:
            try:
                await self.redis.delete(key)
            except Exception as e:
                logger.error(f"Redis delete failed: {e}")
        
        self.memory_fallback.pop(key, None)

class EmailProcessor:
    """Enhanced email processing with deduplication and better parsing"""
    def __init__(self):
        self.processed_emails: Set[str] = set()
        self.email_patterns = {
            'name': [
                r'(?:name|my name is|i am|from):\s*([A-Za-z\s]{2,50})',
                r'dear\s+(?:sir|madam|hiring manager),?\s*i am\s+([A-Za-z\s]{2,50})',
                r'^([A-Za-z\s]{2,50})\s+here'
            ],
            'phone': [
                r'(?:phone|mobile|contact|cell):\s*([\d\s\-\+\(\)]{8,20})',
                r'(?:call me at|reach me on|contact number):\s*([\d\s\-\+\(\)]{8,20})'
            ],
            'student_id': [
                r'(?:student id|id number|roll number):\s*([A-Za-z0-9\-]{5,20})',
                r'(?:registration|reg)\s*(?:no|number):\s*([A-Za-z0-9\-]{5,20})'
            ]
        }
    
    def extract_email_hash(self, email_data: Dict) -> str:
        """Generate unique hash for email deduplication"""
        content = f"{email_data.get('sender', '')}{email_data.get('subject', '')}{email_data.get('date', '')}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def is_duplicate_email(self, email_hash: str) -> bool:
        """Check if email has been processed"""
        return email_hash in self.processed_emails
    
    def mark_email_processed(self, email_hash: str):
        """Mark email as processed"""
        self.processed_emails.add(email_hash)
    
    def extract_student_info_enhanced(self, email_data: Dict) -> Dict[str, str]:
        """Enhanced student information extraction"""
        sender_email = email_data.get('sender', '')
        subject = email_data.get('subject', '')
        body = email_data.get('body_text', '')
        
        extracted = {}
        search_text = f"{subject} {body}".lower()
        
        # Extract name
        for pattern in self.email_patterns['name']:
            match = re.search(pattern, search_text, re.IGNORECASE)
            if match and len(match.group(1).strip()) > 2:
                extracted['name'] = match.group(1).strip().title()
                break
        
        if 'name' not in extracted:
            # Fallback: extract from email
            name_part = sender_email.split('@')[0]
            extracted['name'] = name_part.replace('.', ' ').replace('_', ' ').title()
        
        # Extract phone
        for pattern in self.email_patterns['phone']:
            match = re.search(pattern, search_text, re.IGNORECASE)
            if match:
                phone = re.sub(r'[^\d\+]', '', match.group(1))
                if len(phone) >= 8:
                    extracted['phone'] = phone
                break
        
        # Extract student ID
        for pattern in self.email_patterns['student_id']:
            match = re.search(pattern, search_text, re.IGNORECASE)
            if match:
                extracted['student_id'] = match.group(1).strip().upper()
                break
        
        return extracted

class FileManager:
    """Secure file management with validation and cleanup"""
    def __init__(self, temp_dir: str, max_file_size: int, allowed_types: Set[str]):
        self.temp_dir = Path(temp_dir)
        self.max_file_size = max_file_size
        self.allowed_types = allowed_types
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.active_files: Set[str] = set()
    
    def validate_file(self, filename: str, content: bytes) -> bool:
        """Validate file type and size"""
        # Check file size
        if len(content) > self.max_file_size:
            raise ValueError(f"File {filename} exceeds maximum size of {self.max_file_size} bytes")
        
        # Check file extension
        file_ext = Path(filename).suffix.lower().lstrip('.')
        if file_ext not in self.allowed_types:
            raise ValueError(f"File type {file_ext} not allowed. Allowed types: {self.allowed_types}")
        
        # Check for suspicious content (basic check)
        if content.startswith(b'MZ') or content.startswith(b'\x7fELF'):
            raise ValueError("Executable files not allowed")
        
        return True
    
    async def create_temp_file(self, student_id: str, filename: str, content: bytes) -> str:
        """Create temporary file with validation"""
        self.validate_file(filename, content)
        
        # Generate unique filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        safe_filename = re.sub(r'[^\w\-_\.]', '_', filename)
        temp_filename = f"{student_id}_{timestamp}_{safe_filename}"
        temp_path = self.temp_dir / temp_filename
        
        async with aiofiles.open(temp_path, 'wb') as f:
            await f.write(content)
        
        self.active_files.add(str(temp_path))
        
        # Schedule cleanup
        asyncio.create_task(self._cleanup_file_later(str(temp_path), 3600))  # 1 hour
        
        return str(temp_path)
    
    async def _cleanup_file_later(self, file_path: str, delay: int):
        """Clean up file after delay"""
        await asyncio.sleep(delay)
        await self.cleanup_file(file_path)
    
    async def cleanup_file(self, file_path: str):
        """Clean up temporary file"""
        try:
            path = Path(file_path)
            if path.exists():
                path.unlink()
            self.active_files.discard(file_path)
        except Exception as e:
            logger.error(f"Failed to cleanup file {file_path}: {e}")
    
    async def cleanup_all(self):
        """Clean up all temporary files"""
        for file_path in list(self.active_files):
            await self.cleanup_file(file_path)

class EnhancedApplicationManager:
    """Enhanced Application Manager with production features"""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.state_manager = StateManager(settings.redis_url, settings.redis_password)
        self.email_processor = EmailProcessor()
        self.file_manager = FileManager(
        settings.temp_dir,
        settings.max_file_size,
        settings.get_allowed_file_types_set()  # ✅ Use the helper method
)
        self.metrics = MetricsCollector() if settings.metrics_enabled else None
        
        # HTTP client with connection pooling
        self.http_client = httpx.AsyncClient(
            timeout=30.0,
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=100)
        )
        self.headers = {"X-API-Key": settings.api_key}
        
        # Circuit breakers for each service
        self.circuit_breakers = {
            'email_polling': CircuitBreaker(),
            'database': CircuitBreaker(),
            'ai_validation': CircuitBreaker(),
            'outgoing_email': CircuitBreaker()
        }
        
        # Processing control
        self.shutdown_event = asyncio.Event()
        self.validation_semaphore = asyncio.Semaphore(settings.max_concurrent_validations)
        self.executor = ThreadPoolExecutor(max_workers=4)
        
    async def initialize(self):
        """Initialize the application manager"""
        await self.state_manager.connect()
        
        # Load existing state from persistence
        await self._load_persistent_state()
        
        # Setup signal handlers
        self._setup_signal_handlers()
        
        logger.info("Application Manager initialized successfully")
    
    def _setup_signal_handlers(self):
        """Setup graceful shutdown signal handlers"""
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, initiating shutdown...")
            self.shutdown_event.set()
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    async def _load_persistent_state(self):
        """Load state from persistence layer"""
        try:
            # Load processed emails
            processed_emails = await self.state_manager.get_state("processed_emails")
            if processed_emails:
                self.email_processor.processed_emails = set(processed_emails)
            
            logger.info("Persistent state loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load persistent state: {e}")
    
    async def _save_persistent_state(self):
        """Save state to persistence layer"""
        try:
            # Save processed emails
            await self.state_manager.set_state(
                "processed_emails",
                list(self.email_processor.processed_emails),
                ttl=7*24*3600  # 7 days
            )
            
            logger.info("Persistent state saved successfully")
        except Exception as e:
            logger.error(f"Failed to save persistent state: {e}")

    async def start_monitoring(self):
        """Enhanced monitoring loop with error handling"""
        logger.info("Starting enhanced Application Manager monitoring...")
        
        while not self.shutdown_event.is_set():
            try:
                async with self.metrics.timer("email_processing_cycle") if self.metrics else asynccontextmanager(lambda: iter([None]))():
                    await self.process_new_emails()
                
                # Save state periodically
                await self._save_persistent_state()
                
                # Update metrics
                if self.metrics:
                    self.metrics.set_gauge("active_applications", len(await self._get_active_applications()))
                
                await asyncio.sleep(self.settings.email_poll_interval)
                
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}", exc_info=True)
                if self.metrics:
                    self.metrics.increment("monitoring_errors")
                await asyncio.sleep(60)  # Wait longer on error
    

    async def handle_email_enhanced(self, email_data: Dict):
        email_hash = self.email_processor.extract_email_hash(email_data)
        
        if self.email_processor.is_duplicate_email(email_hash):
            return
        
        try:
            email_id = email_data.get('id')
            sender_email = email_data.get('sender')
            
            correlation_id = f"email_{email_hash}"
            
            # ✅ Create a bound logger and use it directly
            bound_logger = logger.bind(correlation_id=correlation_id, email_id=email_id)
            
            # Determine email type and handle accordingly
            if await self.is_initial_application_enhanced(email_data):
                await self.handle_initial_application_enhanced(email_data, correlation_id)
            elif await self.is_document_submission_enhanced(email_data):
                await self.handle_document_submission_enhanced(email_data, correlation_id)
            else:
                bound_logger.info("Email doesn't match known patterns, skipping")
            
            # Mark as processed
            self.email_processor.mark_email_processed(email_hash)
            
            if self.metrics:
                self.metrics.increment("emails_processed")
                
        except Exception as e:
            bound_logger.error(f"Error handling email: {e}", exc_info=True)
            if self.metrics:
                self.metrics.increment("email_handling_errors")

    async def is_initial_application_enhanced(self, email_data: Dict) -> bool:
        """Enhanced initial application detection"""
        subject = email_data.get('subject', '').lower()
        body = email_data.get('body_text', '').lower()
        sender_email = email_data.get('sender', '')
        
        # Enhanced keyword detection
        initial_keywords = [
            'application', 'apply', 'applying', 'internship', 'position', 
            'job', 'opportunity', 'interested', 'vacancy', 'opening',
            'career', 'joining', 'work', 'employment'
        ]
        
        # Response indicators (NOT initial applications)
        response_keywords = [
            're:', 'response', 'documents', 'attached', 'submission',
            'requested', 'follow up', 'followup', 'as requested'
        ]
        
        # Check if it's a response
        is_response = any(keyword in subject for keyword in response_keywords)
        if is_response:
            return False
        
        # Check for initial application keywords with context
        text_to_search = f"{subject} {body}"
        has_application_intent = any(
            keyword in text_to_search and 
            ('want' in text_to_search or 'would like' in text_to_search or 
             'seeking' in text_to_search or 'interested' in text_to_search)
            for keyword in initial_keywords
        )
        
        # Check if sender already has an active application
        existing_student_id = await self.state_manager.get_state(f"student_email:{sender_email}")
        if existing_student_id:
            # Check if they have an active application
            applications = await self._get_student_applications(existing_student_id)
            active_statuses = [
                ApplicationStatus.INFORMATION_REQUESTED.value,
                ApplicationStatus.DOCUMENTS_RECEIVED.value,
                ApplicationStatus.VALIDATION_IN_PROGRESS.value
            ]
            has_active_app = any(app['status'] in active_statuses for app in applications)
            if has_active_app:
                return False
        
        return has_application_intent

    async def is_document_submission_enhanced(self, email_data: Dict) -> bool:
        """Enhanced document submission detection"""
        sender_email = email_data.get('sender', '')
        subject = email_data.get('subject', '').lower()
        attachments = email_data.get('attachments', [])
        
        # Must be from a known student
        existing_student_id = await self.state_manager.get_state(f"student_email:{sender_email}")
        if not existing_student_id:
            return False
        
        # Check for response indicators or attachments
        response_indicators = [
            're:', 'response', 'documents', 'attached', 'submission',
            'requested', 'follow up', 'followup', 'as requested'
        ]
        
        has_response_indicator = any(indicator in subject for indicator in response_indicators)
        has_attachments = len(attachments) > 0
        
        # Must have either response indicators or attachments
        return has_response_indicator or has_attachments

    async def handle_initial_application_enhanced(self, email_data: Dict, correlation_id: str):
        """Enhanced initial application handling"""
        try:
            sender_email_raw = email_data.get('sender')
            sender_email = extract_email_from_sender(sender_email_raw)
            logger.info(f"Processing initial application from {sender_email}")
            
            # Extract student information with enhanced parsing
            extracted_info = self.email_processor.extract_student_info_enhanced(email_data)
            
            # Generate IDs deterministically
            current_year = datetime.now().year
            application_id = f"{current_year}/{sender_email}"
            student_id = extracted_info.get('student_id') or self.generate_student_id(sender_email)
            
            # Create student info object
            student_info = StudentInfo(
                name=extracted_info.get('name', 'Unknown'),
                email=sender_email,
                phone=extracted_info.get('phone', ''),
                student_id=student_id,
                additional_info={
                    'subject': email_data.get('subject', ''),
                    'initial_contact_date': datetime.now().isoformat(),
                    'correlation_id': correlation_id
                }
            )
            
            # Store student mapping
            await self.state_manager.set_state(f"student_email:{sender_email}", student_id)
            
            # Create and store application info
            app_info = ApplicationInfo(
                application_id=application_id,
                student_id=student_id,
                status=ApplicationStatus.INITIAL_EMAIL_RECEIVED,
                initial_email_id=email_data.get('id'),
                processing_metadata={'correlation_id': correlation_id}
            )
            
            # Store in state manager
            await self.state_manager.set_state(f"application:{application_id}", asdict(app_info))
            await self.state_manager.set_state(f"student:{student_id}", asdict(student_info))
            
            # Create database records with circuit breaker
            await self._create_student_record_with_cb(student_info)
            await self._create_application_record_with_cb(app_info)
            
            # Store email data and attachments
            await self._store_email_data_enhanced(email_data, student_id, "initial_application")
            
            if email_data.get('attachments'):
                await self._store_attachments_enhanced(
                    email_data.get('attachments'), 
                    student_id, 
                    "initial"
                )
            
            # Send information required email
            await self._send_information_required_email_with_cb(student_info, application_id)
            
            # Update application status
            app_info.status = ApplicationStatus.INFORMATION_REQUESTED
            await self.state_manager.set_state(f"application:{application_id}", asdict(app_info))
            await self._update_application_status_with_cb(app_info)
            
            logger.info(f"Initial application processed successfully: {application_id}")
            
            if self.metrics:
                self.metrics.increment("initial_applications_processed")
                
        except Exception as e:
            logger.error(f"Error handling initial application: {e}", exc_info=True)
            if self.metrics:
                self.metrics.increment("initial_application_errors")
            raise

    async def cleanup(self):
        """Enhanced cleanup with proper resource management"""
        logger.info("Starting cleanup process...")
        
        # Set shutdown event
        self.shutdown_event.set()
        
        # Save final state
        await self._save_persistent_state()
        
        # Close HTTP client
        await self.http_client.aclose()
        
        # Cleanup files
        await self.file_manager.cleanup_all()
        
        # Shutdown executor
        self.executor.shutdown(wait=True)
        
        logger.info("Cleanup completed successfully")

    # Helper methods for circuit breaker integration
    async def _create_student_record_with_cb(self, student_info: StudentInfo):
        """Create student record with circuit breaker"""
        circuit_breaker = self.circuit_breakers['database']
        
        @circuit_breaker.call
        async def _create_record():
            data = {
                'student_id': student_info.student_id,
                'student_name': student_info.name,
                'student_email': student_info.email,
                'student_phone': student_info.phone,
                'student_status': StudentStatus.PENDING_DOCUMENTS.value
            }
            
            response = await self.http_client.post(
                f"{self.settings.database_minio_url}/db/student/create",
                headers=self.headers,
                json=data
            )
            response.raise_for_status()
            return response.json()
        
        try:
            return await _create_record()
        except Exception as e:
            logger.error(f"Failed to create student record: {e}")
            raise

    async def _create_application_record_with_cb(self, app_info: ApplicationInfo):
        """Create application record with circuit breaker"""
        circuit_breaker = self.circuit_breakers['database']
        
        @circuit_breaker.call
        async def _create_record():
            data = {
                'student_id': app_info.student_id,
                'application_id': app_info.application_id,
                'application_status': app_info.status.value,
                'intern_project': 'TBD - To be determined after validation',
                'intern_project_start_date': None,  # Will be updated after Excel validation
                'intern_project_end_date': None     # Will be updated after Excel validation
            }
            
            response = await self.http_client.post(
                f"{self.settings.database_minio_url}/db/application/create",
                headers=self.headers,
                json=data
            )
            response.raise_for_status()
            return response.json()
        
        try:
            return await _create_record()
        except Exception as e:
            logger.error(f"Failed to create application record: {e}")
            raise

    async def _update_application_status_with_cb(self, app_info: ApplicationInfo):
        """Update application status with circuit breaker"""
        circuit_breaker = self.circuit_breakers['database']
        
        @circuit_breaker.call
        async def _update_status():
            data = {
                'application_id': app_info.application_id,
                'new_status': app_info.status.value
            }
            
            response = await self.http_client.patch(
                f"{self.settings.database_minio_url}/db/application/update-status",
                headers=self.headers,
                json=data
            )
            response.raise_for_status()
            return response.json()
        
        try:
            return await _update_status()
        except Exception as e:
            logger.error(f"Failed to update application status: {e}")
            raise
    
    async def _update_application_dates_with_cb(self, app_info: ApplicationInfo, excel_data: Dict):
        """Update application with dates from Excel data"""
        circuit_breaker = self.circuit_breakers['database']
        
        @circuit_breaker.call
        async def _update_dates():
            start_date = excel_data.get('application_start_date')
            end_date = excel_data.get('end_date')
            
            data = {
                'application_id': app_info.application_id,
                'start_date': start_date,
                'end_date': end_date
            }
            
            response = await self.http_client.patch(
                f"{self.settings.database_minio_url}/db/application/update-dates",
                headers=self.headers,
                json=data
            )
            response.raise_for_status()
            return response.json()
        
        try:
            return await _update_dates()
        except Exception as e:
            logger.error(f"Failed to update application dates: {e}")
            # Don't raise here as this is optional information

    async def _send_information_required_email_with_cb(self, student_info: StudentInfo, application_id: str):
        """Send information required email with circuit breaker"""
        circuit_breaker = self.circuit_breakers['outgoing_email']
        
        @circuit_breaker.call
        async def _send_email():
            deadline_date = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')
            
            data = {
                'recipient': student_info.email,
                'subject': f'Documents Required - Application {application_id}',
                'student_id': student_info.student_id,
                'deadline_date': deadline_date
            }
            
            response = await self.http_client.post(
                f"{self.settings.outgoing_email_url}/email/template/information_required",
                headers=self.headers,
                json=data
            )
            response.raise_for_status()
            return response.json()
        
        try:
            return await _send_email()
        except Exception as e:
            logger.error(f"Failed to send information required email: {e}")
            raise

    async def _store_email_data_enhanced(self, email_data: Dict, student_id: str, email_type: str):
        """Enhanced email data storage"""
        try:
            email_json = json.dumps(email_data, indent=2, default=str)
            
            # Use file manager for secure temporary file creation
            temp_file = await self.file_manager.create_temp_file(
                student_id, 
                f"{email_type}.json", 
                email_json.encode()
            )
            
            # Upload to MinIO with circuit breaker
            circuit_breaker = self.circuit_breakers['database']
            
            @circuit_breaker.call
            async def _upload_file():
                data = {
                    'student_id': student_id,
                    'object_name': f"emails/{email_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                    'file_path': temp_file
                }
                
                response = await self.http_client.post(
                    f"{self.settings.database_minio_url}/objects/upload/",
                    headers=self.headers,
                    json=data
                )
                response.raise_for_status()
                return response.json()
            
            await _upload_file()
            
            # File will be cleaned up automatically by file manager
            
        except Exception as e:
            logger.error(f"Error storing email data: {e}")
            raise

    async def _store_attachments_enhanced(self, attachments: List[Dict], student_id: str, folder: str):
        """Enhanced attachment storage with validation"""
        for attachment in attachments:
            try:
                filename = attachment.get('filename')
                content_base64 = attachment.get('content_base64')
                
                if not content_base64:
                    continue
                
                # Decode content
                content = base64.b64decode(content_base64)
                
                # Create secure temporary file
                temp_file = await self.file_manager.create_temp_file(
                    student_id, 
                    filename, 
                    content
                )
                
                # Upload to MinIO with circuit breaker
                circuit_breaker = self.circuit_breakers['database']
                
                @circuit_breaker.call
                async def _upload_attachment():
                    data = {
                        'student_id': student_id,
                        'object_name': f"{folder}/{filename}",
                        'file_path': temp_file
                    }
                    
                    response = await self.http_client.post(
                        f"{self.settings.database_minio_url}/objects/upload/",
                        headers=self.headers,
                        json=data
                    )
                    response.raise_for_status()
                    return response.json()
                
                await _upload_attachment()
                
                logger.info(f"Stored attachment: {filename}")
                
            except Exception as e:
                logger.error(f"Failed to store attachment {filename}: {e}")
                # Continue with other attachments

    async def _get_active_applications(self) -> List[Dict]:
        """Get active applications from state"""
        # This is a simplified version - in practice you'd query Redis/DB
        return []

    async def _get_student_applications(self, student_id: str) -> List[Dict]:
        """Get applications for a student"""
        # This is a simplified version - in practice you'd query Redis/DB
        return []

    def generate_student_id(self, email: str) -> str:
        """Generate unique student ID"""
        hash_object = hashlib.md5(email.encode())
        return f"STU_{hash_object.hexdigest()[:8].upper()}"

    def generate_application_id(self) -> str:
        """Generate unique application ID"""
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        random_part = str(uuid.uuid4())[:8].upper()
        return f"APP_{timestamp}_{random_part}"

    async def handle_document_submission_enhanced(self, email_data: Dict, correlation_id: str):
        """Enhanced document submission handling for information-required emails"""
        try:
            sender_email_raw = email_data.get('sender')
            sender_email = extract_email_from_sender(sender_email_raw)
            
            # Generate application_id from sender email (deterministic)
            current_year = datetime.now().year
            application_id = f"{current_year}/{sender_email}"
            
            logger.info(f"Processing document submission from {sender_email} for application {application_id}")
            
            # Get student ID from email mapping
            student_id = await self.state_manager.get_state(f"student_email:{sender_email}")
            if not student_id:
                logger.error(f"No student found for email {sender_email}")
                return
            
            # Get application info
            app_info_dict = await self.state_manager.get_state(f"application:{application_id}")
            if not app_info_dict:
                logger.error(f"No application found for ID {application_id}")
                return
            
            # Convert dict back to ApplicationInfo object
            app_info = ApplicationInfo(**app_info_dict)
            
            # Update application with documents email
            app_info.documents_email_id = email_data.get('id')
            app_info.status = ApplicationStatus.DOCUMENTS_RECEIVED
            app_info.updated_at = datetime.now()
            
            # Store email data and attachments
            await self._store_email_data_enhanced(email_data, student_id, "document_submission")
            
            if email_data.get('attachments'):
                await self._store_attachments_enhanced(
                    email_data.get('attachments'), 
                    student_id, 
                    "documents"
                )
            
            # Update database status
            await self._update_application_status_with_cb(app_info)
            await self.state_manager.set_state(f"application:{application_id}", asdict(app_info))
            
            # Start validation process
            await self._start_validation_process(app_info, student_id)
            
            logger.info(f"Document submission processed successfully: {application_id}")
            
            if self.metrics:
                self.metrics.increment("document_submissions_processed")
                
        except Exception as e:
            logger.error(f"Error handling document submission: {e}", exc_info=True)
            if self.metrics:
                self.metrics.increment("document_submission_errors")
            raise

    async def _start_validation_process(self, app_info: ApplicationInfo, student_id: str):
        """Start the AI validation process for documents"""
        try:
            # Update status to validation in progress
            app_info.status = ApplicationStatus.VALIDATION_IN_PROGRESS
            await self.state_manager.set_state(f"application:{app_info.application_id}", asdict(app_info))
            await self._update_application_status_with_cb(app_info)
            
            # Get attachments from MinIO
            attachments = await self._get_attachments_for_validation(student_id)
            
            # Validate documents with AI
            validation_result = await self._validate_documents_with_ai(attachments, app_info.application_id)
            
            # Validate Excel sheet (dummy function for now)
            excel_validation = await self._validate_excel_sheet(attachments, app_info.application_id)
            
            # Combine validation results
            combined_result = {
                'ai_validation': validation_result,
                'excel_validation': excel_validation,
                'timestamp': datetime.now().isoformat(),
                'status': 'success' if validation_result.get('success') and excel_validation.get('success') else 'failed'
            }
            
            # Update application with validation results
            app_info.validation_result = combined_result
            
            if combined_result['status'] == 'success':
                app_info.status = ApplicationStatus.VALIDATION_SUCCESSFUL
                
                # Update application with dates from Excel validation if available
                if excel_validation.get('details') and len(excel_validation['details']) > 0:
                    excel_data = excel_validation['details'][0].get('extracted_data', {})
                    if excel_data:
                        await self._update_application_dates_with_cb(app_info, excel_data)
                
                await self._send_validation_success_email(student_id, app_info.application_id)
                await self._log_validation_complete(app_info, combined_result)
            else:
                app_info.status = ApplicationStatus.VALIDATION_FAILED
                await self._send_validation_failed_email(student_id, app_info.application_id, combined_result)
            
            # Final status update
            await self.state_manager.set_state(f"application:{app_info.application_id}", asdict(app_info))
            await self._update_application_status_with_cb(app_info)
            
            logger.info(f"Validation process completed for {app_info.application_id}: {combined_result['status']}")
            
        except Exception as e:
            logger.error(f"Error in validation process: {e}", exc_info=True)
            # Update status to error
            app_info.status = ApplicationStatus.ERROR_STATE
            app_info.add_error(f"Validation process failed: {str(e)}")
            await self.state_manager.set_state(f"application:{app_info.application_id}", asdict(app_info))
            await self._update_application_status_with_cb(app_info)
            raise

    async def _get_attachments_for_validation(self, student_id: str) -> List[Dict]:
        """Retrieve attachments from MinIO for validation"""
        circuit_breaker = self.circuit_breakers['database']
        
        @circuit_breaker.call
        async def _get_attachments():
            response = await self.http_client.get(
                f"{self.settings.database_minio_url}/objects/{student_id}",
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()
        
        try:
            result = await _get_attachments()
            return result.get('data', [])
        except Exception as e:
            logger.error(f"Failed to get attachments for validation: {e}")
            return []

    async def _validate_documents_with_ai(self, attachments: List[Dict], application_id: str) -> Dict:
        """Validate documents using AI server"""
        circuit_breaker = self.circuit_breakers['ai_validation']
        
        @circuit_breaker.call
        async def _validate_with_ai():
            # Prepare data for AI validation
            validation_data = {
                'application_id': application_id,
                'attachments': attachments
            }
            
            response = await self.http_client.post(
                f"{self.settings.ai_validation_url}/validate",
                headers=self.headers,
                json=validation_data
            )
            response.raise_for_status()
            return response.json()
        
        try:
            result = await _validate_with_ai()
            logger.info(f"AI validation completed for {application_id}")
            return result
        except Exception as e:
            logger.error(f"AI validation failed for {application_id}: {e}")
            return {'success': False, 'error': str(e), 'details': []}

    async def excel_validate(self, attachments: List[Dict], application_id: str) -> Dict:
        """Excel sheet validation with NRSC application requirements"""
        try:
            logger.info(f"Starting Excel validation for application {application_id}")
            
            excel_files = [att for att in attachments if att.get('filename', '').endswith(('.xlsx', '.xls'))]
            
            if not excel_files:
                return {
                    'success': False,
                    'error': 'No Excel files found for validation',
                    'files_processed': 0,
                    'details': [],
                    'validation_errors': ['No Excel file submitted'],
                    'timestamp': datetime.now().isoformat()
                }
            
            validation_results = {
                'success': True,
                'files_processed': len(excel_files),
                'details': [],
                'validation_errors': [],
                'timestamp': datetime.now().isoformat()
            }
            
            for excel_file in excel_files:
                filename = excel_file.get('filename')
                logger.info(f"Processing Excel file: {filename}")
                
                # Simulate Excel data extraction (in production, use pandas/openpyxl)
                # For now, create sample data structure as if read from Excel
                excel_data = await self._extract_excel_data_simulation(excel_file, application_id)
                
                # Validate the Excel data
                field_validation = self._validate_excel_fields(excel_data)
                
                file_result = {
                    'filename': filename,
                    'size': excel_file.get('size', 0),
                    'status': 'processed',
                    'extracted_data': excel_data,
                    'field_validation': field_validation,
                    'valid': field_validation['all_valid']
                }
                
                validation_results['details'].append(file_result)
                
                if not field_validation['all_valid']:
                    validation_results['success'] = False
                    validation_results['validation_errors'].extend(field_validation['errors'])
                
                # Print excel data for debugging
                print(f"EXCEL DATA VALIDATION - {filename}:")
                print(f"  Application ID: {application_id}")
                print(f"  File Size: {excel_file.get('size', 0)} bytes")
                print(f"  Validation Status: {'PASSED' if field_validation['all_valid'] else 'FAILED'}")
                print("  Extracted Data:")
                for field, value in excel_data.items():
                    print(f"    {field}: {value}")
                if field_validation['errors']:
                    print("  Validation Errors:")
                    for error in field_validation['errors']:
                        print(f"    - {error}")
                print("-" * 50)
            
            return validation_results
            
        except Exception as e:
            logger.error(f"Excel validation failed for {application_id}: {e}")
            return {
                'success': False,
                'error': str(e),
                'files_processed': 0,
                'details': [],
                'validation_errors': [f"Processing error: {str(e)}"],
                'timestamp': datetime.now().isoformat()
            }
    
    async def _extract_excel_data_simulation(self, excel_file: Dict, application_id: str) -> Dict:
        """
        Simulate Excel data extraction. In production, this would use pandas or openpyxl
        to read the actual Excel file and extract the required fields.
        """
        # This is a simulation - in production you would:
        # 1. Download the file from MinIO using the file path
        # 2. Use pandas.read_excel() or openpyxl to read the file
        # 3. Extract the required fields from specific cells/columns
        
        # Create different test scenarios based on application_id for demonstration
        filename = excel_file.get('filename', '').lower()
        
        # Default valid data
        base_data = {
            # Student Details
            'name': 'Sample Student Name',
            'phone_number': '9876543210',
            'email_id': 'student@example.com',
            'date_of_birth': '1995-01-15',
            
            # Internship Details  
            'duration_and_type': '6 months, Research Internship',
            'application_start_date': (datetime.now() + timedelta(days=35)).strftime('%Y-%m-%d'),  # Valid: 35 days from now
            'end_date': (datetime.now() + timedelta(days=220)).strftime('%Y-%m-%d'),
            'project_or_internship': 'Remote Sensing Data Analysis',
            
            # Academic Details
            'college_name': 'Sample Engineering College',
            'semester_completed': 6,
            'cgpa': 7.5,  # Valid: >= 6.32
            'twelfth_mark_percentage': 85.5,  # Valid: >= 60%
            'tenth_mark_percentage': 78.0   # Valid: >= 60%
        }
        
        # Create test scenarios for different validation failures
        if 'fail' in filename or 'invalid' in filename:
            # Test various failure scenarios
            import random
            scenario = random.choice(['date', 'cgpa', 'marks', 'null_fields'])
            
            if scenario == 'date':
                # Fail date validation (less than 30 days)
                base_data['application_start_date'] = (datetime.now() + timedelta(days=10)).strftime('%Y-%m-%d')
            elif scenario == 'cgpa':
                # Fail CGPA validation
                base_data['cgpa'] = 5.8
            elif scenario == 'marks':
                # Fail marks validation
                base_data['tenth_mark_percentage'] = 55.0
                base_data['twelfth_mark_percentage'] = 58.0
            elif scenario == 'null_fields':
                # Fail null field validation
                base_data['name'] = ''
                base_data['college_name'] = None
                base_data['cgpa'] = 'null'
        
        return base_data
    
    def _validate_excel_fields(self, excel_data: Dict) -> Dict:
        """Validate Excel data against NRSC requirements"""
        errors = []
        warnings = []
        
        # Required fields - check for null/empty values
        required_fields = [
            'name', 'phone_number', 'email_id', 'date_of_birth',
            'duration_and_type', 'application_start_date', 'end_date', 
            'project_or_internship', 'college_name', 'semester_completed',
            'cgpa', 'twelfth_mark_percentage', 'tenth_mark_percentage'
        ]
        
        # Rule 4: Check for null/empty fields
        for field in required_fields:
            value = excel_data.get(field)
            if value is None or str(value).strip() == '' or str(value).lower() in ['null', 'none', 'n/a']:
                errors.append(f"Field '{field}' is required but is null or empty")
        
        # Rule 1: Start date validation (30 days after current date)
        try:
            start_date_str = excel_data.get('application_start_date', '')
            if start_date_str:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
                current_date = datetime.now()
                min_start_date = current_date + timedelta(days=30)
                
                if start_date < min_start_date:
                    errors.append(f"Application start date ({start_date_str}) must be at least 30 days from current date ({min_start_date.strftime('%Y-%m-%d')})")
        except (ValueError, TypeError) as e:
            errors.append(f"Invalid application start date format. Expected YYYY-MM-DD, got: {excel_data.get('application_start_date')}")
        
        # Rule 2: CGPA validation (minimum 6.32)
        try:
            cgpa = float(excel_data.get('cgpa', 0))
            if cgpa < 6.32:
                errors.append(f"CGPA ({cgpa}) must be at least 6.32 on a scale of 10")
        except (ValueError, TypeError):
            errors.append(f"Invalid CGPA format. Expected numeric value, got: {excel_data.get('cgpa')}")
        
        # Rule 3: 10th and 12th marks validation (minimum 60%)
        try:
            tenth_marks = float(excel_data.get('tenth_mark_percentage', 0))
            if tenth_marks < 60.0:
                errors.append(f"10th mark percentage ({tenth_marks}%) must be at least 60%")
        except (ValueError, TypeError):
            errors.append(f"Invalid 10th mark percentage format. Expected numeric value, got: {excel_data.get('tenth_mark_percentage')}")
        
        try:
            twelfth_marks = float(excel_data.get('twelfth_mark_percentage', 0))
            if twelfth_marks < 60.0:
                errors.append(f"12th mark percentage ({twelfth_marks}%) must be at least 60%")
        except (ValueError, TypeError):
            errors.append(f"Invalid 12th mark percentage format. Expected numeric value, got: {excel_data.get('twelfth_mark_percentage')}")
        
        # Additional validations
        # Email format validation
        email = excel_data.get('email_id', '')
        if email and not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            errors.append(f"Invalid email format: {email}")
        
        # Phone number validation (basic)
        phone = excel_data.get('phone_number', '')
        if phone and not re.match(r'^\d{10}$', str(phone).replace('+', '').replace('-', '').replace(' ', '')):
            warnings.append(f"Phone number format may be invalid: {phone}")
        
        return {
            'all_valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings,
            'total_errors': len(errors),
            'total_warnings': len(warnings)
        }

    async def _validate_excel_sheet(self, attachments: List[Dict], application_id: str) -> Dict:
        """Wrapper for excel_validate function"""
        return await self.excel_validate(attachments, application_id)

    async def _send_validation_success_email(self, student_id: str, application_id: str):
        """Send validation successful email"""
        circuit_breaker = self.circuit_breakers['outgoing_email']
        
        @circuit_breaker.call
        async def _send_email():
            # Get student info
            student_info_dict = await self.state_manager.get_state(f"student:{student_id}")
            if not student_info_dict:
                raise Exception(f"Student info not found for {student_id}")
            
            student_info = StudentInfo(**student_info_dict)
            
            data = {
                'recipient': student_info.email,
                'subject': f'Validation Successful - Application {application_id}',
                'student_id': student_id,
                'application_id': application_id
            }
            
            response = await self.http_client.post(
                f"{self.settings.outgoing_email_url}/email/template/application_validated",
                headers=self.headers,
                json=data
            )
            response.raise_for_status()
            return response.json()
        
        try:
            await _send_email()
            logger.info(f"Validation success email sent for {application_id}")
        except Exception as e:
            logger.error(f"Failed to send validation success email: {e}")
            raise

    async def _send_validation_failed_email(self, student_id: str, application_id: str, validation_result: Dict):
        """Send validation failed email"""
        circuit_breaker = self.circuit_breakers['outgoing_email']
        
        @circuit_breaker.call
        async def _send_email():
            # Get student info
            student_info_dict = await self.state_manager.get_state(f"student:{student_id}")
            if not student_info_dict:
                raise Exception(f"Student info not found for {student_id}")
            
            student_info = StudentInfo(**student_info_dict)
            
            data = {
                'recipient': student_info.email,
                'subject': f'Validation Failed - Application {application_id}',
                'student_id': student_id,
                'application_id': application_id,
                'validation_details': validation_result
            }
            
            response = await self.http_client.post(
                f"{self.settings.outgoing_email_url}/email/template/validation_failed",
                headers=self.headers,
                json=data
            )
            response.raise_for_status()
            return response.json()
        
        try:
            await _send_email()
            logger.info(f"Validation failed email sent for {application_id}")
        except Exception as e:
            logger.error(f"Failed to send validation failed email: {e}")
            raise

    async def _log_validation_complete(self, app_info: ApplicationInfo, validation_result: Dict):
        """Log validation completion details to validation_complete.txt"""
        try:
            log_entry = {
                'timestamp': datetime.now().isoformat(),
                'application_id': app_info.application_id,
                'student_id': app_info.student_id,
                'status': app_info.status.value,
                'validation_result': validation_result,
                'processing_metadata': app_info.processing_metadata
            }
            
            # Write to validation_complete.txt
            log_line = f"{json.dumps(log_entry, default=str)}\n"
            
            async with aiofiles.open('validation_complete.txt', 'a') as f:
                await f.write(log_line)
            
            logger.info(f"Logged validation completion for {app_info.application_id}")
            
        except Exception as e:
            logger.error(f"Failed to log validation completion: {e}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type(httpx.RequestError)
    )
    async def process_new_emails(self):
        """Enhanced process to handle both application and information-required emails"""
        circuit_breaker = self.circuit_breakers['email_polling']
        
        @circuit_breaker.call
        async def _fetch_application_emails():
            url = f"{self.settings.email_polling_url}/application-emails"
            logger.info(f"Fetching application emails from {url}")
            response = await self.http_client.get(url)
            response.raise_for_status()
            return response.json()
        
        @circuit_breaker.call
        async def _fetch_info_required_emails():
            url = f"{self.settings.email_polling_url}/information-required-emails"
            logger.info(f"Fetching info required emails from {url}")
            response = await self.http_client.get(url)
            response.raise_for_status()
            return response.json()
        
        try:
            # Fetch both types of emails concurrently
            app_emails_data, info_emails_data = await asyncio.gather(
                _fetch_application_emails(),
                _fetch_info_required_emails(),
                return_exceptions=True
            )
            
            # Handle potential exceptions
            if isinstance(app_emails_data, Exception):
                logger.error(f"Failed to fetch application emails: {type(app_emails_data).__name__}: {str(app_emails_data)}", exc_info=app_emails_data)
                app_emails_data = {'emails': []}
            
            if isinstance(info_emails_data, Exception):
                logger.error(f"Failed to fetch info required emails: {type(info_emails_data).__name__}: {str(info_emails_data)}", exc_info=info_emails_data)
                info_emails_data = {'emails': []}
            
            all_emails = []
            all_emails.extend(app_emails_data.get('emails', []))
            all_emails.extend(info_emails_data.get('emails', []))
            
            if self.metrics:
                self.metrics.increment("emails_fetched", len(all_emails))
            
            # Process emails concurrently with limit
            semaphore = asyncio.Semaphore(5)  # Limit concurrent email processing
            
            async def process_single_email(email):
                async with semaphore:
                    await self.handle_email_enhanced(email)
            
            tasks = [process_single_email(email) for email in all_emails]
            
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
                
        except Exception as e:
            logger.error(f"Failed to process emails: {e}")
            if self.metrics:
                self.metrics.increment("email_processing_errors")
            raise

# async def main():
#     """Main function with enhanced error handling"""
#     settings = Settings()
#     manager = EnhancedApplicationManager(settings)
    
#     try:
#         await manager.initialize()
#         await manager.start_monitoring()
#     except KeyboardInterrupt:
#         logger.info("Received shutdown signal")
#     except Exception as e:
#         logger.error(f"Fatal error: {e}", exc_info=True)
#     finally:
#         await manager.cleanup()

# Create FastAPI app
app = FastAPI(title="Application Pipeline Manager", description="API for managing student application pipeline")

# Global manager instance
manager_instance = None

async def get_manager():
    """Get or create manager instance"""
    global manager_instance
    if manager_instance is None:
        settings = Settings()
        manager_instance = EnhancedApplicationManager(settings)
        await manager_instance.initialize()
    return manager_instance

@app.get("/")
async def root():
    """Root endpoint"""
    return {"status": "ok", "message": "Application Pipeline Manager API"}

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}

@app.post("/pipeline/start")
async def start_pipeline():
    """Start the application pipeline monitoring"""
    try:
        manager = await get_manager()
        # Start monitoring in the background
        import asyncio
        asyncio.create_task(manager.start_monitoring())
        return {"status": "success", "message": "Pipeline monitoring started"}
    except Exception as e:
        logger.error(f"Failed to start pipeline: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start pipeline: {str(e)}")

@app.post("/pipeline/process")
async def process_pipeline():
    """Process emails through the pipeline"""
    try:
        manager = await get_manager()
        await manager.process_new_emails()
        return {"status": "success", "message": "Pipeline processing completed"}
    except Exception as e:
        logger.error(f"Pipeline processing failed: {e}")
        raise HTTPException(status_code=500, detail=f"Pipeline processing failed: {str(e)}")

@app.get("/pipeline/status")
async def get_pipeline_status():
    """Get current pipeline status"""
    try:
        manager = await get_manager()
        if manager.metrics:
            metrics = manager.metrics.get_metrics()
            return {
                "status": "success",
                "pipeline_active": not manager.shutdown_event.is_set(),
                "metrics": metrics,
                "timestamp": datetime.now().isoformat()
            }
        else:
            return {
                "status": "success", 
                "pipeline_active": not manager.shutdown_event.is_set(),
                "metrics": {},
                "timestamp": datetime.now().isoformat()
            }
    except Exception as e:
        logger.error(f"Failed to get pipeline status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get pipeline status: {str(e)}")

@app.post("/pipeline/stop")
async def stop_pipeline():
    """Stop the pipeline monitoring"""
    try:
        manager = await get_manager()
        manager.shutdown_event.set()
        return {"status": "success", "message": "Pipeline monitoring stopped"}
    except Exception as e:
        logger.error(f"Failed to stop pipeline: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to stop pipeline: {str(e)}")

@app.get("/applications/{application_id}")
async def get_application_status(application_id: str):
    """Get status of a specific application"""
    try:
        manager = await get_manager()
        app_info_dict = await manager.state_manager.get_state(f"application:{application_id}")
        if not app_info_dict:
            raise HTTPException(status_code=404, detail="Application not found")
        return {"status": "success", "application": app_info_dict}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get application status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get application status: {str(e)}")

@app.get("/students/{student_id}")
async def get_student_info(student_id: str):
    """Get information about a specific student"""
    try:
        manager = await get_manager()
        student_info_dict = await manager.state_manager.get_state(f"student:{student_id}")
        if not student_info_dict:
            raise HTTPException(status_code=404, detail="Student not found")
        return {"status": "success", "student": student_info_dict}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get student info: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get student info: {str(e)}")

if __name__ == "__main__":
    import sys
    # if len(sys.argv) > 1 and sys.argv[1] == "api":
        # Run as FastAPI server
    uvicorn.run("main:app", host="0.0.0.0", port=8006, log_level="info", reload=True)
    # else:
    #     # Run as standalone application
    #     asyncio.run(main())