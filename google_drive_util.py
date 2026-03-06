import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/drive']

def get_drive_service():
    """Shows basic usage of the Drive v3 API.
    Prints the names and ids of the first 10 files the user has access to.
    """
    creds = None
    token_data = os.environ.get('GDRIVE_TOKEN_JSON')
    if token_data:
        try:
            import json
            info = json.loads(token_data)
            creds = Credentials.from_authorized_user_info(info, SCOPES)
            print("✅ Loaded token from environment variable.")
        except Exception as e:
            print(f"⚠️ Warning: Failed to parse GDRIVE_TOKEN_JSON env var. Error: {e}")

    if not creds and os.path.exists('token.json'):
        try:
            creds = Credentials.from_authorized_user_file('token.json', SCOPES)
            print("✅ Loaded token from token.json file.")
        except Exception as e:
            print(f"⚠️ Warning: Failed to parse token.json. Error: {e}")
            
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            creds_data = os.environ.get('GDRIVE_CREDENTIALS_JSON')
            if creds_data:
                try:
                    import json
                    info = json.loads(creds_data)
                    flow = InstalledAppFlow.from_client_config(info, SCOPES)
                    print("✅ Loaded credentials from environment variable.")
                    # In CI/CD headless environment, we can't run_local_server
                    # But if we have a refresh token, creds.refresh() above should work.
                    # This part is mostly for initial auth or local fallback.
                    if not os.environ.get("GITHUB_ACTIONS"):
                         creds = flow.run_local_server(port=0)
                    else:
                         print("❌ Running in GitHub Actions without valid token. Cannot perform interactive login.")
                         raise Exception("GDRIVE_TOKEN_JSON is missing or invalid in GitHub Actions.")
                except Exception as e:
                    print(f"⚠️ Warning: Failed to parse GDRIVE_CREDENTIALS_JSON. Error: {e}")
                    raise e
            elif os.path.exists('credentials.json'):
                flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
                creds = flow.run_local_server(port=0)
            else:
                raise Exception("ไม่พบ credentials.json หรือ GDRIVE_CREDENTIALS_JSON env var")
        # Save the credentials for the next run
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    try:
        service = build('drive', 'v3', credentials=creds)
        return service
    except HttpError as error:
        print(f'An error occurred: {error}')
        return None

def find_or_create_folder(service, folder_name, parent_id=None):
    """ค้นหาโฟลเดอร์ตามชื่อ (ภายใต้ parent_id ถ้าระบุ) ถ้าไม่เจอจะสร้างใหม่"""
    query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    if parent_id:
        query += f" and '{parent_id}' in parents"
    
    results = service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
    files = results.get('files', [])
    
    if files:
        return files[0]['id']
    
    # สร้างโฟลเดอร์ใหม่
    meta = {
        'name': folder_name,
        'mimeType': 'application/vnd.google-apps.folder'
    }
    if parent_id:
        meta['parents'] = [parent_id]
    
    folder = service.files().create(body=meta, fields='id').execute()
    print(f"📁 สร้างโฟลเดอร์ '{folder_name}' สำเร็จ (ID: {folder.get('id')})")
    return folder.get('id')

def get_folder_id_by_path(service, path):
    """แปลง path เช่น 'PK/ยอดขาย' เป็น folder ID โดยสร้างโฟลเดอร์ที่ขาดให้อัตโนมัติ"""
    parts = [p.strip() for p in path.split('/') if p.strip()]
    parent_id = None
    for part in parts:
        parent_id = find_or_create_folder(service, part, parent_id)
    return parent_id

def upload_and_convert_to_gsheet(filepath, filename, folder_path=None):
    service = get_drive_service()
    if not service:
        return None

    file_metadata = {
        'name': filename,
        'mimeType': 'application/vnd.google-apps.spreadsheet' # แปลงเป็น Google Sheet
    }
    
    # ถ้าระบุ folder_path ให้หาหรือสร้างโฟลเดอร์
    if folder_path:
        folder_id = get_folder_id_by_path(service, folder_path)
        if folder_id:
            file_metadata['parents'] = [folder_id]
            print(f"📂 จะอัปโหลดไปที่โฟลเดอร์: {folder_path}")
    
    media = MediaFileUpload(filepath, 
                            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    
    file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
    print(f'✅ อัปโหลดและแปลงไฟล์สำเร็จ File ID: {file.get("id")}')
    return file.get('id')

def upload_file(filepath, filename, folder_name=None):
    """อัปโหลดไฟล์ไปยัง Google Drive โดยใช้ Folder ID จาก env หรือค้นหาตามชื่อ"""
    service = get_drive_service()
    if not service: return None
    
    # 1. หา Folder ID (ลำดับความสำคัญ: ID จาก env > ค้นหาตามชื่อ)
    parent_id = os.environ.get("GDRIVE_FOLDER_ID")
    if not parent_id and folder_name:
        parent_id = get_folder_id_by_path(service, folder_name)

    # 2. ค้นหาไฟล์เดิมที่มีชื่อเดียวกันในโฟลเดอร์นั้น
    query = f"name='{filename}' and trashed=false"
    if parent_id: query += f" and '{parent_id}' in parents"
    
    results = service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
    files = results.get('files', [])

    media = MediaFileUpload(filepath, resumable=True)
    
    if files:
        # อัปเดตไฟล์เดิม
        file_id = files[0]['id']
        file = service.files().update(fileId=file_id, media_body=media).execute()
        print(f"✅ อัปเดตไฟล์ '{filename}' สำเร็จ (ID: {file.get('id')})")
    else:
        # สร้างไฟล์ใหม่
        file_metadata = {'name': filename}
        if parent_id: file_metadata['parents'] = [parent_id]
        file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        print(f"✅ สร้างไฟล์ใหม' '{filename}' สำเร็จ (ID: {file.get('id')})")
    
    return file.get('id')

if __name__ == "__main__":
    print("ระบบตรวจสอบสิทธิ์ Google Drive...")
    try:
        service = get_drive_service()
        if service:
            print("✅ เชื่อมต่อ Google Drive สำเร็จ!")
        else:
            print("❌ เชื่อมต่อ Google Drive ไม่สำเร็จ")
    except Exception as e:
        print(f"❌ Error: {e}")
