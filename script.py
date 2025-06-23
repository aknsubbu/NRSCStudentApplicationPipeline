# test_student_application_pipeline_client.py
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pathlib import Path
from servers.manager.methods import StudentApplicationPipelineClient

# Paths to your sample PDF files
resume = Path("RichardSamuel_Cv.pdf")
lor = Path("PSGCT_RichardSamuel_CSE_AIML.pdf")
class_10 = Path("RichardSamuel_X.pdf")
class_12 = Path("RichardSamuel_XII.pdf")
college = Path("RichardSamuel_Undergrad.pdf")

# Instantiate the client (adjust URLs and API keys if needed)
client = StudentApplicationPipelineClient(
    ai_server_url="http://localhost:8000"
)

# Test AI health check
print("AI Health Check:", client.ai_health_check())

# Test document validation
result = client.validate_documents(
    resume_cover_letter=resume,
    letter_of_recommendation=lor,
    class_10_marksheet=class_10,
    class_12_marksheet=class_12,
    college_marksheets=college
)
print("Validation Result:", result)