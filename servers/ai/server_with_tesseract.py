import os
import fitz  # PyMuPDF
import google.generativeai as genai
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import logging
import re
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import json
import pytesseract
from PIL import Image
import io
import base64

# Configure comprehensive logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY not found in environment variables")

# Configure Gemini with retry mechanism
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.0-flash")

# FastAPI app with enhanced configuration
app = FastAPI(
    title="NRSC Internship AI Validator",
    description="AI-powered validator for NRSC internship applications",
    version="2.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Constants for validation rules
ELIGIBILITY_RULES = {
    "internship": {
        "min_percentage": 60.0,
        "min_cgpa": 6.32,
        "duration_days": 45,
        "advance_days": 30
    },
    "project": {
        "min_percentage": 60.0,
        "min_cgpa": 6.32,
        "duration_range": (90, 365),  # 3-12 months in days
        "advance_days": 30
    }
}

DEGREE_REQUIREMENTS = {
    "BE": {"min_semesters": 6, "type": "engineering"},
    "BTECH": {"min_semesters": 6, "type": "engineering"},
    "MCA": {"min_semesters": 1, "type": "postgrad"},
    "ME": {"min_semesters": 1, "type": "postgrad"},
    "MTECH": {"min_semesters": 1, "type": "postgrad"},
    "BSC": {"min_semesters": 6, "type": "final_year_only"},
    "DIPLOMA": {"min_semesters": 4, "type": "final_year_only"},
    "MSC": {"min_semesters": 1, "type": "postgrad"},
    "PHD": {"min_semesters": 2, "type": "phd"}
}

class ValidationError(Exception):
    """Custom exception for validation errors"""
    pass

class DocumentProcessor:
    """Enhanced document processing with OCR and multiple extraction methods"""
    
    def __init__(self):
        # Configure Tesseract if available
        self.ocr_available = self._check_ocr_availability()
        
    def _check_ocr_availability(self) -> bool:
        """Check if OCR is available"""
        try:
            pytesseract.get_tesseract_version()
            return True
        except Exception:
            logger.warning("Tesseract OCR not available. Only text-based PDFs will be processed.")
            return False
    
    def extract_text_from_pdf(self, file: UploadFile) -> str:
        """Extract text from PDF with multiple methods including OCR"""
        try:
            # Reset file pointer
            file.file.seek(0)
            file_content = file.file.read()
            
            if len(file_content) == 0:
                raise ValidationError("Uploaded file is empty")
            
            # Try direct text extraction first
            text_content = self._extract_direct_text(file_content)
            
            # If direct extraction fails or yields insufficient text, try OCR
            if not text_content or len(text_content.strip()) < 50:
                logger.info("Direct text extraction insufficient, attempting OCR")
                ocr_text = self._extract_text_via_ocr(file_content)
                if ocr_text and len(ocr_text.strip()) > len(text_content.strip()):
                    text_content = ocr_text
            
            # If still no text, try AI-based extraction
            if not text_content or len(text_content.strip()) < 50:
                logger.info("Attempting AI-based text extraction")
                ai_text = self._extract_text_via_ai(file_content)
                if ai_text and len(ai_text.strip()) > len(text_content.strip()):
                    text_content = ai_text
            
            if not text_content or len(text_content.strip()) < 20:
                raise ValidationError(
                    "No readable text found in PDF. Please ensure the document is not a scanned image "
                    "or try uploading a text-based PDF."
                )
                
            logger.info(f"Successfully extracted {len(text_content)} characters from PDF")
            return text_content.strip()
            
        except ValidationError:
            raise
        except Exception as e:
            logger.error(f"Error extracting text from PDF: {str(e)}")
            raise ValidationError(f"Failed to process PDF: {str(e)}")
    
    def _extract_direct_text(self, file_content: bytes) -> str:
        """Extract text directly from PDF"""
        try:
            doc = fitz.open(stream=file_content, filetype="pdf")
            
            if doc.page_count == 0:
                raise ValidationError("PDF contains no pages")
            
            text_content = ""
            for page_num in range(doc.page_count):
                page = doc[page_num]
                page_text = page.get_text()
                if page_text.strip():
                    text_content += page_text + "\n"
            
            doc.close()
            return text_content.strip()
            
        except Exception as e:
            logger.warning(f"Direct text extraction failed: {str(e)}")
            return ""
    
    def _extract_text_via_ocr(self, file_content: bytes) -> str:
        """Extract text using OCR from PDF images"""
        if not self.ocr_available:
            return ""
        
        try:
            doc = fitz.open(stream=file_content, filetype="pdf")
            text_content = ""
            
            for page_num in range(min(doc.page_count, 10)):  # Limit to first 10 pages for performance
                page = doc[page_num]
                
                # Convert page to image
                mat = fitz.Matrix(2, 2)  # Increase resolution for better OCR
                pix = page.get_pixmap(matrix=mat)
                img_data = pix.tobytes("png")
                
                # Use PIL to create image
                image = Image.open(io.BytesIO(img_data))
                
                # Perform OCR
                ocr_text = pytesseract.image_to_string(image, config='--psm 6')
                if ocr_text.strip():
                    text_content += ocr_text + "\n"
            
            doc.close()
            return text_content.strip()
            
        except Exception as e:
            logger.warning(f"OCR extraction failed: {str(e)}")
            return ""
    
    def _extract_text_via_ai(self, file_content: bytes) -> str:
        """Extract text using AI vision capabilities"""
        try:
            doc = fitz.open(stream=file_content, filetype="pdf")
            text_content = ""
            
            # Process first few pages only due to API limits
            for page_num in range(min(doc.page_count, 3)):
                page = doc[page_num]
                
                # Convert page to image
                mat = fitz.Matrix(2, 2)
                pix = page.get_pixmap(matrix=mat)
                img_data = pix.tobytes("png")
                
                # Convert to base64 for AI processing
                img_base64 = base64.b64encode(img_data).decode()
                
                # Use AI to extract text from image
                ai_text = self._ai_extract_from_image(img_base64)
                if ai_text:
                    text_content += ai_text + "\n"
            
            doc.close()
            return text_content.strip()
            
        except Exception as e:
            logger.warning(f"AI text extraction failed: {str(e)}")
            return ""
    
    def _ai_extract_from_image(self, img_base64: str) -> str:
        """Use AI to extract text from image"""
        try:
            # Note: This is a placeholder for AI-based image text extraction
            # You would need to implement this using Google Vision API or similar
            # For now, we'll return empty string as fallback
            logger.info("AI-based image text extraction not implemented")
            return ""
        except Exception as e:
            logger.warning(f"AI image extraction failed: {str(e)}")
            return ""
    
    def extract_text_with_fallback(self, file: UploadFile) -> str:
        """Extract text with comprehensive fallback methods"""
        methods = [
            ("Direct text extraction", self._try_direct_extraction),
            ("OCR extraction", self._try_ocr_extraction),
            ("AI extraction", self._try_ai_extraction)
        ]
        
        for method_name, method in methods:
            try:
                logger.info(f"Attempting {method_name}")
                text = method(file)
                if text and len(text.strip()) >= 20:
                    logger.info(f"{method_name} successful: {len(text)} characters")
                    return text
                else:
                    logger.info(f"{method_name} yielded insufficient text")
            except Exception as e:
                logger.warning(f"{method_name} failed: {str(e)}")
                continue
        
        # If all methods fail, provide helpful error message
        raise ValidationError(
            "Unable to extract text from PDF using any available method. "
            "Please ensure your document is:\n"
            "1. A valid PDF file\n"
            "2. Not password protected\n"
            "3. Contains readable text (not just images)\n"
            "4. Not corrupted\n"
            "Try converting your document to a text-based PDF if it's a scanned image."
        )
    
    def _try_direct_extraction(self, file: UploadFile) -> str:
        """Try direct text extraction"""
        file.file.seek(0)
        file_content = file.file.read()
        return self._extract_direct_text(file_content)
    
    def _try_ocr_extraction(self, file: UploadFile) -> str:
        """Try OCR extraction"""
        if not self.ocr_available:
            return ""
        file.file.seek(0)
        file_content = file.file.read()
        return self._extract_text_via_ocr(file_content)
    
    def _try_ai_extraction(self, file: UploadFile) -> str:
        """Try AI-based extraction"""
        file.file.seek(0)
        file_content = file.file.read()
        return self._extract_text_via_ai(file_content)

class AIResponseParser:
    """Enhanced AI response parsing with better error handling"""
    
    @staticmethod
    def extract_field(response_text: str, field_name: str) -> str:
        """Extract field with multiple fallback patterns"""
        if not response_text:
            return ""
        
        patterns = [
            rf"{field_name}:\s*(.+?)(?:\n|$)",
            rf"{field_name.upper()}:\s*(.+?)(?:\n|$)",
            rf"{field_name.lower()}:\s*(.+?)(?:\n|$)",
            rf"**{field_name}**:\s*(.+?)(?:\n|$)",
            rf"**{field_name.upper()}**:\s*(.+?)(?:\n|$)"
        ]
        
        for pattern in patterns:
            match = re.search(pattern, response_text, re.IGNORECASE | re.MULTILINE)
            if match:
                return match.group(1).strip()
        
        return ""
    
    @staticmethod
    def parse_boolean(text: str) -> bool:
        """Parse boolean from various text formats"""
        if not text:
            return False
        
        text = text.lower().strip()
        true_indicators = ['true', 'yes', 'valid', 'pass', 'passed', 'approved', 'accept']
        false_indicators = ['false', 'no', 'invalid', 'fail', 'failed', 'rejected', 'reject']
        
        for indicator in true_indicators:
            if indicator in text:
                return True
        
        for indicator in false_indicators:
            if indicator in text:
                return False
        
        return False
    
    @staticmethod
    def extract_percentage(text: str) -> float:
        """Extract percentage with multiple pattern matching"""
        if not text:
            return 0.0
        
        # Remove common prefixes and clean the text
        text = re.sub(r'[^\d.,%-]', '', text)
        
        patterns = [
            r'(\d+\.?\d*)\s*%',
            r'(\d+\.?\d*)\s*percent',
            r'(\d+\.?\d*)(?=\s*$)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    return float(match.group(1))
                except ValueError:
                    continue
        
        return 0.0
    
    @staticmethod
    def extract_cgpa(text: str) -> float:
        """Extract CGPA with validation"""
        if not text:
            return 0.0
        
        # Look for CGPA patterns
        patterns = [
            r'(\d+\.?\d*)\s*(?:cgpa|gpa|grade)',
            r'cgpa:\s*(\d+\.?\d*)',
            r'gpa:\s*(\d+\.?\d*)',
            r'(\d+\.?\d*)(?:\s*/\s*10)?'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    cgpa = float(match.group(1))
                    # Validate CGPA range (typically 0-10)
                    if 0 <= cgpa <= 10:
                        return cgpa
                except ValueError:
                    continue
        
        return 0.0

class DocumentClassifier:
    """Enhanced document classification"""
    
    def __init__(self):
        self.parser = AIResponseParser()
    
    def classify_document(self, text: str) -> str:
        """Classify document type with better accuracy"""
        if not text or len(text.strip()) < 50:
            raise ValidationError("Document text too short for classification")
        
        prompt = f"""
        Analyze this document and determine its type. Consider these characteristics:
        
        RESUME indicators:
        - Contains sections like "Experience", "Skills", "Projects", "Education"
        - Lists technical skills, programming languages, tools
        - Has work experience or project descriptions
        - Contains contact information at the top
        - Structured format with bullet points
        
        COVER LETTER indicators:
        - Formal letter format with greeting and closing
        - Addresses specific position or opportunity
        - Explains motivation and interest
        - Written in paragraph form
        - Contains phrases like "I am writing to", "I am interested in"
        
        ACADEMIC TRANSCRIPT/MARKSHEET indicators:
        - Contains grades, marks, or scores
        - Lists subjects and their respective marks
        - Has institutional letterhead
        - Contains CGPA/GPA or percentage
        - Academic year/semester information
        
        Document content (first 1000 characters):
        {text[:1000]}
        
        Respond with ONLY ONE of these words: RESUME, COVERLETTER, MARKSHEET
        """
        
        try:
            response = model.generate_content(prompt)
            doc_type = response.text.strip().upper()
            
            valid_types = ['RESUME', 'COVERLETTER', 'MARKSHEET']
            for valid_type in valid_types:
                if valid_type in doc_type:
                    return valid_type
            
            # Default classification based on content analysis
            return self._fallback_classification(text)
            
        except Exception as e:
            logger.error(f"AI classification failed: {str(e)}")
            return self._fallback_classification(text)
    
    def _fallback_classification(self, text: str) -> str:
        """Fallback classification using keyword analysis"""
        text_lower = text.lower()
        
        resume_keywords = ['experience', 'skills', 'projects', 'technical', 'programming']
        cover_keywords = ['dear', 'sincerely', 'application', 'position', 'opportunity']
        marksheet_keywords = ['marks', 'grade', 'cgpa', 'percentage', 'semester', 'subject']
        
        resume_score = sum(1 for keyword in resume_keywords if keyword in text_lower)
        cover_score = sum(1 for keyword in cover_keywords if keyword in text_lower)
        marksheet_score = sum(1 for keyword in marksheet_keywords if keyword in text_lower)
        
        if marksheet_score >= 2:
            return 'MARKSHEET'
        elif cover_score >= 2:
            return 'COVERLETTER'
        else:
            return 'RESUME'

class ResumeValidator:
    """Enhanced resume validation"""
    
    def __init__(self):
        self.parser = AIResponseParser()
    
    def validate(self, text: str) -> Dict:
        """Validate resume with comprehensive checks"""
        prompt = f"""
        You are validating a student's resume for NRSC internship application.
        
        CRITICAL REQUIREMENTS:
        1. Must contain technical skills (programming languages, tools, technologies)
        2. Must have educational background with marks/CGPA
        3. Should contain projects or relevant experience
        4. Must have contact information
        5. Should demonstrate relevant competencies for technical internship
        
        EVALUATION CRITERIA:
        - Technical Skills: Look for programming languages, software tools, frameworks
        - Education: Check for academic qualifications and performance
        - Projects: Evaluate technical projects and their descriptions
        - Experience: Consider internships, training, or work experience
        - Presentation: Assess overall structure and completeness
        
        Document content:
        {text}
        
        Provide detailed analysis in this EXACT format:
        VALID: [true/false]
        FEEDBACK: [Detailed feedback explaining strengths and weaknesses]
        TECHNICAL_SKILLS: [List all technical skills found]
        EDUCATION_LEVEL: [Highest education level mentioned]
        PROJECTS_COUNT: [Number of projects mentioned]
        CONTACT_INFO: [yes/no - whether contact information is present]
        OVERALL_SCORE: [Score out of 10]
        MISSING_ELEMENTS: [List any critical missing elements]
        """
        
        try:
            response = model.generate_content(prompt)
            response_text = response.text.strip()
            
            # Parse response
            is_valid = self.parser.parse_boolean(self.parser.extract_field(response_text, "VALID"))
            technical_skills = self.parser.extract_field(response_text, "TECHNICAL_SKILLS")
            feedback = self.parser.extract_field(response_text, "FEEDBACK")
            education_level = self.parser.extract_field(response_text, "EDUCATION_LEVEL")
            projects_count = self.parser.extract_field(response_text, "PROJECTS_COUNT")
            contact_info = self.parser.extract_field(response_text, "CONTACT_INFO")
            overall_score = self.parser.extract_field(response_text, "OVERALL_SCORE")
            missing_elements = self.parser.extract_field(response_text, "MISSING_ELEMENTS")
            
            # Additional validation based on content length and structure
            if len(text) < 200:
                is_valid = False
                feedback += " Resume is too brief and lacks sufficient detail."
            
            if not technical_skills:
                is_valid = False
                feedback += " No technical skills identified in the resume."
            
            return {
                "valid": is_valid,
                "feedback": feedback,
                "details": {
                    "technical_skills": technical_skills,
                    "education_level": education_level,
                    "projects_count": projects_count,
                    "has_contact_info": contact_info.lower() == 'yes',
                    "overall_score": overall_score,
                    "missing_elements": missing_elements
                },
                "raw_response": response_text
            }
            
        except Exception as e:
            logger.error(f"Resume validation error: {str(e)}")
            return {
                "valid": False,
                "feedback": f"Error validating resume: {str(e)}",
                "details": {},
                "raw_response": ""
            }

class LORValidator:
    """Enhanced Letter of Recommendation validator"""
    
    def __init__(self):
        self.parser = AIResponseParser()
    
    def validate(self, text: str) -> Dict:
        """Validate LOR with strict NRSC requirements"""
        prompt = f"""
        You are validating a Letter of Recommendation for NRSC internship application.
        
        CRITICAL NRSC REQUIREMENTS:
        1. MUST have official institutional letterhead
        2. MUST be signed by one of these authorities ONLY:
           - Head of Department (HOD)
           - Principal
           - Dean
           - Placement Officer
        3. MUST be addressed to "Group Director, Training, Education and Outreach Group, NRSC"
        4. MUST mention duration of internship/project with start and end dates
        5. Should follow proper official letter format
        6. Must contain student's academic details
        
        NAMING CONVENTION CHECK:
        - Should follow format: CollegeAbbreviation_Studentname_Branch.pdf
        
        Document content:
        {text}
        
        Provide analysis in this EXACT format:
        VALID: [true/false]
        FEEDBACK: [Detailed feedback on all requirements]
        HAS_LETTERHEAD: [yes/no]
        AUTHORITY_NAME: [Name of signing authority]
        AUTHORITY_DESIGNATION: [Exact designation of signing authority]
        ADDRESSED_TO_NRSC: [yes/no]
        DURATION_MENTIONED: [yes/no]
        START_DATE: [Start date if mentioned]
        END_DATE: [End date if mentioned]
        STUDENT_NAME: [Student name mentioned in letter]
        COLLEGE_NAME: [Institution name]
        BRANCH_COURSE: [Course/branch mentioned]
        LETTER_FORMAT: [Proper/Improper]
        """
        
        try:
            response = model.generate_content(prompt)
            response_text = response.text.strip()
            
            # Parse all fields
            is_valid = self.parser.parse_boolean(self.parser.extract_field(response_text, "VALID"))
            has_letterhead = self.parser.extract_field(response_text, "HAS_LETTERHEAD").lower() == 'yes'
            authority_name = self.parser.extract_field(response_text, "AUTHORITY_NAME")
            authority_designation = self.parser.extract_field(response_text, "AUTHORITY_DESIGNATION")
            addressed_to_nrsc = self.parser.extract_field(response_text, "ADDRESSED_TO_NRSC").lower() == 'yes'
            duration_mentioned = self.parser.extract_field(response_text, "DURATION_MENTIONED").lower() == 'yes'
            
            # Validate authority designation
            valid_authorities = ['head of department', 'hod', 'principal', 'dean', 'placement officer']
            authority_valid = any(auth in authority_designation.lower() for auth in valid_authorities)
            
            # Override validation if critical requirements not met
            if not has_letterhead or not authority_valid or not addressed_to_nrsc:
                is_valid = False
            
            feedback = self.parser.extract_field(response_text, "FEEDBACK")
            if not authority_valid:
                feedback += f" Invalid signing authority: {authority_designation}. Must be HOD/Principal/Dean/Placement Officer."
            
            return {
                "valid": is_valid and authority_valid,
                "feedback": feedback,
                "details": {
                    "has_letterhead": has_letterhead,
                    "authority_name": authority_name,
                    "authority_designation": authority_designation,
                    "authority_valid": authority_valid,
                    "addressed_to_nrsc": addressed_to_nrsc,
                    "duration_mentioned": duration_mentioned,
                    "start_date": self.parser.extract_field(response_text, "START_DATE"),
                    "end_date": self.parser.extract_field(response_text, "END_DATE"),
                    "student_name": self.parser.extract_field(response_text, "STUDENT_NAME"),
                    "college_name": self.parser.extract_field(response_text, "COLLEGE_NAME"),
                    "branch_course": self.parser.extract_field(response_text, "BRANCH_COURSE"),
                    "letter_format": self.parser.extract_field(response_text, "LETTER_FORMAT")
                },
                "raw_response": response_text
            }
            
        except Exception as e:
            logger.error(f"LOR validation error: {str(e)}")
            return {
                "valid": False,
                "feedback": f"Error validating letter of recommendation: {str(e)}",
                "details": {},
                "raw_response": ""
            }

class MarksheetValidator:
    """Enhanced marksheet validation with comprehensive academic checks"""
    
    def __init__(self):
        self.parser = AIResponseParser()
    
    def validate_school_marksheet(self, text: str, class_level: str) -> Dict:
        """Validate 10th/12th marksheet with enhanced accuracy"""
        logger.info(f"Validating Class {class_level} marksheet")
        
        prompt = f"""
        You are validating a Class {class_level} marksheet for NRSC internship application.
        
        REQUIREMENTS:
        1. Must contain student's full name
        2. Must have school/board name clearly mentioned
        3. Must show overall percentage or grade
        4. Minimum 60% required for eligibility
        5. Must have year of passing
        6. Should have subject-wise marks
        7. Must be an official document (with school seal/signature)
        
        Document content:
        {text}
        
        Analyze carefully and respond in this EXACT format:
        VALID: [true/false]
        FEEDBACK: [Detailed analysis of the marksheet]
        STUDENT_NAME: [Full name of student]
        SCHOOL_BOARD: [Name of school/board]
        PERCENTAGE: [Overall percentage - number only]
        GRADE: [Overall grade if percentage not available]
        YEAR_OF_PASSING: [Year of examination]
        SUBJECTS_COUNT: [Number of subjects listed]
        HIGHEST_MARKS: [Highest marks in any subject]
        LOWEST_MARKS: [Lowest marks in any subject]
        OFFICIAL_STATUS: [Official/Unofficial - based on seals, signatures]
        MEETS_MINIMUM: [yes/no - whether meets 60% requirement]
        """
        
        try:
            response = model.generate_content(prompt)
            response_text = response.text.strip()
            
            # Extract and validate percentage
            percentage_str = self.parser.extract_field(response_text, "PERCENTAGE")
            percentage = self.parser.extract_percentage(percentage_str)
            
            # Check if meets minimum requirement
            meets_minimum = percentage >= 60.0
            
            # Extract other details
            student_name = self.parser.extract_field(response_text, "STUDENT_NAME")
            school_board = self.parser.extract_field(response_text, "SCHOOL_BOARD")
            year_of_passing = self.parser.extract_field(response_text, "YEAR_OF_PASSING")
            
            # Validate year of passing
            current_year = datetime.now().year
            try:
                year_int = int(year_of_passing) if year_of_passing else 0
                year_valid = 1990 <= year_int <= current_year
            except ValueError:
                year_valid = False
            
            # Overall validation
            is_valid = (meets_minimum and 
                       bool(student_name.strip()) and 
                       bool(school_board.strip()) and 
                       year_valid)
            
            feedback = self.parser.extract_field(response_text, "FEEDBACK")
            if not meets_minimum:
                feedback += f" Does not meet minimum 60% requirement (obtained: {percentage}%)."
            if not year_valid:
                feedback += f" Invalid or missing year of passing: {year_of_passing}."
            
            return {
                "valid": is_valid,
                "percentage": percentage,
                "meets_minimum": meets_minimum,
                "student_name": student_name,
                "school_board": school_board,
                "year_of_passing": year_of_passing,
                "year_valid": year_valid,
                "feedback": feedback,
                "class_level": class_level,
                "details": {
                    "subjects_count": self.parser.extract_field(response_text, "SUBJECTS_COUNT"),
                    "highest_marks": self.parser.extract_field(response_text, "HIGHEST_MARKS"),
                    "lowest_marks": self.parser.extract_field(response_text, "LOWEST_MARKS"),
                    "official_status": self.parser.extract_field(response_text, "OFFICIAL_STATUS")
                },
                "raw_response": response_text
            }
            
        except Exception as e:
            logger.error(f"Class {class_level} marksheet validation error: {str(e)}")
            return {
                "valid": False,
                "percentage": 0.0,
                "meets_minimum": False,
                "feedback": f"Error validating Class {class_level} marksheet: {str(e)}",
                "class_level": class_level,
                "details": {},
                "raw_response": ""
            }
    
    def validate_college_marksheet(self, text: str) -> Dict:
        """Validate college marksheets with comprehensive CGPA and backlog analysis"""
        prompt = f"""
        You are validating college semester marksheets for NRSC internship application.
        
        CRITICAL REQUIREMENTS:
        1. Current CGPA must be at least 6.32 out of 10
        2. NO current backlogs allowed (all subjects must be cleared)
        3. Must contain semester-wise academic records
        4. Should show progression through semesters
        5. Must have college name and student details
        
        DETAILED ANALYSIS REQUIRED:
        - Check each semester's GPA/performance
        - Identify any failed subjects or backlogs
        - Calculate overall CGPA if not explicitly mentioned
        - Verify academic progression
        
        Document content:
        {text}
        
        Provide comprehensive analysis in this EXACT format:
        VALID: [true/false]
        FEEDBACK: [Detailed feedback on academic performance]
        CURRENT_CGPA: [Current cumulative GPA]
        SEMESTER_WISE_GPA: [List all semester GPAs separated by commas]
        TOTAL_SEMESTERS: [Number of completed semesters]
        CURRENT_SEMESTER: [Current/latest semester]
        BACKLOGS_COUNT: [Number of current backlogs]
        FAILED_SUBJECTS: [List of failed subjects if any]
        CLEARED_BACKLOGS: [Previously failed but now cleared subjects]
        COLLEGE_NAME: [Name of institution]
        STUDENT_NAME: [Student name]
        COURSE_BRANCH: [Course and branch/specialization]
        DEGREE_TYPE: [BE/BTech/MCA/etc.]
        MEETS_CGPA_REQ: [yes/no - whether meets 6.32 requirement]
        NO_BACKLOGS: [yes/no - whether has zero current backlogs]
        ACADEMIC_YEAR: [Current academic year]
        """
        
        try:
            response = model.generate_content(prompt)
            response_text = response.text.strip()
            
            # Extract critical fields
            current_cgpa = self.parser.extract_cgpa(self.parser.extract_field(response_text, "CURRENT_CGPA"))
            backlogs_count = int(self.parser.extract_field(response_text, "BACKLOGS_COUNT") or 0)
            
            # Validation checks
            meets_cgpa = current_cgpa >= 6.32
            no_backlogs = backlogs_count == 0
            
            # Parse semester GPAs
            semester_gpas_str = self.parser.extract_field(response_text, "SEMESTER_WISE_GPA")
            semester_gpas = []
            if semester_gpas_str:
                for gpa_str in semester_gpas_str.split(','):
                    try:
                        gpa = float(gpa_str.strip())
                        semester_gpas.append(gpa)
                    except ValueError:
                        continue
            
            # Extract degree information
            degree_type = self.parser.extract_field(response_text, "DEGREE_TYPE").upper()
            course_branch = self.parser.extract_field(response_text, "COURSE_BRANCH")
            
            # Overall validation
            is_valid = meets_cgpa and no_backlogs and current_cgpa > 0
            
            feedback = self.parser.extract_field(response_text, "FEEDBACK")
            if not meets_cgpa:
                feedback += f" CGPA {current_cgpa} does not meet minimum requirement of 6.32."
            if backlogs_count > 0:
                feedback += f" Has {backlogs_count} current backlogs. No backlogs allowed."
            
            return {
                "valid": is_valid,
                "current_cgpa": current_cgpa,
                "meets_cgpa_requirement": meets_cgpa,
                "has_no_backlogs": no_backlogs,
                "backlogs_count": backlogs_count,
                "semester_gpas": semester_gpas,
                "total_semesters": int(self.parser.extract_field(response_text, "TOTAL_SEMESTERS") or 0),
                "degree_type": degree_type,
                "college_name": self.parser.extract_field(response_text, "COLLEGE_NAME"),
                "student_name": self.parser.extract_field(response_text, "STUDENT_NAME"),
                "course_branch": course_branch,
                "feedback": feedback,
                "details": {
                    "current_semester": self.parser.extract_field(response_text, "CURRENT_SEMESTER"),
                    "failed_subjects": self.parser.extract_field(response_text, "FAILED_SUBJECTS"),
                    "cleared_backlogs": self.parser.extract_field(response_text, "CLEARED_BACKLOGS"),
                    "academic_year": self.parser.extract_field(response_text, "ACADEMIC_YEAR")
                },
                "raw_response": response_text
            }
            
        except Exception as e:
            logger.error(f"College marksheet validation error: {str(e)}")
            return {
                "valid": False,
                "current_cgpa": 0.0,
                "meets_cgpa_requirement": False,
                "has_no_backlogs": False,
                "feedback": f"Error validating college marksheet: {str(e)}",
                "details": {},
                "raw_response": ""
            }
    
    def validate_all_marksheets(self, class_10_text: str, class_12_text: str, college_text: str) -> Dict:
        """Validate all academic documents with comprehensive analysis"""
        logger.info("Starting comprehensive marksheet validation")
        
        # Validate each marksheet
        class_10_result = self.validate_school_marksheet(class_10_text, "10")
        class_12_result = self.validate_school_marksheet(class_12_text, "12")
        college_result = self.validate_college_marksheet(college_text)
        
        # Check consistency between documents
        student_names = [
            class_10_result.get("student_name", "").strip(),
            class_12_result.get("student_name", "").strip(),
            college_result.get("student_name", "").strip()
        ]
        
        # Name consistency check (allowing for minor variations)
        names_consistent = self._check_name_consistency(student_names)
        
        # Overall validation
        all_valid = (class_10_result["valid"] and 
                    class_12_result["valid"] and 
                    college_result["valid"] and
                    names_consistent)
        
        # Generate comprehensive feedback
        issues = []
        if not class_10_result["valid"]:
            issues.append(f"Class 10: {class_10_result.get('feedback', 'Validation failed')}")
        if not class_12_result["valid"]:
            issues.append(f"Class 12: {class_12_result.get('feedback', 'Validation failed')}")
        if not college_result["valid"]:
            issues.append(f"College: {college_result.get('feedback', 'Validation failed')}")
        if not names_consistent:
            issues.append("Student names are inconsistent across documents")
        
        return {
            "valid": all_valid,
            "names_consistent": names_consistent,
            "academic_records": {
                "class_10": class_10_result,
                "class_12": class_12_result,
                "college": college_result
            },
            "summary": {
                "class_10_percentage": class_10_result.get("percentage", 0),
                "class_12_percentage": class_12_result.get("percentage", 0),
                "college_cgpa": college_result.get("current_cgpa", 0),
                "meets_all_criteria": all_valid,
                "total_issues": len(issues),
                "issues": issues
            },
            "student_info": {
                "names_from_documents": student_names,
                "primary_name": self._get_primary_name(student_names),
                "degree_type": college_result.get("degree_type", ""),
                "college_name": college_result.get("college_name", "")
            }
        }
    
    def _check_name_consistency(self, names: List[str]) -> bool:
        """Check if student names are consistent across documents"""
        valid_names = [name for name in names if name and len(name) > 2]
        
        if len(valid_names) < 2:
            return True  # Cannot check consistency with insufficient data
        
        # Extract first and last names for comparison
        def extract_key_parts(full_name):
            parts = full_name.lower().split()
            return set(part for part in parts if len(part) > 2)
        
        name_sets = [extract_key_parts(name) for name in valid_names]
        
        # Check if there's significant overlap between names
        if len(name_sets) >= 2:
            intersection = name_sets[0]
            for name_set in name_sets[1:]:
                intersection = intersection.intersection(name_set)
            
            # If at least one significant name part matches
            return len(intersection) > 0
        
        return True
    
    def _get_primary_name(self, names: List[str]) -> str:
        """Get the most complete name from the list"""
        valid_names = [name for name in names if name and len(name) > 2]
        if not valid_names:
            return ""
        
        # Return the longest name (likely most complete)
        return max(valid_names, key=len)

class EligibilityChecker:
    """Check eligibility based on NRSC rules"""
    
    def __init__(self):
        self.parser = AIResponseParser()
    
    def check_degree_eligibility(self, degree_type: str, semester_count: int, 
                               application_type: str = "internship") -> Dict:
        """Check if degree and semester meet NRSC requirements"""
        degree_upper = degree_type.upper()
        
        if degree_upper not in DEGREE_REQUIREMENTS:
            return {
                "eligible": False,
                "reason": f"Degree type {degree_type} not recognized for NRSC programs"
            }
        
        req = DEGREE_REQUIREMENTS[degree_upper]
        min_semesters = req["min_semesters"]
        degree_category = req["type"]
        
        # Special rules for different degree types
        if degree_category == "final_year_only":
            # BSc/Diploma - only final year students
            if application_type == "internship":
                min_required = 6 if degree_upper == "BSC" else 4
                eligible = semester_count >= min_required
                reason = f"BSc/Diploma students must be in final year (completed {min_required}+ semesters)"
            else:  # project
                eligible = semester_count >= min_semesters
                reason = f"Must have completed at least {min_semesters} semesters"
        else:
            eligible = semester_count >= min_semesters
            reason = f"Must have completed at least {min_semesters} semesters for {degree_type}"
        
        return {
            "eligible": eligible,
            "reason": reason if not eligible else f"Meets semester requirement for {degree_type}",
            "semesters_completed": semester_count,
            "minimum_required": min_semesters,
            "degree_category": degree_category
        }
    
    def check_advance_application(self, application_date: datetime) -> Dict:
        """Check if application is submitted at least 30 days in advance"""
        current_date = datetime.now()
        days_advance = (application_date - current_date).days
        
        meets_requirement = days_advance >= 30
        
        return {
            "meets_advance_requirement": meets_requirement,
            "days_in_advance": days_advance,
            "minimum_required": 30,
            "reason": "Application must be submitted at least 30 days in advance" if not meets_requirement else "Meets advance application requirement"
        }

class ApplicationEvaluator:
    """Comprehensive application evaluation"""
    
    def __init__(self):
        self.parser = AIResponseParser()
    
    def evaluate_complete_application(self, resume_result: Dict, lor_result: Dict, 
                                   marksheet_result: Dict, application_type: str = "internship") -> Dict:
        """Evaluate complete application with detailed analysis"""
        
        # Extract key information
        student_info = marksheet_result.get("student_info", {})
        primary_name = student_info.get("primary_name", "Unknown")
        degree_type = student_info.get("degree_type", "")
        college_name = student_info.get("college_name", "")
        
        # Get academic performance
        academic_records = marksheet_result.get("academic_records", {})
        college_record = academic_records.get("college", {})
        current_cgpa = college_record.get("current_cgpa", 0)
        total_semesters = college_record.get("total_semesters", 0)
        
        # Check degree eligibility
        eligibility_checker = EligibilityChecker()
        degree_eligibility = eligibility_checker.check_degree_eligibility(
            degree_type, total_semesters, application_type
        )
        
        # Validation flags
        resume_valid = resume_result.get("valid", False)
        lor_valid = lor_result.get("valid", False)
        marksheet_valid = marksheet_result.get("valid", False)
        degree_eligible = degree_eligibility.get("eligible", False)
        
        # Overall validation
        all_documents_valid = resume_valid and lor_valid and marksheet_valid
        overall_valid = all_documents_valid and degree_eligible
        
        # Generate detailed feedback
        validation_details = {
            "resume": {
                "status": "PASS" if resume_valid else "FAIL",
                "feedback": resume_result.get("feedback", ""),
                "technical_skills": resume_result.get("details", {}).get("technical_skills", ""),
                "issues": [] if resume_valid else ["Resume validation failed"]
            },
            "letter_of_recommendation": {
                "status": "PASS" if lor_valid else "FAIL", 
                "feedback": lor_result.get("feedback", ""),
                "authority": lor_result.get("details", {}).get("authority_designation", ""),
                "addressed_correctly": lor_result.get("details", {}).get("addressed_to_nrsc", False),
                "issues": [] if lor_valid else ["LOR validation failed"]
            },
            "academic_records": {
                "status": "PASS" if marksheet_valid else "FAIL",
                "class_10_percentage": academic_records.get("class_10", {}).get("percentage", 0),
                "class_12_percentage": academic_records.get("class_12", {}).get("percentage", 0),
                "college_cgpa": current_cgpa,
                "backlogs": college_record.get("backlogs_count", 0),
                "issues": marksheet_result.get("summary", {}).get("issues", [])
            },
            "eligibility": {
                "status": "PASS" if degree_eligible else "FAIL",
                "degree_type": degree_type,
                "semesters_completed": total_semesters,
                "eligibility_reason": degree_eligibility.get("reason", ""),
                "issues": [] if degree_eligible else [degree_eligibility.get("reason", "")]
            }
        }
        
        # Generate application status
        if overall_valid:
            application_status = "APPROVED"
            summary = (f"Application for {primary_name} has been approved. "
                      f"All documents are valid and eligibility criteria met. "
                      f"CGPA: {current_cgpa}/10, Degree: {degree_type}")
        else:
            application_status = "REJECTED"
            failed_components = []
            if not resume_valid:
                failed_components.append("Resume")
            if not lor_valid:
                failed_components.append("Letter of Recommendation")
            if not marksheet_valid:
                failed_components.append("Academic Records")
            if not degree_eligible:
                failed_components.append("Eligibility Criteria")
                
            summary = (f"Application for {primary_name} has been rejected. "
                      f"Issues found in: {', '.join(failed_components)}")
        
        # Collect all issues
        all_issues = []
        for component in validation_details.values():
            all_issues.extend(component.get("issues", []))
        
        return {
            "application_status": application_status,
            "overall_valid": overall_valid,
            "summary": summary,
            "applicant_info": {
                "name": primary_name,
                "degree": degree_type,
                "college": college_name,
                "cgpa": current_cgpa,
                "semesters_completed": total_semesters
            },
            "validation_details": validation_details,
            "document_validation_summary": {
                "resume_valid": resume_valid,
                "lor_valid": lor_valid,
                "marksheet_valid": marksheet_valid,
                "eligibility_met": degree_eligible,
                "total_issues": len(all_issues)
            },
            "all_issues": all_issues,
            "recommendations": self._generate_recommendations(validation_details),
            "next_steps": self._generate_next_steps(overall_valid, all_issues)
        }
    
    def _generate_recommendations(self, validation_details: Dict) -> List[str]:
        """Generate recommendations for improvement"""
        recommendations = []
        
        if validation_details["resume"]["status"] == "FAIL":
            recommendations.append("Improve resume by adding more technical skills and project details")
        
        if validation_details["letter_of_recommendation"]["status"] == "FAIL":
            recommendations.append("Obtain proper LOR from HOD/Principal/Dean addressed to NRSC with duration details")
        
        if validation_details["academic_records"]["status"] == "FAIL":
            recommendations.append("Ensure all academic records meet minimum percentage/CGPA requirements with no backlogs")
        
        if validation_details["eligibility"]["status"] == "FAIL":
            recommendations.append("Check degree eligibility and semester completion requirements")
        
        return recommendations
    
    def _generate_next_steps(self, approved: bool, issues: List[str]) -> List[str]:
        """Generate next steps based on application status"""
        if approved:
            return [
                "Application approved - await confirmation from NRSC",
                "Prepare for potential interview or selection process",
                "Ensure availability for the internship duration"
            ]
        else:
            steps = ["Address the following issues and resubmit:"]
            steps.extend(f"- {issue}" for issue in issues[:5])  # Limit to top 5 issues
            steps.append("Contact NRSC at student@nrsc.gov.in for clarifications")
            return steps

# Enhanced FastAPI Routes
@app.post("/validate")
async def validate_documents(
    resume: UploadFile = File(..., description="Resume/CV PDF"),
    lor: UploadFile = File(..., description="Letter of Recommendation PDF"),
    class_10: UploadFile = File(..., description="Class 10 Marksheet PDF"),
    class_12: UploadFile = File(..., description="Class 12 Marksheet PDF"),
    college_marksheets: UploadFile = File(..., description="College Marksheets PDF"),
    application_type: str = "internship"
):
    """
    Validate all documents for NRSC internship/project application
    """
    try:
        logger.info("Starting comprehensive document validation")
        
        # Validate file types
        allowed_types = ["application/pdf"]
        files = [resume, lor, class_10, class_12, college_marksheets]
        file_names = ["resume", "lor", "class_10", "class_12", "college_marksheets"]
        
        for file, name in zip(files, file_names):
            if file.content_type not in allowed_types:
                raise HTTPException(
                    status_code=400, 
                    detail=f"{name} must be a PDF file"
                )
        
        # Initialize processors
        doc_processor = DocumentProcessor()
        classifier = DocumentClassifier()
        resume_validator = ResumeValidator()
        lor_validator = LORValidator()
        marksheet_validator = MarksheetValidator()
        evaluator = ApplicationEvaluator()
        
        # Extract text from all documents
        logger.info("Extracting text from documents")
        resume_text = doc_processor.extract_text_with_fallback(resume)
        lor_text = doc_processor.extract_text_with_fallback(lor)
        class_10_text = doc_processor.extract_text_with_fallback(class_10)
        class_12_text = doc_processor.extract_text_with_fallback(class_12)
        college_text = doc_processor.extract_text_with_fallback(college_marksheets)
        
        logger.info("Text extraction completed successfully")
        
        # Classify and validate resume/cover letter
        doc_type = classifier.classify_document(resume_text)
        logger.info(f"Document classified as: {doc_type}")
        
        if doc_type == "RESUME":
            resume_result = resume_validator.validate(resume_text)
        elif doc_type == "COVERLETTER":
            resume_result = resume_validator.validate(resume_text)  # Use same validation for now
            resume_result["document_type"] = "COVERLETTER"
        else:
            resume_result = {
                "valid": False,
                "feedback": f"Document classified as {doc_type}, expected RESUME or COVERLETTER",
                "details": {}
            }
        
        # Validate LOR
        logger.info("Validating Letter of Recommendation")
        lor_result = lor_validator.validate(lor_text)
        
        # Validate all marksheets
        logger.info("Validating academic records")
        marksheet_result = marksheet_validator.validate_all_marksheets(
            class_10_text, class_12_text, college_text
        )
        
        # Comprehensive evaluation
        logger.info("Performing comprehensive evaluation")
        final_result = evaluator.evaluate_complete_application(
            resume_result, lor_result, marksheet_result, application_type
        )
        
        # Add metadata
        final_result["metadata"] = {
            "validation_timestamp": datetime.now().isoformat(),
            "document_type": doc_type,
            "application_type": application_type,
            "validator_version": "2.0.0"
        }
        
        logger.info(f"Validation completed. Status: {final_result['application_status']}")
        
        return JSONResponse(content=final_result)
        
    except ValidationError as ve:
        logger.error(f"Validation error: {str(ve)}")
        return JSONResponse(
            content={
                "error": "Validation Error",
                "message": str(ve),
                "application_status": "REJECTED"
            },
            status_code=400
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in validate_documents: {str(e)}", exc_info=True)
        return JSONResponse(
            content={
                "error": "Internal Server Error",
                "message": "An unexpected error occurred while processing your application",
                "application_status": "ERROR"
            },
            status_code=500
        )

@app.post("/validate-resume")
async def validate_resume_only(
    resume: UploadFile = File(..., description="Resume/CV PDF")
):
    """Validate only the resume document"""
    try:
        doc_processor = DocumentProcessor()
        classifier = DocumentClassifier()
        resume_validator = ResumeValidator()
        
        resume_text = doc_processor.extract_text_with_fallback(resume)
        doc_type = classifier.classify_document(resume_text)
        result = resume_validator.validate(resume_text)
        result["document_type"] = doc_type
        
        return JSONResponse(content=result)
        
    except Exception as e:
        logger.error(f"Resume validation error: {str(e)}")
        return JSONResponse(
            content={"error": str(e), "valid": False},
            status_code=500
        )

@app.post("/validate-lor")
async def validate_lor_only(
    lor: UploadFile = File(..., description="Letter of Recommendation PDF")
):
    """Validate only the Letter of Recommendation"""
    try:
        doc_processor = DocumentProcessor()
        lor_validator = LORValidator()
        
        lor_text = doc_processor.extract_text_with_fallback(lor)
        result = lor_validator.validate(lor_text)
        
        return JSONResponse(content=result)
        
    except Exception as e:
        logger.error(f"LOR validation error: {str(e)}")
        return JSONResponse(
            content={"error": str(e), "valid": False},
            status_code=500
        )

@app.post("/validate-marksheets")
async def validate_marksheets_only(
    class_10: UploadFile = File(..., description="Class 10 Marksheet PDF"),
    class_12: UploadFile = File(..., description="Class 12 Marksheet PDF"),
    college_marksheets: UploadFile = File(..., description="College Marksheets PDF")
):
    """Validate only the academic marksheets"""
    try:
        doc_processor = DocumentProcessor()
        marksheet_validator = MarksheetValidator()
        
        class_10_text = doc_processor.extract_text_with_fallback(class_10)
        class_12_text = doc_processor.extract_text_with_fallback(class_12)
        college_text = doc_processor.extract_text_with_fallback(college_marksheets)
        
        result = marksheet_validator.validate_all_marksheets(
            class_10_text, class_12_text, college_text
        )
        
        return JSONResponse(content=result)
        
    except Exception as e:
        logger.error(f"Marksheet validation error: {str(e)}")
        return JSONResponse(
            content={"error": str(e), "valid": False},
            status_code=500
        )

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "version": "2.0.0",
        "timestamp": datetime.now().isoformat()
    }

@app.get("/eligibility-rules")
async def get_eligibility_rules():
    """Get NRSC eligibility rules"""
    return {
        "eligibility_rules": ELIGIBILITY_RULES,
        "degree_requirements": DEGREE_REQUIREMENTS,
        "document_requirements": {
            "resume": "Technical skills, education, projects, contact information",
            "lor": "From HOD/Principal/Dean, addressed to NRSC Group Director, with duration",
            "marksheets": "Class 10/12 with 60%+, College with 6.32+ CGPA and no backlogs"
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)