# Outgoing Email API

A FastAPI-based server for sending outgoing communications with MinIO integration. This server provides endpoints for sending individual emails, template-based emails, and test communications with secure API key authentication.

## Features

- Secure API key authentication
- Individual email sending
- Template-based email system
- MinIO presigned URL integration
- HTML email support
- File attachment handling
- Email connection testing
- Template debugging tools
- Health monitoring

## Prerequisites

- Python 3.7+
- SMTP-enabled email account
- MinIO server
- Required Python packages (install via pip):
  - fastapi
  - uvicorn
  - python-dotenv
  - jinja2
  - httpx

## Environment Variables

Create a `.env` file in the project directory with the following variables:

```env
API_KEY=your-secret-api-key-123
MINIO_SERVER_URL=http://localhost:8000
EMAIL_USERNAME=your_email@gmail.com
EMAIL_PASSWORD_OUT=your_app_password
```

## API Endpoints

### Health and Status

- **GET** `/`

  - Returns API information and available endpoints
  - No authentication required

- **GET** `/health`
  - Returns server health status
  - No authentication required

### Email Operations

#### Send Individual Email

- **POST** `/email/send/`
  - Sends a single email with optional MinIO presigned URL
  - Requires API key authentication
  - Request body:
  ```json
  {
    "recipient": "string",
    "subject": "string",
    "body": "string",
    "is_html": "boolean",
    "file_list": ["string"],
    "student_id": "string",
    "object_name": "string",
    "expires": "integer"
  }
  ```

#### Template Emails

##### Application Received

- **POST** `/email/template/application_received`
  - Sends application received notification
  - Requires API key authentication
  - Request body:
  ```json
  {
    "recipient": "string",
    "subject": "string",
    "student_name": "string",
    "application_id": "string",
    "student_id": "string"
  }
  ```

##### Information Required

- **POST** `/email/template/information_required`

  - Sends information required notification
  - Requires API key authentication
  - Request body:

  ```json
  {
    "recipient": "string",
    "subject": "string",
    "student_id": "string",
    "deadline_date": "string"
  }
  ```

  The deadline date is set to 7 days from the date of the email.

##### Application Validated

- **POST** `/email/template/application_validated`
  - Sends application validation confirmation
  - Requires API key authentication
  - Request body:
  ```json
  {
    "recipient": "string",
    "subject": "string",
    "student_name": "string",
    "application_id": "string",
    "student_id": "string"
  }
  ```

##### Validation Failed

- **POST** `/email/template/validation_failed`
  - Sends validation failure notification
  - Requires API key authentication
  - Request body:
  ```json
  {
    "recipient": "string",
    "subject": "string",
    "student_id": "string",
    "object_name": "string",
    "expires": "integer",
    "template_data": {
      "student_name": "string",
      "message": "string",
      "issues": ["string"]
    },
    "file_list": ["string"]
  }
  ```

### Testing and Debugging

#### Connection Testing

- **GET** `/email/test-connection/`
  - Tests email connection configuration
  - Requires API key authentication

#### Test Email

- **POST** `/email/test-send/`
  - Sends a test email
  - Requires API key authentication
  - Query parameters:
    - recipient: string
    - subject: string (optional)
    - message: string (optional)

#### Template Debugging

- **GET** `/email/debug-templates/`
  - Checks template system configuration
  - Requires API key authentication
  - Returns template directory status and available templates

## Authentication

All endpoints (except root and health check) require API key authentication. Include the API key in the request header:

```
X-API-Key: your-secret-api-key-123
```

## Template System

The server uses Jinja2 for template rendering. Templates should be placed in the `templates` directory:

- `application_received.html`
- `application_validated.html`
- `validation_failed.html`

Template variables are passed through the API requests and rendered before sending.

## MinIO Integration

The server integrates with MinIO for generating presigned URLs:

- URLs are generated for file access
- Default expiration time is 3600 seconds (1 hour)
- URLs are included in email bodies when requested

## Running the Server

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Start the server:

```bash
python main.py
```

The server will start on `http://0.0.0.0:8001`

## Error Handling

The server implements comprehensive error handling:

- Authentication failures
- Email sending errors
- Template rendering errors
- MinIO integration errors

All errors are logged and returned with appropriate HTTP status codes:

- 401: Unauthorized (invalid API key)
- 500: Internal Server Error

## Notes

- The server supports both plain text and HTML emails
- File attachments are handled through file lists (no direct uploads)
- Template emails are pre-formatted for specific use cases
- All email operations are logged for debugging
- The server includes built-in testing and debugging tools
