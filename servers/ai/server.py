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

# Specialized document validation functions
def validate_resume(text: str) -> dict:
    prompt = (
        "You are validating a student's resume for an internship application.\n"
        "Requirements:\n"
        "- Must mention technical skills\n"
        "- Should list projects or work experience\n"
        "- Should include education details\n\n"
        f"Resume content:\n{text}\n\n"
        "Return your response in this exact format:\n"
        "VALID: [true/false]\n"
        "FEEDBACK: [your detailed feedback]\n"
        "SKILLS: [list of skills detected]"
    )
    
    try:
        response = model.generate_content(prompt)
        response_text = response.text.strip()
        
        # More robust parsing of the valid status
        valid_line = next((line for line in response_text.split('\n') 
                          if line.lower().startswith('valid:')), '')
        valid = 'true' in valid_line.lower() and 'false' not in valid_line.lower()
        
        return {
            "valid": valid,
            "feedback": response_text
        }
    except Exception as e:
        return {
            "valid": False,
            "feedback": f"Error validating resume: {str(e)}"
        }

def validate_lor(text: str) -> dict:
    prompt = (
        "You are validating a letter of recommendation (LOR) for an internship application.\n"
        "Requirements:\n"
        "- Must include professor/recommender name\n"
        "- Should have signature or proper closing\n"
        "- Should mention student's qualities or achievements\n\n"
        f"LOR content:\n{text}\n\n"
        "Return your response in this exact format:\n"
        "VALID: [true/false]\n"
        "FEEDBACK: [your detailed feedback]\n"
        "RECOMMENDER: [name of recommender if found]"
    )
    
    try:
        response = model.generate_content(prompt)
        response_text = response.text.strip()
        
        # More robust parsing of the valid status
        valid_line = next((line for line in response_text.split('\n') 
                          if line.lower().startswith('valid:')), '')
        valid = 'true' in valid_line.lower() and 'false' not in valid_line.lower()
        
        return {
            "valid": valid,
            "feedback": response_text
        }
    except Exception as e:
        return {
            "valid": False,
            "feedback": f"Error validating letter of recommendation: {str(e)}"
        }

def validate_marksheet(text: str) -> dict:
    prompt = (
        "You are validating a student's marksheet/transcript for an internship application.\n"
        "Requirements:\n"
        "- Must include GPA or CGPA\n"
        "- Should have student name and institution details\n"
        "- Should include course/subject details\n\n"
        f"Marksheet content:\n{text}\n\n"
        "Return your response in this exact format:\n"
        "VALID: [true/false]\n"
        "FEEDBACK: [your detailed feedback]\n"
        "GPA: [the GPA/CGPA value if found]"
    )
    
    try:
        response = model.generate_content(prompt)
        response_text = response.text.strip()
        
        # More robust parsing of the valid status
        valid_line = next((line for line in response_text.split('\n') 
                          if line.lower().startswith('valid:')), '')
        valid = 'true' in valid_line.lower() and 'false' not in valid_line.lower()
        
        return {
            "valid": valid,
            "feedback": response_text
        }
    except Exception as e:
        return {
            "valid": False,
            "feedback": f"Error validating marksheet: {str(e)}"
        }

# Add utility function to extract structured data from AI responses
def extract_field(response_text: str, field_name: str) -> str:
    """Extract a specific field from structured AI response text"""
    field_prefix = f"{field_name}:"
    for line in response_text.split('\n'):
        if line.lower().startswith(field_prefix.lower()):
            return line[len(field_prefix):].strip()
    return ""
    
# Combine validations and make final decision
def evaluate_overall_application(resume_result: dict, lor_result: dict, marksheet_result: dict) -> dict:
    all_valid = resume_result["valid"] and lor_result["valid"] and marksheet_result["valid"]
    
    # Extract specific data points
    skills = extract_field(resume_result["feedback"], "SKILLS")
    recommender = extract_field(lor_result["feedback"], "RECOMMENDER")
    gpa = extract_field(marksheet_result["feedback"], "GPA")
    
    detailed_feedback = {
        "resume": {
            "valid": resume_result["valid"],
            "feedback": extract_field(resume_result["feedback"], "FEEDBACK"),
            "skills": skills
        },
        "letter_of_recommendation": {
            "valid": lor_result["valid"],
            "feedback": extract_field(lor_result["feedback"], "FEEDBACK"),
            "recommender": recommender
        },
        "marksheet": {
            "valid": marksheet_result["valid"],
            "feedback": extract_field(marksheet_result["feedback"], "FEEDBACK"),
            "gpa": gpa
        }
    }
    
    overall_status = "accepted" if all_valid else "rejected"
    
    # Generate overall summary
    if all_valid:
        summary = f"Application is complete and meets all requirements. GPA: {gpa}, Skills: {skills}, Recommended by: {recommender}."
    else:
        missing_docs = []
        if not resume_result["valid"]:
            missing_docs.append("resume")
        if not lor_result["valid"]:
            missing_docs.append("letter of recommendation")
        if not marksheet_result["valid"]:
            missing_docs.append("marksheet")
        
        summary = f"Application incomplete. Issues found in: {', '.join(missing_docs)}."
    
    return {
        "valid": all_valid,
        "status": overall_status,
        "summary": summary,
        "detailed_feedback": detailed_feedback
    }

# Route: Validate uploaded documents
@app.post("/validate")
async def validate_documents(
    resume: UploadFile = File(...),
    lor: UploadFile = File(...),
    marksheet: UploadFile = File(...)
):
    try:
        # Extract text from all documents
        resume_text = extract_text_from_pdf(resume)
        lor_text = extract_text_from_pdf(lor)
        marksheet_text = extract_text_from_pdf(marksheet)
        
        # Validate each document individually
        resume_result = validate_resume(resume_text)
        lor_result = validate_lor(lor_text)
        marksheet_result = validate_marksheet(marksheet_text)
        
        # Evaluate the overall application
        result = evaluate_overall_application(resume_result, lor_result, marksheet_result)
        
        return JSONResponse(content=result)
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)