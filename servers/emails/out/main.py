from fastapi import FastAPI, Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from utils.models import EmailRequest, TemplateEmailRequest, TemplateEmailRecieved
from utils.email_client import send_email, render_template
import httpx
import os
from dotenv import load_dotenv
import logging
from typing import List, Optional
from pathlib import Path
from datetime import datetime, timedelta


load_dotenv(dotenv_path=Path(__file__).parent.parent.parent / '.env')

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
async def send_single_email(request: EmailRequest):
    """Send a single email with optional MinIO presigned URL."""
    try:
        # Generate MinIO presigned URL if requested
        minio_url = None
        if request.student_id and request.object_name:
            expires_time = request.expires or 3600
            minio_url = await get_presigned_url(
                request.student_id,
                request.object_name,
                expires_time
            )
            logger.info(f"Generated MinIO URL for student {request.student_id}")

        # Send email
        result = send_email(
            recipient=request.recipient,
            subject=request.subject,
            body=request.body,
            is_html=request.is_html,
            file_list=request.file_list,
            minio_url=minio_url
        )
        
        logger.info(f"Email sent successfully to {request.recipient}")
        return result
        
    except Exception as e:
        logger.error(f"Error sending email: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    

@app.post("/email/template/application_received", response_model=dict, dependencies=[Depends(get_api_key)])
async def send_template_email_application_received(request: TemplateEmailRecieved):
    """Send an email using a predefined template with optional MinIO presigned URL."""
    try: 
        # Use default subject if none provided
        subject = request.subject or 'Application Received by NRSC Training and Outreach Team'
        
        # Render template
        body = render_template(
            template_name='application_received.html',
            subject=subject,
            student_name=request.student_name,
            application_id=request.application_id,
            student_id=request.student_id,
        )

        # Send email
        result = send_email(
            recipient=request.recipient,
            subject=subject,
            body=body,
            is_html=True,
        )
        
        logger.info(f"Template email sent successfully to {request.recipient}")
        return result
        
    except Exception as e:
        logger.error(f"Error sending template email: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    
@app.post("/email/template/application_validated", response_model=dict, dependencies=[Depends(get_api_key)])
async def send_template_email_application_validated(request: TemplateEmailRecieved):
    """Send an email using a predefined template with optional MinIO presigned URL."""
    try: 
        # Use default subject if none provided
        subject = request.subject or 'Application Validated by NRSC Training and Outreach Team'
        
        # Render template
        body = render_template(
            template_name='application_validated.html',
            subject=subject,
            student_name=request.student_name,
            application_id=request.application_id,
            student_id=request.student_id,
            message='Your application has been successfully validated by NRSC Training and Outreach Team. Please wait for the next steps.'
            )

        # Send email
        result = send_email(
            recipient=request.recipient,
            subject=subject,
            body=body,
            is_html=True,
        )
        
        logger.info(f"Template email sent successfully to {request.recipient}")
        return result
        
    except Exception as e:
        logger.error(f"Error sending template email: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    
@app.post("/email/template/information_required", response_model=dict, dependencies=[Depends(get_api_key)])
async def send_template_email_information_required(request: TemplateEmailRecieved):
    """Send an email using a predefined template with optional MinIO presigned URL."""
    try: 
        # Use default subject if none provided
        subject = request.subject or 'Information Required by NRSC Training and Outreach Team'
        
        # Render template
        body = render_template(
            template_name='information_required.html',
            subject=subject,
            student_name=request.student_name,
            student_id=request.student_id,
            deadline_date=(datetime.now() + timedelta(days=7)).strftime('%d/%m/%Y')
            )

        # Send email
        result = send_email(
            recipient=request.recipient,
            subject=subject,
            body=body,
            is_html=True,
        )
        
        logger.info(f"Template email sent successfully to {request.recipient}")
        return result
        
    except Exception as e:
        logger.error(f"Error sending template email: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    


@app.post("/email/template/validation_failed", response_model=dict, dependencies=[Depends(get_api_key)])
async def send_template_email_validation_failed(request: TemplateEmailRequest):
    """Send an email using a predefined template with optional MinIO presigned URL."""
    try:
        # Generate MinIO presigned URL if requested
        minio_url = None
        if request.student_id and request.object_name:
            expires_time = request.expires or 3600
            minio_url = await get_presigned_url(
                request.student_id,
                request.object_name,
                expires_time
            )

        # Render template
        body = render_template(
            template_name='validation_failed.html',
            subject=request.subject,
            student_name=request.template_data.get("student_name", "Student"),
            recipient_name=request.recipient.split('@')[0],
            message=request.template_data.get("message", ""),
            file_url=minio_url,
            file_list=request.file_list or [],
            issues=request.template_data.get("issues", []),

        )

        # Send email
        result = send_email(
            recipient=request.recipient,
            subject=request.subject,
            body=body,
            is_html=True,
            file_list=request.file_list,
            minio_url=minio_url
        )
        
        logger.info(f"Template email sent successfully to {request.recipient}")
        return result
        
    except Exception as e:
        logger.error(f"Error sending template email: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/email/test-connection/", dependencies=[Depends(get_api_key)])
async def test_email_connection():
    """Test the email connection configuration."""
    from utils.email_client import test_email_connection
    return test_email_connection()

@app.post("/email/test-send/")
async def send_test_email(
    recipient: str, 
    subject: str = "Test Email from Your FastAPI Service",
    message: str = "Your Gmail integration is working correctly!",
    api_key: str = Depends(get_api_key)
):
    """Send a test email to verify everything works."""
    try:
        result = send_email(
            recipient=recipient,
            subject=subject,
            body=f"<h2>Success!</h2><p>{message}</p>",
            is_html=True
        )
        return result
    except Exception as e:
        logger.error(f"Test email failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "message": "Email FastAPI Server",
        "version": "2.0.0",
        "description": "Simplified email API with filename lists and MinIO integration",
        "endpoints": {
            "send_email": "/email/send/",
            "template_email": "/email/template/",
            "test_connection": "/email/test-connection/",
            "test_send": "/email/test-send/"
        },
        "features": [
            "Send plain text and HTML emails",
            "MinIO presigned URL integration",
            "Template-based emails",
            "File list references (no file uploads)"
        ]
    }

@app.get("/email/debug-templates/", dependencies=[Depends(get_api_key)])
async def debug_templates():
    """Debug endpoint to check template system."""
    import os
    from jinja2 import Environment, FileSystemLoader
    
    templates_dir = 'templates'
    
    debug_info = {
        "templates_directory_exists": os.path.exists(templates_dir),
        "current_working_directory": os.getcwd(),
        "templates_directory_path": os.path.abspath(templates_dir) if os.path.exists(templates_dir) else "Does not exist"
    }
    
    if os.path.exists(templates_dir):
        try:
            files_in_templates = os.listdir(templates_dir)
            debug_info["files_in_templates_directory"] = files_in_templates
            
            env = Environment(loader=FileSystemLoader(templates_dir))
            available_templates = env.list_templates()
            debug_info["jinja2_available_templates"] = available_templates
            
            # Try to render a simple test
            if "test.html" in available_templates:
                template = env.get_template("test.html")
                rendered = template.render(recipient_name="TestUser", message="Debug test")
                debug_info["test_template_render"] = "SUCCESS"
                debug_info["test_template_output"] = rendered[:200] + "..." if len(rendered) > 200 else rendered
            else:
                debug_info["test_template_render"] = "test.html not found"
                
        except Exception as e:
            debug_info["template_error"] = str(e)
    else:
        debug_info["error"] = f"Templates directory '{templates_dir}' does not exist"
    
    return debug_info

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "email-api"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
