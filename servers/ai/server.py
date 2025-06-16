import os
import fitz  # PyMuPDF
import google.generativeai as genai
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
import logging
import io
from PIL import Image
import base64

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load .env file
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Configure Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash-preview-05-20")


# FastAPI app
app = FastAPI(title="Internship AI Validator")

def extract_field(response_text: str, field_name: str) -> str:
    """Extract a specific field from structured AI response text"""
    field_prefix = f"{field_name}:"
    for line in response_text.split('\n'):
        if line.lower().startswith(field_prefix.lower()):
            return line[len(field_prefix):].strip()
    return ""

def pdf_to_images(file: UploadFile) -> list:
    """Convert PDF pages to images"""
    try:
        # Reset file pointer
        file.file.seek(0)
        doc = fitz.open(stream=file.file.read(), filetype="pdf")
        images = []
        
        for page_num in range(doc.page_count):
            page = doc[page_num]
            # Convert page to image with good resolution
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 2x scaling for better quality
            img_data = pix.tobytes("png")
            
            # Convert to PIL Image and then to base64
            pil_image = Image.open(io.BytesIO(img_data))
            buffered = io.BytesIO()
            pil_image.save(buffered, format="PNG")
            img_base64 = base64.b64encode(buffered.getvalue()).decode()
            
            images.append({
                "mime_type": "image/png",
                "data": img_base64
            })
            
        doc.close()
        return images
    except Exception as e:
        logger.error(f"Error converting PDF to images: {str(e)}")
        return []

def is_text_extractable(text: str, min_length: int = 50) -> bool:
    """Check if extracted text is meaningful (not just whitespace/symbols)"""
    if not text:
        return False
    
    # Remove whitespace and check length
    clean_text = text.strip()
    if len(clean_text) < min_length:
        return False
    
    # Check if text contains meaningful content (letters/numbers)
    import re
    meaningful_chars = re.findall(r'[a-zA-Z0-9]', clean_text)
    return len(meaningful_chars) > min_length * 0.3  # At least 30% meaningful characters

def extract_text_from_pdf(file: UploadFile) -> tuple[str, bool]:
    """Extract text from uploaded PDF and return (text, is_text_based)"""
    try:
        # Reset file pointer
        file.file.seek(0)
        doc = fitz.open(stream=file.file.read(), filetype="pdf")
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        
        # Check if extraction was successful
        is_extractable = is_text_extractable(text)
        return text.strip(), is_extractable
    except Exception as e:
        logger.error(f"Error extracting text from PDF: {str(e)}")
        return "", False

def process_document_with_vision(images: list, prompt: str) -> str:
    """Process document images using Gemini Vision"""
    try:
        # Prepare content with images and prompt
        content = [prompt]
        
        for img in images:
            content.append({
                "mime_type": img["mime_type"],
                "data": img["data"]
            })
        
        response = model.generate_content(content)
        return response.text.strip()
    except Exception as e:
        logger.error(f"Error processing document with vision: {str(e)}")
        return f"Error processing document: {str(e)}"

def classify_document(text: str = None, images: list = None) -> str:
    """Classify document as RESUME or COVER LETTER using text or vision"""
    prompt = (
        "Analyze this document and determine if it's a RESUME or a COVER LETTER.\n"
        "Key differences:\n"
        "- Resumes are structured lists of experience, skills, and qualifications\n"
        "- Cover letters are formal letters explaining motivation and interest\n\n"
        "Return only one word: RESUME or COVERLETTER"
    )
    
    try:
        if text and is_text_extractable(text):
            # Use text-based classification
            full_prompt = f"{prompt}\n\nDocument content:\n{text}"
            response = model.generate_content(full_prompt)
            doc_type = response.text.strip().upper()
        elif images:
            # Use vision-based classification
            doc_type = process_document_with_vision(images, prompt).upper()
        else:
            return "RESUME"  # Default fallback
        
        return "RESUME" if "RESUME" in doc_type else "COVERLETTER"
    except Exception as e:
        logger.error(f"Error in document classification: {str(e)}")
        return "RESUME"  # Default to resume in case of error

def validate_resume(text: str = None, images: list = None) -> dict:
    """Validate resume using text or vision"""
    prompt = (
        "You are validating a student's resume for an internship application.\n"
        "Requirements:\n"
        "- Must mention technical skills\n"
        "- Should list projects or work experience\n"
        "- Should include education details\n\n"
        "Return your response in this exact format:\n"
        "VALID: [true/false]\n"
        "FEEDBACK: [your detailed feedback]\n"
        "SKILLS: [list of skills detected]"
    )
    
    try:
        if text and is_text_extractable(text):
            # Use text-based validation
            full_prompt = f"{prompt}\n\nResume content:\n{text}"
            response = model.generate_content(full_prompt)
            response_text = response.text.strip()
        elif images:
            # Use vision-based validation
            response_text = process_document_with_vision(images, prompt)
        else:
            return {"valid": False, "feedback": "No content to validate"}
        
        # Parse response
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

def validate_lor(text: str = None, images: list = None) -> dict:
    """Validate letter of recommendation using text or vision"""
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
        "Return your response in this exact format:\n"
        "VALID: [true/false]\n"
        "FEEDBACK: [your detailed feedback]\n"
        "LETTERHEAD: [yes/no]\n"
        "AUTHORITY: [title and name of signing authority]\n"
        "DOCUMENT_TYPE: [type of document detected]"
    )
    
    try:
        if text and is_text_extractable(text):
            full_prompt = f"{prompt}\n\nDocument content:\n{text}"
            response = model.generate_content(full_prompt)
            response_text = response.text.strip()
        elif images:
            response_text = process_document_with_vision(images, prompt)
        else:
            return {"valid": False, "feedback": "No content to validate"}
        
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

def validate_cover_letter(text: str = None, images: list = None) -> dict:
    """Validate cover letter using text or vision"""
    prompt = (
        "You are validating a student's cover letter for an internship application.\n"
        "Requirements:\n"
        "- Must include student's motivation/interest\n"
        "- Should reference specific skills relevant to the position\n"
        "- Should have proper formatting (greeting, closing)\n\n"
        "Return your response in this exact format:\n"
        "VALID: [true/false]\n"
        "FEEDBACK: [your detailed feedback]\n"
        "HIGHLIGHTS: [key points mentioned]"
    )
    
    try:
        if text and is_text_extractable(text):
            full_prompt = f"{prompt}\n\nCover letter content:\n{text}"
            response = model.generate_content(full_prompt)
            response_text = response.text.strip()
        elif images:
            response_text = process_document_with_vision(images, prompt)
        else:
            return {"valid": False, "feedback": "No content to validate"}
        
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

def validate_school_marksheet(text: str = None, images: list = None, class_level: str = "10") -> dict:
    """Validate 10th or 12th marksheet with minimum 60% requirement using text or vision"""
    logger.info(f"Starting validation for Class {class_level} marksheet")
    
    prompt = (
        f"You are validating a Class {class_level} marksheet.\n"
        "Requirements:\n"
        "- Must have student name and school details\n"
        "- Must have overall percentage\n"
        "- Minimum required percentage is 60%\n\n"
        "IMPORTANT: Look for the overall percentage or total marks percentage in the document.\n"
        "Return your response in this exact format (DO NOT include brackets):\n"
        "VALID: true or false\n"
        "FEEDBACK: detailed feedback\n"
        "STUDENT_NAME: name of student\n"
        "SCHOOL_NAME: name of school\n"
        "PERCENTAGE: ONLY the number (e.g., 75.5 or 82) without any brackets or symbols\n"
        "YEAR: year of passing"
    )
    
    try:
        logger.info("Generating AI response")
        
        if text and is_text_extractable(text):
            # Use text-based validation
            full_prompt = f"{prompt}\n\nMarksheet content:\n{text}"
            response = model.generate_content(full_prompt)
            response_text = response.text.strip()
        elif images:
            # Use vision-based validation
            logger.info("Using vision-based validation for marksheet")
            response_text = process_document_with_vision(images, prompt)
        else:
            return {
                "valid": False,
                "feedback": "No content to validate",
                "percentage": 0,
                "student_name": "",
                "school_name": "",
                "year": "",
                "class_level": class_level
            }
        
        logger.debug(f"AI Response for Class {class_level}: {response_text}")
        
        # Extract percentage with better error handling
        percentage_str = extract_field(response_text, "PERCENTAGE")
        logger.debug(f"Raw percentage string: {percentage_str}")
        
        # Clean and validate percentage string
        import re
        cleaned_percentage = re.sub(r'[^\d.]', '', percentage_str)
        
        if not cleaned_percentage:
            logger.warning(f"No valid percentage found in: {percentage_str}")
            percentage = 0
        else:
            try:
                percentage = float(cleaned_percentage)
                if percentage < 0 or percentage > 100:
                    logger.warning(f"Percentage out of range: {percentage}")
                    percentage = 0
            except ValueError:
                logger.error(f"Could not convert percentage to float: {cleaned_percentage}")
                percentage = 0
        
        logger.info(f"Final parsed percentage: {percentage}")
        
        meets_criteria = percentage >= 60.0
        
        result = {
            "valid": meets_criteria,
            "percentage": percentage,
            "student_name": extract_field(response_text, "STUDENT_NAME"),
            "school_name": extract_field(response_text, "SCHOOL_NAME"),
            "year": extract_field(response_text, "YEAR"),
            "feedback": (f"Percentage {percentage}% {'meets' if meets_criteria else 'does not meet'} "
                       "the minimum requirement of 60%"),
            "class_level": class_level
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

def validate_college_marksheet(text: str = None, images: list = None) -> dict:
    """Validate college semester marksheets with CGPA requirement and backlog check"""
    prompt = (
        "You are validating college semester marksheets.\n"
        "Critical Requirements:\n"
        "1. CGPA must be at least 6.32\n"
        "2. No current backlogs allowed\n"
        "3. Extract GPAs for each semester\n\n"
        "IMPORTANT: Look for CGPA, GPA, or cumulative grade point average in the document.\n"
        "Return your response in this exact format (DO NOT include brackets):\n"
        "VALID: true or false\n"
        "FEEDBACK: detailed feedback\n"
        "SEMESTER_GPAS: comma-separated list of GPAs (e.g., 7.5,8.0,7.8)\n"
        "CURRENT_CGPA: ONLY the number (e.g., 7.5) without brackets\n"
        "BACKLOGS: number of current backlogs (use 0 if none)\n"
        "FAILED_SUBJECTS: list any currently failed subjects (or write 'None')\n"
        "COLLEGE_NAME: name of institution"
    )
    
    try:
        if text and is_text_extractable(text):
            full_prompt = f"{prompt}\n\nMarksheet content:\n{text}"
            response = model.generate_content(full_prompt)
            response_text = response.text.strip()
        elif images:
            response_text = process_document_with_vision(images, prompt)
        else:
            return {"valid": False, "feedback": "No content to validate"}
        
        # Extract CGPA with better parsing
        cgpa_str = extract_field(response_text, "CURRENT_CGPA")
        import re
        cleaned_cgpa = re.sub(r'[^\d.]', '', cgpa_str)
        
        try:
            cgpa = float(cleaned_cgpa) if cleaned_cgpa else 0
        except ValueError:
            cgpa = 0
        
        # Extract backlogs
        backlogs_str = extract_field(response_text, "BACKLOGS")
        cleaned_backlogs = re.sub(r'[^\d]', '', backlogs_str)
        
        try:
            backlogs = int(cleaned_backlogs) if cleaned_backlogs else 0
        except ValueError:
            backlogs = 0
        
        # Extract semester GPAs
        semester_gpas_str = extract_field(response_text, "SEMESTER_GPAS")
        semester_gpas = []
        if semester_gpas_str:
            for gpa in semester_gpas_str.split(','):
                cleaned_gpa = re.sub(r'[^\d.]', '', gpa.strip())
                if cleaned_gpa:
                    try:
                        semester_gpas.append(float(cleaned_gpa))
                    except ValueError:
                        continue
        
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

def validate_all_marksheets(class_10_file: UploadFile, class_12_file: UploadFile, college_file: UploadFile) -> dict:
    """Validate all academic documents together with smart text/vision processing"""
    logger.info("Starting validation of all marksheets")
    
    # Process Class 10 marksheet
    class_10_text, class_10_text_extractable = extract_text_from_pdf(class_10_file)
    if not class_10_text_extractable:
        logger.info("Class 10 marksheet: Text not extractable, using vision")
        class_10_images = pdf_to_images(class_10_file)
        class_10_result = validate_school_marksheet(images=class_10_images, class_level="10")
        print("Class 10 marksheet output", class_10_result)
    else:
        logger.info("Class 10 marksheet: Using text-based validation")
        class_10_result = validate_school_marksheet(text=class_10_text, class_level="10")
    
    # Process Class 12 marksheet
    class_12_text, class_12_text_extractable = extract_text_from_pdf(class_12_file)
    if not class_12_text_extractable:
        logger.info("Class 12 marksheet: Text not extractable, using vision")
        class_12_images = pdf_to_images(class_12_file)
        class_12_result = validate_school_marksheet(images=class_12_images, class_level="12")
    else:
        logger.info("Class 12 marksheet: Using text-based validation")
        class_12_result = validate_school_marksheet(text=class_12_text, class_level="12")
    
    # Process College marksheet
    college_text, college_text_extractable = extract_text_from_pdf(college_file)
    if not college_text_extractable:
        logger.info("College marksheet: Text not extractable, using vision")
        college_images = pdf_to_images(college_file)
        college_result = validate_college_marksheet(images=college_images)
    else:
        logger.info("College marksheet: Using text-based validation")
        college_result = validate_college_marksheet(text=college_text)
    
    logger.info(f"Class 10 validation result: {class_10_result}")
    logger.info(f"Class 12 validation result: {class_12_result}")
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
        "processing_methods": {
            "class_10": "vision" if not class_10_text_extractable else "text",
            "class_12": "vision" if not class_12_text_extractable else "text",
            "college": "vision" if not college_text_extractable else "text"
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
            "overall_feedback": marksheet_result.get("overall_feedback", {}),
            "processing_methods": marksheet_result.get("processing_methods", {})
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
        
        # Process resume with smart text/vision fallback
        resume_text, resume_text_extractable = extract_text_from_pdf(resume)
        logger.info(f"Resume text extractable: {resume_text_extractable}")
        
        if resume_text_extractable:
            doc_type = classify_document(text=resume_text)
            if doc_type == "RESUME":
                resume_result = validate_resume(text=resume_text)
            else:
                resume_result = validate_cover_letter(text=resume_text)
        else:
            logger.info("Resume: Using vision-based processing")
            resume_images = pdf_to_images(resume)
            doc_type = classify_document(images=resume_images)
            if doc_type == "RESUME":
                resume_result = validate_resume(images=resume_images)
            else:
                resume_result = validate_cover_letter(images=resume_images)
        
        # Process LOR with smart text/vision fallback
        lor_text, lor_text_extractable = extract_text_from_pdf(lor)
        logger.info(f"LOR text extractable: {lor_text_extractable}")
        
        if lor_text_extractable:
            lor_result = validate_lor(text=lor_text)
        else:
            logger.info("LOR: Using vision-based processing")
            lor_images = pdf_to_images(lor)
            lor_result = validate_lor(images=lor_images)
        
        # Process marksheets (this function now handles text/vision internally)
        marksheet_result = validate_all_marksheets(class_10, class_12, college_marksheets)
        
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