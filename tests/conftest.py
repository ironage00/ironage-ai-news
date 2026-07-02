"""pytest 공통 설정.

news_engine은 import 시점에 DB를 초기화하므로, 테스트에서는 실제
Supabase/운영 SQLite 대신 임시 SQLite 파일을 쓰도록 DATABASE_URL을
먼저 고정한다 (news_engine import보다 반드시 앞서야 함).
"""
import os
import sys
import tempfile
import uuid
from pathlib import Path

# 강제 할당 (setdefault 금지) — 환경에 실제 Supabase DATABASE_URL이 있어도
# 테스트가 절대 운영 DB에 붙지 않도록 보장. 파일명은 실행마다 고유(동시 실행 충돌 방지).
_TMP_DB = Path(tempfile.gettempdir()) / f'ironage_test_{uuid.uuid4().hex[:8]}.db'
os.environ['DATABASE_URL'] = f'sqlite:///{_TMP_DB.as_posix()}'

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def pytest_sessionfinish(session, exitstatus):
    """세션 종료 시 임시 SQLite 파일 정리."""
    try:
        _TMP_DB.unlink(missing_ok=True)
    except OSError:
        pass
