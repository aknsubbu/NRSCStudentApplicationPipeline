from minio import Minio
from minio.error import S3Error
import os
from dotenv import load_dotenv

load_dotenv()

def get_minio_client():
    """Initialize and return a MinIO client."""
    return Minio(
        endpoint=os.getenv("MINIO_ENDPOINT", "localhost:9000"),
        access_key=os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
        secret_key=os.getenv("MINIO_SECRET_KEY", "minioadmin123"),
        secure=os.getenv("MINIO_SECURE", "false").lower() == "true"
    )

def upload_file(client: Minio, bucket_name: str, student_id: str, object_name: str, file_path: str):
    """Upload a file to the bucket with student ID prefix."""
    try:
        prefixed_object_name = f"{student_id}/{object_name}"
        client.fput_object(bucket_name, prefixed_object_name, file_path)
        return {"message": f"File '{prefixed_object_name}' uploaded to '{bucket_name}'"}
    except S3Error as e:
        raise Exception(f"Failed to upload file: {str(e)}")

def download_file(client: Minio, bucket_name: str, student_id: str, object_name: str, file_path: str):
    """Download a file from the bucket with student ID prefix."""
    try:
        prefixed_object_name = f"{student_id}/{object_name}"
        client.fget_object(bucket_name, prefixed_object_name, file_path)
        return {"message": f"File '{prefixed_object_name}' downloaded to '{file_path}'"}
    except S3Error as e:
        raise Exception(f"Failed to download file: {str(e)}")

def list_objects(client: Minio, bucket_name: str, student_id: str):
    """List objects for a student in the bucket."""
    try:
        objects = client.list_objects(bucket_name, prefix=f"{student_id}/", recursive=True)
        return [{"name": obj.object_name, "size": obj.size, "last_modified": obj.last_modified} for obj in objects]
    except S3Error as e:
        raise Exception(f"Failed to list objects: {str(e)}")

def delete_object(client: Minio, bucket_name: str, student_id: str, object_name: str):
    """Delete an object from the bucket with student ID prefix."""
    try:
        prefixed_object_name = f"{student_id}/{object_name}"
        client.remove_object(bucket_name, prefixed_object_name)
        return {"message": f"Object '{prefixed_object_name}' deleted from '{bucket_name}'"}
    except S3Error as e:
        raise Exception(f"Failed to delete object: {str(e)}")

def generate_presigned_url(client: Minio, bucket_name: str, student_id: str, object_name: str, expires: int = 3600):
    """Generate a presigned URL for an object with student ID prefix."""
    try:
        prefixed_object_name = f"{student_id}/{object_name}"
        url = client.presigned_get_object(bucket_name, prefixed_object_name, expires=expires)
        return {"url": url}
    except S3Error as e:
        raise Exception(f"Failed to generate presigned URL: {str(e)}")