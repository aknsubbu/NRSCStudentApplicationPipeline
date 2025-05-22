import os
import fitz  # PyMuPDF
import google.generativeai as genai
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
# Load .env file
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Configure Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.0-flash")

# FastAPI app
app = FastAPI(title="Internship AI Validator")

def extract_field(response_text: str, field_name: str) -> str:
    """Extract a specific field from structured AI response text"""
    field_prefix = f"{field_name}:"
    for line in response_text.split('\n'):
        if line.lower().startswith(field_prefix.lower()):
            return line[len(field_prefix):].strip()
    return ""

def extract_text_from_pdf(file: UploadFile) -> str:
    """Extract text from uploaded PDF"""
    doc = fitz.open(stream=file.file.read(), filetype="pdf")
    text = ""
    for page in doc:
        text += page.get_text()
    return text.strip()
# Utility: Extract text from uploaded PDF
def extract_text_from_pdf(file: UploadFile) -> str:
    doc = fitz.open(stream=file.file.read(), filetype="pdf")
    text = ""
    for page in doc:
        text += page.get_text()
    return text.strip()

def classify_document(text: str) -> str:
    prompt = (
        "Analyze this document and determine if it's a RESUME or a COVER LETTER.\n"
        "Key differences:\n"
        "- Resumes are structured lists of experience, skills, and qualifications\n"
        "- Cover letters are formal letters explaining motivation and interest\n\n"
        f"Document content:\n{text}\n\n"
        "Return only one word: RESUME or COVERLETTER"
    )
    
    try:
        response = model.generate_content(prompt)
        doc_type = response.text.strip().upper()
        return "RESUME" if "RESUME" in doc_type else "COVERLETTER"
    except Exception as e:
        return "RESUME"  # Default to resume in case of classification error

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
        "You are validating a letter of recommendation (LOR) or official document for an internship application.\n"
        "Critical Requirements:\n"
        "1. Must have official letterhead of the institution\n"
        "2. Must have a signature from any one of these authorities:\n"
           "   - Head of Department\n"
           "   - Dean\n"
           "   - Principal\n"
        "3. Document can be one of:\n"
           "   - Letter of Recommendation\n"
           "   - Bonafide Certificate\n"
           "   - Any official endorsement letter\n\n"
        f"Document content:\n{text}\n\n"
        "Return your response in this exact format:\n"
        "VALID: [true/false]\n"
        "FEEDBACK: [your detailed feedback]\n"
        "LETTERHEAD: [yes/no]\n"
        "AUTHORITY: [title and name of signing authority]\n"
        "DOCUMENT_TYPE: [type of document detected]"
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
def validate_cover_letter(text: str) -> dict:
    prompt = (
        "You are validating a student's cover letter for an internship application.\n"
        "Requirements:\n"
        "- Must include student's motivation/interest\n"
        "- Should reference specific skills relevant to the position\n"
        "- Should have proper formatting (greeting, closing)\n\n"
        f"Cover letter content:\n{text}\n\n"
        "Return your response in this exact format:\n"
        "VALID: [true/false]\n"
        "FEEDBACK: [your detailed feedback]\n"
        "HIGHLIGHTS: [key points mentioned]"
    )
    
    try:
        response = model.generate_content(prompt)
        response_text = response.text.strip()
        
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
            "feedback": f"Error validating cover letter: {str(e)}"
        }

def validate_school_marksheet(text: str, class_level: str) -> dict:
    """Validate 10th or 12th marksheet with minimum 60% requirement"""
    logger.info(f"Starting validation for Class {class_level} marksheet")
    
    prompt = (
        f"You are validating a Class {class_level} marksheet.\n"
        "Requirements:\n"
        "- Must have student name and school details\n"
        "- Must have overall percentage\n"
        "- Minimum required percentage is 60%\n"
        f"Marksheet content:\n{text}\n\n"
        "Return your response in this exact format:\n"
        "VALID: [true/false]\n"
        "FEEDBACK: [detailed feedback]\n"
        "STUDENT_NAME: [name of student]\n"
        "SCHOOL_NAME: [name of school]\n"
        "PERCENTAGE: [overall percentage]\n"
        "YEAR: [year of passing]"
    )
    
    try:
        logger.info("Generating AI response")
        response = model.generate_content(prompt)
        response_text = response.text.strip()
        
        logger.debug(f"AI Response for Class {class_level}: {response_text}")
        
        # Extract fields with logging
        percentage_str = extract_field(response_text, "PERCENTAGE")
        logger.debug(f"Extracted percentage string: {percentage_str}")
        
        # Clean percentage string and convert to float
        percentage = float(percentage_str.replace('%', '').strip() or 0)
        logger.info(f"Parsed percentage: {percentage}")
        
        meets_criteria = percentage >= 60.0
        
        result = {
            "valid": meets_criteria,
            "percentage": percentage,
            "student_name": extract_field(response_text, "STUDENT_NAME"),
            "school_name": extract_field(response_text, "SCHOOL_NAME"),
            "year": extract_field(response_text, "YEAR"),
            "feedback": extract_field(response_text, "FEEDBACK"),
            "class_level": class_level  # Add this to help with debugging
        }
        
        logger.info(f"Class {class_level} validation result: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Error validating Class {class_level} marksheet: {str(e)}", exc_info=True)
        return {
            "valid": False,
            "feedback": f"Error validating Class {class_level} marksheet: {str(e)}",
            "percentage": 0,
            "student_name": "",
            "school_name": "",
            "year": "",
            "class_level": class_level
        }
def validate_college_marksheet(text: str) -> dict:
    """Validate college semester marksheets with CGPA requirement and backlog check"""
    prompt = (
        "You are validating college semester marksheets.\n"
        "Critical Requirements:\n"
        "1. CGPA must be at least 6.32\n"
        "2. No current backlogs allowed\n"
        "3. Extract GPAs for each semester\n\n"
        f"Marksheet content:\n{text}\n\n"
        "Return your response in this exact format:\n"
        "VALID: [true/false]\n"
        "FEEDBACK: [detailed feedback]\n"
        "SEMESTER_GPAS: [comma-separated list of semester-wise GPAs]\n"
        "CURRENT_CGPA: [current cumulative GPA]\n"
        "BACKLOGS: [number of current backlogs]\n"
        "FAILED_SUBJECTS: [list any currently failed subjects]\n"
        "COLLEGE_NAME: [name of institution]"
    )
    
    try:
        response = model.generate_content(prompt)
        response_text = response.text.strip()
        
        # Extract fields
        cgpa = float(extract_field(response_text, "CURRENT_CGPA") or 0)
        backlogs = int(extract_field(response_text, "BACKLOGS") or 0)
        semester_gpas = [float(gpa.strip()) for gpa in 
                        extract_field(response_text, "SEMESTER_GPAS").split(',') if gpa.strip()]
        
        # Validation criteria
        meets_cgpa = cgpa >= 6.32
        no_backlogs = backlogs == 0
        
        return {
            "valid": meets_cgpa and no_backlogs,
            "college_name": extract_field(response_text, "COLLEGE_NAME"),
            "academic_details": {
                "semester_gpas": semester_gpas,
                "current_cgpa": cgpa,
                "backlogs": backlogs,
                "failed_subjects": extract_field(response_text, "FAILED_SUBJECTS")
            },
            "validation_summary": {
                "meets_cgpa_requirement": meets_cgpa,
                "has_no_backlogs": no_backlogs
            },
            "feedback": extract_field(response_text, "FEEDBACK")
        }
    except Exception as e:
        return {
            "valid": False,
            "feedback": f"Error validating college marksheet: {str(e)}"
        }

def validate_all_marksheets(class_10_text: str, class_12_text: str, college_text: str) -> dict:
    """Validate all academic documents together"""
    logger.info("Starting validation of all marksheets")
    
    # Validate each marksheet with logging
    class_10_result = validate_school_marksheet(class_10_text, "10")
    logger.info(f"Class 10 validation result: {class_10_result}")
    
    class_12_result = validate_school_marksheet(class_12_text, "12")
    logger.info(f"Class 12 validation result: {class_12_result}")
    
    college_result = validate_college_marksheet(college_text)
    logger.info(f"College validation result: {college_result}")
    
    all_valid = (class_10_result["valid"] and 
                class_12_result["valid"] and 
                college_result["valid"])
    
    return {
        "valid": all_valid,
        "academic_records": {
            "class_10": class_10_result,
            "class_12": class_12_result,
            "college": college_result
        },
        "overall_feedback": {
            "meets_all_criteria": all_valid,
            "issues": [item for item in [
                "Class 10: Below 60%" if not class_10_result["valid"] else None,
                "Class 12: Below 60%" if not class_12_result["valid"] else None,
                "College: CGPA below 6.32 or has backlogs" if not college_result["valid"] else None
            ] if item is not None]
        }
    }
# Add utility function to extract structured data from AI responses

    
# Combine validations and make final decision
def evaluate_overall_application(resume_result: dict, lor_result: dict, marksheet_result: dict) -> dict:
    """Evaluate all documents and provide overall application status"""
    all_valid = resume_result["valid"] and lor_result["valid"] and marksheet_result["valid"]
    
    # Extract specific data points from results
    skills = extract_field(resume_result.get("feedback", ""), "SKILLS")
    recommender = extract_field(lor_result.get("feedback", ""), "RECOMMENDER")
    
    # Extract academic information from marksheet result
    academic_records = marksheet_result.get("academic_records", {})
    college_details = academic_records.get("college", {}).get("academic_details", {})
    cgpa = college_details.get("current_cgpa", "N/A")
    
    detailed_feedback = {
        "resume": {
            "valid": resume_result["valid"],
            "feedback": extract_field(resume_result.get("feedback", ""), "FEEDBACK"),
            "skills": skills
        },
        "letter_of_recommendation": {
            "valid": lor_result["valid"],
            "feedback": extract_field(lor_result.get("feedback", ""), "FEEDBACK"),
            "recommender": recommender
        },
        "academic_records": {
            "valid": marksheet_result["valid"],
            "details": marksheet_result.get("academic_records", {}),
            "overall_feedback": marksheet_result.get("overall_feedback", {})
        }
    }
    
    overall_status = "accepted" if all_valid else "rejected"
    
    # Generate overall summary
    if all_valid:
        summary = (f"Application is complete and meets all requirements. "
                  f"CGPA: {cgpa}, Skills: {skills}, "
                  f"Recommended by: {recommender}.")
    else:
        missing_docs = []
        if not resume_result["valid"]:
            missing_docs.append("resume")
        if not lor_result["valid"]:
            missing_docs.append("letter of recommendation")
        if not marksheet_result["valid"]:
            missing_docs.append("academic records")
        
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
    class_10: UploadFile = File(...),
    class_12: UploadFile = File(...),
    college_marksheets: UploadFile = File(...)
):
    try:
        logger.info("Starting document validation")
        
        # Extract text from all documents
        resume_text = extract_text_from_pdf(resume)
        lor_text = extract_text_from_pdf(lor)
        class_10_text = extract_text_from_pdf(class_10)
        class_12_text = extract_text_from_pdf(class_12)
        college_text = extract_text_from_pdf(college_marksheets)
        
        logger.info("Text extraction complete")
        
        # Validate documents
        doc_type = classify_document(resume_text)
        if doc_type == "RESUME":
            resume_result = validate_resume(resume_text)
        else:
            resume_result = validate_cover_letter(resume_text)
        
        lor_result = validate_lor(lor_text)
        marksheet_result = validate_all_marksheets(class_10_text, class_12_text, college_text)
        
        logger.info("Document validation complete")
        
        # Evaluate overall application
        result = evaluate_overall_application(resume_result, lor_result, marksheet_result)
        result["document_type"] = doc_type
        result["academic_details"] = marksheet_result
        
        return JSONResponse(content=result)
    except Exception as e:
        logger.error(f"Error in validate_documents: {str(e)}", exc_info=True)
        return JSONResponse(
            content={
                "error": str(e),
                "message": "An error occurred while processing your request"
            }, 
            status_code=500
        )