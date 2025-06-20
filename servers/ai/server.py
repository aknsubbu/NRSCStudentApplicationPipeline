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
import re
from datetime import datetime, timedelta

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

def extract_percentage(text: str) -> float:
    """Extract percentage value from text and return as float"""
    if not text:
        return 0
    
    # Clean and validate percentage string
    cleaned_percentage = re.sub(r'[^\d.]', '', text)
    
    if not cleaned_percentage:
        return 0
    
    try:
        percentage = float(cleaned_percentage)
        if percentage < 0 or percentage > 100:
            return 0
        return percentage
    except ValueError:
        return 0

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
    
def extract_skills_and_course_info(text: str = None, images: list = None) -> dict:
    """Extract detailed skills, projects, and course information from resume"""
    prompt = (
        "Analyze this resume and extract detailed information about the candidate's capabilities.\n"
        "Focus on:\n"
        "1. Technical skills mentioned\n"
        "2. Programming languages\n"
        "3. Projects and their descriptions\n"
        "4. Course/degree information\n"
        "5. Tools and technologies used\n"
        "6. Domain expertise (web dev, mobile, AI/ML, data science, etc.)\n\n"
        "Return your response in this exact format:\n"
        "TECHNICAL_SKILLS: [list of technical skills]\n"
        "PROGRAMMING_LANGUAGES: [list of programming languages]\n"
        "PROJECTS: [brief description of each project]\n"
        "COURSE_DEGREE: [course name and specialization]\n"
        "TOOLS_TECHNOLOGIES: [frameworks, tools, databases, etc.]\n"
        "DOMAIN_EXPERTISE: [areas of expertise like web development, AI/ML, etc.]\n"
        "SUITABILITY_ASSESSMENT: [brief assessment of candidate's technical readiness]"
        "Use the information provided to generate a comprehensive analysis in around 200 characterss.\n"
    )
    
    try:
        if text and is_text_extractable(text):
            full_prompt = f"{prompt}\n\nResume content:\n{text}"
            response = model.generate_content(full_prompt)
            response_text = response.text.strip()
        elif images:
            response_text = process_document_with_vision(images, prompt)
        else:
            return {"error": "No content to analyze"}
        
        return {
            "technical_skills": extract_field(response_text, "TECHNICAL_SKILLS"),
            "programming_languages": extract_field(response_text, "PROGRAMMING_LANGUAGES"),
            # "projects": extract_field(response_text, "PROJECTS"),
            "course_degree": extract_field(response_text, "COURSE_DEGREE"),
            "tools_technologies": extract_field(response_text, "TOOLS_TECHNOLOGIES"),
            "domain_expertise": extract_field(response_text, "DOMAIN_EXPERTISE"),
            "suitability_assessment": extract_field(response_text, "SUITABILITY_ASSESSMENT"),
            # "full_analysis": response_text
        }
    except Exception as e:
        logger.error(f"Error extracting skills and course info: {str(e)}")
        return {
            "error": f"Failed to extract skills information: {str(e)}"
        }

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

def validate_resume_with_marks(text: str = None, images: list = None) -> dict:
    """Validate resume ensuring academic marks are present and meet requirements"""
    prompt = (
        "You are validating a student's resume for an internship application.\n"
        "CRITICAL REQUIREMENTS:\n"
        "1. The resume MUST mention academic performance (Class 10, Class 12, and CGPA)\n"
        "2. Minimum requirements: Class 10: 60%, Class 12: 60%, CGPA: 6.32\n"
        "3. Must mention technical skills\n"
        "4. Should list projects or work experience\n"
        "5. Should include education details\n\n"
        "IMPORTANT: If academic marks are not mentioned in the resume, mark as INVALID.\n"
        "Return your response in this exact format:\n"
        "VALID: [true/false]\n"
        "FEEDBACK: [your detailed feedback]\n"
        "SKILLS: [list of skills detected]\n"
        "CLASS_10_PERCENTAGE: [percentage found in resume or NA]\n"
        "CLASS_12_PERCENTAGE: [percentage found in resume or NA]\n"
        "CGPA: [CGPA found in resume or NA]\n"
        "MARKS_MENTIONED: [true/false - whether academic marks are mentioned]\n"
        "MEETS_MINIMUM_CRITERIA: [true/false - whether marks meet minimum requirements]"
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
        
        # Extract academic details
        class_10_percentage = extract_percentage(extract_field(response_text, "CLASS_10_PERCENTAGE"))
        class_12_percentage = extract_percentage(extract_field(response_text, "CLASS_12_PERCENTAGE"))
        cgpa_str = extract_field(response_text, "CGPA")
        cgpa = extract_percentage(cgpa_str) if cgpa_str != "NA" else 0
        
        # Check if marks are mentioned
        marks_mentioned_line = extract_field(response_text, "MARKS_MENTIONED")
        marks_mentioned = 'true' in marks_mentioned_line.lower()
        
        # Validate minimum criteria
        meets_class_10 = class_10_percentage >= 60
        meets_class_12 = class_12_percentage >= 60
        meets_cgpa = cgpa >= 6.32
        
        academic_valid = meets_class_10 and meets_class_12 and meets_cgpa
        
        # Check other resume requirements
        valid_line = next((line for line in response_text.split('\n') 
                          if line.lower().startswith('valid:')), '')
        skills_valid = 'true' in valid_line.lower()
        
        # Overall validation: must have marks mentioned AND meet criteria AND have skills
        overall_valid = marks_mentioned and academic_valid and skills_valid
        
        feedback_parts = []
        if not marks_mentioned:
            feedback_parts.append("Academic marks (Class 10, Class 12, CGPA) must be mentioned in resume")
        if not meets_class_10 and class_10_percentage > 0:
            feedback_parts.append(f"Class 10 percentage ({class_10_percentage}%) below required 60%")
        if not meets_class_12 and class_12_percentage > 0:
            feedback_parts.append(f"Class 12 percentage ({class_12_percentage}%) below required 60%")
        if not meets_cgpa and cgpa > 0:
            feedback_parts.append(f"CGPA ({cgpa}) below required 6.32")
        if not skills_valid:
            feedback_parts.append("Technical skills not adequately mentioned")
        
        detailed_feedback = ". ".join(feedback_parts) if feedback_parts else "Resume meets all requirements"
        
        return {
            "valid": overall_valid,
            "feedback": detailed_feedback,
            "marks_mentioned": marks_mentioned,
            "academic_details": {
                "class_10": class_10_percentage,
                "class_12": class_12_percentage,
                "cgpa": cgpa,
                "meets_criteria": academic_valid
            },
            "full_ai_response": response_text
        }
    except Exception as e:
        return {
            "valid": False,
            "feedback": f"Error validating resume: {str(e)}"
        }

def validate_cover_letter_with_marks(text: str = None, images: list = None) -> dict:
    """Validate cover letter ensuring academic marks are present and meet requirements"""
    prompt = (
        "You are validating a student's cover letter for an internship application.\n"
        "CRITICAL REQUIREMENTS:\n"
        "1. The cover letter MUST mention academic performance (Class 10, Class 12, and CGPA)\n"
        "2. Minimum requirements: Class 10: 60%, Class 12: 60%, CGPA: 6.32\n"
        "3. Must include student's motivation/interest\n"
        "4. Should reference specific skills relevant to the position\n"
        "5. Should have proper formatting (greeting, closing)\n\n"
        "IMPORTANT: If academic marks are not mentioned in the cover letter, mark as INVALID.\n"
        "Return your response in this exact format:\n"
        "VALID: [true/false]\n"
        "FEEDBACK: [your detailed feedback]\n"
        "HIGHLIGHTS: [key points mentioned]\n"
        "CLASS_10_PERCENTAGE: [percentage found in cover letter or NA]\n"
        "CLASS_12_PERCENTAGE: [percentage found in cover letter or NA]\n"
        "CGPA: [CGPA found in cover letter or NA]\n"
        "MARKS_MENTIONED: [true/false - whether academic marks are mentioned]\n"
        "MEETS_MINIMUM_CRITERIA: [true/false - whether marks meet minimum requirements]"
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
        
        # Extract academic details
        class_10_percentage = extract_percentage(extract_field(response_text, "CLASS_10_PERCENTAGE"))
        class_12_percentage = extract_percentage(extract_field(response_text, "CLASS_12_PERCENTAGE"))
        cgpa_str = extract_field(response_text, "CGPA")
        cgpa = extract_percentage(cgpa_str) if cgpa_str != "NA" else 0
        
        # Check if marks are mentioned
        marks_mentioned_line = extract_field(response_text, "MARKS_MENTIONED")
        marks_mentioned = 'true' in marks_mentioned_line.lower()
        
        # Validate minimum criteria
        meets_class_10 = class_10_percentage >= 60
        meets_class_12 = class_12_percentage >= 60
        meets_cgpa = cgpa >= 6.32
        
        academic_valid = meets_class_10 and meets_class_12 and meets_cgpa
        
        # Check other cover letter requirements
        valid_line = next((line for line in response_text.split('\n') 
                          if line.lower().startswith('valid:')), '')
        content_valid = 'true' in valid_line.lower()
        
        # Overall validation: must have marks mentioned AND meet criteria AND have good content
        overall_valid = marks_mentioned and academic_valid and content_valid
        
        feedback_parts = []
        if not marks_mentioned:
            feedback_parts.append("Academic marks (Class 10, Class 12, CGPA) must be mentioned in cover letter")
        if not meets_class_10 and class_10_percentage > 0:
            feedback_parts.append(f"Class 10 percentage ({class_10_percentage}%) below required 60%")
        if not meets_class_12 and class_12_percentage > 0:
            feedback_parts.append(f"Class 12 percentage ({class_12_percentage}%) below required 60%")
        if not meets_cgpa and cgpa > 0:
            feedback_parts.append(f"CGPA ({cgpa}) below required 6.32")
        if not content_valid:
            feedback_parts.append("Cover letter content does not meet formatting/motivation requirements")
        
        detailed_feedback = ". ".join(feedback_parts) if feedback_parts else "Cover letter meets all requirements"
        
        return {
            "valid": overall_valid,
            "feedback": detailed_feedback,
            "marks_mentioned": marks_mentioned,
            "academic_details": {
                "class_10": class_10_percentage,
                "class_12": class_12_percentage,
                "cgpa": cgpa,
                "meets_criteria": academic_valid
            },
            "full_ai_response": response_text
        }
    except Exception as e:
        return {
            "valid": False,
            "feedback": f"Error validating cover letter: {str(e)}"
        }

#---------------------****THIS IS FOR CHECKING THE EXACT DATES IN LOR****--------------------------#
'''
def validate_lor(text: str = None, images: list = None, application_date: str = None) -> dict:
    """Validate letter of recommendation using text or vision with date validation"""
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
           "   - Any official endorsement letter\n"
        "4. Must mention internship start date and end date\n"
        "5. Dates should be clearly specified (look for phrases like 'from [date] to [date]', 'duration', 'period', etc.)\n\n"
        "Return your response in this exact format:\n"
        "VALID: [true/false]\n"
        
        "LETTERHEAD: [yes/no]\n"
        "AUTHORITY: [title and name of signing authority]\n"
        "START_DATE: [Mentioned start date]\n"
        "END_DATE: [Mentioned end date]\n"
        "DATES_MENTIONED: [true/false - whether both start and end dates are clearly mentioned]"
        "FEEDBACK: [your detailed feedback]\n"
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
        
        # Extract date information
        start_date_str = extract_field(response_text, "START_DATE")
        end_date_str = extract_field(response_text, "END_DATE")
        dates_mentioned_str = extract_field(response_text, "DATES_MENTIONED")
        dates_mentioned = 'true' in dates_mentioned_str.lower()
        
        # Basic LOR validation
        valid_line = next((line for line in response_text.split('\n') 
                          if line.lower().startswith('valid:')), '')
        basic_valid = 'true' in valid_line.lower() and 'false' not in valid_line.lower()
        
        # Date validation
        date_validation_result = {"valid": True, "feedback": ""}
        
        if not dates_mentioned:
            date_validation_result = {
                "valid": False, 
                "feedback": "Internship start date and end date must be mentioned in LOR"
            }
        elif application_date:
            # Parse application date and validate 30-day gap
            try:
                app_date = datetime.strptime(application_date, "%Y-%m-%d")
                required_start_date = app_date + timedelta(days=30)
                
                # Try to parse the start date from LOR
                start_date_parsed = None
                if start_date_str and start_date_str != "Not mentioned":
                    # Try multiple date formats
                    date_formats = ["%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d", 
                                  "%B %d, %Y", "%d %B %Y", "%b %d, %Y", "%d %b %Y"]
                    
                    for fmt in date_formats:
                        try:
                            start_date_parsed = datetime.strptime(start_date_str.strip(), fmt)
                            break
                        except ValueError:
                            continue
                
                if start_date_parsed:
                    if start_date_parsed < required_start_date:
                        date_validation_result = {
                            "valid": False,
                            "feedback": f"Internship start date ({start_date_str}) must be at least 30 days after application date ({application_date}). Required start date: {required_start_date.strftime('%Y-%m-%d')}"
                        }
                else:
                    date_validation_result = {
                        "valid": False,
                        "feedback": f"Could not parse start date format: {start_date_str}. Please use a standard date format."
                    }
                    
            except ValueError:
                date_validation_result = {
                    "valid": False,
                    "feedback": f"Invalid application date format: {application_date}. Expected format: YYYY-MM-DD"
                }
        
        # Overall validation
        overall_valid = basic_valid and dates_mentioned and date_validation_result["valid"]
        
        # Combine feedback
        feedback_parts = [response_text]
        if not date_validation_result["valid"]:
            feedback_parts.append(f"Date Validation Error: {date_validation_result['feedback']}")
        
        return {
            "valid": overall_valid,
            "dates_mentioned": dates_mentioned,
            "start_date": start_date_str,
            "end_date": end_date_str,
            "date_validation": date_validation_result,
            "feedback": "\n".join(feedback_parts),
            "basic_lor_valid": basic_valid
        }
    except Exception as e:
        return {
            "valid": False,
            "feedback": f"Error validating letter of recommendation: {str(e)}"
        }
'''
#--------------------------------------------------------------------------------------------------#

#---------------------****THIS IS FOR CHECKING THE MONTH VALIDIY IN LOR****------------------------#
'''
def validate_lor(text: str = None, images: list = None) -> dict:
    """Validate letter of recommendation using text or vision with automatic date validation"""
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
           "   - Any official endorsement letter\n"
        "4. Must mention internship start date and end date\n"
        "5. Dates should be clearly specified (look for phrases like 'from [date] to [date]', 'duration', 'period', etc.)\n\n"
        "Return your response in this exact format:\n"
        "VALID: [true/false]\n"
        "FEEDBACK: [your detailed feedback]\n"
        "LETTERHEAD: [yes/no]\n"
        "AUTHORITY: [title and name of signing authority]\n"
        "START_DATE: [internship start date mentioned in document or 'Not mentioned']\n"
        "END_DATE: [internship end date mentioned in document or 'Not mentioned']\n"
        "DATES_MENTIONED: [true/false - whether both start and end dates are clearly mentioned]"
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
        
        # Extract date information
        start_date_str = extract_field(response_text, "START_DATE")
        end_date_str = extract_field(response_text, "END_DATE")
        dates_mentioned_str = extract_field(response_text, "DATES_MENTIONED")
        dates_mentioned = 'true' in dates_mentioned_str.lower()
        
        # Basic LOR validation
        valid_line = next((line for line in response_text.split('\n') 
                          if line.lower().startswith('valid:')), '')
        basic_valid = 'true' in valid_line.lower() and 'false' not in valid_line.lower()
        
        # Automatic date validation using current system time
        date_validation_result = {"valid": True, "feedback": ""}
        current_date = datetime.now()
        
        if not dates_mentioned:
            date_validation_result = {
                "valid": False, 
                "feedback": "Internship start date and end date must be mentioned in LOR"
            }
        else:
            # Parse and validate start date
            start_date_parsed = None
            if start_date_str and start_date_str != "Not mentioned":
                # Try multiple date formats
                date_formats = ["%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d", 
                              "%B %d, %Y", "%d %B %Y", "%b %d, %Y", "%d %b %Y",
                              "%B %Y", "%b %Y"]  # Added month-year formats
                
                for fmt in date_formats:
                    try:
                        start_date_parsed = datetime.strptime(start_date_str.strip(), fmt)
                        break
                    except ValueError:
                        continue
            
            if start_date_parsed:
                # Check if start month is at least next month from current month
                current_month = current_date.month
                current_year = current_date.year
                start_month = start_date_parsed.month
                start_year = start_date_parsed.year
                
                # Calculate if start date is in next month or later
                months_difference = (start_year - current_year) * 12 + (start_month - current_month)
                
                if months_difference < 1:
                    current_month_name = current_date.strftime("%B %Y")
                    start_month_name = start_date_parsed.strftime("%B %Y")
                    date_validation_result = {
                        "valid": False,
                        "feedback": f"Internship start date ({start_month_name}) must be at least next month from current month ({current_month_name})"
                    }
                else:
                    date_validation_result = {
                        "valid": True,
                        "feedback": f"Start date validation passed. Internship starts in {start_date_parsed.strftime('%B %Y')}"
                    }
            else:
                date_validation_result = {
                    "valid": False,
                    "feedback": f"Could not parse start date format: '{start_date_str}'. Please use a standard date format."
                }
        
        # Overall validation
        overall_valid = basic_valid and dates_mentioned and date_validation_result["valid"]
        
        # Combine feedback
        feedback_parts = [response_text]
        if not date_validation_result["valid"]:
            feedback_parts.append(f"Date Validation Error: {date_validation_result['feedback']}")
        elif date_validation_result["feedback"]:
            feedback_parts.append(date_validation_result["feedback"])
        
        return {
            "valid": overall_valid,
            "feedback": "\n".join(feedback_parts),
            "dates_mentioned": dates_mentioned,
            "start_date": start_date_str,
            "end_date": end_date_str,
            "date_validation": date_validation_result,
            "basic_lor_valid": basic_valid,
            "current_month": current_date.strftime("%B %Y"),
            "validation_time": current_date.strftime("%Y-%m-%d %H:%M:%S")
        }
    except Exception as e:
        return {
            "valid": False,
            "feedback": f"Error validating letter of recommendation: {str(e)}"
        }
'''
#--------------------------------------------------------------------------------------------------#
def validate_lor(text: str = None, images: list = None) -> dict:
    """Validate letter of recommendation using text or vision with automatic date validation"""
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
           "   - Any official endorsement letter\n"
        "4. Must mention internship start date and end date\n"
        "5. Dates should be clearly specified (look for phrases like 'from [date] to [date]', 'duration', 'period', etc.)\n\n"
        "Return your response in this exact format:\n"
        "VALID: [true/false]\n"
        "FEEDBACK: [your detailed feedback]\n"
        "LETTERHEAD: [yes/no]\n"
        "AUTHORITY: [title and name of signing authority]\n"
        "START_DATE: [internship start date mentioned in document or 'Not mentioned']\n"
        "END_DATE: [internship end date mentioned in document or 'Not mentioned']\n"
        "DATES_MENTIONED: [true/false - whether both start and end dates are clearly mentioned]"
    )
    
    try:
        if text and is_text_extractable(text):
            full_prompt = f"{prompt}\n\nDocument content:\n{text}"
            response = model.generate_content(full_prompt)
            response_text = response.text.strip()
        elif images:
            response_text = process_document_with_vision(images, prompt)
        else:
            return {"valid": False, "feedback": "No content to validate", "issues": ["No content to validate"]}
        
        # Extract date information
        start_date_str = extract_field(response_text, "START_DATE")
        end_date_str = extract_field(response_text, "END_DATE")
        dates_mentioned_str = extract_field(response_text, "DATES_MENTIONED")
        dates_mentioned = 'true' in dates_mentioned_str.lower()
        
        # Basic LOR validation
        valid_line = next((line for line in response_text.split('\n') 
                          if line.lower().startswith('valid:')), '')
        basic_valid = 'true' in valid_line.lower() and 'false' not in valid_line.lower()
        
        # Get current date
        current_date = datetime.now()
        current_month = current_date.month
        current_year = current_date.year
        
        # Date validation with detailed issues tracking
        issues = []
        date_validation_valid = True
        
        if not dates_mentioned:
            issues.append("Internship start date and end date not mentioned in LOR")
            date_validation_valid = False
        else:
            # Parse and validate start date
            start_date_parsed = None
            if start_date_str and start_date_str != "Not mentioned":
                # Try multiple date formats
                date_formats = ["%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d", 
                              "%B %d, %Y", "%d %B %Y", "%b %d, %Y", "%d %b %Y",
                              "%B %Y", "%b %Y"]  # Added month-year formats
                
                for fmt in date_formats:
                    try:
                        start_date_parsed = datetime.strptime(start_date_str.strip(), fmt)
                        break
                    except ValueError:
                        continue
                
                if start_date_parsed:
                    start_month = start_date_parsed.month
                    start_year = start_date_parsed.year
                    
                    # Check if start date is at least next month
                    if start_year < current_year or (start_year == current_year and start_month <= current_month):
                        issues.append(f"Internship start date ({start_date_str}) must be at least next month from application date. Current: {current_date.strftime('%B %Y')}")
                        date_validation_valid = False
                else:
                    issues.append(f"Could not parse start date format: {start_date_str}")
                    date_validation_valid = False
            else:
                issues.append("Start date not mentioned in LOR")
                date_validation_valid = False
        
        # Check basic LOR requirements
        if not basic_valid:
            issues.append("LOR does not meet basic requirements (letterhead, authority signature, proper format)")
        
        # Overall validation
        overall_valid = basic_valid and dates_mentioned and date_validation_valid
        
        return {
            "valid": overall_valid,
            "feedback": response_text,
            "issues": issues,
            "dates_mentioned": dates_mentioned,
            "start_date": start_date_str,
            "end_date": end_date_str,
            "basic_lor_valid": basic_valid,
            "date_validation_valid": date_validation_valid
        }
    except Exception as e:
        return {
            "valid": False,
            "feedback": f"Error validating letter of recommendation: {str(e)}",
            "issues": [f"Error validating LOR: {str(e)}"]
        }


def validate_marksheet_for_backlogs(text: str = None, images: list = None, class_level: str = "10") -> dict:
    """Validate marksheet specifically checking for backlogs only"""
    prompt = (
        f"You are validating a Class {class_level} marksheet for backlog check only.\n"
        "CRITICAL REQUIREMENT:\n"
        "- Check if there are any current backlogs/failed subjects\n"
        "- If ANY backlogs exist, mark as INVALID\n\n"
        "Return your response in this exact format:\n"
        "VALID: [true/false]\n"
        "FEEDBACK: [your detailed feedback]\n"
        "BACKLOGS: [number of backlogs found]\n"
        "FAILED_SUBJECTS: [list of failed subjects or 'None']\n"
        "STUDENT_NAME: [name of student]\n"
        "SCHOOL_NAME: [name of school/institution]"
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
        
        # Extract backlog information
        backlogs_str = extract_field(response_text, "BACKLOGS")
        cleaned_backlogs = re.sub(r'[^\d]', '', backlogs_str)
        
        try:
            backlogs = int(cleaned_backlogs) if cleaned_backlogs else 0
        except ValueError:
            backlogs = 0
        
        # Validation based on backlogs only
        no_backlogs = backlogs == 0
        
        return {
            "valid": no_backlogs,
            "feedback": f"Backlog check: {'Pass' if no_backlogs else 'Fail'} - {backlogs} backlogs found",
            "backlogs": backlogs,
            "failed_subjects": extract_field(response_text, "FAILED_SUBJECTS"),
            "student_name": extract_field(response_text, "STUDENT_NAME"),
            "institution_name": extract_field(response_text, "SCHOOL_NAME"),
            "class_level": class_level
        }
    except Exception as e:
        return {
            "valid": False,
            "feedback": f"Error validating marksheet: {str(e)}",
            "backlogs": 999,  # Assume backlogs if error
            "class_level": class_level
        }

def validate_all_marksheets_for_backlogs(class_10_file: UploadFile, class_12_file: UploadFile, college_file: UploadFile) -> dict:
    """Validate all marksheets specifically for backlog check only"""
    logger.info("Starting backlog validation for all marksheets")
    
    # Process Class 10 marksheet
    class_10_text, class_10_text_extractable = extract_text_from_pdf(class_10_file)
    if not class_10_text_extractable:
        logger.info("Class 10 marksheet: Text not extractable, using vision")
        class_10_images = pdf_to_images(class_10_file)
        class_10_result = validate_marksheet_for_backlogs(images=class_10_images, class_level="10")
    else:
        logger.info("Class 10 marksheet: Using text-based validation")
        class_10_result = validate_marksheet_for_backlogs(text=class_10_text, class_level="10")
    
    # Process Class 12 marksheet
    class_12_text, class_12_text_extractable = extract_text_from_pdf(class_12_file)
    if not class_12_text_extractable:
        logger.info("Class 12 marksheet: Text not extractable, using vision")
        class_12_images = pdf_to_images(class_12_file)
        class_12_result = validate_marksheet_for_backlogs(images=class_12_images, class_level="12")
    else:
        logger.info("Class 12 marksheet: Using text-based validation")
        class_12_result = validate_marksheet_for_backlogs(text=class_12_text, class_level="12")
    
    # Process College marksheet
    college_text, college_text_extractable = extract_text_from_pdf(college_file)
    if not college_text_extractable:
        logger.info("College marksheet: Text not extractable, using vision")
        college_images = pdf_to_images(college_file)
        college_result = validate_marksheet_for_backlogs(images=college_images, class_level="College")
    else:
        logger.info("College marksheet: Using text-based validation")
        college_result = validate_marksheet_for_backlogs(text=college_text, class_level="College")
    
    logger.info(f"Class 10 backlog check: {class_10_result}")
    logger.info(f"Class 12 backlog check: {class_12_result}")
    logger.info(f"College backlog check: {college_result}")
    
    all_valid = (class_10_result["valid"] and 
                class_12_result["valid"] and 
                college_result["valid"])
    
    total_backlogs = (class_10_result.get("backlogs", 0) + 
                     class_12_result.get("backlogs", 0) + 
                     college_result.get("backlogs", 0))
    
    return {
        "valid": all_valid,
        "total_backlogs": total_backlogs,
        "marksheet_results": {
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
            "passes_backlog_check": all_valid,
            "total_backlogs_found": total_backlogs
        }
    }

def evaluate_overall_application(resume_result: dict, lor_result: dict, marksheet_result: dict, 
                               resume_filename: str, lor_filename: str, 
                               class_10_filename: str, class_12_filename: str, college_filename: str) -> dict:
    """Evaluate all documents with strict academic mark requirements and track invalid files with detailed reasons"""
    
    # Check if resume/cover letter has marks mentioned and meets criteria
    marks_mentioned = resume_result.get("marks_mentioned", False)
    academic_criteria_met = resume_result.get("academic_details", {}).get("meets_criteria", False)
    
    # Track invalid documents and their reasons
    invalid_documents = []
    validation_details = {}
    all_rejection_reasons = []  # Detailed reasons for rejection
    
    # Check resume/cover letter validity
    resume_valid = resume_result["valid"] and marks_mentioned and academic_criteria_met
    validation_details["resume_cover_letter"] = {
        "filename": resume_filename,
        "valid": resume_valid,
        "marks_mentioned": marks_mentioned,
        "academic_details": resume_result.get("academic_details", {}),
        "feedback": resume_result.get("feedback", ""),
        "issues": []
    }
    
    if not resume_result["valid"]:
        validation_details["resume_cover_letter"]["issues"].append("Document validation failed")
        all_rejection_reasons.append(f"{resume_filename}: Document validation failed")
    if not marks_mentioned:
        validation_details["resume_cover_letter"]["issues"].append("Academic marks not mentioned")
        all_rejection_reasons.append(f"{resume_filename}: Academic marks not mentioned")
    if not academic_criteria_met and marks_mentioned:
        academic_details = resume_result.get("academic_details", {})
        class_10 = academic_details.get("class_10", 0)
        class_12 = academic_details.get("class_12", 0)
        cgpa = academic_details.get("cgpa", 0)
        
        mark_issues = []
        if class_10 > 0 and class_10 < 60:
            mark_issues.append(f"Class 10: {class_10}% (required: 60%)")
        if class_12 > 0 and class_12 < 60:
            mark_issues.append(f"Class 12: {class_12}% (required: 60%)")
        if cgpa > 0 and cgpa < 6.32:
            mark_issues.append(f"CGPA: {cgpa} (required: 6.32)")
        
        if mark_issues:
            issue_text = f"Academic marks below requirements: {', '.join(mark_issues)}"
            validation_details["resume_cover_letter"]["issues"].append(issue_text)
            all_rejection_reasons.append(f"{resume_filename}: {issue_text}")
    
    if not resume_valid:
        invalid_documents.append(resume_filename)
    
    # Check LOR validity with detailed issues
    lor_valid = lor_result["valid"]
    lor_issues = lor_result.get("issues", [])
    validation_details["letter_of_recommendation"] = {
        "filename": lor_filename,
        "valid": lor_valid,
        "feedback": lor_result.get("feedback", ""),
        "issues": lor_issues
    }
    if not lor_valid:
        invalid_documents.append(lor_filename)
        for issue in lor_issues:
            all_rejection_reasons.append(f"{lor_filename}: {issue}")    
    marksheet_valid = marksheet_result["valid"]
    validation_details["marksheets"] = {
        "filenames": {
            "class_10": class_10_filename,
            "class_12": class_12_filename,
            "college": college_filename
        },
        "valid": marksheet_valid,
        "total_backlogs": marksheet_result.get("total_backlogs", 0),
        "details": marksheet_result.get("marksheet_results", {}),
        "feedback": marksheet_result.get("overall_feedback", {}),
        "issues": []
    }    
    marksheet_results = marksheet_result.get("marksheet_results", {})
    if not marksheet_results.get("class_10", {}).get("valid", True):
        backlogs_10 = marksheet_results.get("class_10", {}).get("backlogs", 0)
        issue = f"Class 10 marksheet has {backlogs_10} backlog(s)"
        validation_details["marksheets"]["issues"].append(issue)
        all_rejection_reasons.append(f"{class_10_filename}: {issue}")
        invalid_documents.append(class_10_filename)
    
    if not marksheet_results.get("class_12", {}).get("valid", True):
        backlogs_12 = marksheet_results.get("class_12", {}).get("backlogs", 0)
        issue = f"Class 12 marksheet has {backlogs_12} backlog(s)"
        validation_details["marksheets"]["issues"].append(issue)
        all_rejection_reasons.append(f"{class_12_filename}: {issue}")
        invalid_documents.append(class_12_filename)
    if not marksheet_results.get("college", {}).get("valid", True):
        backlogs_college = marksheet_results.get("college", {}).get("backlogs", 0)
        issue = f"College marksheet has {backlogs_college} backlog(s)"
        validation_details["marksheets"]["issues"].append(issue)
        all_rejection_reasons.append(f"{college_filename}: {issue}")
        invalid_documents.append(college_filename)
    # Remove duplicates from invalid_documents
    invalid_documents = list(set(invalid_documents))
    # Overall validation
    all_valid = resume_valid and lor_valid and marksheet_valid
    overall_status = "accepted" if all_valid else "rejected"
    # Generate summary
    if all_valid:
        summary = "Application meets all requirements: academic marks mentioned and meet criteria, dates valid, no backlogs found."
    else:
        summary = f"Application rejected. {len(all_rejection_reasons)} specific issues found across {len(invalid_documents)} documents."
    return {
        "valid": all_valid,
        "status": overall_status,
        "summary": summary,
        "invalid_documents": invalid_documents,
        "total_invalid_documents": len(invalid_documents),
        "rejection_reasons": all_rejection_reasons,  # Detailed list of all issues
        "validation_details": validation_details,
        "marks_mentioned_in_resume": marks_mentioned,
        "academic_criteria_met": academic_criteria_met,
        "detailed_feedback": {
            "resume_cover_letter": validation_details["resume_cover_letter"],
            "letter_of_recommendation": validation_details["letter_of_recommendation"],
            "marksheets_backlog_check": validation_details["marksheets"]
        }
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
        logger.info("Starting document validation with strict mark requirements")
        # Store filenames for tracking
        resume_filename = resume.filename
        lor_filename = lor.filename
        class_10_filename = class_10.filename
        class_12_filename = class_12.filename
        college_filename = college_marksheets.filename
        # Process resume (same as before)
        resume_text, resume_text_extractable = extract_text_from_pdf(resume)
        logger.info(f"Resume text extractable: {resume_text_extractable}")
        if resume_text_extractable:
            doc_type = classify_document(text=resume_text)
            resume_result = (
                validate_resume_with_marks(text=resume_text)
                if doc_type == "RESUME"
                else validate_cover_letter_with_marks(text=resume_text)
            )
        else:
            logger.info("Resume: Using vision-based processing")
            resume_images = pdf_to_images(resume)
            doc_type = classify_document(images=resume_images)
            resume_result = (
                validate_resume_with_marks(images=resume_images)
                if doc_type == "RESUME"
                else validate_cover_letter_with_marks(images=resume_images)
            )
        # Extract skills and course information from resume
        logger.info("Extracting skills and course information")
        if resume_text_extractable:
            skills_info = extract_skills_and_course_info(text=resume_text)
        else:
            skills_info = extract_skills_and_course_info(images=resume_images)
        # Process LOR without application_date parameter
        lor_text, lor_text_extractable = extract_text_from_pdf(lor)
        logger.info(f"LOR text extractable: {lor_text_extractable}")
        if lor_text_extractable:
            lor_result = validate_lor(text=lor_text)  # Remove application_date parameter
        else:
            logger.info("LOR: Using vision-based processing")
            lor_images = pdf_to_images(lor)
            lor_result = validate_lor(images=lor_images)  # Removed application_date parameter
        # Process marksheets (same as before)
        marksheet_result = validate_all_marksheets_for_backlogs(
            class_10, class_12, college_marksheets
        )
        logger.info("Document validation complete")
        # Evaluate result with filenames
        result = evaluate_overall_application(
            resume_result, lor_result, marksheet_result,
            resume_filename, lor_filename, class_10_filename, 
            class_12_filename, college_filename
        )
        result["applicant_profile"] = {
            "skills_analysis": skills_info,
        }
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
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8005)