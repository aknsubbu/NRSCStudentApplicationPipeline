import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional

class EmailTracker:
    """
    Tracks the status and history of sent emails.
    Useful for monitoring delivery and troubleshooting issues.
    """
    def __init__(self):
        self.emails = {}
        self.MAX_HISTORY = 10000  # Maximum number of emails to track before pruning
    
    def create_tracking_id(self, recipient: str, subject: str, notification_type: str = '') -> str:
        """
        Create a new tracking entry for an email.
        
        Args:
            recipient: Email recipient
            subject: Email subject
            notification_type: Type of notification (e.g., validation_failed)
            
        Returns:
            Unique tracking ID
        """
        tracking_id = str(uuid.uuid4())
        self.emails[tracking_id] = {
            "recipient": recipient,
            "subject": subject,
            "notification_type": notification_type,
            "created_at": datetime.now().isoformat(),
            "status": "queued",
            "sent_at": None,
            "delivery_status": None,
            "error": None
        }
        
        # Prune history if it gets too large
        if len(self.emails) > self.MAX_HISTORY:
            self._prune_old_entries()
            
        return tracking_id
    
    def update_status(self, tracking_id: str, status: str, error: Optional[str] = None) -> bool:
        """
        Update the status of a tracked email.
        
        Args:
            tracking_id: Unique tracking ID
            status: New status (queued, processing, sent, failed)
            error: Optional error message
            
        Returns:
            True if update successful, False otherwise
        """
        if tracking_id in self.emails:
            self.emails[tracking_id]["status"] = status
            if status == "sent":
                self.emails[tracking_id]["sent_at"] = datetime.now().isoformat()
            if error:
                self.emails[tracking_id]["error"] = error
            return True
        return False
    
    def get_status(self, tracking_id: str) -> Dict[str, Any]:
        """
        Get the status of a tracked email.
        
        Args:
            tracking_id: Unique tracking ID
            
        Returns:
            Email tracking information or not found message
        """
        return self.emails.get(tracking_id, {"status": "not_found"})
    
    def get_all_by_recipient(self, recipient: str) -> List[Dict[str, Any]]:
        """
        Get all emails sent to a specific recipient.
        
        Args:
            recipient: Email address of recipient
            
        Returns:
            List of email tracking information for this recipient
        """
        return [
            {"tracking_id": tid, **data} 
            for tid, data in self.emails.items() 
            if data["recipient"] == recipient
        ]
    
    def get_by_status(self, status: str) -> List[Dict[str, Any]]:
        """
        Get all emails with a specified status.
        
        Args:
            status: Email status to filter by
            
        Returns:
            List of email tracking information with this status
        """
        return [
            {"tracking_id": tid, **data} 
            for tid, data in self.emails.items() 
            if data["status"] == status
        ]
    
    def get_stats(self) -> Dict[str, int]:
        """
        Get statistics about tracked emails.
        
        Returns:
            Dictionary with counts of emails in each status
        """
        stats = {"total": len(self.emails), "queued": 0, "processing": 0, "sent": 0, "failed": 0}
        for email in self.emails.values():
            if email["status"] in stats:
                stats[email["status"]] += 1
        return stats
    
    def _prune_old_entries(self):
        """Remove old entries to prevent memory issues."""
        # Sort by creation time and keep the most recent MAX_HISTORY/2
        sorted_entries = sorted(
            self.emails.items(), 
            key=lambda x: x[1]["created_at"], 
            reverse=True
        )
        
        keep_count = self.MAX_HISTORY // 2
        self.emails = {k: v for k, v in sorted_entries[:keep_count]}
