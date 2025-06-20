# AI Document Validation Server

This FastAPI server provides AI-powered document validation for student internship applications. It uses Google's Gemini AI model to analyze and validate various documents including resumes, cover letters, letters of recommendation, and academic marksheets.

## Features

### Document Validation

- Resume/Cover Letter validation with academic mark requirements
- Letter of Recommendation (LOR) validation with date checks
- Academic marksheet validation for backlogs
- Skills and course information extraction
- Document classification (Resume vs Cover Letter)

### Text Extraction Methods

- Direct PDF text extraction using PyMuPDF
- AI-based extraction using Gemini Vision for scanned documents
- Automatic fallback to vision-based extraction when text extraction fails

### Validation Criteria

#### Resume/Cover Letter

- Academic marks must be mentioned (Class 10, Class 12, CGPA)
- Minimum requirements:
  - Class 10: 60%
  - Class 12: 60%
  - CGPA: 6.32
- Technical skills must be present
- Projects/work experience should be listed
- Education details must be included

#### Letter of Recommendation

- Must have official letterhead
- Must have signature from authorized personnel (HOD/Dean/Principal)
- Must mention internship start and end dates
- Start date must be at least next month from current date
- Proper formatting and structure required

#### Academic Marksheets

- Checks for backlogs in:
  - Class 10 marksheet
  - Class 12 marksheet
  - College marksheet
- Validates student name consistency across documents
- Verifies institution details

## API Endpoints

### Main Validation Endpoint

```http
POST /validate
```

Validates all required documents in a single request.

**Required Files:**

- Resume/Cover Letter (PDF)
- Letter of Recommendation (PDF)
- Class 10 Marksheet (PDF)
- Class 12 Marksheet (PDF)
- College Marksheets (PDF)

### Health Check

```http
GET /health
```

Returns server health status and timestamp.

## Response Format

### Success Response

```json
{
    "valid": true/false,
    "status": "accepted/rejected",
    "summary": "Detailed summary of validation",
    "invalid_documents": ["list of invalid documents"],
    "total_invalid_documents": 0,
    "rejection_reasons": ["detailed list of issues"],
    "validation_details": {
        "resume_cover_letter": {...},
        "letter_of_recommendation": {...},
        "marksheets_backlog_check": {...}
    },
    "applicant_profile": {
        "skills_analysis": {...}
    }
}
```

### Error Response

```json
{
  "error": "Error message",
  "message": "User-friendly error message"
}
```

## Setup and Installation

1. Install dependencies:

```bash
pip install fastapi uvicorn pymupdf google-generativeai pillow python-dotenv
```

2. Set up environment variables:

```bash
GEMINI_API_KEY=your-gemini-api-key
```

3. Run the server:

```bash
python server.py
```

The server will start on `http://localhost:8005`

## Dependencies

- FastAPI: Web framework
- PyMuPDF (fitz): PDF text extraction
- Google Generative AI: Document analysis and validation
- Pillow: Image processing
- Python-dotenv: Environment variable management
- Uvicorn: ASGI server

## Text Extraction Process

1. **Direct Extraction**

   - Uses PyMuPDF to extract text directly from PDF
   - Fastest method for digital PDFs
   - Checks if extracted text is meaningful (minimum length and character requirements)

2. **AI Extraction**

   - Converts PDF pages to high-resolution images
   - Uses Gemini Vision for document analysis
   - Fallback method when direct extraction fails
   - More reliable for scanned documents

## Error Handling

The server implements comprehensive error handling:

- File format validation
- Text extraction validation
- API error handling
- Validation error tracking
- Detailed error messages and logging

## Notes

- The server uses Gemini AI model "gemini-2.5-flash-preview-05-20"
- All file operations are performed in memory
- Maximum file size limits may apply
- Response times may vary based on document complexity and size
- Logging is configured for debugging and monitoring

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.
