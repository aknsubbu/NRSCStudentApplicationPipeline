from enum import Enum
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field, EmailStr

class NotificationType(str, Enum):
    """Types of notifications that can be sent through the system."""
    # Application status notifications
    APPLICATION_RECEIVED = "application_received"
    VALIDATION_FAILED = "validation_failed"
    VALIDATION_PASSED = "validation_passed"
    ADMIN_REVIEW_REQUESTED = "admin_review_requested"
    APPLICATION_APPROVED = "application_approved"
    APPLICATION_REJECTED = "application_rejected"
    
    # Scheduling notifications
    INTERVIEW_SCHEDULED = "interview_scheduled"
    INTERVIEW_REMINDER = "interview_reminder"
    INTERVIEW_RESCHEDULED = "interview_rescheduled"
    INTERVIEW_CANCELED = "interview_canceled"
    
    # Onboarding notifications
    ONBOARDING_INSTRUCTIONS = "onboarding_instructions"
    ONBOARDING_REMINDER = "onboarding_reminder"
    ACCOUNT_CREATED = "account_created"
    ORIENTATION_SCHEDULED = "orientation_scheduled"

class DocumentIssue(BaseModel):
    """Represents an issue found in a document during validation."""
    document_type: str
    problem: str
    suggestion: Optional[str] = None

class NotificationData(BaseModel):
    """Data required for sending a notification."""
    student_id: str
    student_email: EmailStr
    student_name: Optional[str] = None
    template_data: Dict[str, Any] = Field(default_factory=dict)
    document_objects: Optional[List[str]] = None
    issues: Optional[List[DocumentIssue]] = None
    
    class Config:
        schema_extra = {
            "example": {
                "student_id": "ST12345",
                "student_email": "student@example.com",
                "student_name": "John Smith",
                "template_data": {
                    "message": "Your application has been received and is being processed.",
                    "next_steps": "Please wait for our validation team to review your documents."
                },
                "document_objects": ["resume.pdf", "transcript.pdf"],
                "issues": [
                    {
                        "document_type": "Resume",
                        "problem": "Missing contact information",
                        "suggestion": "Please include your phone number and email address."
                    }
                ]
            }
        }
    
def get_notification_subject(notification_type: NotificationType) -> str:
    """
    Return a default subject line for each notification type.
    
    Args:
        notification_type: Type of notification
        
    Returns:
        Appropriate subject line for the email
    """
    subject_templates = {
        NotificationType.APPLICATION_RECEIVED: "Application Received - NRSC Student Program",
        NotificationType.VALIDATION_FAILED: "Action Required: Application Issues Detected",
        NotificationType.VALIDATION_PASSED: "Application Successfully Validated",
        NotificationType.ADMIN_REVIEW_REQUESTED: "Your Application is Under Review",
        NotificationType.APPLICATION_APPROVED: "Congratulations! Your Application is Approved",
        NotificationType.APPLICATION_REJECTED: "Important Update on Your NRSC Application",
        NotificationType.INTERVIEW_SCHEDULED: "Interview Scheduled - NRSC Student Program",
        NotificationType.INTERVIEW_REMINDER: "Reminder: Upcoming Interview - NRSC Student Program",
        NotificationType.INTERVIEW_RESCHEDULED: "Interview Rescheduled - NRSC Student Program",
        NotificationType.INTERVIEW_CANCELED: "Interview Canceled - NRSC Student Program",
        NotificationType.ONBOARDING_INSTRUCTIONS: "Welcome to NRSC - Onboarding Instructions",
        NotificationType.ONBOARDING_REMINDER: "Reminder: Complete Your Onboarding Tasks",
        NotificationType.ACCOUNT_CREATED: "Your NRSC Account Has Been Created",
        NotificationType.ORIENTATION_SCHEDULED: "NRSC Orientation Details"
    }
    
    return subject_templates.get(notification_type, "Update on Your NRSC Application")
