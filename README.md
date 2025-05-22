# NRSC Student Application Pipeline

This is a pipeline for automated processing of the NRSC Student Applications.
The steps are:

1. **Data Importing**: The pipeline automatically polls email inboxes via IMAP, identifies student applications, and extracts relevant data from emails and attachments.
2. **Storage in the MinIO Bucket**: The email and all corresponding attachments are stored in a MinIO bucket. The email is stored in a JSON format, and the attachments are stored in their original format.
3. **Data Processing**: The pipeline processes the email and attachments, extracting relevant information and storing it in a structured format. We are using the gemini API for the validation and a set of rules and requirements for the processing.
4. **Error Handling**: The pipeline includes error handling mechanisms to ensure that any issues encountered during the processing are logged and addressed. This includes handling errors related to the email format, attachment types, and validation failures. After this it jumps to **Sending a reply to the student about fixing the application**.
5. **Sending a reply to the student about fixing the application**: The pipeline sends a reply to the student with information about the errors encountered and instructions on how to fix them.
6. **Sending for review**: The pipeline sends the processed email and attachments for review to the designated reviewers. This includes sending a notification to the reviewers with a link to the email and attachments in the MinIO bucket. The reviewers can then access the email and attachments, review the information, and provide feedback or approval.
7. **Sending a reply to the student about the acceptance**: The pipeline sends a reply to the student with information about the review process and any feedback or approval received from the reviewers.
8. **Sending email about accuiring the further details**: The pipeline sends an email to the student with information about the next steps in the process, including any additional information or documentation required.

## Tech Stack

| Name                | Role                             |
| ------------------- | -------------------------------- |
| Storage             | MinIO Docker Image               |
| Outgoing Emails     | Python SMTP Lib                  |
| Incoming Emails     | IMAP Protocol with Python        |
| AI Platform         | Gemini API (or) Ollama           |
| Calendar Processing | Cal.com (or) Google Calendar API |
| API Framework       | FastAPI                          |
| Containerization    | Docker & Docker Compose          |

## Architecture

The system consists of the following microservices:

1. **DB Server** (Port 8000): Manages file storage in MinIO for student applications
2. **Email Server** (Port 8001): Handles outgoing email communications
3. **Email Polling Server** (Port 8002): Monitors mailboxes for incoming applications
4. **AI Server** (Port 8003): Validates and processes application documents

## Getting Started

### Running with Docker Compose

```bash
# Clone the repository
git clone https://github.com/your-org/nrsc-student-pipeline.git
cd nrsc-student-pipeline

# Set up environment variables
cp .env.sample .env
# Edit .env with your credentials

# Start all services
docker-compose up -d

# View logs
docker-compose logs -f
```

### Manual Setup

```bash
# Create and activate a virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run each server in separate terminals
cd servers/db && python -m uvicorn main:app --host 0.0.0.0 --port 8000
cd servers/emails && python -m uvicorn main:app --host 0.0.0.0 --port 8001
cd servers/email_polling && python -m uvicorn main:app --host 0.0.0.0 --port 8002
cd servers/ai && python -m uvicorn server:app --host 0.0.0.0 --port 8003
```
