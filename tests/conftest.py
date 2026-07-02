"""pytest 공통 설정.

news_engine은 import 시점에 DB를 초기화하므로, 테스트에서는 실제
Supabase/운영 SQLite 대신 임시 SQLite 파일을 쓰도록 DATABASE_URL을
먼저 고정한다 (news_engine import보다 반드시 앞서야 함).
"""
import os
import sys
import tempfile
from pathlib import Path

_TMP_DB = Path(tempfile.gettempdir()) / 'ironage_test_news.db'
os.environ.setdefault('DATABASE_URL', f'sqlite:///{_TMP_DB.as_posix()}')

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
