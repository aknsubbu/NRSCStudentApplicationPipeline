import datetime
from servers.manager.methods import StudentApplicationPipelineClient
from dotenv import load_dotenv
import os

load_dotenv()

client = StudentApplicationPipelineClient(db_api_key=os.getenv("API_KEY"),email_api_key=os.getenv("API_KEY"))
import logging

information_required_emails=client.get_information_required_emails()
print(information_required_emails)
