# MinIO FastAPI Server

A FastAPI-based server for managing student files in a MinIO bucket. This server provides endpoints for uploading, downloading, listing, and managing student documents with secure API key authentication.

## Features

- Secure API key authentication
- File upload and download functionality
- Presigned URL generation for secure file access
- Student-specific file organization
- Health check endpoint
- Email notification support (currently commented out)

## Prerequisites

- Python 3.7+
- MinIO server
- Required Python packages (install via pip):
  - fastapi
  - uvicorn
  - python-dotenv
  - minio

## Environment Variables

Create a `.env` file in the parent directory with the following variables:

```env
API_KEY=your-secret-api-key-123
BUCKET_NAME=applicationdocs
# Optional email configuration
# EMAIL_SENDER=your_email@gmail.com
# EMAIL_PASSWORD=your_app_password
```

## API Endpoints

### Health Check

- **GET** `/health`
- Returns server health status and timestamp
- No authentication required

### File Upload

- **POST** `/objects/upload/`
- Uploads a file to the student-files bucket
- Requires API key authentication
- Request body:
  ```json
  {
    "student_id": "string",
    "object_name": "string",
    "file_path": "string"
  }
  ```

### File Upload with Email

- **POST** `/objects/upload-with-email/`
- Uploads a file and generates a presigned URL
- Requires API key authentication
- Request body:
  ```json
  {
    "student_id": "string",
    "object_name": "string",
    "file_path": "string",
    "recipient_email": "string"
  }
  ```

### File Download

- **POST** `/objects/download/`
- Downloads a file from the student-files bucket
- Requires API key authentication
- Request body:
  ```json
  {
    "student_id": "string",
    "object_name": "string",
    "file_path": "string"
  }
  ```

### List Objects

- **GET** `/objects/{student_id}`
- Lists all objects for a specific student
- Requires API key authentication
- URL parameter: `student_id`

### Delete Object

- **DELETE** `/objects/`
- Deletes an object from the student-files bucket
- Requires API key authentication
- Request body:
  ```json
  {
    "student_id": "string",
    "object_name": "string"
  }
  ```

### Generate Presigned URL

- **POST** `/objects/presigned-url/`
- Generates a presigned URL for secure file access
- Requires API key authentication
- Request body:
  ```json
  {
    "student_id": "string",
    "object_name": "string"
  }
  ```

## Authentication

All endpoints (except health check) require API key authentication. Include the API key in the request header:

```
X-API-Key: your-secret-api-key-123
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

The server will start on `http://0.0.0.0:8000`

## Error Handling

The server returns appropriate HTTP status codes and error messages:

- 400: Bad Request (e.g., file path does not exist)
- 401: Unauthorized (invalid API key)
- 500: Internal Server Error

## Notes

- The email functionality is currently commented out but can be enabled by uncommenting the relevant code sections and configuring the email settings in the `.env` file.
- All file operations are performed within a single MinIO bucket, organized by student ID.
- Presigned URLs expire after 1 hour (3600 seconds) by default.
