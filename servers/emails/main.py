from fastapi import FastAPI, Depends, HTTPException, Security, status, File, UploadFile
from fastapi.security import APIKeyHeader
from utils.models import EmailRequest, BulkEmailRequest, TemplateEmailRequest
from utils.email_client import send_email, render_template
import httpx
import os
from dotenv import load_dotenv
import logging
from typing import List

load_dotenv()

app = FastAPI(title="Email FastAPI Server", description="API for sending outgoing communications with MinIO integration")

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# API Key Authentication
API_KEY = os.getenv("API_KEY", "your-secret-api-key-123")
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def get_api_key(api_key: str = Security(api_key_header)):
    if api_key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key"
        )
    return api_key

# MinIO server URL
MINIO_SERVER_URL = os.getenv("MINIO_SERVER_URL", "http://localhost:8000")

async def get_presigned_url(student_id: str, object_name: str, expires: int = 3600):
    """Fetch a presigned URL from the MinIO FastAPI server."""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{MINIO_SERVER_URL}/objects/presigned-url/",
                json={"student_id": student_id, "object_name": object_name, "expires": expires},
                headers={"X-API-Key": API_KEY}
            )
            response.raise_for_status()
            return response.json()["url"]
        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to fetch presigned URL: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to fetch presigned URL: {str(e)}")

@app.post("/email/send/", response_model=dict, dependencies=[Depends(get_api_key)])
async def send_single_email(request: EmailRequest, attachments: List[UploadFile] = File(None)):
    """Send a single email with optional attachments and MinIO presigned URL."""
    try:
        # Process attachments
        attachment_list = []
        if attachments:
            for attachment in attachments:
                content = await attachment.read()
                attachment_list.append({
                    "filename": attachment.filename,
                    "content": content
                })

        # Generate MinIO presigned URL if requested
        minio_url = None
        if request.student_id and request.object_name:
            minio_url = await get_presigned_url(
                request.student_id,
                request.object_name,
                request.expires
            )

        # Send email
        return send_email(
            recipient=request.recipient,
            subject=request.subject,
            body=request.body,
            is_html=request.is_html,
            attachments=attachment_list,
            minio_url=minio_url
        )
    except Exception as e:
        logger.error(f"Error sending email: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/email/bulk/", response_model=dict, dependencies=[Depends(get_api_key)])
async def send_bulk_email(request: BulkEmailRequest, attachments: List[UploadFile] = File(None)):
    """Send emails to multiple recipients with optional attachments and MinIO presigned URLs."""
    try:
        # Process attachments
        attachment_list = []
        if attachments:
            for attachment in attachments:
                content = await attachment.read()
                attachment_list.append({
                    "filename": attachment.filename,
                    "content": content
                })

        # Send emails to each recipient
        results = []
        for i, recipient in enumerate(request.recipients):
            student_id = request.student_ids[i] if request.student_ids and i < len(request.student_ids) else None
            object_name = request.object_names[i] if request.object_names and i < len(request.object_names) else None
            minio_url = None

            # Generate MinIO presigned URL if requested
            if student_id and object_name:
                minio_url = await get_presigned_url(
                    student_id,
                    object_name,
                    request.expires
                )

            result = send_email(
                recipient=recipient,
                subject=request.subject,
                body=request.body,
                is_html=request.is_html,
                attachments=attachment_list,
                minio_url=minio_url
            )
            results.append(result)

        return {"message": f"Emails sent to {len(results)} recipients"}
    except Exception as e:
        logger.error(f"Error sending bulk email: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/email/template/", response_model=dict, dependencies=[Depends(get_api_key)])
async def send_template_email(request: TemplateEmailRequest, attachments: List[UploadFile] = File(None)):
    """Send an email using a predefined template with optional attachments and MinIO presigned URL."""
    try:
        # Process attachments
        attachment_list = []
        if attachments:
            for attachment in attachments:
                content = await attachment.read()
                attachment_list.append({
                    "filename": attachment.filename,
                    "content": content
                })

        # Generate MinIO presigned URL if requested
        minio_url = None
        if request.student_id and request.object_name:
            minio_url = await get_presigned_url(
                request.student_id,
                request.object_name,
                request.expires
            )

        # Render template
        body = render_template(
            template_name=request.template_name,
            subject=request.subject,
            recipient_name=request.recipient.split('@')[0],
            message=request.template_data.get("message"),
            file_url=minio_url
        )

        # Send email
        return send_email(
            recipient=request.recipient,
            subject=request.subject,
            body=body,
            is_html=True,
            attachments=attachment_list,
            minio_url=minio_url
        )
    except Exception as e:
        logger.error(f"Error sending template email: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)  # Use different port to avoid conflict