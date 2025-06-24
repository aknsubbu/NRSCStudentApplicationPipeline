from servers.manager.methods import StudentApplicationPipelineClient
from dotenv import load_dotenv
import os

load_dotenv()

client = StudentApplicationPipelineClient(db_api_key=os.getenv("API_KEY"),email_api_key=os.getenv("API_KEY"))
import logging


file_list_names=['1234567890_V.pdf','1234567890_X.pdf','1234567890_XI.pdf','1234567890_undergrad.pdf','1234567890_letter_of_recommendation.txt']

student_id='1234567890'


filename_validity=client.validate_pdf_attachments(file_list_names)
if filename_validity['isValid']==True:
    logging.info(f"Attachments are valid for student {student_id}")
else:
    logging.info(f"Attachments are invalid for student {student_id}")
    logging.info(f"Invalid attachments: {filename_validity['issues']}")
    template_data = {
        "student_name": "test",
        "message": "Your PDF document submission has validation issues that need to be corrected:",
        "issues": filename_validity["issues"]
    }
    response = client.send_validation_failed_email(
        recipient="aknsubbu@gmail.com",
        subject=f"Document Validation Failed - Action Required ({student_id})",
        student_id=student_id,
        object_name="pdf_attachment_validation",  # or whatever object name you use
        expires=36000,  # 1 hour expiry, adjust as needed
        template_data=template_data,
        file_list=filename_validity["file_list"]
    )


print(filename_validity)