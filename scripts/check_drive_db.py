"""Drive의 news.db 메타데이터와 오늘 수집된 기사 수를 확인."""
import json
import os
import re
import sys


def load_sa_json():
    if os.path.exists('ironage-sa.json'):
        return open('ironage-sa.json').read()
    if os.path.exists('streamlit_secrets.toml'):
        txt = open('streamlit_secrets.toml').read()
        m = re.search(r'GOOGLE_SERVICE_ACCOUNT_JSON\s*=\s*"""(.*?)"""', txt, re.DOTALL)
        if m:
            return m.group(1).strip()
    env = os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON')
    if env:
        return env
    return None


sa_json = load_sa_json()
if not sa_json:
    print('❌ 서비스 계정 키를 찾을 수 없음')
    sys.exit(1)

from google.oauth2 import service_account
from googleapiclient.discovery import build

info = json.loads(sa_json)
creds = service_account.Credentials.from_service_account_info(
    info, scopes=['https://www.googleapis.com/auth/drive.readonly']
)
drive = build('drive', 'v3', credentials=creds)

folders = drive.files().list(
    q="name='AI_news' and mimeType='application/vnd.google-apps.folder' and trashed=false",
    fields='files(id)'
).execute().get('files', [])

if not folders:
    print('❌ AI_news 폴더 없음')
    sys.exit(1)

fid = folders[0]['id']

files = drive.files().list(
    q=f"name='news.db' and '{fid}' in parents and trashed=false",
    fields='files(id, name, size, modifiedTime, createdTime)'
).execute().get('files', [])

if not files:
    print('❌ Drive에 news.db 없음 — 어제(5/18) 동기화가 실패했을 가능성 있음')
else:
    f = files[0]
    size_kb = int(f.get('size', 0)) // 1024
    print(f"✅ Drive news.db 확인")
    print(f"   크기:     {size_kb} KB")
    print(f"   수정시각: {f['modifiedTime']}")
    print(f"   생성시각: {f['createdTime']}")
