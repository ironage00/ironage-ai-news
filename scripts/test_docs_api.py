"""서비스 계정으로 Google Docs API 직접 테스트."""
import json, os, sys

def load_sa():
    if os.path.exists('ironage-sa.json'):
        return json.load(open('ironage-sa.json'))
    env = os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON')
    if env:
        return json.loads(env)
    return None

sa_info = load_sa()
if not sa_info:
    print("❌ 서비스 계정 키 없음"); sys.exit(1)

print(f"서비스 계정: {sa_info.get('client_email')}")
print(f"프로젝트:   {sa_info.get('project_id')}")

from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/documents', 'https://www.googleapis.com/auth/drive']
creds = service_account.Credentials.from_service_account_info(sa_info, scopes=SCOPES)

drive = build('drive', 'v3', credentials=creds)
docs  = build('docs',  'v1', credentials=creds)

# 1) Docs API - documents().create() (기존 방식)
print("\n[1] Docs API - documents().create() ...")
try:
    doc = docs.documents().create(body={'title': '[TEST] 삭제 가능'}).execute()
    doc_id = doc['documentId']
    drive.files().delete(fileId=doc_id).execute()
    print(f"  ✅ 성공 (삭제 완료)")
except Exception as e:
    print(f"  ❌ 실패: {e}")

# 2) Drive API - Google Docs mimeType으로 생성 (우회 방법)
print("\n[2] Drive API - files().create(mimeType=Docs) ...")
try:
    file = drive.files().create(
        body={'name': '[TEST] 삭제 가능', 'mimeType': 'application/vnd.google-apps.document'},
        fields='id'
    ).execute()
    doc_id = file['id']
    print(f"  ✅ 문서 생성 성공: https://docs.google.com/document/d/{doc_id}/edit")

    # batchUpdate로 텍스트 삽입 테스트
    docs.documents().batchUpdate(
        documentId=doc_id,
        body={'requests': [{'insertText': {'location': {'index': 1}, 'text': '테스트 내용\n'}}]}
    ).execute()
    print("  ✅ batchUpdate 성공")

    drive.files().delete(fileId=doc_id).execute()
    print("  ✅ 테스트 문서 삭제 완료")
except Exception as e:
    print(f"  ❌ 실패: {e}")

# 3) Drive API - files().list()
print("\n[3] Drive API - files().list() ...")
try:
    result = drive.files().list(pageSize=1, fields='files(id,name)').execute()
    print(f"  ✅ 접근 성공")
except Exception as e:
    print(f"  ❌ 실패: {e}")
