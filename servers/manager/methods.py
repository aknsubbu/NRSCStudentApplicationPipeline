import requests
import json
import os
from typing import Dict, List, Optional, Any, Union
from pathlib import Path
from dotenv import load_dotenv
import re
import pandas as pd
from datetime import datetime, timedelta
import shutil


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
    import requests
    from typing import Union, Dict, Any
    from pathlib import Path

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
            
        Raises:
            FileNotFoundError: If any of the specified files don't exist
            requests.RequestException: If the API request fails
            Exception: For other validation errors
        """
        url = f"{self.ai_server_url}/validate"
        
        # Convert to Path objects for easier handling
        resume_path = Path(resume_cover_letter)
        lor_path = Path(letter_of_recommendation)
        class_10_path = Path(class_10_marksheet)
        class_12_path = Path(class_12_marksheet)
        college_path = Path(college_marksheets)
        
        # Validate that all files exist before making the request
        files_to_check = [
            (resume_path, "Resume/Cover Letter"),
            (lor_path, "Letter of Recommendation"),
            (class_10_path, "Class 10 Marksheet"),
            (class_12_path, "Class 12 Marksheet"),
            (college_path, "College Marksheets")
        ]
        
        for file_path, file_desc in files_to_check:
            if not file_path.exists():
                raise FileNotFoundError(f"{file_desc} file not found: {file_path}")
        
        # Prepare files dict with correct parameter names matching the FastAPI server
        files = {
            'resume': open(resume_path, 'rb'),
            'lor': open(lor_path, 'rb'), 
            'class_10': open(class_10_path, 'rb'),
            'class_12': open(class_12_path, 'rb'),
            'college_marksheets': open(college_path, 'rb')
        }
        
        try:
            # Make the API request
            response = requests.post(url, files=files, timeout=300)  # 5 minute timeout
            
            # Check if request was successful
            response.raise_for_status()
            
            # Return the JSON response
            return response.json()
            
        except requests.exceptions.Timeout:
            raise Exception("Request timed out. The validation process is taking too long.")
        except requests.exceptions.ConnectionError:
            raise Exception(f"Could not connect to AI validation server at {self.ai_server_url}")
        except requests.exceptions.HTTPError as e:
            if response.status_code == 500:
                error_detail = response.json().get('error', 'Unknown server error')
                raise Exception(f"Server error during validation: {error_detail}")
            else:
                raise Exception(f"HTTP error {response.status_code}: {e}")
        except requests.exceptions.RequestException as e:
            raise Exception(f"Request failed: {e}")
        except Exception as e:
            raise Exception(f"Validation failed: {e}")
        finally:
            # Ensure all file handles are closed
            for file_handle in files.values():
                if not file_handle.closed:
                    file_handle.close()


# Alternative version with more robust error handling and logging
    def validate_documents_with_logging(self, 
                                    resume_cover_letter: Union[str, Path],
                                    letter_of_recommendation: Union[str, Path],
                                    class_10_marksheet: Union[str, Path],
                                    class_12_marksheet: Union[str, Path],
                                    college_marksheets: Union[str, Path]) -> Dict[str, Any]:
        """
        Validate all required documents using AI validation server with detailed logging.
        
        Args:
            resume_cover_letter: Path to resume/cover letter PDF
            letter_of_recommendation: Path to recommendation letter PDF
            class_10_marksheet: Path to class 10 marksheet PDF
            class_12_marksheet: Path to class 12 marksheet PDF
            college_marksheets: Path to college marksheets PDF
            
        Returns:
            Dict containing validation results
        """
        import logging
        logger = logging.getLogger(__name__)
        
        url = f"{self.ai_server_url}/validate"
        logger.info(f"Starting document validation using server: {url}")
        
        # Convert to Path objects
        file_paths = {
            'resume': Path(resume_cover_letter),
            'lor': Path(letter_of_recommendation),
            'class_10': Path(class_10_marksheet),
            'class_12': Path(class_12_marksheet),
            'college_marksheets': Path(college_marksheets)
        }
        
        # Validate file existence
        for param_name, file_path in file_paths.items():
            if not file_path.exists():
                logger.error(f"File not found: {file_path}")
                raise FileNotFoundError(f"Required file not found: {file_path}")
            logger.info(f"Found {param_name}: {file_path}")
        
        # Prepare files for upload
        files = {}
        
        try:
            # Open all files
            for param_name, file_path in file_paths.items():
                files[param_name] = open(file_path, 'rb')
                logger.info(f"Opened {param_name} file: {file_path.name}")
            
            # Make the API request
            logger.info("Sending validation request to server...")
            response = requests.post(url, files=files, timeout=300)
            
            # Check response
            response.raise_for_status()
            result = response.json()
            
            # Log results
            status = result.get('status', 'unknown')
            logger.info(f"Validation completed with status: {status}")
            
            if not result.get('valid', False):
                invalid_docs = result.get('invalid_documents', [])
                logger.warning(f"Validation failed. Invalid documents: {invalid_docs}")
            
            return result
            
        except Exception as e:
            logger.error(f"Document validation failed: {e}")
            raise
        finally:
            # Ensure all files are closed
            for param_name, file_handle in files.items():
                if hasattr(file_handle, 'close') and not file_handle.closed:
                    file_handle.close()
                    logger.debug(f"Closed {param_name} file")
                
                
    def ai_health_check(self) -> Dict[str, Any]:
        """Check AI server health status."""
        url = f"{self.ai_server_url}/health"
        response = requests.get(url)
        return response.json()


    def extract_validation_data(self,validation_output):
        """Extract validation issues and applicant profile from validation output"""
        
        # Initialize result dictionary
        result = {
            'validation_issues': [],
            'applicant_profile': {}
        }
        
        # Extract validation issues
        if 'invalid_documents' in validation_output and validation_output['invalid_documents']:
            result['validation_issues'].extend(validation_output['invalid_documents'])
        
        if 'rejection_reasons' in validation_output and validation_output['rejection_reasons']:
            result['validation_issues'].extend(validation_output['rejection_reasons'])
        
        # Extract detailed document issues
        doc_issues = []
        if 'validation_details' in validation_output:
            for doc_type, details in validation_output['validation_details'].items():
                if not details.get('valid', True) and 'issues' in details:
                    doc_issues.append({
                        'document_type': doc_type,
                        'filename': details.get('filename', ''),
                        'issues': details['issues']
                    })
        result['document_issues'] = doc_issues
        
        # Extract applicant profile
        if 'applicant_profile' in validation_output:
            result['applicant_profile'] = validation_output['applicant_profile']['skills_analysis']
        
        return result


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
    
    def archive_and_delete_files(self,source_root, archive_root="attachments/archive"):
        """
        Moves files from source path to archive path (preserving directory structure)
        and then deletes them from source path.
        
        Args:
            source_root (str): Root directory to search for files
            archive_root (str): Root directory for archive (default: "attachments/archive")
        """
        # Convert to Path objects for better path handling
        source_root = Path(source_root)
        archive_root = Path(archive_root)
        
        # Walk through all files in source directory
        for file_path in source_root.rglob('*'):
            if file_path.is_file():
                try:
                    # Create relative path from source root
                    relative_path = file_path.relative_to(source_root)
                    
                    # Create destination path in archive
                    archive_path = archive_root / relative_path
                    
                    # Create parent directories if they don't exist
                    archive_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    # Move the file
                    shutil.move(str(file_path), str(archive_path))
                    print(f"Moved: {file_path} -> {archive_path}")
                    
                except Exception as e:
                    print(f"Error processing {file_path}: {str(e)}")

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
        url=f"{self.email_polling_url}/application-emails"
        response=requests.get(url)
        info_required_emails=[]
        for email in response.json()['emails']:
            if email['is_info_required']:
                info_required_emails.append(email)
        return info_required_emails
 
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
    
    def send_information_required_email(self, recipient: str,
                                       student_id: str, student_name: str) -> Dict[str, Any]:
        """Send information required template email."""
        url = f"{self.outgoing_email_url}/email/template/information_required"
        data = {
            "recipient": recipient,
            "student_name": student_name,
            "student_id": student_id,
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
            "template_name": "validation_failed",
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

    # ===================
    # File Name Validation
    # ===================
    def validate_pdf_attachments(self,file_list: List[str]) -> Dict[str, Union[bool, List[str]]]:
        """
        Validates PDF attachments according to specific naming requirements.
        
        Requirements:
        - Exactly 5 PDF files
        - 1 file ending with _CV.pdf
        - 1 file ending with _X.pdf
        - 1 file ending with _XII.pdf
        - 1 file ending with _undergrad.pdf
        - 1 additional PDF file that doesn't match the above patterns
        
        Args:
            file_list: List of filenames to validate
            
        Returns:
            Dict containing:
            - isValid: Boolean indicating if validation passed
            - issues: List of failure reasons
            - file_list: Original file list
        """
        result = {
            "isValid": False,
            "issues": [],
            "file_list": file_list or []
        }
        
        # Check if file_list exists and is a list
        if not isinstance(file_list, list):
            result["issues"].append("File list must be a list")
            return result
        
        # Check if exactly 5 files
        if len(file_list) != 5:
            result["issues"].append(f"Expected exactly 5 files, but received {len(file_list)} files")
            return result
        
        # Check if all files are PDFs
        non_pdf_files = [file for file in file_list if not file.lower().endswith('.pdf')]
        if non_pdf_files:
            result["issues"].append(f"Non-PDF files found: {', '.join(non_pdf_files)}")
        
        # Define required patterns
        required_patterns = [
            {"pattern": re.compile(r"_CV\.pdf$", re.IGNORECASE), "name": "CV document", "found": False},
            {"pattern": re.compile(r"_X\.pdf$", re.IGNORECASE), "name": "X document", "found": False},
            {"pattern": re.compile(r"_XII\.pdf$", re.IGNORECASE), "name": "XII document", "found": False},
            {"pattern": re.compile(r"_undergrad\.pdf$", re.IGNORECASE), "name": "undergrad document", "found": False}
        ]
        
        matched_files = set()
        
        # Check for required patterns
        for file in file_list:
            for requirement in required_patterns:
                if requirement["pattern"].search(file) and not requirement["found"]:
                    requirement["found"] = True
                    matched_files.add(file)
                    break
        
        # Check for missing required documents
        missing_docs = [req["name"] for req in required_patterns if not req["found"]]
        if missing_docs:
            result["issues"].append(f"Missing required documents: {', '.join(missing_docs)}")
        
        # Check for duplicate pattern matches
        duplicate_matches = []
        for file in file_list:
            match_count = sum(1 for req in required_patterns if req["pattern"].search(file))
            if match_count > 1:
                duplicate_matches.append(file)
        
        if duplicate_matches:
            result["issues"].append(f"Files matching multiple patterns: {', '.join(duplicate_matches)}")
        
        # Check if the 5th file is a valid PDF that doesn't match the first 4 patterns
        unmatched_files = [file for file in file_list if file not in matched_files]
        
        if len(unmatched_files) == 0 and len(file_list) == 5:
            result["issues"].append("All files match the first 4 patterns - need exactly one additional PDF file")
        elif len(unmatched_files) > 1:
            result["issues"].append(f"Too many unmatched files ({len(unmatched_files)}). Expected exactly 1 additional PDF file that doesn't match the first 4 patterns")
        elif len(unmatched_files) == 1:
            fifth_file = unmatched_files[0]
            if not fifth_file.lower().endswith('.pdf'):
                result["issues"].append(f'Fifth file "{fifth_file}" must be a PDF')
        
        # If no issues found, validation passes
        if not result["issues"]:
            result["isValid"] = True
        
        return result
    
    
    def categorize_attachments(self,attachments):
        """
        Simple categorization of 5 files:
        - 1 Resume (_CV.pdf)
        - 1 Class 10 (_X.pdf)
        - 1 Class 12 (_XII.pdf)
        - 1 College (_undergrad.pdf)
        - 1 LOR (exact name match)
        """
        categories = {
            'resume': None,        # Ends with _CV.pdf
            'class_10': None,      # Ends with _X.pdf
            'class_12': None,     # Ends with _XII.pdf
            'college': None,       # Ends with _undergrad.pdf
            'lor': None            # Exact name 'letter_of_recommendation.pdf'
        }
        
        for attachment in attachments:
            name = attachment['filename']
            path = attachment['path']
            
            if name.endswith('_CV.pdf') or name.endswith('_cv.pdf') or name.endswith('_Cv.pdf'):
                categories['resume'] = path
            elif name.endswith('_X.pdf'):
                categories['class_10'] = path
            elif name.endswith('_XII.pdf'):
                categories['class_12'] = path
            elif name.endswith('_undergrad.pdf'):
                categories['college'] = path
            else:
                categories['lor'] = path
        
        return categories
        
        