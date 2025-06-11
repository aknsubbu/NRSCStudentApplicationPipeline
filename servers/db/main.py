from fastapi import FastAPI, Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from utils.minio_client import (
    get_minio_client, upload_file, download_file, list_objects, delete_object, generate_presigned_url
)
from utils.models import FileUpload, FileDownload, ObjectDelete, PresignedUrl, FileUploadWithEmail
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

#Uncomment the following lines to enable email functionality
# import smtplib

app = FastAPI(title="MinIO FastAPI Server", description="API to manage student files in a single MinIO bucket")

# API Key Authentication ... This is a static key for the current time... 
API_KEY = os.getenv("API_KEY", "your-secret-api-key-123")
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def get_api_key(api_key: str = Security(api_key_header)):
    if api_key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key"
        )
    return api_key

# Initialize MinIO client and bucket
minio_client = get_minio_client()
BUCKET_NAME = os.getenv("BUCKET_NAME", "applicationdocs")

# # Email configuration
# EMAIL_SENDER = os.getenv("EMAIL_SENDER", "your_email@gmail.com")
# EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "your_app_password")

# def send_email(recipient: str, subject: str, body: str):
#     """Send an email using Gmail SMTP."""
#     msg = MIMEMultipart()
#     msg['From'] = EMAIL_SENDER
#     msg['To'] = recipient
#     msg['Subject'] = subject
#     msg.attach(MIMEText(body, 'plain'))

#     try:
#         server = smtplib.SMTP('smtp.gmail.com', 587)
#         server.starttls()
#         server.login(EMAIL_SENDER, EMAIL_PASSWORD)
#         server.sendmail(EMAIL_SENDER, recipient, msg.as_string())
#         server.quit()
#         return {"message": f"Email sent to {recipient}"}
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Failed to send email: {str(e)}")

@app.get("/health")
def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.post("/objects/upload/", response_model=dict, dependencies=[Depends(get_api_key)])
async def upload_file_endpoint(file: FileUpload):
    """Upload a file to the student-files bucket with student ID prefix."""
    try:
        if not os.path.exists(file.file_path):
            raise HTTPException(status_code=400, detail="File path does not exist")
        return upload_file(minio_client, BUCKET_NAME, file.student_id, file.object_name, file.file_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/objects/upload-with-email/", response_model=dict, dependencies=[Depends(get_api_key)])
async def upload_file_with_email_endpoint(file: FileUploadWithEmail):
    """Upload a file and send a presigned URL via email."""
    try:
        if not os.path.exists(file.file_path):
            raise HTTPException(status_code=400, detail="File path does not exist")
        
        # Upload file
        upload_result = upload_file(minio_client, BUCKET_NAME, file.student_id, file.object_name, file.file_path)
        
        # Generate presigned URL
        url_result = generate_presigned_url(minio_client, BUCKET_NAME, file.student_id, file.object_name, expires=3600)
        
        # # Send email with presigned URL
        # email_body = f"File '{file.object_name}' for student {file.student_id} has been uploaded.\nDownload it here: {url_result['url']}"
        # email_result = send_email(file.recipient_email, f"MinIO File Upload for {file.student_id}", email_body)
        
        return {
            "upload": upload_result,
            "presigned_url": url_result,
            # "email": email_result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/objects/download/", response_model=dict, dependencies=[Depends(get_api_key)])
async def download_file_endpoint(file: FileDownload):
    """Download a file from the student-files bucket."""
    try:
        return download_file(minio_client, BUCKET_NAME, file.student_id, file.object_name, file.file_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/objects/{student_id}", response_model=list[dict], dependencies=[Depends(get_api_key)])
async def list_objects_endpoint(student_id: str):
    """List objects for a student in the student-files bucket."""
    try:
        return list_objects(minio_client, BUCKET_NAME, student_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/objects/", response_model=dict, dependencies=[Depends(get_api_key)])
async def delete_object_endpoint(obj: ObjectDelete):
    """Delete an object from the student-files bucket."""
    try:
        return delete_object(minio_client, BUCKET_NAME, obj.student_id, obj.object_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/objects/presigned-url/", response_model=dict, dependencies=[Depends(get_api_key)])
async def generate_presigned_url_endpoint(url: PresignedUrl):
    """Generate a presigned URL for an object in the student-files bucket."""
    try:
        return generate_presigned_url(minio_client, BUCKET_NAME, url.student_id, url.object_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)