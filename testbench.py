import datetime
from servers.manager.methods import StudentApplicationPipelineClient
from dotenv import load_dotenv
import os

load_dotenv()

client = StudentApplicationPipelineClient(db_api_key=os.getenv("API_KEY"),email_api_key=os.getenv("API_KEY"))
import logging

client.send_information_required_email(recipient="aknsubbu@gmail.com",student_id="1234567890",student_name="test")