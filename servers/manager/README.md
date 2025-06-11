# Email Processing Manager API

The Email Processing Manager API orchestrates the complete email processing workflow by coordinating between the Email Polling Service, Database API, and MinIO Storage Service.

## 🏗️ **Architecture Overview**

```
Email Poller → Manager API → Database API
               ↓
            MinIO Storage
```

## 📋 **Features**

- **Intelligent Student ID Extraction** - Multiple methods to identify students
- **Automatic File Upload** - Uploads attachments to MinIO with proper organization
- **Database Integration** - Saves email metadata and processing results
- **Batch Processing** - Handles multiple emails efficiently
- **Error Handling** - Comprehensive error tracking and recovery
- **Background Processing** - Non-blocking email processing
- **Health Monitoring** - Monitors all connected services

## 🚀 **Quick Start**

### **1. Installation**

```bash
pip install fastapi uvicorn httpx pydantic python-dotenv
```

### **2. Configuration**

Update your `.env` file:

```bash
# API Authentication
API_KEY='your-secret-api-key-123'

# Service URLs
DB_SERVER_URL='http://localhost:8000'
EMAIL_POLLER_URL='http://localhost:8002'
MINIO_SERVER_URL='http://localhost:8000'
EMAIL_MANAGER_URL='http://localhost:8003'
```

### **3. Run the Service**

```bash
python email_manager_api.py
```

The API will be available at: `http://localhost:8003`

## 📡 **API Endpoints**

### **Health & Status**

#### `GET /`

Basic service information

```json
{
  "status": "running",
  "message": "Email Processing Manager API is running",
  "services": {
    "db_server": "http://localhost:8000",
    "email_poller": "http://localhost:8002",
    "minio_server": "http://localhost:8000"
  }
}
```

#### `GET /health`

Health check for all connected services

```json
{
  "manager": "healthy",
  "timestamp": "2025-06-11T10:30:00",
  "services": {
    "db_server": { "status": "healthy", "response_time": 0.15 },
    "email_poller": { "status": "healthy", "response_time": 0.23 },
    "minio_server": { "status": "healthy", "response_time": 0.18 }
  }
}
```

### **Email Processing**

#### `POST /process-email/`

Process a single email

```bash
curl -X POST "http://localhost:8003/process-email/" \
  -H "X-API-Key: your-secret-api-key-123" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "2",
    "subject": "Application for Internship",
    "sender": "student@college.edu",
    "body_text": "My name is John Doe, student ID: 20CS1234...",
    "is_application": true,
    "attachments": [...],
    ...
  }'
```

**Response:**

```json
{
  "email_id": "2",
  "student_id": "20CS1234",
  "status": "completed",
  "database_saved": true,
  "attachments_uploaded": 3,
  "total_attachments": 3,
  "errors": [],
  "minio_files": [
    "20CS1234/resume.pdf",
    "20CS1234/transcript.pdf",
    "20CS1234/cover_letter.pdf"
  ]
}
```

#### `POST /process-batch/`

Process multiple emails at once

```bash
curl -X POST "http://localhost:8003/process-batch/" \
  -H "X-API-Key: your-secret-api-key-123" \
  -H "Content-Type: application/json" \
  -d '{
    "total_emails": 5,
    "application_emails": 3,
    "emails": [...]
  }'
```

**Response:**

```json
{
  "total_processed": 5,
  "successful": 4,
  "failed": 1,
  "results": [...],
  "processing_time": 12.5,
  "errors": []
}
```

#### `GET /poll-and-process/`

Automatically poll emails and process them

```bash
curl -X GET "http://localhost:8003/poll-and-process/" \
  -H "X-API-Key: your-secret-api-key-123"
```

This endpoint:

1. Calls the Email Poller API to get new emails
2. Processes all application emails
3. Returns complete processing results

#### `POST /process-background/`

Process emails in the background

```bash
curl -X POST "http://localhost:8003/process-background/" \
  -H "X-API-Key: your-secret-api-key-123" \
  -H "Content-Type: application/json" \
  -d '{...email_batch...}'
```

Results are saved to `processing_results/processing_result_YYYYMMDD_HHMMSS.json`

### **Utilities**

#### `GET /extract-student-id/`

Test student ID extraction

```bash
curl -X GET "http://localhost:8003/extract-student-id/?email_text=My%20name%20is%20John%20Doe%20student%20ID%2020CS1234" \
  -H "X-API-Key: your-secret-api-key-123"
```

## 🧠 **Student ID Extraction Methods**

The Manager API uses multiple intelligent methods to extract student IDs:

### **1. Pattern Matching (Confidence: 0.8)**

Searches for common student ID patterns:

- `20CS1234`, `22AI5678` (Year + Department + Number)
- `CSE2022001`, `AIML20220045` (Department + Year + Number)
- `2022CS001`, `2023AI045` (Year + Department + Number)
- `Roll No: ABC123`, `Student ID: XYZ789`

### **2. Email Username (Confidence: 0.6)**

Extracts potential ID from email address:

- `john.doe2022@college.edu` → `2022`
- `20cs1234@university.ac.in` → `20cs1234`

### **3. Name-Based Generation (Confidence: 0.4)**

Generates ID from extracted name:

- "My name is John Doe" → `JOHN_DOE_202506`

### **4. Hash-Based Fallback (Confidence: 0.2)**

Uses email hash as last resort:

- Email hash `c8b0c628...` → `STU_c8b0c628_0611`

## 📁 **File Organization**

### **MinIO Storage Structure**

```
applicationdocs/
├── 20CS1234/
│   ├── resume.pdf
│   ├── transcript.pdf
│   └── cover_letter.pdf
├── 22AI5678/
│   ├── cv.pdf
│   └── certificates.pdf
└── JOHN_DOE_202506/
    └── application.pdf
```

### **Local Processing Results**

```
processing_results/
├── processing_result_20250611_103000.json
├── processing_result_20250611_114500.json
└── processing_result_20250611_120000.json
```

## 🔄 **Complete Workflow Example**

### **1. Automatic Email Processing**

```bash
# Poll and process all new emails automatically
curl -X GET "http://localhost:8003/poll-and-process/" \
  -H "X-API-Key: your-secret-api-key-123"
```

### **2. Manual Email Processing**

```bash
# First, get emails from poller
curl -X GET "http://localhost:8002/application-emails" \
  -H "X-API-Key: your-secret-api-key-123" > emails.json

# Then process them
curl -X POST "http://localhost:8003/process-batch/" \
  -H "X-API-Key: your-secret-api-key-123" \
  -H "Content-Type: application/json" \
  -d @emails.json
```

### **3. Background Processing**

```bash
# For large batches, use background processing
curl -X POST "http://localhost:8003/process-background/" \
  -H "X-API-Key: your-secret-api-key-123" \
  -H "Content-Type: application/json" \
  -d @large_email_batch.json
```

## 🔍 **Monitoring & Debugging**

### **Check Service Health**

```bash
curl -X GET "http://localhost:8003/health" \
  -H "X-API-Key: your-secret-api-key-123"
```

### **Test Student ID Extraction**

```bash
curl -X GET "http://localhost:8003/extract-student-id/?email_text=Your%20email%20text%20here" \
  -H "X-API-Key: your-secret-api-key-123"
```

### **View Processing Results**

```bash
cat processing_results/processing_result_20250611_103000.json | jq '.'
```

## 🚨 **Error Handling**

The Manager API provides comprehensive error handling:

### **Processing Status Types**

- `completed` - All operations successful
- `partial` - Some operations failed
- `failed` - All operations failed
- `processing` - Currently in progress

### **Common Error Scenarios**

1. **Missing Attachments** - File not found at specified path
2. **MinIO Upload Failures** - Network or storage issues
3. **Database Save Failures** - Database connection or validation errors
4. **Service Unavailable** - Connected services not responding

### **Error Response Example**

```json
{
  "email_id": "123",
  "student_id": "STU_ABC_0611",
  "status": "partial",
  "database_saved": true,
  "attachments_uploaded": 2,
  "total_attachments": 3,
  "errors": [
    "Failed to upload large_file.zip: File size too large",
    "Attachment file not found: /missing/path.pdf"
  ],
  "minio_files": ["STU_ABC_0611/resume.pdf", "STU_ABC_0611/transcript.pdf"]
}
```

## ⚙️ **Configuration Options**

### **Concurrency Control**

The API processes emails concurrently but limits concurrency to avoid overwhelming backend services:

```python
semaphore = asyncio.Semaphore(3)  # Max 3 concurrent email processing
```

### **Timeout Settings**

```python
async with httpx.AsyncClient(timeout=60.0) as client:  # MinIO uploads
async with httpx.AsyncClient(timeout=30.0) as client:  # Database saves
async with httpx.AsyncClient(timeout=10.0) as client:  # Health checks
```

## 📊 **Performance Considerations**

- **Batch Processing**: Processes multiple emails concurrently
- **Semaphore Control**: Limits concurrent operations to prevent overload
- **Background Tasks**: Non-blocking processing for large batches
- **Error Recovery**: Continues processing even if individual emails fail
- **Resource Management**: Proper connection pooling and cleanup

## 🔐 **Security**

- **API Key Authentication**: All endpoints require valid API key
- **Input Validation**: Pydantic models validate all input data
- **File Path Safety**: Validates file paths before operations
- **Error Sanitization**: Prevents sensitive information leakage in errors

This Manager API provides a robust, scalable solution for processing application emails and coordinating between multiple services in your application processing system!
