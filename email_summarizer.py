import os
import base64
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from openai import OpenAI
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from bs4 import BeautifulSoup

# Set up Gmail API
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly', 'https://www.googleapis.com/auth/gmail.send', 'https://www.googleapis.com/auth/gmail.modify']

def authenticate_gmail():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return build('gmail', 'v1', credentials=creds)

def get_unread_emails(service):
    query = "is:unread is:inbox"
    response = service.users().messages().list(userId='me', q=query).execute()
    messages = []
    if 'messages' in response:
        messages.extend(response['messages'])
    return messages

def get_email_data(service, message_id):
    msg = service.users().messages().get(userId='me', id=message_id, format='full').execute()
    payload = msg['payload']
    headers = payload['headers']
    email_data = {'id': message_id}
    
    for header in headers:
        name = header['name']
        value = header['value']
        if name.lower() in ['from', 'date', 'subject']:
            email_data[name.lower()] = value
    
    if 'parts' in payload:
        parts = payload['parts']
        for part in parts:
            if part['mimeType'] in ['text/plain', 'text/html']:
                data = part['body'].get('data')
                if data:
                    text = base64.urlsafe_b64decode(data).decode()
                    if part['mimeType'] == 'text/html':
                        soup = BeautifulSoup(text, 'html.parser')
                        email_data['text'] = soup.get_text()
                    else:
                        email_data['text'] = text
                    break
    else:
        data = payload['body'].get('data')
        if data:
            email_data['text'] = base64.urlsafe_b64decode(data).decode()
    
    return email_data

def email_summarizer(email_text):
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You are a language model that summarizes emails in 3-5 bullet points."},
            {"role": "user", "content": f"Summarize the following in less than 100 words and only using 3-5 bullet points: {email_text}"}
        ],
        temperature=1,
        max_tokens=150
    )
    
    return response.choices[0].message.content

def create_email(sender, to, subject, body):
    message = MIMEMultipart()
    message['To'] = to
    message['From'] = sender
    message['Subject'] = subject
    message.attach(MIMEText(body, 'plain'))
    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
    return {'raw': raw_message}

def send_email(service, email):
    try:
        sent_message = service.users().messages().send(userId='me', body=email).execute()
        print('Successfully sent message.')
    except Exception as error:
        print(f'Error: {error}')

def main():
    service = authenticate_gmail()
    unread_emails = get_unread_emails(service)
    email_summaries = ''
    
    for message in unread_emails:
        email_data = get_email_data(service, message['id'])
        if 'text' in email_data:
            summary = email_summarizer(email_data['text'])
            
            email_summaries += f"From: {email_data.get('from', 'Unknown')}\n"
            email_summaries += f"Subject: {email_data.get('subject', 'No Subject')}\n"
            email_summaries += f"Timestamp: {email_data.get('date', 'Unknown')}\n"
            email_summaries += f"Link: https://mail.google.com/mail/u/0/#inbox/{message['id']}\n"
            email_summaries += f"Summary:\n{summary}\n\n\n"
            
            service.users().messages().modify(
                userId='me',
                id=message['id'],
                body={'removeLabelIds': ['UNREAD', 'INBOX']}
            ).execute()
        else:
            print(f"Skipping email {message['id']} because no text content was found.")
    
    if email_summaries:
        composed_email = create_email("achyutram734@gmail.com", "achyutram734@gmail.com", "Email Summaries", email_summaries)
        send_email(service, composed_email)
    else:
        print("No emails to summarize.")

if __name__ == "__main__":
    main()
