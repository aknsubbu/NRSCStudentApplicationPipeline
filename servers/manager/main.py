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
from pydantic import BaseSettings, validator
import asyncpg
from concurrent.futures import ThreadPoolExecutor
import signal
import sys
from functools import wraps
import time
from collections import defaultdict

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
    """Configuration settings with validation"""
    # Server URLs
    email_polling_url: str = "http://localhost:8002"
    database_minio_url: str = "http://localhost:8000"
    ai_validation_url: str = "http://localhost:8005"
    outgoing_email_url: str = "http://localhost:8001"
    
    # Security
    api_key: str
    encryption_key: Optional[str] = None
    
    # Redis Configuration
    redis_url: str = "redis://localhost:6379"
    redis_password: Optional[str] = None
    
    # Database Configuration
    postgres_url: Optional[str] = None
    
    # Processing Configuration
    email_poll_interval: int = 30
    validation_timeout: int = 300
    max_concurrent_validations: int = 5
    retry_attempts: int = 3
    
    # File Configuration
    temp_dir: str = "/tmp/app-manager"
    max_file_size: int = 50 * 1024 * 1024  # 50MB
    allowed_file_types: Set[str] = {"pdf", "doc", "docx", "jpg", "jpeg", "png"}
    
    # Monitoring
    metrics_enabled: bool = True
    log_level: str = "INFO"
    
    class Config:
        env_file = ".env"
        case_sensitive = False

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
            settings.allowed_types
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
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type(httpx.RequestError)
    )
    async def process_new_emails(self):
        """Process new emails with retry logic and circuit breaker"""
        circuit_breaker = self.circuit_breakers['email_polling']
        
        @circuit_breaker.call
        async def _fetch_emails():
            response = await self.http_client.get(
                f"{self.settings.email_polling_url}/application-emails"
            )
            response.raise_for_status()
            return response.json()
        
        try:
            emails_data = await _fetch_emails()
            
            if self.metrics:
                self.metrics.increment("emails_fetched", len(emails_data.get('emails', [])))
            
            # Process emails concurrently with limit
            semaphore = asyncio.Semaphore(5)  # Limit concurrent email processing
            
            async def process_single_email(email):
                async with semaphore:
                    await self.handle_email_enhanced(email)
            
            tasks = [
                process_single_email(email)
                for email in emails_data.get('emails', [])
            ]
            
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
                
        except Exception as e:
            logger.error(f"Failed to process emails: {e}")
            if self.metrics:
                self.metrics.increment("email_processing_errors")
            raise

    async def handle_email_enhanced(self, email_data: Dict):
        """Enhanced email handling with deduplication and better logic"""
        email_hash = self.email_processor.extract_email_hash(email_data)
        
        # Skip if already processed
        if self.email_processor.is_duplicate_email(email_hash):
            return
        
        try:
            email_id = email_data.get('id')
            sender_email = email_data.get('sender')
            
            # Create correlation ID for tracking
            correlation_id = f"email_{email_hash}"
            
            with logger.bind(correlation_id=correlation_id, email_id=email_id):
                # Determine email type and handle accordingly
                if await self.is_initial_application_enhanced(email_data):
                    await self.handle_initial_application_enhanced(email_data, correlation_id)
                elif await self.is_document_submission_enhanced(email_data):
                    await self.handle_document_submission_enhanced(email_data, correlation_id)
                else:
                    logger.info("Email doesn't match known patterns, skipping")
                
                # Mark as processed
                self.email_processor.mark_email_processed(email_hash)
                
                if self.metrics:
                    self.metrics.increment("emails_processed")
                    
        except Exception as e:
            logger.error(f"Error handling email: {e}", exc_info=True)
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
            sender_email = email_data.get('sender')
            logger.info(f"Processing initial application from {sender_email}")
            
            # Extract student information with enhanced parsing
            extracted_info = self.email_processor.extract_student_info_enhanced(email_data)
            
            # Generate IDs
            application_id = self.generate_application_id()
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
                'application_status': app_info.status.value
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
                params=data
            )
            response.raise_for_status()
            return response.json()
        
        try:
            return await _update_status()
        except Exception as e:
            logger.error(f"Failed to update application status: {e}")
            raise

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

# Additional methods would be implemented here following the same patterns...
# This is a substantial improvement but due to length constraints, 
# I'm showing the key architectural improvements

async def main():
    """Main function with enhanced error handling"""
    settings = Settings()
    manager = EnhancedApplicationManager(settings)
    
    try:
        await manager.initialize()
        await manager.start_monitoring()
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
    finally:
        await manager.cleanup()

if __name__ == "__main__":
    asyncio.run(main())