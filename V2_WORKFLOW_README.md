# V2 Email Workflow Documentation

## Overview

The V2 Email Workflow is an enhanced version of the email processing system that implements a complete student application workflow with email notifications, AI validation, and review management.

## Workflow Steps

The V2 workflow follows this sequence:

```
1. Email Received by Poller
   ↓
2. Send "Application Received" Email
   ↓
3. Process Email & Attachments → Store to Database
   ↓
4. Validate Documents with AI (Parallel)
   ↓
5. Send Validation Result Email
   ↓ (if validation passes)
6. Mark for Review in validated.txt
```

## New V2 API Endpoints

All V2 endpoints are prefixed with `/v2/` to maintain compatibility with existing V1 routes.

### Core Workflow Endpoints

#### `POST /v2/process-email/`
Process a single email with the complete V2 workflow.

**Request Body:**
```json
{
  "email_data": {
    "id": "email_123",
    "subject": "Internship Application",
    "sender": "student@university.edu",
    "date": "2024-01-15T10:30:00",
    "body_text": "Application email content...",
    "is_application": true,
    "keywords_found": ["internship", "application"],
    "attachments": [
      {
        "filename": "MIT_John_Doe_ComputerScience.pdf",
        "content_type": "application/pdf",
        "path": "/path/to/file.pdf",
        "size": 256000
      }
    ],
    "processed_timestamp": "2024-01-15T10:30:00",
    "email_hash": "abc123"
  },
  "send_confirmation": true,
  "perform_validation": true
}
```

**Response:**
```json
{
  "email_id": "email_123",
  "student_id": "MIT_JOHN_DOE_COMPUTERSCIENCE",
  "workflow_stage": "completed",
  "application_received_sent": true,
  "documents_processed": true,
  "validation_completed": true,
  "validation_result": {
    "is_valid": true,
    "feedback": "All required documents are present...",
    "validation_details": {...}
  },
  "validation_email_sent": true,
  "marked_for_review": true,
  "errors": [],
  "processing_time": 2.45
}
```

#### `POST /v2/process-batch/`
Process multiple emails using the V2 workflow.

**Query Parameters:**
- `send_confirmation` (bool): Whether to send confirmation emails
- `perform_validation` (bool): Whether to perform AI validation

#### `GET /v2/poll-and-process/`
Poll emails from the email poller and process them automatically with V2 workflow.

**Query Parameters:**
- `send_confirmation` (bool): Whether to send confirmation emails
- `perform_validation` (bool): Whether to perform AI validation

### Management Endpoints

#### `GET /v2/workflow-status/{student_id}`
Get the workflow status for a specific student.

**Response:**
```json
{
  "student_id": "MIT_JOHN_DOE_COMPUTERSCIENCE",
  "found_in_review": true,
  "review_entry": {
    "timestamp": "2024-01-15T10:35:00",
    "student_id": "MIT_JOHN_DOE_COMPUTERSCIENCE",
    "student_email": "john.doe@mit.edu",
    "validation_status": "passed",
    "feedback": "All documents validated successfully",
    "validation_details": {...}
  },
  "workflow_version": "v2"
}
```

#### `GET /v2/review-queue/`
Get all applications in the review queue.

**Response:**
```json
{
  "total_applications": 5,
  "applications": [
    {
      "timestamp": "2024-01-15T10:35:00",
      "student_id": "MIT_JOHN_DOE_COMPUTERSCIENCE",
      "student_email": "john.doe@mit.edu",
      "validation_status": "passed",
      "feedback": "All documents validated successfully"
    }
  ],
  "workflow_version": "v2"
}
```

## Email Templates Used

The V2 workflow uses these email templates from the `emails/out` server:

1. **Application Received** (`/email/template/application_received`)
   - Sent immediately when email is received
   - Confirms application submission

2. **Application Validated** (`/email/template/application_validated`)
   - Sent when validation passes
   - Notifies student of successful validation

3. **Validation Failed** (`/email/template/validation_failed`)
   - Sent when validation fails
   - Includes specific issues found

## AI Validation

The V2 workflow integrates with the AI server for document validation:

- **Document Type Detection**: Resume, Cover Letter, Transcripts, LOR
- **Content Validation**: Checks for required information
- **Basic Requirements Check**: Ensures minimum documents are present

### Validation Criteria

- **Resume/CV**: Must be present
- **Academic Transcripts**: Must be present
- **Letter of Recommendation**: Recommended
- **Minimum 3 documents** required for validation to pass

## Review Management

### validated.txt File

All processed applications are logged to `validated.txt` with entries like:

```json
{
  "timestamp": "2024-01-15T10:35:00",
  "student_id": "MIT_JOHN_DOE_COMPUTERSCIENCE", 
  "student_email": "john.doe@mit.edu",
  "validation_status": "passed",
  "feedback": "All required documents are present and appear to be in correct format.",
  "validation_details": {
    "documents_found": {
      "resume": true,
      "marksheet": true,
      "letter_of_recommendation": true
    },
    "total_attachments": 3
  }
}
```

## Student ID Extraction

The system extracts student IDs from attachment filenames using the pattern:
`{college}_{name}_{branch}.pdf`

Example: `MIT_John_Doe_ComputerScience.pdf` → `MIT_JOHN_DOE_COMPUTERSCIENCE`

## Configuration

### Environment Variables

Add these to your `.env` file:

```bash
# Existing variables
API_KEY=your-secret-api-key-123
DB_SERVER_URL=http://localhost:8000
EMAIL_POLLER_URL=http://localhost:8002
MINIO_SERVER_URL=http://localhost:8000

# New V2 variables
EMAIL_OUT_SERVER_URL=http://localhost:8001
AI_SERVER_URL=http://localhost:8005
```

### Required Services

For V2 workflow to work, ensure these services are running:

1. **Manager Server** (port 8004) - Main orchestrator
2. **DB Server** (port 8000) - Document storage
3. **Email Poller** (port 8002) - Email intake
4. **Email Out Server** (port 8001) - Email notifications
5. **AI Server** (port 8005) - Document validation

## Testing

Use the provided test script:

```bash
python test_v2_workflow.py
```

This will test:
- Manager server connectivity
- V2 workflow processing
- Review queue functionality

## Migration from V1

V1 endpoints remain fully functional:
- `/process-email/` 
- `/process-batch/`
- `/poll-and-process/`

V2 adds the `/v2/` prefix for new functionality while maintaining backward compatibility.

## Error Handling

The V2 workflow includes robust error handling:
- Email notification failures don't stop the workflow
- Validation failures still mark applications for review
- Partial failures are tracked in the response
- All errors are logged for debugging

## Monitoring

Monitor the workflow through:
- Application logs with detailed step-by-step progress
- `validated.txt` file for review queue status
- API responses with processing time and error details
- Review queue endpoint for application status

## Example Usage

### Basic V2 Processing

```python
import requests

response = requests.post(
    "http://localhost:8004/v2/process-email/",
    headers={"X-API-Key": "your-secret-api-key-123"},
    json={
        "email_data": {...},  # Email data from poller
        "send_confirmation": True,
        "perform_validation": True
    }
)

result = response.json()
print(f"Student {result['student_id']} processed: {result['workflow_stage']}")
```

### Automated Processing

```python
# Poll and process all new emails
response = requests.get(
    "http://localhost:8004/v2/poll-and-process/",
    headers={"X-API-Key": "your-secret-api-key-123"},
    params={
        "send_confirmation": True,
        "perform_validation": True
    }
)
```

### Check Review Queue

```python
response = requests.get(
    "http://localhost:8004/v2/review-queue/",
    headers={"X-API-Key": "your-secret-api-key-123"}
)

queue = response.json()
print(f"Applications waiting for review: {queue['total_applications']}")
```