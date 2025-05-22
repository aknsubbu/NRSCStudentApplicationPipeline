import asyncio
import logging
from typing import Callable, Dict, Any
from fastapi import BackgroundTasks

logger = logging.getLogger(__name__)

class EmailQueue:
    """
    Asynchronous queue for handling email sending operations.
    Prevents blocking the main application thread during email sending.
    """
    def __init__(self):
        self.queue = asyncio.Queue()
        self.is_processing = False
        self.processing_task = None
    
    async def add_email_task(self, email_func: Callable, background_tasks: BackgroundTasks, **kwargs) :
        """
        Add an email task to the queue and start processing if not already running.
        
        Args:
            email_func: The email function to call
            background_tasks: FastAPI background tasks object
            **kwargs: Arguments for the email function
        """
        tracking_id = kwargs.get("tracking_id", None)
        await self.queue.put((email_func, kwargs))
        
        if not self.is_processing:
            self.is_processing = True
            background_tasks.add_task(self.process_queue)
            
        return tracking_id
    
    async def process_queue(self):
        """Process email tasks from the queue one by one with error handling."""
        while not self.queue.empty():
            try:
                email_func, kwargs = await self.queue.get()
                
                tracking_id = kwargs.pop("tracking_id", None)
                tracker = kwargs.pop("tracker", None)
                
                if tracker and tracking_id:
                    tracker.update_status(tracking_id, "processing")
                    
                try:
                    result = await email_func(**kwargs)
                    if tracker and tracking_id:
                        tracker.update_status(tracking_id, "sent")
                except Exception as e:
                    logger.error(f"Error processing email task: {str(e)}")
                    if tracker and tracking_id:
                        tracker.update_status(tracking_id, "failed", str(e))
                    
                self.queue.task_done()
            except Exception as e:
                logger.error(f"Queue processing error: {str(e)}")
            finally:
                await asyncio.sleep(0.1)  # Prevent CPU overload
        
        self.is_processing = False

    async def get_queue_stats(self) -> Dict[str, Any]:
        """Get current queue statistics."""
        return {
            "queue_size": self.queue.qsize(),
            "is_processing": self.is_processing
        }
