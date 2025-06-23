#!/usr/bin/env python3
"""
Test script for NRSC Excel validation rules
"""

import sys
import os
from datetime import datetime, timedelta
import re

def validate_excel_fields(excel_data):
    """Validate Excel data against NRSC requirements"""
    errors = []
    warnings = []
    
    # Required fields - check for null/empty values
    required_fields = [
        'name', 'phone_number', 'email_id', 'date_of_birth',
        'duration_and_type', 'application_start_date', 'end_date', 
        'project_or_internship', 'college_name', 'semester_completed',
        'cgpa', 'twelfth_mark_percentage', 'tenth_mark_percentage'
    ]
    
    # Rule 4: Check for null/empty fields
    for field in required_fields:
        value = excel_data.get(field)
        if value is None or str(value).strip() == '' or str(value).lower() in ['null', 'none', 'n/a']:
            errors.append(f"Field '{field}' is required but is null or empty")
    
    # Rule 1: Start date validation (30 days after current date)
    try:
        start_date_str = excel_data.get('application_start_date', '')
        if start_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            current_date = datetime.now()
            min_start_date = current_date + timedelta(days=30)
            
            if start_date < min_start_date:
                errors.append(f"Application start date ({start_date_str}) must be at least 30 days from current date ({min_start_date.strftime('%Y-%m-%d')})")
    except (ValueError, TypeError) as e:
        errors.append(f"Invalid application start date format. Expected YYYY-MM-DD, got: {excel_data.get('application_start_date')}")
    
    # Rule 2: CGPA validation (minimum 6.32)
    try:
        cgpa = float(excel_data.get('cgpa', 0))
        if cgpa < 6.32:
            errors.append(f"CGPA ({cgpa}) must be at least 6.32 on a scale of 10")
    except (ValueError, TypeError):
        errors.append(f"Invalid CGPA format. Expected numeric value, got: {excel_data.get('cgpa')}")
    
    # Rule 3: 10th and 12th marks validation (minimum 60%)
    try:
        tenth_marks = float(excel_data.get('tenth_mark_percentage', 0))
        if tenth_marks < 60.0:
            errors.append(f"10th mark percentage ({tenth_marks}%) must be at least 60%")
    except (ValueError, TypeError):
        errors.append(f"Invalid 10th mark percentage format. Expected numeric value, got: {excel_data.get('tenth_mark_percentage')}")
    
    try:
        twelfth_marks = float(excel_data.get('twelfth_mark_percentage', 0))
        if twelfth_marks < 60.0:
            errors.append(f"12th mark percentage ({twelfth_marks}%) must be at least 60%")
    except (ValueError, TypeError):
        errors.append(f"Invalid 12th mark percentage format. Expected numeric value, got: {excel_data.get('twelfth_mark_percentage')}")
    
    # Additional validations
    # Email format validation
    email = excel_data.get('email_id', '')
    if email and not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
        errors.append(f"Invalid email format: {email}")
    
    # Phone number validation (basic)
    phone = excel_data.get('phone_number', '')
    if phone and not re.match(r'^\d{10}$', str(phone).replace('+', '').replace('-', '').replace(' ', '')):
        warnings.append(f"Phone number format may be invalid: {phone}")
    
    return {
        'all_valid': len(errors) == 0,
        'errors': errors,
        'warnings': warnings,
        'total_errors': len(errors),
        'total_warnings': len(warnings)
    }

def create_test_data():
    """Create various test data scenarios"""
    current_date = datetime.now()
    
    # Test Case 1: Valid Application (should pass all validations)
    valid_data = {
        'name': 'John Doe',
        'phone_number': '9876543210',
        'email_id': 'john.doe@example.com',
        'date_of_birth': '1995-01-15',
        'duration_and_type': '6 months, Research Internship',
        'application_start_date': (current_date + timedelta(days=35)).strftime('%Y-%m-%d'),
        'end_date': (current_date + timedelta(days=220)).strftime('%Y-%m-%d'),
        'project_or_internship': 'Remote Sensing Data Analysis',
        'college_name': 'ABC Engineering College',
        'semester_completed': 6,
        'cgpa': 7.5,
        'twelfth_mark_percentage': 85.0,
        'tenth_mark_percentage': 78.0
    }
    
    # Test Case 2: Invalid Date (start date too soon)
    invalid_date_data = valid_data.copy()
    invalid_date_data['application_start_date'] = (current_date + timedelta(days=10)).strftime('%Y-%m-%d')
    invalid_date_data['name'] = 'Jane Smith'
    invalid_date_data['email_id'] = 'jane.smith@example.com'
    
    # Test Case 3: Invalid CGPA (too low)
    invalid_cgpa_data = valid_data.copy()
    invalid_cgpa_data['cgpa'] = 5.8
    invalid_cgpa_data['name'] = 'Bob Wilson'
    invalid_cgpa_data['email_id'] = 'bob.wilson@example.com'
    
    # Test Case 4: Invalid Marks (below 60%)
    invalid_marks_data = valid_data.copy()
    invalid_marks_data['tenth_mark_percentage'] = 55.0
    invalid_marks_data['twelfth_mark_percentage'] = 58.0
    invalid_marks_data['name'] = 'Alice Brown'
    invalid_marks_data['email_id'] = 'alice.brown@example.com'
    
    # Test Case 5: Null/Empty Fields
    null_fields_data = valid_data.copy()
    null_fields_data['name'] = ''
    null_fields_data['college_name'] = None
    null_fields_data['cgpa'] = 'null'
    null_fields_data['email_id'] = 'test.null@example.com'
    
    # Test Case 6: Multiple Validation Failures
    multiple_failures_data = {
        'name': '',  # Null field
        'phone_number': '98765',  # Invalid format
        'email_id': 'invalid-email',  # Invalid format
        'date_of_birth': '1995-01-15',
        'duration_and_type': '6 months, Research Internship',
        'application_start_date': (current_date + timedelta(days=5)).strftime('%Y-%m-%d'),  # Too soon
        'end_date': (current_date + timedelta(days=220)).strftime('%Y-%m-%d'),
        'project_or_internship': 'Remote Sensing Data Analysis',
        'college_name': None,  # Null field
        'semester_completed': 6,
        'cgpa': 4.5,  # Too low
        'twelfth_mark_percentage': 45.0,  # Too low
        'tenth_mark_percentage': 38.0   # Too low
    }
    
    return [
        ('Valid Application', valid_data),
        ('Invalid Date (Too Soon)', invalid_date_data),
        ('Invalid CGPA (Too Low)', invalid_cgpa_data),
        ('Invalid Marks (Below 60%)', invalid_marks_data),
        ('Null/Empty Fields', null_fields_data),
        ('Multiple Validation Failures', multiple_failures_data)
    ]

def main():
    print("🧪 NRSC Excel Validation Testing")
    print("=" * 60)
    print("\nValidation Rules:")
    print("1. ⏰ Start date must be at least 30 days from current date")
    print("2. 📊 CGPA must be at least 6.32 on a scale of 10")
    print("3. 📈 10th and 12th marks must be at least 60%")
    print("4. ✅ All fields must be non-null/non-empty")
    print("=" * 60)
    
    test_cases = create_test_data()
    
    for i, (test_name, test_data) in enumerate(test_cases, 1):
        print(f"\n🔍 Test Case {i}: {test_name}")
        print("-" * 40)
        
        validation_result = validate_excel_fields(test_data)
        
        # Display result
        if validation_result['all_valid']:
            print("✅ VALIDATION PASSED")
        else:
            print("❌ VALIDATION FAILED")
            print(f"   Errors: {validation_result['total_errors']}")
            
        # Show key data points
        print("\n📋 Key Data Points:")
        print(f"   Name: {test_data.get('name', 'N/A')}")
        print(f"   Email: {test_data.get('email_id', 'N/A')}")
        print(f"   CGPA: {test_data.get('cgpa', 'N/A')}")
        print(f"   10th Marks: {test_data.get('tenth_mark_percentage', 'N/A')}%")
        print(f"   12th Marks: {test_data.get('twelfth_mark_percentage', 'N/A')}%")
        print(f"   Start Date: {test_data.get('application_start_date', 'N/A')}")
        print(f"   College: {test_data.get('college_name', 'N/A')}")
        
        # Show validation errors
        if validation_result['errors']:
            print("\n🚨 Validation Errors:")
            for error in validation_result['errors']:
                print(f"   • {error}")
        
        # Show warnings
        if validation_result['warnings']:
            print("\n⚠️  Warnings:")
            for warning in validation_result['warnings']:
                print(f"   • {warning}")
    
    print("\n" + "=" * 60)
    print("✨ Testing Complete!")
    print("\n💡 In production, the excel_validate() function will:")
    print("   • Read actual Excel files using pandas/openpyxl")
    print("   • Extract data from specific cells/columns")
    print("   • Apply these validation rules automatically")
    print("   • Send appropriate success/failure emails based on results")

if __name__ == "__main__":
    main()