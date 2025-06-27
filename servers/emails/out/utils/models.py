from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional

class EmailRequest(BaseModel):
    recipient: EmailStr
    subject: str = Field(..., min_length=1)
    body: str = Field(..., min_length=1)
    is_html: bool = False
    file_list: Optional[List[str]] = None  # List of filename strings
    student_id: Optional[str] = None
    object_name: Optional[str] = None
    expires: Optional[int] = Field(3600, ge=1, le=604800)


class TemplateEmailRequest(BaseModel):
    recipient: EmailStr
    subject: str = Field(..., min_length=1)
    template_name: str = Field(..., min_length=1)
    template_data: dict = Field(default_factory=dict)
    file_list: Optional[List[str]] = None  # List of filename strings
    student_id: Optional[str] = None
    object_name: Optional[str] = None
    expires: Optional[int] = Field(3600, ge=1, le=604800)

class TemplateEmailRecieved(BaseModel):
    recipient: EmailStr
    subject: Optional[str] = None
    student_id: Optional[str] = None
    expires: Optional[int] = Field(3600, ge=1, le=604800)
    application_id: Optional[str] = None
    student_name: Optional[str] = None
    
class TemplateEmailInformationRequired(BaseModel):
    recipient: EmailStr
    student_name: Optional[str] = None
    student_id: Optional[str] = None
