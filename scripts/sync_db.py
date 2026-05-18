#!/usr/bin/env python3
"""
Google Drive <-> 로컬 news.db 동기화 스크립트.

사용법:
  python scripts/sync_db.py download   # Drive -> 로컬
  python scripts/sync_db.py upload     # 로컬 -> Drive
"""
import io
import json
import os
import sys
from pathlib import Path

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

SCOPES = ['https://www.googleapis.com/auth/drive']
DB_LOCAL_PATH = 'data/news.db'
DB_DRIVE_NAME = 'news.db'
FOLDER_NAME = 'AI_news'


def get_drive_service():
    sa_json = os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON')
    if not sa_json:
        raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON 환경변수가 설정되지 않았습니다.")
    info = json.loads(sa_json) if isinstance(sa_json, str) else dict(sa_json)
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return build('drive', 'v3', credentials=creds)


def get_or_create_folder(drive, name=FOLDER_NAME):
    q = f"name='{name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    results = drive.files().list(q=q, fields='files(id)').execute()
    folders = results.get('files', [])
    if folders:
        return folders[0]['id']
    folder = drive.files().create(
        body={'name': name, 'mimeType': 'application/vnd.google-apps.folder'},
        fields='id'
    ).execute()
    print(f"✅ '{name}' 폴더 생성")
    return folder['id']


def find_db_file(drive, folder_id):
    q = f"name='{DB_DRIVE_NAME}' and '{folder_id}' in parents and trashed=false"
    results = drive.files().list(q=q, fields='files(id, name, size)').execute()
    files = results.get('files', [])
    return files[0] if files else None


def cmd_download(drive):
    """Drive의 AI_news 폴더에서 news.db를 로컬로 다운로드."""
    folder_id = get_or_create_folder(drive)
    db_file = find_db_file(drive, folder_id)

    if not db_file:
        print("ℹ️  Drive에 news.db 없음 — 새 DB로 시작합니다.")
        return

    Path('data').mkdir(exist_ok=True)

    request = drive.files().get_media(fileId=db_file['id'])
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request, chunksize=4 * 1024 * 1024)
    done = False
    while not done:
        _, done = downloader.next_chunk()

    with open(DB_LOCAL_PATH, 'wb') as f:
        f.write(buf.getvalue())

    size_mb = len(buf.getvalue()) / 1024 / 1024
    print(f"✅ news.db 다운로드 완료 ({size_mb:.1f} MB)")


def cmd_upload(drive):
    """로컬 news.db를 Drive의 AI_news 폴더에 업로드(덮어쓰기)."""
    if not os.path.exists(DB_LOCAL_PATH):
        print(f"⚠️  {DB_LOCAL_PATH} 파일 없음 — 업로드 건너뜀")
        return

    folder_id = get_or_create_folder(drive)
    db_file = find_db_file(drive, folder_id)

    size_mb = os.path.getsize(DB_LOCAL_PATH) / 1024 / 1024
    media = MediaFileUpload(DB_LOCAL_PATH, mimetype='application/x-sqlite3', resumable=True)

    if db_file:
        drive.files().update(fileId=db_file['id'], media_body=media).execute()
    else:
        drive.files().create(
            body={'name': DB_DRIVE_NAME, 'parents': [folder_id]},
            media_body=media,
            fields='id'
        ).execute()

    print(f"✅ news.db 업로드 완료 ({size_mb:.1f} MB)")


if __name__ == '__main__':
    if len(sys.argv) < 2 or sys.argv[1] not in ('download', 'upload'):
        print("사용법: python scripts/sync_db.py [download|upload]")
        sys.exit(1)

    command = sys.argv[1]
    try:
        service = get_drive_service()
        if command == 'download':
            cmd_download(service)
        else:
            cmd_upload(service)
    except Exception as e:
        print(f"❌ 오류 ({command}): {e}")
        sys.exit(1)
