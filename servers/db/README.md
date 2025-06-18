# Database and File Management API Server

This FastAPI server manages both student/application details in a SQLite database and student files in a MinIO bucket.

## API Routes

### Database Routes

#### Student Routes

##### Create Student

- **POST** `/db/student/create`
- Creates a new student record
- Required fields: `student_id`, `student_name`, `student_email`, `student_phone`
- Optional fields: `student_status` (defaults to "active")

##### Get Student

- **GET** `/db/student/get`
- Retrieves a single student by ID
- Query parameter: `student_id`

##### Get All Students

- **GET** `/db/student/get-all`
- Retrieves all student records

##### Update Student

- **PUT** `/db/student/update`
- Updates all student information
- Required fields: `student_id`, `student_name`, `student_email`, `student_phone`, `student_status`

##### Delete Student

- **DELETE** `/db/student/delete`
- Deletes a student record
- Query parameter: `student_id`

##### Update Student Status

- **PATCH** `/db/student/update-status`
- Updates only the student's status
- Parameters: `student_id`, `new_status`

##### Update Student Contact

- **PATCH** `/db/student/update-contact`
- Updates student's contact information
- Parameters: `student_id`, `email` (optional), `phone` (optional)

##### Get Students by Status

- **GET** `/db/student/get-by-status`
- Retrieves all students with a specific status
- Query parameter: `status`

#### Application Routes

##### Create Application

- **POST** `/db/application/create`
- Creates a new application record
- Required fields: `student_id`, `application_id`, `application_status`
- Optional fields: `intern_project`, `intern_project_start_date`, `intern_project_end_date`

##### Get Application

- **GET** `/db/application/get`
- Retrieves a single application by ID
- Query parameter: `application_id`

##### Get All Applications

- **GET** `/db/application/get-all`
- Retrieves all application records

##### Update Application

- **PUT** `/db/application/update`
- Updates all application information
- Required fields: `application_id`, `student_id`, `application_status`
- Optional fields: `intern_project`, `intern_project_start_date`, `intern_project_end_date`

##### Delete Application

- **DELETE** `/db/application/delete`
- Deletes an application record
- Query parameter: `application_id`

##### Update Application Status

- **PATCH** `/db/application/update-status`
- Updates only the application's status
- Parameters: `application_id`, `new_status`

##### Update Application Project

- **PATCH** `/db/application/update-project`
- Updates only the project details
- Parameters: `application_id`, `project`

##### Update Application Dates

- **PATCH** `/db/application/update-dates`
- Updates project start and end dates
- Parameters: `application_id`, `start_date`, `end_date`

##### Get Applications by Status

- **GET** `/db/application/get-by-status`
- Retrieves all applications with a specific status
- Query parameter: `status`

### MinIO File Operations

#### Health Check

- **GET** `/health`
- Returns server health status and timestamp
- No authentication required

#### File Upload

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

#### File Upload with Email

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

#### File Download

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

#### List Objects

- **GET** `/objects/{student_id}`
- Lists all objects for a specific student
- Requires API key authentication
- URL parameter: `student_id`

#### Delete Object

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

#### Generate Presigned URL

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

All routes (except health check) require API key authentication using the `X-API-Key` header.

## Error Handling

The API returns appropriate HTTP status codes:

- 200: Success
- 400: Bad Request
- 401: Unauthorized (Invalid API Key)
- 404: Not Found
- 500: Internal Server Error

## Response Format

All responses follow this format:

```json
{
  "message": "Operation status message",
  "data": {
    // Response data specific to the operation
  }
}
```

## Database Schema

### Students Table

```sql
CREATE TABLE students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id TEXT,
    student_name TEXT,
    student_email TEXT,
    student_phone TEXT,
    student_status TEXT
)
```

### Applications Table

```sql
CREATE TABLE applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id TEXT,
    application_id TEXT,
    application_status TEXT,
    intern_project TEXT,
    intern_project_start_date TEXT,
    intern_project_end_date TEXT
)
```

## Setup and Installation

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Set up environment variables:

```bash
API_KEY=your-secret-api-key-123
BUCKET_NAME=applicationdocs
# Optional email configuration
# EMAIL_SENDER=your_email@gmail.com
# EMAIL_PASSWORD=your_app_password
```

3. Run the server:

```bash
python main.py
```

The server will start on `http://localhost:8000`

## Notes

- The email functionality is currently commented out but can be enabled by uncommenting the relevant code sections and configuring the email settings in the `.env` file.
- All file operations are performed within a single MinIO bucket, organized by student ID.
- Presigned URLs expire after 1 hour (3600 seconds) by default.
