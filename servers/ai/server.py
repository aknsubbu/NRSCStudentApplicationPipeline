import os
import fitz  # PyMuPDF
import google.generativeai as genai
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

# Load .env file
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Configure Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.0-flash")

# FastAPI app
app = FastAPI(title="Internship AI Validator")

# Utility: Extract text from uploaded PDF
def extract_text_from_pdf(file: UploadFile) -> str:
    doc = fitz.open(stream=file.file.read(), filetype="pdf")
    text = ""
    for page in doc:
        text += page.get_text()
    return text.strip()

# AI validation using Gemini
def validate_application(texts: list[str]) -> dict:
    combined_text = "\n\n".join(texts)
    prompt = (
        "You are validating a student internship application.\n"
        "Requirements:\n"
        "- Must include GPA or CGPA\n"
        "- Resume must mention skills or projects\n"
        "- LOR should include professor name or signature\n\n"
        f"Content:\n{combined_text}\n\n"
        "Return:\n1. Valid: true/false\n2. Feedback explaining what is missing or okay."
    )

    try:
        response = model.generate_content(prompt)
        valid = "true" in response.text.lower()
        return {
            "valid": valid,
            "feedback": response.text.strip()
        }
    except Exception as e:
        return {
            "valid": False,
            "feedback": f"Error during validation: {str(e)}"
        }

# Route: Validate uploaded documents
@app.post("/validate")
async def validate_documents(
    resume: UploadFile = File(...),
    lor: UploadFile = File(...),
    marksheet: UploadFile = File(...)
):
    try:
        resume_text = extract_text_from_pdf(resume)
        lor_text = extract_text_from_pdf(lor)
        marksheet_text = extract_text_from_pdf(marksheet)

        result = validate_application([resume_text, lor_text, marksheet_text])
        return JSONResponse(content=result)
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)
