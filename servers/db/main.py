from fastapi import FastAPI, Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from utils.minio_client import (
    get_minio_client, upload_file, download_file, list_objects, delete_object, generate_presigned_url
)
from utils.models import FileUpload, FileDownload, ObjectDelete, PresignedUrl, FileUploadWithEmail
from dotenv import load_dotenv
from datetime import datetime, date
from pathlib import Path
import sqlite3
import os
from models import Application, Student

load_dotenv(dotenv_path=Path(__file__).parent.parent / '.env')

# Models

#Uncomment the following lines to enable email functionality
# import smtplib



app = FastAPI(title="Database FastAPI Server", description="API to manage student and application details")

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

# Initialize SQLite DB
conn = sqlite3.connect('application.db')
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS applications (id INTEGER PRIMARY KEY AUTOINCREMENT, student_id TEXT, application_id TEXT, application_status TEXT, intern_project TEXT, intern_project_start_date TEXT, intern_project_end_date TEXT, application_status TEXT)''')
cursor.execute(" CREATE TABLE IF NOT EXISTS STUDENT_DETAILS (id INTEGER PRIMARY KEY AUTOINCREMENT, student_id TEXT, student_name TEXT, student_email TEXT, student_phone TEXT, student_status TEXT, )")
conn.commit()

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

@app.post('/db/student/create', response_model=dict, dependencies=[Depends(get_api_key)])
async def create_student(student: Student):
    """Create a new student in the database."""
    try:
        cursor.execute("INSERT INTO students (student_id, student_name, student_email, student_phone, student_status) VALUES (?, ?, ?, ?, ?)", (student.student_id, student.student_name, student.student_email, student.student_phone, student.student_status))
        conn.commit()
        return {"message": "Student created successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get('/db/student/get', response_model=dict, dependencies=[Depends(get_api_key)])
async def get_student(student_id: str):
    """Get a student from the database."""
    try:
        cursor.execute("SELECT * FROM students WHERE student_id = ?", (student_id,))
        student = cursor.fetchone()
        if not student:
            raise HTTPException(status_code=404, detail="Student not found")
        return {"message": "Student fetched successfully", "student": student}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put('/db/student/update', response_model=dict, dependencies=[Depends(get_api_key)])
async def update_student(student: Student):
    """Update a student in the database."""
    try:
        cursor.execute("UPDATE students SET student_name = ?, student_email = ?, student_phone = ?, student_status = ? WHERE student_id = ?", (student.student_name, student.student_email, student.student_phone, student.student_status, student.student_id))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Student not found")
        conn.commit()
        return {"message": "Student updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete('/db/student/delete', response_model=dict, dependencies=[Depends(get_api_key)])
async def delete_student(student_id: str):
    """Delete a student from the database."""
    try:
        cursor.execute("DELETE FROM students WHERE student_id = ?", (student_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Student not found")
        conn.commit()
        return {"message": "Student deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get('/db/student/get-all', response_model=dict, dependencies=[Depends(get_api_key)])
async def get_all_students():
    """Get all students from the database."""
    try:
        cursor.execute("SELECT * FROM students")
        students = cursor.fetchall()
        return {"message": "All students fetched successfully", "students": students}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post('/db/application/create', response_model=dict, dependencies=[Depends(get_api_key)])
async def create_application(application: Application):
    """Create a new application in the database."""
    try:
        cursor.execute("INSERT INTO applications (student_id, application_id, application_status, intern_project, intern_project_start_date, intern_project_end_date) VALUES (?, ?, ?, ?, ?, ?)", 
            (application.student_id, application.application_id, application.application_status, 
             application.intern_project, application.intern_project_start_date, application.intern_project_end_date))
        conn.commit()
        return {"message": "Application created successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get('/db/application/get', response_model=dict, dependencies=[Depends(get_api_key)])
async def get_application(application_id: str):
    """Get an application from the database."""
    try:
        cursor.execute("SELECT * FROM applications WHERE application_id = ?", (application_id,))
        application = cursor.fetchone()
        if not application:
            raise HTTPException(status_code=404, detail="Application not found")
        return {"message": "Application fetched successfully", "application": application}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put('/db/application/update', response_model=dict, dependencies=[Depends(get_api_key)])
async def update_application(application: Application):
    """Update an application in the database."""
    try:
        cursor.execute("""
            UPDATE applications 
            SET student_id = ?, 
                application_status = ?, 
                intern_project = ?, 
                intern_project_start_date = ?, 
                intern_project_end_date = ? 
            WHERE application_id = ?
        """, (
            application.student_id,
            application.application_status,
            application.intern_project,
            application.intern_project_start_date,
            application.intern_project_end_date,
            application.application_id
        ))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Application not found")
        conn.commit()
        return {"message": "Application updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete('/db/application/delete', response_model=dict, dependencies=[Depends(get_api_key)])
async def delete_application(application_id: str):
    """Delete an application from the database."""
    try:
        cursor.execute("DELETE FROM applications WHERE application_id = ?", (application_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Application not found")
        conn.commit()
        return {"message": "Application deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get('/db/application/get-all', response_model=dict, dependencies=[Depends(get_api_key)])
async def get_all_applications():
    """Get all applications from the database."""
    try:
        cursor.execute("SELECT * FROM applications")
        applications = cursor.fetchall()
        return {"message": "All applications fetched successfully", "applications": applications}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.patch('/db/application/update-status', response_model=dict, dependencies=[Depends(get_api_key)])
async def update_application_status(application_id: str, new_status: str):
    """Update only the status of an application."""
    try:
        cursor.execute("UPDATE applications SET application_status = ? WHERE application_id = ?", 
            (new_status, application_id))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Application not found")
        conn.commit()
        return {"message": "Application status updated successfully", "new_status": new_status}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.patch('/db/application/update-project', response_model=dict, dependencies=[Depends(get_api_key)])
async def update_application_project(application_id: str, project: str):
    """Update only the project details of an application."""
    try:
        cursor.execute("UPDATE applications SET intern_project = ? WHERE application_id = ?", 
            (project, application_id))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Application not found")
        conn.commit()
        return {"message": "Application project updated successfully", "new_project": project}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.patch('/db/application/update-dates', response_model=dict, dependencies=[Depends(get_api_key)])
async def update_application_dates(application_id: str, start_date: date, end_date: date):
    """Update only the project dates of an application."""
    try:
        cursor.execute("""
            UPDATE applications 
            SET intern_project_start_date = ?, 
                intern_project_end_date = ? 
            WHERE application_id = ?
        """, (start_date, end_date, application_id))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Application not found")
        conn.commit()
        return {
            "message": "Application dates updated successfully",
            "new_start_date": start_date,
            "new_end_date": end_date
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.patch('/db/student/update-status', response_model=dict, dependencies=[Depends(get_api_key)])
async def update_student_status(student_id: str, new_status: str):
    """Update only the status of a student."""
    try:
        cursor.execute("UPDATE students SET student_status = ? WHERE student_id = ?", 
            (new_status, student_id))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Student not found")
        conn.commit()
        return {"message": "Student status updated successfully", "new_status": new_status}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.patch('/db/student/update-contact', response_model=dict, dependencies=[Depends(get_api_key)])
async def update_student_contact(student_id: str, email: str = None, phone: str = None):
    """Update only the contact information of a student."""
    try:
        if email is None and phone is None:
            raise HTTPException(status_code=400, detail="At least one contact field must be provided")
        
        update_fields = []
        params = []
        if email is not None:
            update_fields.append("student_email = ?")
            params.append(email)
        if phone is not None:
            update_fields.append("student_phone = ?")
            params.append(phone)
        
        params.append(student_id)
        query = f"UPDATE students SET {', '.join(update_fields)} WHERE student_id = ?"
        
        cursor.execute(query, params)
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Student not found")
        conn.commit()
        return {
            "message": "Student contact information updated successfully",
            "updated_fields": {
                "email": email,
                "phone": phone
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get('/db/application/get-by-status', response_model=dict, dependencies=[Depends(get_api_key)])
async def get_applications_by_status(status: str):
    """Get all applications with a specific status."""
    try:
        cursor.execute("SELECT * FROM applications WHERE application_status = ?", (status,))
        applications = cursor.fetchall()
        return {
            "message": f"Applications with status '{status}' fetched successfully",
            "applications": applications
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get('/db/student/get-by-status', response_model=dict, dependencies=[Depends(get_api_key)])
async def get_students_by_status(status: str):
    """Get all students with a specific status."""
    try:
        cursor.execute("SELECT * FROM students WHERE student_status = ?", (status,))
        students = cursor.fetchall()
        return {
            "message": f"Students with status '{status}' fetched successfully",
            "students": students
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)