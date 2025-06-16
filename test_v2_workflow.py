#!/usr/bin/env python3
"""
Test script for the new V2 email workflow in the manager server.
This script demonstrates the complete workflow from email processing to validation.
"""

import requests
import json
from datetime import datetime

# Configuration
MANAGER_URL = "http://localhost:8004"
API_KEY = "your-secret-api-key-123"

# Headers for API calls
headers = {
    "X-API-Key": API_KEY,
    "Content-Type": "application/json"
}

def test_v2_workflow():
    """Test the complete V2 email workflow"""
    
    print("🚀 Testing V2 Email Workflow")
    print("=" * 50)
    
    # Sample email data that would come from the email poller
    sample_email = {
        "email_data": {
            "id": f"test_email_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "subject": "Internship Application - John Doe",
            "sender": "john.doe@example.com",
            "recipient": "internships@nrsc.gov.in",
            "date": datetime.now().isoformat(),
            "body_text": "Dear NRSC Team,\n\nI am writing to apply for the internship program. Please find my documents attached.\n\nBest regards,\nJohn Doe",
            "body_html": "<p>Dear NRSC Team,</p><p>I am writing to apply for the internship program. Please find my documents attached.</p><p>Best regards,<br>John Doe</p>",
            "is_application": True,
            "keywords_found": ["internship", "application"],
            "attachments": [
                {
                    "filename": "MIT_John_Doe_ComputerScience.pdf",
                    "content_type": "application/pdf",
                    "path": "/tmp/resume.pdf",
                    "size": 256000,
                    "file_hash": "abc123"
                },
                {
                    "filename": "academic_transcript.pdf",
                    "content_type": "application/pdf", 
                    "path": "/tmp/transcript.pdf",
                    "size": 512000,
                    "file_hash": "def456"
                },
                {
                    "filename": "recommendation_letter.pdf",
                    "content_type": "application/pdf",
                    "path": "/tmp/lor.pdf", 
                    "size": 128000,
                    "file_hash": "ghi789"
                }
            ],
            "processed_timestamp": datetime.now().isoformat(),
            "email_hash": "test_hash_123"
        },
        "send_confirmation": True,
        "perform_validation": True
    }
    
    print("📧 Sample Email Data:")
    print(f"   From: {sample_email['email_data']['sender']}")
    print(f"   Subject: {sample_email['email_data']['subject']}")
    print(f"   Attachments: {len(sample_email['email_data']['attachments'])}")
    print(f"   Expected Student ID: MIT_JOHN_DOE_COMPUTERSCIENCE")
    print()
    
    try:
        # Test the V2 workflow
        print("🔄 Starting V2 Workflow...")
        response = requests.post(
            f"{MANAGER_URL}/v2/process-email/",
            headers=headers,
            json=sample_email
        )
        
        if response.status_code == 200:
            result = response.json()
            print("✅ V2 Workflow Completed Successfully!")
            print()
            print("📊 Workflow Results:")
            print(f"   Student ID: {result['student_id']}")
            print(f"   Workflow Stage: {result['workflow_stage']}")
            print(f"   Processing Time: {result['processing_time']:.2f}s")
            print()
            print("📋 Workflow Steps:")
            print(f"   ✅ Application Received Email Sent: {result['application_received_sent']}")
            print(f"   ✅ Documents Processed: {result['documents_processed']}")
            print(f"   ✅ Validation Completed: {result['validation_completed']}")
            print(f"   ✅ Validation Email Sent: {result['validation_email_sent']}")
            print(f"   ✅ Marked for Review: {result['marked_for_review']}")
            print()
            
            if result.get('validation_result'):
                validation = result['validation_result']
                print("🔍 Validation Results:")
                print(f"   Status: {'PASSED' if validation['is_valid'] else 'FAILED'}")
                print(f"   Feedback: {validation['feedback']}")
                print()
            
            if result.get('errors'):
                print("⚠️  Errors encountered:")
                for error in result['errors']:
                    print(f"   - {error}")
                print()
                
        else:
            print(f"❌ V2 Workflow Failed: {response.status_code}")
            print(f"   Error: {response.text}")
            
    except requests.exceptions.ConnectionError:
        print("❌ Connection Error: Manager server not running on port 8004")
        print("   Start the manager server first: python servers/manager/main.py")
    except Exception as e:
        print(f"❌ Error: {str(e)}")

def test_review_queue():
    """Test the review queue functionality"""
    print("\n📋 Testing Review Queue...")
    print("=" * 30)
    
    try:
        response = requests.get(f"{MANAGER_URL}/v2/review-queue/", headers=headers)
        
        if response.status_code == 200:
            queue = response.json()
            print(f"✅ Review Queue Retrieved")
            print(f"   Total Applications: {queue['total_applications']}")
            
            if queue['applications']:
                print("\n📝 Applications in Queue:")
                for i, app in enumerate(queue['applications'][-3:], 1):  # Show last 3
                    print(f"   {i}. Student: {app['student_id']}")
                    print(f"      Status: {app['validation_status']}")
                    print(f"      Time: {app['timestamp']}")
                    print()
        else:
            print(f"❌ Failed to get review queue: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Error: {str(e)}")

def test_manager_info():
    """Test the manager info endpoint"""
    print("\n🏠 Manager Server Information...")
    print("=" * 35)
    
    try:
        response = requests.get(f"{MANAGER_URL}/", headers=headers)
        
        if response.status_code == 200:
            info = response.json()
            print("✅ Manager Server Running")
            print(f"   Status: {info['status']}")
            print()
            print("🔧 Configured Services:")
            for service, url in info['services'].items():
                print(f"   {service}: {url}")
            print()
            print("📚 Available API Versions:")
            for version, details in info['api_versions'].items():
                print(f"   {version.upper()}: {details['description']}")
                print(f"   Endpoints: {len(details['endpoints'])}")
        else:
            print(f"❌ Failed to get manager info: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Error: {str(e)}")

if __name__ == "__main__":
    print("🎯 V2 Email Workflow Tester")
    print("=" * 60)
    
    # Test manager info
    test_manager_info()
    
    # Test V2 workflow
    test_v2_workflow()
    
    # Test review queue
    test_review_queue()
    
    print("\n🎉 Testing Complete!")
    print("\nNext Steps:")
    print("1. Start all required servers (emails/out, ai, db)")
    print("2. Use /v2/poll-and-process/ for automatic email processing")
    print("3. Check /v2/review-queue/ for applications requiring review")
    print("4. Monitor validated.txt file for review entries")