Here is a comprehensive README that documents all API servers in your Student Application Pipeline project. This README includes the main features, all API routes, and the expected input/output for each service, based on the information from the individual service READMEs.

---

# Student Application Pipeline – API Documentation

This project is a modular system for managing student internship applications, including document validation, database and file management, email polling, and outgoing communications. Each service runs as a FastAPI server with its own endpoints and responsibilities.

---

## Table of Contents

1. [AI Document Validation Server](#ai-document-validation-server)
2. [Database and File Management API Server](#database-and-file-management-api-server)
3. [Email Polling API](#email-polling-api)
4. [Outgoing Email API](#outgoing-email-api)

---

## AI Document Validation Server

**Location:** `servers/ai/`  
**Port:** `8005`

### Features

- Validates resumes, cover letters, letters of recommendation, and marksheets using Gemini AI.
- Extracts text from PDFs (direct or AI-based for scanned docs).
- Checks academic marks, skills, project experience, and document authenticity.

### Endpoints

#### `POST /validate`

- **Description:** Validates all required documents in a single request.
- **Input:** Multipart form-data with the following files:
  - Resume/Cover Letter (PDF)
  - Letter of Recommendation (PDF)
  - Class 10 Marksheet (PDF)
  - Class 12 Marksheet (PDF)
  - College Marksheets (PDF)
- **Output (Success):**
  ```json
  {
    "valid": true,
    "status": "accepted",
    "summary": "Detailed summary of validation",
    "invalid_documents": [],
    "total_invalid_documents": 0,
    "rejection_reasons": [],
    "validation_details": {
      "resume_cover_letter": {},
      "letter_of_recommendation": {},
      "marksheets_backlog_check": {}
    },
    "applicant_profile": {
      "skills_analysis": {}
    }
  }
  ```
- **Output (Error):**
  ```json
  {
    "error": "Error message",
    "message": "User-friendly error message"
  }
  ```

#### `GET /health`

- **Description:** Returns server health status and timestamp.
- **Output:**
  ```json
  {
    "status": "ok",
    "timestamp": "2024-06-XXTXX:XX:XX"
  }
  ```

---

## Database and File Management API Server

**Location:** `servers/db/`  
**Port:** `8000`

### Features

- Manages student and application records in SQLite.
- Handles file storage and retrieval via MinIO.
- API key authentication for all routes except health.

### Endpoints

#### Student Management

- `POST /db/student/create`  
  **Input:**

  ```json
  {
    "student_id": "string",
    "student_name": "string",
    "student_email": "string",
    "student_phone": "string",
    "student_status": "string" // optional, defaults to "active"
  }
  ```

  **Output:**

  ```json
  { "message": "Student created", "data": { ... } }
  ```

- `GET /db/student/get?student_id=...`  
  **Output:**

  ```json
  { "message": "Student found", "data": { ... } }
  ```

- `GET /db/student/get-all`  
  **Output:**

  ```json
  { "message": "All students", "data": [ ... ] }
  ```

- `PUT /db/student/update`  
  **Input:**

  ```json
  {
    "student_id": "string",
    "student_name": "string",
    "student_email": "string",
    "student_phone": "string",
    "student_status": "string"
  }
  ```

  **Output:**

  ```json
  { "message": "Student updated", "data": { ... } }
  ```

- `DELETE /db/student/delete?student_id=...`  
  **Output:**

  ```json
  { "message": "Student deleted", "data": { ... } }
  ```

- `PATCH /db/student/update-status`  
  **Input:**

  ```json
  { "student_id": "string", "new_status": "string" }
  ```

  **Output:**

  ```json
  { "message": "Status updated", "data": { ... } }
  ```

- `PATCH /db/student/update-contact`  
  **Input:**

  ```json
  { "student_id": "string", "email": "string", "phone": "string" }
  ```

  **Output:**

  ```json
  { "message": "Contact updated", "data": { ... } }
  ```

- `GET /db/student/get-by-status?status=...`  
  **Output:**
  ```json
  { "message": "Students by status", "data": [ ... ] }
  ```

#### Application Management

- `POST /db/application/create`  
  **Input:**

  ```json
  {
    "student_id": "string",
    "application_id": "string",
    "application_status": "string",
    "intern_project": "string",
    "intern_project_start_date": "string",
    "intern_project_end_date": "string"
  }
  ```

  **Output:**

  ```json
  { "message": "Application created", "data": { ... } }
  ```

- `GET /db/application/get?application_id=...`  
  **Output:**

  ```json
  { "message": "Application found", "data": { ... } }
  ```

- `GET /db/application/get-all`  
  **Output:**

  ```json
  { "message": "All applications", "data": [ ... ] }
  ```

- `PUT /db/application/update`  
  **Input:**

  ```json
  {
    "application_id": "string",
    "student_id": "string",
    "application_status": "string",
    "intern_project": "string",
    "intern_project_start_date": "string",
    "intern_project_end_date": "string"
  }
  ```

  **Output:**

  ```json
  { "message": "Application updated", "data": { ... } }
  ```

- `DELETE /db/application/delete?application_id=...`  
  **Output:**

  ```json
  { "message": "Application deleted", "data": { ... } }
  ```

- `PATCH /db/application/update-status`  
  **Input:**

  ```json
  { "application_id": "string", "new_status": "string" }
  ```

  **Output:**

  ```json
  { "message": "Status updated", "data": { ... } }
  ```

- `PATCH /db/application/update-project`  
  **Input:**

  ```json
  { "application_id": "string", "project": "string" }
  ```

  **Output:**

  ```json
  { "message": "Project updated", "data": { ... } }
  ```

- `PATCH /db/application/update-dates`  
  **Input:**

  ```json
  { "application_id": "string", "start_date": "string", "end_date": "string" }
  ```

  **Output:**

  ```json
  { "message": "Dates updated", "data": { ... } }
  ```

- `GET /db/application/get-by-status?status=...`  
  **Output:**
  ```json
  { "message": "Applications by status", "data": [ ... ] }
  ```

#### MinIO File Operations

- `POST /objects/upload/`  
  **Input:**

  ```json
  { "student_id": "string", "object_name": "string", "file_path": "string" }
  ```

  **Output:**

  ```json
  { "message": "File uploaded", "data": { ... } }
  ```

- `POST /objects/upload-with-email/`  
  **Input:**

  ```json
  {
    "student_id": "string",
    "object_name": "string",
    "file_path": "string",
    "recipient_email": "string"
  }
  ```

  **Output:**

  ```json
  { "message": "File uploaded and email sent", "data": { ... } }
  ```

- `POST /objects/download/`  
  **Input:**

  ```json
  { "student_id": "string", "object_name": "string", "file_path": "string" }
  ```

  **Output:**

  ```json
  { "message": "File downloaded", "data": { ... } }
  ```

- `GET /objects/{student_id}`  
  **Output:**

  ```json
  { "message": "Objects listed", "data": [ ... ] }
  ```

- `DELETE /objects/`  
  **Input:**

  ```json
  { "student_id": "string", "object_name": "string" }
  ```

  **Output:**

  ```json
  { "message": "Object deleted", "data": { ... } }
  ```

- `POST /objects/presigned-url/`  
  **Input:**

  ```json
  { "student_id": "string", "object_name": "string" }
  ```

  **Output:**

  ```json
  { "message": "Presigned URL generated", "data": { "url": "..." } }
  ```

- `GET /health`  
  **Output:**
  ```json
  { "status": "ok", "timestamp": "..." }
  ```

---

## Email Polling API

**Location:** `servers/emails/in/`  
**Port:** `8002`

### Features

- Polls IMAP inbox for application emails and attachments.
- Configurable keywords, folders, and deduplication.
- Attachment handling and storage.

### Endpoints

- `GET /`  
  **Output:**

  ```json
  { "status": "ok", "message": "Email Polling API running" }
  ```

- `GET /health`  
  **Output:**

  ```json
  { "status": "ok", "timestamp": "..." }
  ```

- `GET /config`  
  **Output:**

  ```json
  { "config": { ... } }
  ```

- `POST /config`  
  **Input:**

  ```json
  {
    "imap_server": "string",
    "username": "string",
    "password": "string",
    "folder": "string",
    "processed_folder": "string",
    "app_keywords": ["string"],
    "max_emails": "integer",
    "mark_as_read": "boolean",
    "move_processed": "boolean",
    "attachment_dir": "string",
    "timeout": "integer",
    "include_raw_email": "boolean"
  }
  ```

  **Output:**

  ```json
  { "message": "Config updated", "config": { ... } }
  ```

- `GET /poll`  
  **Output:**

  ```json
  {
    "total_emails": 10,
    "application_emails": 2,
    "processed_emails": 10,
    "moved_emails": 2,
    "emails": [
      /* EmailData objects */
    ],
    "processing_time": 1.23,
    "errors": []
  }
  ```

- `POST /poll/save`  
  **Output:**

  ```json
  { "message": "Polling started", "status": "processing" }
  ```

- `GET /application-emails`  
  **Output:**

  ```json
  {
    "emails": [
      /* Only application-related EmailData */
    ]
  }
  ```

- `GET /test-connection`  
  **Output:**

  ```json
  { "status": "ok", "folders": [ ... ] }
  ```

- `GET /folders`  
  **Output:**
  ```json
  { "folders": [ ... ], "current_folder": "...", "processed_folder": "..." }
  ```

---

## Outgoing Email API

**Location:** `servers/emails/out/`  
**Port:** `8001`

### Features

- Secure API key authentication.
- Send individual or template-based emails.
- MinIO presigned URL integration for attachments.
- HTML and plain text support.

### Endpoints

- `GET /`  
  **Output:**

  ```json
  { "status": "ok", "endpoints": [ ... ] }
  ```

- `GET /health`  
  **Output:**
  ```json
  { "status": "ok" }
  ```

#### Email Sending

- `POST /email/send/`  
  **Input:**
  ```json
  {
    "recipient": "string",
    "subject": "string",
    "body": "string",
    "is_html": true,
    "file_list": ["string"],
    "student_id": "string",
    "object_name": "string",
    "expires": 3600
  }
  ```
  **Output:**
  ```json
  { "message": "Email sent", "data": { ... } }
  ```

#### Template Emails

- `POST /email/template/application_received`  
  **Input:**

  ```json
  {
    "recipient": "string",
    "subject": "string",
    "student_name": "string",
    "application_id": "string",
    "student_id": "string"
  }
  ```

  **Output:**

  ```json
  { "message": "Template email sent", "data": { ... } }
  ```

- `POST /email/template/information_required`  
  **Input:**

  ```json
  {
    "recipient": "string",
    "subject": "string",
    "student_id": "string",
    "deadline_date": "string"
  }
  ```

  **Output:**

  ```json
  { "message": "Template email sent", "data": { ... } }
  ```

- `POST /email/template/application_validated`  
  **Input:**

  ```json
  {
    "recipient": "string",
    "subject": "string",
    "student_name": "string",
    "application_id": "string",
    "student_id": "string"
  }
  ```

  **Output:**

  ```json
  { "message": "Template email sent", "data": { ... } }
  ```

- `POST /email/template/validation_failed`  
  **Input:**
  ```json
  {
    "recipient": "string",
    "subject": "string",
    "student_id": "string",
    "object_name": "string",
    "expires": 3600,
    "template_data": {
      "student_name": "string",
      "message": "string",
      "issues": ["string"]
    },
    "file_list": ["string"]
  }
  ```
  **Output:**
  ```json
  { "message": "Template email sent", "data": { ... } }
  ```

#### Testing and Debugging

- `GET /email/test-connection/`  
  **Output:**

  ```json
  { "status": "ok", "message": "Connection successful" }
  ```

- `POST /email/test-send/`  
  **Query Parameters:**

  - recipient: string
  - subject: string (optional)
  - message: string (optional)
    **Output:**

  ```json
  { "message": "Test email sent", "data": { ... } }
  ```

- `GET /email/debug-templates/`  
  **Output:**
  ```json
  { "templates": [ ... ], "status": "ok" }
  ```

---

## Authentication

- **Database and File Management API** and **Outgoing Email API** require an `X-API-Key` header for all routes except health checks.
- See each service's `.env` or README for the required API key.

---

## Error Handling

All APIs return structured error responses with appropriate HTTP status codes and messages.

---

## Notes

- Each service runs independently and may require its own environment variables and dependencies.
- See each service's README for setup, environment, and running instructions.

---

This README provides a unified reference for all API endpoints, their features, and input/output formats for the Student Application Pipeline project. For further details, refer to the individual service READMEs.
