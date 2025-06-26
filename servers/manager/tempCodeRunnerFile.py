  # elif response['valid']==False:
                #     logging.info(f"Attachments are invalid for student {student_id}")
                #     validation_data=client.extract_validation_data(response)
                #     #send the validation failed email
                #     client.send_validation_failed_email(recipient=information_required['sender'],subject=f"Document Validation Failed - Action Required ({student_id})",student_id=student_id,object_name="pdf_attachment_validation",expires=36000,template_data={"student_name":student_name,"message":"Your PDF document submission has validation issues that need to be corrected:","issues":validation_data['validation_issues']},file_list=response['file_list'])
