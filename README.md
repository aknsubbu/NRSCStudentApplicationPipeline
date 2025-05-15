# NRSC Student Application Pipeline

This is a pipeline for automated processing of the NRSC Student Applications.
The steps are: -

1. **Data Importing**: The pipeline starts bny importing the email from the mailbox once it is identified as a student application.
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
| AI Platform         | Gemini API (or) Ollama           |
| Calendar Processing | Cal.com (or) Google Calendar API |
