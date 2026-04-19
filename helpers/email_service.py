import os
import base64
from typing import List
from azure.communication.email import EmailClient


def send_email(
    subject: str,
    file_path: str,
    body: str,
    recipient_list: List[dict],
    sender_address: str,
):
    """
    Send an email using Azure Communication Services.

    Args:
        subject (str): Subject of the email.
        file_path (str): Path to the file to be attached.
        body (str): Body of the email.
        recipient_list (List[dict]): List of recipients with 'address' and 'displayName'.
        sender_address (str): The sender's email address.
    """
    try:
        # Create the EmailClient object to send Email messages.
        email_client = EmailClient.from_connection_string(
            f'endpoint=https://phmai-email.uk.communication.azure.com/;accesskey={os.environ.get("AZURE_PHM_COMM_SERVICE_PASS")}'
        )

        # Read the file and encode it in base64
        with open(file_path, "rb") as file:
            file_bytes_b64 = base64.b64encode(file.read())

        # Prepare the email message
        message = {
            "content": {
                "subject": subject,
                "plainText": body,
            },
            "recipients": {"to": recipient_list},
            "senderAddress": sender_address,
            "attachments": [
                {
                    "name": os.path.basename(file_path),
                    "contentType": "text/csv",
                    "contentInBase64": file_bytes_b64.decode(),
                }
            ],
        }

        # Send the email
        poller = email_client.begin_send(message)
        print(poller.result())

    except Exception as ex:
        print("Exception:")
        print(ex)


if __name__ == "__main__":
    subject = "A Test Email From Azure Communication Services"
    file_path = "la.csv"
    body = "This is the body of this message. If you have any queries, please do not reply."
    recipient_list = [
        {"address": "sajawalkhan111@gmail.com", "displayName": "Mr. Sajawal Khan"},
        {"address": "jatinarora2689@gmail.com", "displayName": "Mr. Jatin Arora"},
    ]
    sender_address = "donotreply@e444ea86-37e7-4a7d-857b-261cf490d7ce.azurecomm.net"

    send_email(subject, file_path, body, recipient_list, sender_address)
