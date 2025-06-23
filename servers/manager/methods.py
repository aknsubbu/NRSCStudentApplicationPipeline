import requests
import json
import os
from typing import Dict, List, Optional, Any, Union
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


class StudentApplicationPipelineClient:
    """
    Client for interacting with the Student Application Pipeline API servers.
    """
    
    def __init__(self, 
                 ai_server_url: str = "http://localhost:8005",
                 db_server_url: str = "http://localhost:8000", 
                 email_polling_url: str = "http://localhost:8004",
                 outgoing_email_url: str = "http://localhost:8001",
                 db_api_key: Optional[str] = os.getenv("API_KEY"),
                 email_api_key: Optional[str] = os.getenv("API_KEY")):
        """
        Initialize the API client with server URLs and API keys.
        
        Args:
            ai_server_url: URL for AI Document Validation Server
            db_server_url: URL for Database and File Management Server
            email_polling_url: URL for Email Polling Server
            outgoing_email_url: URL for Outgoing Email Server
            db_api_key: API key for database server
            email_api_key: API key for outgoing email server
        """
        self.ai_server_url = ai_server_url.rstrip('/')
        self.db_server_url = db_server_url.rstrip('/')
        self.email_polling_url = email_polling_url.rstrip('/')
        self.outgoing_email_url = outgoing_email_url.rstrip('/')
        
        self.db_headers = {"X-API-Key": db_api_key} if db_api_key else {}
        self.email_headers = {"X-API-Key": email_api_key} if email_api_key else {}

    # =================
    # AI VALIDATION API
    # =================
    
    def validate_documents(self, 
                          resume_cover_letter: Union[str, Path],
                          letter_of_recommendation: Union[str, Path],
                          class_10_marksheet: Union[str, Path],
                          class_12_marksheet: Union[str, Path],
                          college_marksheets: Union[str, Path]) -> Dict[str, Any]:
        """
        Validate all required documents using AI validation server.
        
        Args:
            resume_cover_letter: Path to resume/cover letter PDF
            letter_of_recommendation: Path to recommendation letter PDF
            class_10_marksheet: Path to class 10 marksheet PDF
            class_12_marksheet: Path to class 12 marksheet PDF
            college_marksheets: Path to college marksheets PDF
            
        Returns:
            Dict containing validation results
        """
        url = f"{self.ai_server_url}/validate"
        
        files = {
            'resume_cover_letter': open(resume_cover_letter, 'rb'),
            'letter_of_recommendation': open(letter_of_recommendation, 'rb'),
            'class_10_marksheet': open(class_10_marksheet, 'rb'),
            'class_12_marksheet': open(class_12_marksheet, 'rb'),
            'college_marksheets': open(college_marksheets, 'rb')
        }
        
        try:
            response = requests.post(url, files=files)
            return response.json()
        finally:
            # Close all file handles
            for file in files.values():
                file.close()
    
    def ai_health_check(self) -> Dict[str, Any]:
        """Check AI server health status."""
        url = f"{self.ai_server_url}/health"
        response = requests.get(url)
        return response.json()

    # ===================
    # DATABASE & FILE API
    # ===================
    
    # Student Management
    def create_student(self, student_id: str, student_name: str, 
                      student_email: str, student_phone: str, 
                      student_status: str = "active") -> Dict[str, Any]:
        """Create a new student record."""
        url = f"{self.db_server_url}/db/student/create"
        data = {
            "student_id": student_id,
            "student_name": student_name,
            "student_email": student_email,
            "student_phone": student_phone,
            "student_status": student_status
        }
        response = requests.post(url, json=data, headers=self.db_headers)
        return response.json()
    
    def get_student(self, student_id: str) -> Dict[str, Any]:
        """Get student by ID."""
        url = f"{self.db_server_url}/db/student/get"
        params = {"student_id": student_id}
        response = requests.get(url, params=params, headers=self.db_headers)
        return response.json()
    
    def get_all_students(self) -> Dict[str, Any]:
        """Get all students."""
        url = f"{self.db_server_url}/db/student/get-all"
        response = requests.get(url, headers=self.db_headers)
        return response.json()
    
    def update_student(self, student_id: str, student_name: str,
                      student_email: str, student_phone: str,
                      student_status: str) -> Dict[str, Any]:
        """Update student information."""
        url = f"{self.db_server_url}/db/student/update"
        data = {
            "student_id": student_id,
            "student_name": student_name,
            "student_email": student_email,
            "student_phone": student_phone,
            "student_status": student_status
        }
        response = requests.put(url, json=data, headers=self.db_headers)
        return response.json()
    
    def delete_student(self, student_id: str) -> Dict[str, Any]:
        """Delete student by ID."""
        url = f"{self.db_server_url}/db/student/delete"
        params = {"student_id": student_id}
        response = requests.delete(url, params=params, headers=self.db_headers)
        return response.json()
    
    def update_student_status(self, student_id: str, new_status: str) -> Dict[str, Any]:
        """Update student status."""
        url = f"{self.db_server_url}/db/student/update-status"
        data = {"student_id": student_id, "new_status": new_status}
        response = requests.patch(url, json=data, headers=self.db_headers)
        return response.json()
    
    def update_student_contact(self, student_id: str, email: str, phone: str) -> Dict[str, Any]:
        """Update student contact information."""
        url = f"{self.db_server_url}/db/student/update-contact"
        data = {"student_id": student_id, "email": email, "phone": phone}
        response = requests.patch(url, json=data, headers=self.db_headers)
        return response.json()
    
    def get_students_by_status(self, status: str) -> Dict[str, Any]:
        """Get students by status."""
        url = f"{self.db_server_url}/db/student/get-by-status"
        params = {"status": status}
        response = requests.get(url, params=params, headers=self.db_headers)
        return response.json()
    
    # Application Management
    def create_application(self, student_id: str, application_id: str,
                          application_status: str, intern_project: str,
                          intern_project_start_date: str, 
                          intern_project_end_date: str) -> Dict[str, Any]:
        """Create a new application record."""
        url = f"{self.db_server_url}/db/application/create"
        data = {
            "student_id": student_id,
            "application_id": application_id,
            "application_status": application_status,
            "intern_project": intern_project,
            "intern_project_start_date": intern_project_start_date,
            "intern_project_end_date": intern_project_end_date
        }
        response = requests.post(url, json=data, headers=self.db_headers)
        return response.json()
    
    def get_application(self, application_id: str) -> Dict[str, Any]:
        """Get application by ID."""
        url = f"{self.db_server_url}/db/application/get"
        params = {"application_id": application_id}
        response = requests.get(url, params=params, headers=self.db_headers)
        return response.json()
    
    def get_all_applications(self) -> Dict[str, Any]:
        """Get all applications."""
        url = f"{self.db_server_url}/db/application/get-all"
        response = requests.get(url, headers=self.db_headers)
        return response.json()
    
    def update_application(self, application_id: str, student_id: str,
                          application_status: str, intern_project: str,
                          intern_project_start_date: str,
                          intern_project_end_date: str) -> Dict[str, Any]:
        """Update application information."""
        url = f"{self.db_server_url}/db/application/update"
        data = {
            "application_id": application_id,
            "student_id": student_id,
            "application_status": application_status,
            "intern_project": intern_project,
            "intern_project_start_date": intern_project_start_date,
            "intern_project_end_date": intern_project_end_date
        }
        response = requests.put(url, json=data, headers=self.db_headers)
        return response.json()
    
    def delete_application(self, application_id: str) -> Dict[str, Any]:
        """Delete application by ID."""
        url = f"{self.db_server_url}/db/application/delete"
        params = {"application_id": application_id}
        response = requests.delete(url, params=params, headers=self.db_headers)
        return response.json()
    
    def update_application_status(self, application_id: str, new_status: str) -> Dict[str, Any]:
        """Update application status."""
        url = f"{self.db_server_url}/db/application/update-status"
        data = {"application_id": application_id, "new_status": new_status}
        response = requests.patch(url, json=data, headers=self.db_headers)
        return response.json()
    
    def update_application_project(self, application_id: str, project: str) -> Dict[str, Any]:
        """Update application project."""
        url = f"{self.db_server_url}/db/application/update-project"
        data = {"application_id": application_id, "project": project}
        response = requests.patch(url, json=data, headers=self.db_headers)
        return response.json()
    
    def update_application_dates(self, application_id: str, start_date: str, 
                               end_date: str) -> Dict[str, Any]:
        """Update application dates."""
        url = f"{self.db_server_url}/db/application/update-dates"
        data = {
            "application_id": application_id,
            "start_date": start_date,
            "end_date": end_date
        }
        response = requests.patch(url, json=data, headers=self.db_headers)
        return response.json()
    
    def get_applications_by_status(self, status: str) -> Dict[str, Any]:
        """Get applications by status."""
        url = f"{self.db_server_url}/db/application/get-by-status"
        params = {"status": status}
        response = requests.get(url, params=params, headers=self.db_headers)
        return response.json()
    
    # MinIO File Operations
    def upload_file(self, student_id: str, object_name: str, file_path: str) -> Dict[str, Any]:
        """Upload file to MinIO."""
        url = f"{self.db_server_url}/objects/upload/"
        data = {
            "student_id": student_id,
            "object_name": object_name,
            "file_path": file_path
        }
        response = requests.post(url, json=data, headers=self.db_headers)
        return response.json()
    
    def upload_file_with_email(self, student_id: str, object_name: str, 
                              file_path: str, recipient_email: str) -> Dict[str, Any]:
        """Upload file to MinIO and send email notification."""
        url = f"{self.db_server_url}/objects/upload-with-email/"
        data = {
            "student_id": student_id,
            "object_name": object_name,
            "file_path": file_path,
            "recipient_email": recipient_email
        }
        response = requests.post(url, json=data, headers=self.db_headers)
        return response.json()
    
    def download_file(self, student_id: str, object_name: str, file_path: str) -> Dict[str, Any]:
        """Download file from MinIO."""
        url = f"{self.db_server_url}/objects/download/"
        data = {
            "student_id": student_id,
            "object_name": object_name,
            "file_path": file_path
        }
        response = requests.post(url, json=data, headers=self.db_headers)
        return response.json()
    
    def list_objects(self, student_id: str) -> Dict[str, Any]:
        """List objects for a student."""
        url = f"{self.db_server_url}/objects/{student_id}"
        response = requests.get(url, headers=self.db_headers)
        return response.json()
    
    def delete_object(self, student_id: str, object_name: str) -> Dict[str, Any]:
        """Delete object from MinIO."""
        url = f"{self.db_server_url}/objects/"
        data = {"student_id": student_id, "object_name": object_name}
        response = requests.delete(url, json=data, headers=self.db_headers)
        return response.json()
    
    def get_presigned_url(self, student_id: str, object_name: str) -> Dict[str, Any]:
        """Get presigned URL for object."""
        url = f"{self.db_server_url}/objects/presigned-url/"
        data = {"student_id": student_id, "object_name": object_name}
        response = requests.post(url, json=data, headers=self.db_headers)
        return response.json()
    
    def db_health_check(self) -> Dict[str, Any]:
        """Check database server health."""
        url = f"{self.db_server_url}/health"
        response = requests.get(url)
        return response.json()

    # ===================
    # EMAIL POLLING API
    # ===================
    
    def email_polling_status(self) -> Dict[str, Any]:
        """Get email polling service status."""
        url = f"{self.email_polling_url}/"
        response = requests.get(url)
        return response.json()
    
    def email_polling_health(self) -> Dict[str, Any]:
        """Check email polling service health."""
        url = f"{self.email_polling_url}/health"
        response = requests.get(url)
        return response.json()
    
    def get_email_config(self) -> Dict[str, Any]:
        """Get email polling configuration."""
        url = f"{self.email_polling_url}/config"
        response = requests.get(url)
        return response.json()
    
    def update_email_config(self, imap_server: str, username: str, password: str,
                           folder: str = "INBOX", processed_folder: str = "Processed",
                           app_keywords: List[str] = None, max_emails: int = 50,
                           mark_as_read: bool = True, move_processed: bool = True,
                           attachment_dir: str = "./attachments", timeout: int = 30,
                           include_raw_email: bool = False) -> Dict[str, Any]:
        """Update email polling configuration."""
        url = f"{self.email_polling_url}/config"
        data = {
            "imap_server": imap_server,
            "username": username,
            "password": password,
            "folder": folder,
            "processed_folder": processed_folder,
            "app_keywords": app_keywords or ["application", "internship"],
            "max_emails": max_emails,
            "mark_as_read": mark_as_read,
            "move_processed": move_processed,
            "attachment_dir": attachment_dir,
            "timeout": timeout,
            "include_raw_email": include_raw_email
        }
        response = requests.post(url, json=data)
        return response.json()
    
    def poll_emails(self) -> Dict[str, Any]:
        """Poll emails without saving."""
        url = f"{self.email_polling_url}/poll"
        response = requests.get(url)
        return response.json()
    
    def poll_and_save_emails(self) -> Dict[str, Any]:
        """Poll and save emails."""
        url = f"{self.email_polling_url}/poll/save"
        response = requests.post(url)
        return response.json()
    
    def get_application_emails(self) -> Dict[str, Any]:
        """Get application-related emails only."""
        url = f"{self.email_polling_url}/application-emails"
        response = requests.get(url)
        return response.json()

    def get_information_required_emails(self)->Dict[str,Any]:
        url:f"{self.email_polling_url}/information-required"
        response=requests.get(url)
        return response.json
 
    def test_email_connection(self) -> Dict[str, Any]:
        """Test email server connection."""
        url = f"{self.email_polling_url}/test-connection"
        response = requests.get(url)
        return response.json()
    
    def get_email_folders(self) -> Dict[str, Any]:
        """Get available email folders."""
        url = f"{self.email_polling_url}/folders"
        response = requests.get(url)
        return response.json()

    # ===================
    # OUTGOING EMAIL API
    # ===================
    
    def outgoing_email_status(self) -> Dict[str, Any]:
        """Get outgoing email service status."""
        url = f"{self.outgoing_email_url}/"
        response = requests.get(url)
        return response.json()
    
    def outgoing_email_health(self) -> Dict[str, Any]:
        """Check outgoing email service health."""
        url = f"{self.outgoing_email_url}/health"
        response = requests.get(url)
        return response.json()
    
    def send_email(self, recipient: str, subject: str, body: str,
                   is_html: bool = False, file_list: List[str] = None,
                   student_id: str = None, object_name: str = None,
                   expires: int = 3600) -> Dict[str, Any]:
        """Send individual email."""
        url = f"{self.outgoing_email_url}/email/send/"
        data = {
            "recipient": recipient,
            "subject": subject,
            "body": body,
            "is_html": is_html,
            "file_list": file_list or [],
            "student_id": student_id,
            "object_name": object_name,
            "expires": expires
        }
        response = requests.post(url, json=data, headers=self.email_headers)
        return response.json()
    
    def send_application_received_email(self, recipient: str, subject: str,
                                       student_name: str, application_id: str,
                                       student_id: str) -> Dict[str, Any]:
        """Send application received template email."""
        url = f"{self.outgoing_email_url}/email/template/application_received"
        data = {
            "recipient": recipient,
            "subject": subject,
            "student_name": student_name,
            "application_id": application_id,
            "student_id": student_id
        }
        response = requests.post(url, json=data, headers=self.email_headers)
        return response.json()
    
    def send_information_required_email(self, recipient: str, subject: str,
                                       student_id: str, deadline_date: str) -> Dict[str, Any]:
        """Send information required template email."""
        url = f"{self.outgoing_email_url}/email/template/information_required"
        data = {
            "recipient": recipient,
            "subject": subject,
            "student_id": student_id,
            "deadline_date": deadline_date
        }
        response = requests.post(url, json=data, headers=self.email_headers)
        return response.json()
    
    def send_application_validated_email(self, recipient: str, subject: str,
                                        student_name: str, application_id: str,
                                        student_id: str) -> Dict[str, Any]:
        """Send application validated template email."""
        url = f"{self.outgoing_email_url}/email/template/application_validated"
        data = {
            "recipient": recipient,
            "subject": subject,
            "student_name": student_name,
            "application_id": application_id,
            "student_id": student_id
        }
        response = requests.post(url, json=data, headers=self.email_headers)
        return response.json()
    
    def send_validation_failed_email(self, recipient: str, subject: str,
                                    student_id: str, object_name: str,
                                    expires: int, template_data: Dict[str, Any],
                                    file_list: List[str] = None) -> Dict[str, Any]:
        """Send validation failed template email."""
        url = f"{self.outgoing_email_url}/email/template/validation_failed"
        data = {
            "recipient": recipient,
            "subject": subject,
            "student_id": student_id,
            "object_name": object_name,
            "expires": expires,
            "template_data": template_data,
            "file_list": file_list or []
        }
        response = requests.post(url, json=data, headers=self.email_headers)
        return response.json()
    
    def test_email_connection_outgoing(self) -> Dict[str, Any]:
        """Test outgoing email connection."""
        url = f"{self.outgoing_email_url}/email/test-connection/"
        response = requests.get(url, headers=self.email_headers)
        return response.json()
    
    def send_test_email(self, recipient: str, subject: str = "Test Email",
                       message: str = "This is a test email.") -> Dict[str, Any]:
        """Send test email."""
        url = f"{self.outgoing_email_url}/email/test-send/"
        params = {
            "recipient": recipient,
            "subject": subject,
            "message": message
        }
        response = requests.post(url, params=params, headers=self.email_headers)
        return response.json()
    
    def debug_email_templates(self) -> Dict[str, Any]:
        """Debug email templates."""
        url = f"{self.outgoing_email_url}/email/debug-templates/"
        response = requests.get(url, headers=self.email_headers)
        return response.json()

