from pydantic import BaseModel, Field

class FileUpload(BaseModel):
    object_name: str = Field(..., min_length=1)
    file_path: str = Field(..., min_length=1)
    student_id: str = Field(..., min_length=1)

class FileDownload(BaseModel):
    object_name: str = Field(..., min_length=1)
    file_path: str = Field(..., min_length=1)
    student_id: str = Field(..., min_length=1)

class ObjectDelete(BaseModel):
    object_name: str = Field(..., min_length=1)
    student_id: str = Field(..., min_length=1)

class PresignedUrl(BaseModel):
    object_name: str = Field(..., min_length=1)
    student_id: str = Field(..., min_length=1)
    expires: int = Field(3600, ge=1, le=604800)  

class FileUploadWithEmail(BaseModel):
    object_name: str = Field(..., min_length=1)
    file_path: str = Field(..., min_length=1)
    student_id: str = Field(..., min_length=1)
    recipient_email: str = Field(..., min_length=1)