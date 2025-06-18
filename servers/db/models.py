from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import date

class Student(BaseModel):
    student_id: str
    student_name: str
    student_email: EmailStr
    student_phone: str
    student_status: str = "active"

class Application(BaseModel):
    student_id: str
    application_id: str
    application_status: str
    intern_project: Optional[str] = None
    intern_project_start_date: Optional[date] = None
    intern_project_end_date: Optional[date] = None
