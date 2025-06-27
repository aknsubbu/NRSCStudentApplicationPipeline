import os
import datetime
from pathlib import Path
from dotenv import load_dotenv
import logging

load_dotenv()


from methods import StudentApplicationPipelineClient
from excel_validator import validate_nrsc_excel_file

client = StudentApplicationPipelineClient(
    ai_server_url=os.getenv("AI_SERVER_URL"),
    db_server_url=os.getenv("DB_SERVER_URL"),
    email_polling_url=os.getenv("EMAIL_POLLING_URL"),
    outgoing_email_url=os.getenv("OUTGOING_EMAIL_URL"),
    db_api_key=os.getenv("API_KEY"),
    email_api_key=os.getenv("API_KEY")
)

def setup_logging(log_file="log/manager.log"):
    """Configure logging with directory creation"""
    try:
        # Create the log directory if it doesn't exist
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
        logging.info("Logging initialized successfully")
    except Exception as e:
        print(f"Failed to initialize logging: {str(e)}")
        raise
    
    
setup_logging()

logging.info("Application Pipeline Manager Booted Up")


class ApplicationPipelineManager:
    def __init__(self,client: StudentApplicationPipelineClient):
        self.client = client
        logging.info("Application Pipeline Manager Initialized")
        logging.info("Fetching applications")
        applications=self.client.get_application_emails()
        logging.info(f"Found {len(applications['emails'])} applications")
        for application in applications['emails']:
            if application['is_application']==True:
                application_id=application['application_id']
                student_id=application['student_id']
                logging.info(f"Creating student {student_id} for application {application_id}")
                logging.info(f"Creating application {application_id} for student {student_id}")
                # logging.info(f"Application: {application}")
                client.create_student(student_id=student_id,student_name=application['sender_name'],student_email=application['sender'],student_phone='',student_status='received')
                client.create_application(application_id=application_id,student_id=student_id,application_status='received',intern_project='',intern_project_start_date='',intern_project_end_date='')
                logging.info(f"Checking attachment names for student {student_id}")
                file_list=[]
                for attachment in application['attachments']:
                    file_list.append(attachment['filename'])
                    
                #upload to minio bucket
                client.update_application_status(application_id=application_id,new_status='information_required')
                client.update_student_status(student_id=student_id,new_status='information_required')
                logging.info(f"Uploading email body and attachments to MinIO bucket for student {student_id}")
                #save the attachements in the MinIO bucket
                client.upload_file(student_id=student_id,object_name=f"email_body.txt",file_path=application['body_text'])
                for attachment in application['attachments']:
                    client.upload_file(student_id=student_id,object_name=f"{attachment['filename']}",file_path=attachment['path'])  
                logging.info(f"Email body and attachments uploaded to MinIO bucket for student {student_id}")
                #send the information required email
                client.send_information_required_email(recipient=application['sender'],student_id=student_id,student_name=application['sender_name'])
                
                
                    # logging.info(f"Moving files to archive subfolder within the attachements folder for student {student_id}")
                    # client.archive_and_delete_files(source_root=f"attachments/{student_id}",archive_root=f"attachments/archive/{student_id}")
                    # logging.info(f"Files moved to archive subfolder within the attachements folder for student {student_id}")


class InformationRequiredManager:
    def __init__(self,client: StudentApplicationPipelineClient):
        self.client = client
        logging.info("Information Required Manager Initialized")
        logging.info("Fetching information required emails")
        information_required_emails=self.client.get_information_required_emails()
        # logging.info(f"Found {len(information_required_emails['emails'])} information required emails")
        print(information_required_emails)
        for information_required in information_required_emails:
            if information_required['is_info_required']==True:
                logging.info(f"Processing information required email for student {information_required['student_id']} for application {information_required['application_id']}")
                student_id=information_required['student_id']
                application_id=information_required['application_id']
                student_name=information_required['sender_name']
                #upload the excel file to the MinIO bucket
                client.upload_file(student_id=student_id,object_name=f"excel_attachment.xlsx",file_path=information_required['attachments'][0]['path'])
                logging.info(f"Excel file uploaded to MinIO bucket for student {student_id}")
                #validate the excel file
                logging.info(f"Validating excel file for student {student_id}")
                validation_data=validate_nrsc_excel_file(file_path=information_required['attachments'][0]['path'])
                if not validation_data['success']:
                    logging.info(f"Excel file is invalid for student {student_id}")
                    logging.info(f"Sending validation failed email to {information_required['sender']}")
                    client.send_validation_failed_email(recipient=information_required['sender'],subject=f"Document Validation Failed - Action Required ({student_id})",student_id=student_id,object_name="excel_attachment_validation",expires=36000,template_data={"student_name":student_name,"message":"Your Excel document submission has validation issues that need to be corrected:","issues":validation_data['validation_result']['errors']},file_list=information_required['attachments'][0]['filename'])
                    continue
                # #fetch the attachments from the MinIO bucket
                # logging.info(f"Fetching attachments from MinIO bucket for student {student_id}")
                # attachments=client.list_objects(student_id=student_id)
                # for attachment in attachments:
                #     client.download_file(student_id=student_id,object_name=attachment['name'],file_path=attachment['path'])
                # logging.info(f"Attachments fetched from MinIO bucket for student {student_id}")
                # #categorize the attachments
                # logging.info(f"Categorizing attachments for student {student_id}")
                # categories=client.categorize_attachments(attachments=attachments)
                # logging.info(f"Attachments categorized for student {student_id}")
                # #validate the attachments
                # logging.info(f"Validating attachments for student {student_id}")
                # response=client.validate_documents(resume_cover_letter=categories['resume'],letter_of_recommendation=categories['lor'],class_10_marksheet=categories['class_10'],class_12_marksheet=categories['class_12'],college_marksheets=categories['college'])
                # logging.info(f"Attachments validated for student {student_id}")
                if validation_data['success']:
                    logging.info(f"Attachments are valid for student {student_id}")
                    #update the application status to validated
                    client.update_application_status(application_id=application_id,new_status='validated')
                    client.update_student_status(student_id=student_id,new_status='validated')
                    #send the application validated email
                    client.send_application_validated_email(recipient=information_required['sender'],subject=f"Application Validated for {student_name}",student_name=student_name,application_id=application_id,student_id=student_id)
                # elif response['valid']==False:
                #     logging.info(f"Attachments are invalid for student {student_id}")
                #     validation_data=client.extract_validation_data(response)
                #     #send the validation failed email
                #     client.send_validation_failed_email(recipient=information_required['sender'],subject=f"Document Validation Failed - Action Required ({student_id})",student_id=student_id,object_name="pdf_attachment_validation",expires=36000,template_data={"student_name":student_name,"message":"Your PDF document submission has validation issues that need to be corrected:","issues":validation_data['validation_issues']},file_list=response['file_list'])



if __name__ == "__main__":
    manager=InformationRequiredManager(client=client)
