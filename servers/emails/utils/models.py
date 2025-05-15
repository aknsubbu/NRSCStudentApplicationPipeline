from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional
from fastapi import UploadFile

class EmailRequest(BaseModel):
    recipient: EmailStr
    subject: str = Field(..., min_length=1)
    body: str = Field(..., min_length=1)
    is_html: bool = False
    student_id: Optional[str] = None
    object_name: Optional[str] = None
    expires: Optional[int] = Field(3600, ge=1, le=604800)

class BulkEmailRequest(BaseModel):
    recipients: List[EmailStr]
    subject: str = Field(..., min_length=1)
    body: str = Field(..., min_length=1)
    is_html: bool = False
    student_ids: Optional[List[str]] = None
    object_names: Optional[List[str]] = None
    expires: Optional[int] = Field(3600, ge=1, le=604800)

class TemplateEmailRequest(BaseModel):
    recipient: EmailStr
    subject: str = Field(..., min_length=1)
    template_name: str = Field(..., min_length=1)
    template_data: dict = Field(default_factory=dict)
    student_id: Optional[str] = None
    object_name: Optional[str] = None
    expires: Optional[int] = Field(3600, ge=1, le=604800)
    