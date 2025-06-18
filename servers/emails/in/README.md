# Email Polling API

A FastAPI-based server for polling emails using IMAP with advanced folder management, application email detection, and attachment handling. This server provides endpoints for managing email configurations, polling emails, and processing application-related emails.

## Features

- IMAP email polling with folder management
- Application email detection using configurable keywords
- Automatic email processing and organization
- Attachment handling and storage
- Email deduplication using message hashing
- Background task processing
- Configurable email processing rules
- Health monitoring and connection testing
- Secure credential management

## Prerequisites

- Python 3.7+
- IMAP-enabled email account
- Required Python packages (install via pip):
  - fastapi
  - uvicorn
  - python-dotenv
  - pydantic
  - email

## Environment Variables

Create a `.env` file in the project directory with the following variables:

```env
IMAP_SERVER=imap.gmail.com
EMAIL_USERNAME=your_email@gmail.com
EMAIL_PASSWORD_IN=your_app_password
EMAIL_FOLDER=INBOX
PROCESSED_FOLDER=Processed
APP_KEYWORDS=application,apply,job,position,vacancy
MARK_AS_READ=False
MOVE_PROCESSED=True
ATTACHMENT_DIR=attachments
INCLUDE_RAW_EMAIL=False
```

## API Endpoints

### Health and Status

- **GET** `/`

  - Returns basic server status
  - No authentication required

- **GET** `/health`
  - Returns server health status and timestamp
  - No authentication required

### Configuration Management

- **GET** `/config`

  - Returns current email configuration
  - Response includes all settings (password masked)

- **POST** `/config`
  - Updates email configuration
  - Request body:
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

### Email Operations

- **GET** `/poll`

  - Polls emails and returns application emails
  - Response includes:
    - Total emails processed
    - Application emails found
    - Processing time
    - Email details with attachments

- **POST** `/poll/save`

  - Polls emails and saves results to JSON file
  - Runs in background
  - Returns processing status

- **GET** `/application-emails`
  - Returns only application-related emails
  - Filters based on configured keywords

### Connection and Folder Management

- **GET** `/test-connection`

  - Tests IMAP connection
  - Verifies folder configuration
  - Returns connection status and folder information

- **GET** `/folders`
  - Lists all available email folders
  - Shows current source and processed folders

## Email Processing Features

### Application Email Detection

- Configurable keywords for identifying application emails
- Searches in both subject and body
- Case-insensitive matching
- Regular expression support

### Attachment Handling

- Automatic attachment saving
- File deduplication
- Safe filename sanitization
- Base64 encoding for API responses
- File integrity verification using MD5 hashing

### Email Organization

- Automatic folder creation
- Email movement to processed folder
- Read/unread status management
- Email deduplication using message hashing

## Response Models

### EmailData

```json
{
  "id": "string",
  "subject": "string",
  "sender": "string",
  "recipient": "string",
  "date": "string",
  "body_text": "string",
  "body_html": "string",
  "is_application": "boolean",
  "keywords_found": ["string"],
  "attachments": [
    {
      "filename": "string",
      "content_type": "string",
      "path": "string",
      "size": "integer",
      "content_base64": "string",
      "file_hash": "string"
    }
  ],
  "raw_email_base64": "string",
  "processed_timestamp": "string",
  "email_hash": "string"
}
```

### EmailResponse

```json
{
  "total_emails": "integer",
  "application_emails": "integer",
  "processed_emails": "integer",
  "moved_emails": "integer",
  "emails": ["EmailData"],
  "processing_time": "float",
  "errors": ["string"]
}
```

## Running the Server

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Start the server:

```bash
python main.py
```

The server will start on `http://0.0.0.0:8002`

## Error Handling

The server implements comprehensive error handling:

- Connection errors
- Authentication failures
- File system errors
- Email processing errors
- Configuration validation

All errors are logged and returned with appropriate HTTP status codes:

- 400: Bad Request (e.g., missing credentials)
- 401: Unauthorized (e.g., IMAP authentication failed)
- 500: Internal Server Error

## Notes

- The server creates necessary directories for attachments and output files
- Email credentials can be configured via environment variables or API
- Processing is optimized for handling large numbers of emails
- All sensitive operations are logged for debugging
- The server supports both synchronous and asynchronous operations
