import pandas as pd
import re
from datetime import datetime, timedelta
from typing import Dict, Any, Union, List, Optional
import logging

# Set up logging
logger = logging.getLogger(__name__)

class NRSCExcelValidator:
    """NRSC Student Projects & Internships Excel Validator"""
    
    def __init__(self):
        """Initialize validator with field mappings and validation rules"""
        self.errors = []
        self.warnings = []
        
        # Field mapping based on Excel structure (row indices)
        self.field_mapping = {
            'name': 4,                          # Row 5 (Name)
            'phone_number': 5,                  # Row 6 (Phone Number)
            'email_id': 6,                      # Row 7 (Email ID)
            'date_of_birth': 7,                 # Row 8 (Date of Birth)
            'college_name': 9,                  # Row 10 (College Name)
            'degree_type': 10,                  # Row 15 (Degree Type)
            'branch_specialization': 15,        # Row 16 (Branch/Specialization)
            'semester_completed': 16,           # Row 17 (Semester Completed)
            'cgpa': 17,                        # Row 18 (CGPA)
            'twelfth_mark_percentage': 18,      # Row 19 (12th Mark Percentage)
            'tenth_mark_percentage': 19,        # Row 20 (10th Mark Percentage)
            'program_type': 21,                # Row 22 (Program Type)
            'application_start_date': 22,       # Row 23 (Application Start Date)
            'end_date': 23,                    # Row 24 (End Date)
            'duration_preference': 24          # Row 25 (Duration Preference)
        }
        
        # Required fields for all applications
        self.required_fields = [
            'name', 'phone_number', 'email_id', 'date_of_birth',
            'college_name', 'degree_type', 'branch_specialization',
            'semester_completed', 'cgpa', 'twelfth_mark_percentage',
            'tenth_mark_percentage', 'program_type', 'application_start_date',
            'duration_preference'
        ]
        
        # Date fields that need special formatting
        self.date_fields = ['date_of_birth', 'application_start_date', 'end_date']
        
        # Numeric fields that need validation
        self.numeric_fields = [
            'semester_completed', 'cgpa', 'twelfth_mark_percentage',
            'tenth_mark_percentage', 'duration_preference'
        ]
        
        # Valid degree types
        self.valid_degree_types = [
            'Engineering(BE/BTech)', 'MCA/ME/MTech', 'BSc/BE', 'MSc', 'PhD'
        ]
        
        # Valid program types
        self.valid_program_types = ['project', 'internship','Project','Internship']
        
        # Degree-specific eligibility criteria
        self.degree_requirements = {
            'Engineering(BE/BTech)': {
                'min_semester': 6,
                'min_duration_days': 90,
                'description': 'Must have completed 6th semester'
            },
            'MCA/ME/MTech': {
                'min_semester': 1,
                'min_duration_days': 120,
                'description': 'Must have completed 1st semester'
            },
            'BSc/Diploma': {
                'final_year_only': True,
                'min_duration_days': 90,
                'description': 'Only final year students eligible'
            },
            'MSc': {
                'min_semester': 1,
                'min_duration_days': 120,
                'description': 'Must have completed 1st semester'
            },
            'PhD': {
                'coursework_required': True,
                'min_duration_days': 90,
                'description': 'Must have completed coursework'
            }
        }
        
        # Program-specific requirements
        self.program_requirements = {
            'project': {
                'min_duration_months': 3,
                'max_duration_months': 12,
                'min_cgpa': 6.32,
                'min_percentage': 60.0,
                'advance_application_days': 15,
                'end_date_required': True
            },
            'internship': {
                'duration_days': 45,
                'min_cgpa': 6.32,
                'min_percentage': 60.0,
                'advance_application_days': 15,
                'eligible_degrees': ['Engineering(BE/BTech)', 'MCA/ME/MTech', 'PhD'],
                'end_date_required': False
            }
        }

    def extract_excel_data(self, file_path: str) -> Dict[str, Any]:
        """Extract data from Excel file based on NRSC template structure"""
        try:
            # Read Excel file
            try:
                df = pd.read_excel(file_path, sheet_name=0, header=None)
            except FileNotFoundError:
                raise Exception(f"Excel file not found: {file_path}")
            except Exception as e:
                raise Exception(f"Failed to read Excel file: {str(e)}")
            
            if df.empty:
                raise Exception("Excel file is empty")
            
            # Check minimum requirements
            min_rows_required = 25  # Based on the template structure
            min_cols_required = 3   # A, B, C columns
            
            if len(df) < min_rows_required:
                raise Exception(f"Excel file must have at least {min_rows_required} rows, found {len(df)}")
            
            if len(df.columns) < min_cols_required:
                raise Exception(f"Excel file must have at least {min_cols_required} columns, found {len(df.columns)}")
            
            # Safe extraction function (data is in column C, index 2)
            def safe_extract(row_idx: int, col_idx: int = 1) -> str:
                try:
                    if row_idx >= len(df) or col_idx >= len(df.columns):
                        return ''
                    value = df.iloc[row_idx, col_idx]
                    return str(value).strip() if not pd.isna(value) else ''
                except Exception:
                    return ''
            
            # Extract data using field mapping
            extracted_data = {}
            for field_name, row_index in self.field_mapping.items():
                extracted_data[field_name] = safe_extract(row_index)
                
            print(extracted_data)
            
            # Handle date formatting
            for date_field in self.date_fields:
                if date_field in extracted_data and extracted_data[date_field]:
                    extracted_data[date_field] = self._format_date(extracted_data[date_field])
            
            # Handle numeric fields
            for numeric_field in self.numeric_fields:
                if numeric_field in extracted_data and extracted_data[numeric_field]:
                    extracted_data[numeric_field] = self._clean_numeric_value(extracted_data[numeric_field])
            
            # Clean program type
            if 'program_type' in extracted_data:
                extracted_data['program_type'] = str(extracted_data['program_type']).lower().strip()
            
            return extracted_data
            
        except Exception as e:
            logger.error(f"Failed to extract data from Excel file {file_path}: {str(e)}")
            raise Exception(f"Failed to extract data from Excel file: {str(e)}")

    def validate_excel_fields(self, excel_data: Dict[str, Any]) -> Dict[str, Any]:
        """Comprehensive validation with NRSC-specific rules"""
        
        program_type = excel_data.get('program_type', '').lower().strip()
        degree_type = excel_data.get('degree_type', '').strip()
        
        # Rule 1: Check for null/empty required fields
        required_fields = self._get_required_fields(program_type)
        for field in required_fields:
            value = excel_data.get(field)
            if self._is_empty_value(value):
                self.errors.append(f"Field '{field}' is required but is null or empty")
        
        # Rule 2: Validate program type
        program_error = self._validate_program_type(program_type)
        if program_error:
            self.errors.append(program_error)
        
        # Rule 3: Validate degree type
        degree_error = self._validate_degree_type(degree_type)
        if degree_error:
            self.errors.append(degree_error)
        
        # Rule 4: Validate degree-specific eligibility
        eligibility_error = self._validate_degree_eligibility(excel_data)
        if eligibility_error:
            self.errors.append(eligibility_error)
        
        # Rule 5: Validate CGPA (minimum 6.32)
        cgpa_error = self._validate_cgpa(excel_data.get('cgpa'))
        if cgpa_error:
            self.errors.append(cgpa_error)
        
        # Rule 6: Validate percentage marks (minimum 60%)
        tenth_error = self._validate_percentage(excel_data.get('tenth_mark_percentage'), '10th mark')
        if tenth_error:
            self.errors.append(tenth_error)
        
        twelfth_error = self._validate_percentage(excel_data.get('twelfth_mark_percentage'), '12th mark')
        if twelfth_error:
            self.errors.append(twelfth_error)
        
        # Rule 7: Validate application start date (at least 15 days from today)
        start_date_error = self._validate_application_start_date(excel_data.get('application_start_date'))
        if start_date_error:
            self.errors.append(start_date_error)
        
        # Rule 8: Validate duration preference
        duration_error = self._validate_duration_preference(excel_data)
        if duration_error:
            self.errors.append(duration_error)
        
        # Rule 9: Validate end date (for projects)
        end_date_error = self._validate_end_date(excel_data)
        if end_date_error:
            self.errors.append(end_date_error)
        
        # Rule 10: Validate email format
        email_error = self._validate_email(excel_data.get('email_id'))
        if email_error:
            self.errors.append(email_error)
        
        # Rule 11: Validate phone number format (warning)
        phone_warning = self._validate_phone_number(excel_data.get('phone_number'))
        if phone_warning:
            self.warnings.append(phone_warning)
        
        # Rule 12: Validate date of birth (age check - warning)
        dob_warning = self._validate_date_of_birth(excel_data.get('date_of_birth'))
        if dob_warning:
            self.warnings.append(dob_warning)
        
        # Rule 13: Program-specific validations
        program_specific_errors = self._validate_program_specific_requirements(excel_data)
        self.errors.extend(program_specific_errors)
        
        return {
            'all_valid': len(self.errors) == 0,
            'errors': self.errors,
            'warnings': self.warnings,
            'total_errors': len(self.errors),
            'total_warnings': len(self.warnings),
            'program_type': program_type,
            'degree_type': degree_type,
            'validation_summary': self._generate_validation_summary(self.errors, self.warnings)
        }
    
    def _get_required_fields(self, program_type: str) -> List[str]:
        """Get required fields based on program type"""
        base_required = self.required_fields.copy()
        
        # End date is required for projects but not internships
        if program_type == 'project':
            base_required.append('end_date')
        
        return base_required
    
    def _validate_program_type(self, program_type: str) -> str:
        """Rule: Program type must be 'project' or 'internship'"""
        if not program_type:
            return "Program type is required (must be 'project' or 'internship')"
        
        if program_type not in self.valid_program_types:
            return f"Invalid program type '{program_type}'. Must be 'project' or 'internship'"
        
        return ""
    
    def _validate_degree_type(self, degree_type: str) -> str:
        """Rule: Degree type must be from valid options"""
        if not degree_type:
            return "Degree type is required"
        
        if degree_type not in self.valid_degree_types:
            return f"Invalid degree type '{degree_type}'. Valid options: {', '.join(self.valid_degree_types)}"
        
        return ""
    
    def _validate_degree_eligibility(self, excel_data: Dict[str, Any]) -> str:
        """Rule: Check degree-specific eligibility criteria"""
        degree_type = excel_data.get('degree_type', '').strip()
        semester_completed = excel_data.get('semester_completed')
        program_type = excel_data.get('program_type', '').lower().strip()
        
        if not degree_type or degree_type not in self.degree_requirements:
            return ""  # Will be caught by degree type validation
        
        requirements = self.degree_requirements[degree_type]
        
        # Check minimum semester requirement
        if 'min_semester' in requirements:
            try:
                semester = int(float(semester_completed)) if semester_completed else 0
                if semester < requirements['min_semester']:
                    return f"For {degree_type}, minimum {requirements['min_semester']} semester(s) must be completed. Current: {semester}"
            except (ValueError, TypeError):
                return f"Invalid semester value: {semester_completed}"
        
        # Check internship eligibility
        if program_type == 'internship':
            eligible_degrees = self.program_requirements['internship']['eligible_degrees']
            if degree_type not in eligible_degrees:
                return f"Internship is only available for: {', '.join(eligible_degrees)}"
        
        return ""
    
    def _validate_cgpa(self, cgpa_value: Any) -> str:
        """Rule: CGPA must be at least 6.32 on scale of 10"""
        if self._is_empty_value(cgpa_value):
            return ""
        
        try:
            cgpa = float(cgpa_value)
            if cgpa < 6.32:
                return f"CGPA ({cgpa}) must be at least 6.32"
            if cgpa > 10.0:
                return f"CGPA ({cgpa}) cannot exceed 10.0"
        except (ValueError, TypeError):
            return f"Invalid CGPA format: {cgpa_value}"
        
        return ""
    
    def _validate_percentage(self, percentage_value: Any, field_name: str) -> str:
        """Rule: Percentage marks must be at least 60%"""
        if self._is_empty_value(percentage_value):
            return ""
        
        try:
            if percentage_value <1:
                percentage_value=percentage_value*100
                print("Converted to percentage in 100 scale")
            percentage = float(percentage_value)
            if percentage < 60.0:
                return f"{field_name} ({percentage}%) must be at least 60%"
            if percentage > 100.0:
                return f"{field_name} ({percentage}%) cannot exceed 100%"
        except (ValueError, TypeError):
            return f"Invalid {field_name} format: {percentage_value}"
        
        return ""
    
    def _validate_application_start_date(self, start_date_str: Any) -> str:
        """Rule: Application start date must be at least 15 days from today"""
        if self._is_empty_value(start_date_str):
            return ""
        
        try:
            start_date = datetime.strptime(str(start_date_str), '%Y-%m-%d')
            current_date = datetime.now()
            min_start_date = current_date + timedelta(days=15)
            
            if start_date < min_start_date:
                return f"Application start date ({start_date_str}) must be at least 15 days from today ({min_start_date.strftime('%Y-%m-%d')})"
        except (ValueError, TypeError):
            return f"Invalid application start date format: {start_date_str}"
        
        return ""
    
    def _validate_duration_preference(self, excel_data: Dict[str, Any]) -> str:
        """Rule: Validate duration based on program type"""
        duration = excel_data.get('duration_preference')
        program_type = excel_data.get('program_type', '').lower().strip()
        
        if self._is_empty_value(duration):
            return ""
        
        try:
            duration_value = float(duration)
        except (ValueError, TypeError):
            return f"Invalid duration format: {duration}"
        
        if program_type == 'project':
            # Projects: 3-12 months
            if duration_value < 3 or duration_value > 12:
                return f"Project duration must be 3-12 months, got: {duration_value}"
        elif program_type == 'internship':
            # Internships: around 45 days
            if duration_value < 30 or duration_value > 60:
                return f"Internship duration should be around 45 days (30-60 acceptable), got: {duration_value}"
        
        return ""
    
    def _validate_end_date(self, excel_data: Dict[str, Any]) -> str:
        """Rule: End date validation for projects"""
        program_type = excel_data.get('program_type', '').lower().strip()
        end_date = excel_data.get('end_date')
        start_date = excel_data.get('application_start_date')
        
        if program_type == 'project':
            if self._is_empty_value(end_date):
                return "End date is required for project applications"
            
            # Validate end date is after start date
            if not self._is_empty_value(start_date):
                try:
                    start_dt = datetime.strptime(str(start_date), '%Y-%m-%d')
                    end_dt = datetime.strptime(str(end_date), '%Y-%m-%d')
                    
                    if end_dt <= start_dt:
                        return "End date must be after application start date"
                    
                    # Check if duration matches preference
                    duration_months = (end_dt - start_dt).days / 30
                    duration_pref = excel_data.get('duration_preference')
                    if duration_pref:
                        try:
                            pref_months = float(duration_pref)
                            if abs(duration_months - pref_months) > 1:  # Allow 1 month tolerance
                                self.warnings.append(f"Duration mismatch: End date suggests {duration_months:.1f} months, but preference is {pref_months} months")
                        except (ValueError, TypeError):
                            pass
                except (ValueError, TypeError):
                    return "Invalid date format for start or end date"
        
        return ""
    
    def _validate_email(self, email: Any) -> str:
        """Rule: Email must be in valid format"""
        if self._is_empty_value(email):
            return ""
        
        email_str = str(email).strip()
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        
        if not re.match(email_pattern, email_str):
            return f"Invalid email format: {email_str}"
        
        return ""
    
    def _validate_phone_number(self, phone: Any) -> str:
        """Rule: Phone number format validation (warning)"""
        if self._is_empty_value(phone):
            return ""
        
        phone_str = str(phone).strip()
        # Remove common formatting characters
        cleaned_phone = re.sub(r'[+\-\s\(\)]', '', phone_str)
        
        # Indian phone numbers: 10 digits or with country code (12-13 digits)
        if not re.match(r'^\d{10,15}$', cleaned_phone):
            return f"Phone number format may be invalid: {phone_str}"
        
        return ""
    
    def _validate_date_of_birth(self, dob: Any) -> str:
        """Rule: Age validation based on date of birth (warning)"""
        if self._is_empty_value(dob):
            return ""
        
        try:
            birth_date = datetime.strptime(str(dob), '%Y-%m-%d')
            current_date = datetime.now()
            age = (current_date - birth_date).days // 365
            
            if age < 17:
                return f"Age ({age}) seems too young for this program"
            if age > 35:
                return f"Age ({age}) seems unusual for this program"
        except (ValueError, TypeError):
            return f"Invalid date of birth format: {dob}"
        
        return ""
    
    def _validate_program_specific_requirements(self, excel_data: Dict[str, Any]) -> List[str]:
        """Additional program-specific validation rules"""
        errors = []
        program_type = excel_data.get('program_type', '').lower().strip()
        
        if program_type in self.program_requirements:
            requirements = self.program_requirements[program_type]
            
            # Add any additional program-specific validations here
            # if program_type == 'internship':
            #     errors.append("Note: Internship seats are limited and selection is competitive")
        
        return errors
    
    def _generate_validation_summary(self, errors: List[str], warnings: List[str]) -> str:
        """Generate a human-readable validation summary"""
        if not errors and not warnings:
            return "✅ All validations passed successfully"
        
        summary = []
        if errors:
            summary.append(f"❌ {len(errors)} error(s) found")
        if warnings:
            summary.append(f"⚠️ {len(warnings)} warning(s) found")
        
        return " | ".join(summary)
    
    # Utility methods
    def _is_empty_value(self, value: Any) -> bool:
        """Check if value is empty or null"""
        if value is None:
            return True
        str_value = str(value).strip().lower()
        return str_value in ['', 'null', 'none', 'n/a', 'nan', 'na']
    
    def _format_date(self, date_value: Any) -> str:
        """Format date value to YYYY-MM-DD string"""
        if not date_value:
            return ''
        
        if isinstance(date_value, pd.Timestamp):
            return date_value.strftime('%Y-%m-%d')
        
        date_str = str(date_value).strip()
        date_formats = [
            '%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%d-%m-%Y',
            '%Y/%m/%d', '%d.%m.%Y', '%Y%m%d', '%Y-%m-%d %H:%M:%S'
        ]
        
        for fmt in date_formats:
            try:
                parsed_date = datetime.strptime(date_str, fmt)
                return parsed_date.strftime('%Y-%m-%d')
            except ValueError:
                continue
        
        try:
            parsed_date = pd.to_datetime(date_str)
            return parsed_date.strftime('%Y-%m-%d')
        except Exception:
            pass
        
        return date_str
    
    def _clean_numeric_value(self, value: Any) -> Union[float, str]:
        """Clean and convert numeric values"""
        if not value:
            return ''
        
        cleaned = str(value).strip().replace(',', '').replace('%', '')
        try:
            return float(cleaned)
        except ValueError:
            return str(value).strip()
    
    def validate_excel_file(self, file_path: str) -> Dict[str, Any]:
        """Main validation method - validates complete Excel file"""
        try:
            # Extract data from Excel
            excel_data = self.extract_excel_data(file_path)
            
            # Validate extracted data
            validation_result = self.validate_excel_fields(excel_data)
            
            return {
                'success': validation_result['all_valid'],
                'extracted_data': excel_data,
                'validation_result': validation_result,
                'timestamp': datetime.now().isoformat(),
                'file_path': file_path,
                'summary': validation_result['validation_summary']
            }
            
        except Exception as e:
            logger.error(f"Error validating Excel file {file_path}: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'extracted_data': {},
                'validation_result': {
                    'all_valid': False,
                    'errors': [f"File processing error: {str(e)}"],
                    'warnings': [],
                    'total_errors': 1,
                    'total_warnings': 0,
                    'validation_summary': "❌ File processing failed"
                },
                'timestamp': datetime.now().isoformat(),
                'file_path': file_path
            }


# Convenience functions
def create_nrsc_validator() -> NRSCExcelValidator:
    """Factory function to create NRSC validator"""
    return NRSCExcelValidator()

def validate_nrsc_excel_file(file_path: str) -> Dict[str, Any]:
    """Validate NRSC Excel application file"""
    validator = create_nrsc_validator()
    return validator.validate_excel_file(file_path)

# # Example usage
# if __name__ == "__main__":
#     # Example usage
#     validator = NRSCExcelValidator()
#     result = validator.validate_excel_file("/Volumes/DevDrive/NRSC/StudentApplicationPipeline/servers/manager/testing.xlsx")
    
#     print(f"Validation Result: {result['summary']}")
#     if not result['success']:
#         print("Errors:")
#         for error in result['validation_result']['errors']:
#             print(f"  - {error}")
    
#     if result['validation_result']['warnings']:
#         print("Warnings:")
#         for warning in result['validation_result']['warnings']:
#             print(f"  - {warning}")

