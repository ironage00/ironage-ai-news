"""
IRONAGE AI Analytics System v5.0
뉴스 수집 및 분석 엔진 (오류 수정 버전)
"""

# ==============================================================================
# --- Import 섹션 ---
# ==============================================================================

import sys
import json
import re
import os
import os.path
import time
import warnings

# .env 파일 자동 로드 (로컬 개발용 — 프로덕션은 환경변수 직접 주입)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv 없으면 무시 (환경변수가 이미 주입된 경우)
import urllib.parse
import getpass
import datetime
import logging
import functools
import traceback
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from contextlib import contextmanager

# 네트워크 및 웹
import socket
import requests
import urllib3
import feedparser
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs

# 이메일
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate
from email.header import Header

# 날짜 처리
from dateutil import parser as date_parser
from dateutil.tz import tzutc
import pytz

# Google API
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# AI
import openai
from functools import lru_cache

# SQLAlchemy 2.0 호환
from sqlalchemy import create_engine, Column, Integer, String, Text, Float, DateTime, Boolean
from sqlalchemy.orm import sessionmaker, DeclarativeBase
import pandas as pd
from openpyxl.styles import Font, PatternFill, Alignment

# 병렬 처리
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter, defaultdict
# FIX: DB_ENGINE 재생성 시 thread-safe 보호를 위한 Lock
import threading
_DB_ENGINE_LOCK = threading.Lock()

# ==============================================================================
# --- 모델명 상수 정의 ---
# ==============================================================================

# FIX: 하드코딩된 모델명을 상수로 정의하여 중앙 관리
OPENAI_MODEL_DEFAULT = "gpt-4o"
CLAUDE_MODEL_DEFAULT = "claude-sonnet-4-6"
GEMINI_MODEL_DEFAULT = "gemini-2.5-flash"
PERPLEXITY_MODEL_DEFAULT = "sonar-pro"

# ==============================================================================
# --- SSL 경고 무시 설정 ---
# ==============================================================================

# FIX: SSL 검증은 기본 활성화(verify=True). 개별 요청에서 SSLError 시에만 fallback
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings('ignore', message='Unverified HTTPS request')

# ==============================================================================
# --- 로깅 설정 ---
# ==============================================================================

Path("data/logs").mkdir(parents=True, exist_ok=True)

logger = logging.getLogger('IRONAGE')
logger.setLevel(logging.INFO)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S')
console_handler.setFormatter(console_formatter)

log_filename = f"data/logs/ironage_{datetime.datetime.now().strftime('%Y%m%d')}.log"
file_handler = logging.FileHandler(log_filename, encoding='utf-8')
file_handler.setLevel(logging.INFO)
file_formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
file_handler.setFormatter(file_formatter)

logger.addHandler(console_handler)
logger.addHandler(file_handler)

def log_info(message):
    logger.info(message)
    sys.stdout.flush()

def log_warning(message):
    logger.warning(message)
    sys.stdout.flush()

def log_error(message):
    logger.error(message)
    sys.stdout.flush()

log_info("=" * 60)
log_info("IRONAGE AI Analytics System v5.0 초기화 중...")
log_info("=" * 60)

# ==============================================================================
# --- 예외 클래스 정의 ---
# ==============================================================================

class IRONAGEException(Exception):
    """IRONAGE 시스템 기본 예외"""
    pass

class ConfigurationError(IRONAGEException):
    """설정 오류"""
    pass

class APIError(IRONAGEException):
    """API 호출 오류"""
    pass

class DatabaseError(IRONAGEException):
    """데이터베이스 오류"""
    pass

class NewsCollectionError(IRONAGEException):
    """뉴스 수집 오류"""
    pass

# ==============================================================================
# --- 헬퍼 함수 ---
# ==============================================================================

def safe_execute(func, error_msg="작업 실패", default_return=None):
    """안전한 함수 실행 래퍼"""
    try:
        return func()
    except IRONAGEException as e:
        log_error(f"❌ {error_msg}: {str(e)}")
        return default_return
    except Exception as e:
        log_error(f"❌ 예상치 못한 오류 ({error_msg}): {str(e)}")
        import traceback
        log_error(traceback.format_exc())
        return default_return

def performance_monitor(func):
    """성능 모니터링 데코레이터"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        func_name = func.__name__
        start_time = time.time()
        
        log_info(f"⏱️ [{func_name}] 시작...")
        
        try:
            result = func(*args, **kwargs)
            elapsed = time.time() - start_time
            
            if elapsed < 1:
                log_info(f"✅ [{func_name}] 완료 ({elapsed:.2f}초)")
            elif elapsed < 10:
                log_info(f"✅ [{func_name}] 완료 ({elapsed:.2f}초)")
            else:
                log_warning(f"⚠️ [{func_name}] 완료 (느림: {elapsed:.2f}초)")
            
            return result
        
        except Exception as e:
            elapsed = time.time() - start_time
            log_error(f"❌ [{func_name}] 실패 ({elapsed:.2f}초): {str(e)}")
            raise
    
    return wrapper

@contextmanager
def timeout_context(seconds):
    """타임아웃 컨텍스트 매니저"""
    import socket
    old_timeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(seconds)
    try:
        yield
    finally:
        socket.setdefaulttimeout(old_timeout)

# ==============================================================================
# --- 데이터베이스 모델 ---
# ==============================================================================

log_info("📦 데이터베이스 모듈 로드 중...")

class Base(DeclarativeBase):
    """SQLAlchemy 2.0 Base 클래스"""
    pass

class NewsArticle(Base):
    """뉴스 기사 테이블"""
    __tablename__ = 'news_articles'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(500), nullable=False)
    link = Column(String(1000), unique=True, nullable=False)
    source = Column(String(100))
    published = Column(DateTime)
    collected_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))
    
    content = Column(Text)
    quality_score = Column(Float, default=0.0)
    
    is_selected = Column(Boolean, default=False)
    is_analyzed = Column(Boolean, default=False)
    
    analysis_result = Column(Text)
    ai_model = Column(String(50))
    extracted_keywords = Column(Text)
    
    def __repr__(self):
        return f"<NewsArticle(id={self.id}, title='{self.title[:30]}...')>"


class IssueTracker(Base):
    """주간/월간 핵심 이슈 연속성 추적 테이블"""
    __tablename__ = 'issue_tracker'

    id = Column(Integer, primary_key=True, autoincrement=True)
    issue_key = Column(String(200), nullable=False, index=True)  # 이슈 대표 키워드 (정규화)
    title = Column(String(500), nullable=False)
    description = Column(Text)
    impact_level = Column(String(10))           # 상/중/하
    report_type = Column(String(10))            # weekly / monthly
    report_date = Column(DateTime, nullable=False)
    week_number = Column(Integer)               # ISO 주차
    occurrence_count = Column(Integer, default=1)
    first_seen = Column(DateTime)
    last_seen = Column(DateTime)
    related_articles_json = Column(Text)        # JSON list of {title, link}
    tta_action = Column(Text)
    trend_direction = Column(String(20))        # 상승/유지/하락

    def __repr__(self):
        return f"<IssueTracker(key='{self.issue_key}', count={self.occurrence_count})>"


class StandardizationGap(Base):
    """표준화 공백/선점 필요 영역 누적 DB"""
    __tablename__ = 'standardization_gaps'

    id = Column(Integer, primary_key=True, autoincrement=True)
    area = Column(String(300), nullable=False)  # 표준화 공백 영역명
    description = Column(Text)
    source_issue_title = Column(String(500))    # 발견된 이슈 제목
    report_type = Column(String(10))
    report_date = Column(DateTime, nullable=False)
    status = Column(String(20), default='미해결')  # 미해결/진행중/해결됨
    priority = Column(String(10), default='중')    # 상/중/하
    months_open = Column(Integer, default=0)
    first_detected = Column(DateTime)
    last_updated = Column(DateTime)
    resolution_note = Column(Text)

    def __repr__(self):
        return f"<StandardizationGap(area='{self.area[:40]}', status='{self.status}')>"


class ArticleEmbedding(Base):
    """RAG 검색용 기사 임베딩 저장 테이블"""
    __tablename__ = 'article_embeddings'

    id = Column(Integer, primary_key=True, autoincrement=True)
    article_id = Column(Integer, nullable=False, index=True, unique=True)
    embedding_json = Column(Text, nullable=False)   # JSON float array
    embedded_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))
    model_name = Column(String(100), default='text-embedding-3-small')

    def __repr__(self):
        return f"<ArticleEmbedding(article_id={self.article_id})>"


# ==============================================================================
# --- 데이터베이스 초기화 (중복 제거) ---
# ==============================================================================

def init_database(db_path="data/news.db"):
    """데이터베이스 초기화 및 연결. DATABASE_URL 환경변수 우선, 없으면 SQLite 폴백."""
    try:
        # 환경변수 또는 Streamlit Secrets에서 DB URL 읽기
        db_url = os.environ.get('DATABASE_URL')
        if not db_url:
            try:
                import streamlit as st
                db_url = st.secrets.get('DATABASE_URL')
            except Exception:
                pass

        if db_url:
            # Supabase는 postgresql:// → postgresql+psycopg2:// 변환 필요
            if db_url.startswith('postgresql://'):
                db_url = db_url.replace('postgresql://', 'postgresql+psycopg2://', 1)
            connect_args = {}
            log_info(f"✅ PostgreSQL 연결 모드 (Supabase)")
        else:
            Path("data").mkdir(exist_ok=True)
            db_url = f'sqlite:///{db_path}'
            connect_args = {'check_same_thread': False}
            log_info(f"✅ SQLite 연결 모드: {db_path}")

        engine = create_engine(
            db_url,
            echo=False,
            pool_pre_ping=True,
            pool_recycle=3600,
            connect_args=connect_args,
        )

        Base.metadata.create_all(engine)

        SessionLocal = sessionmaker(
            bind=engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False
        )

        return engine, SessionLocal

    except Exception as e:
        log_error(f"❌ 데이터베이스 초기화 실패: {e}")
        raise DatabaseError(f"DB 초기화 실패: {e}")

# ===== 🔥 추가: 자동 DB 스키마 업데이트 함수 =====

def check_and_migrate_database():
    """
    데이터베이스 스키마 자동 확인 및 업데이트.
    SQLite / PostgreSQL 모두 지원 (SQLAlchemy Inspector 사용).
    """
    from sqlalchemy import inspect, text

    try:
        # 모든 테이블을 ORM 기준으로 생성 (없으면 신규, 있으면 무시)
        Base.metadata.create_all(DB_ENGINE)
        log_info("✅ 테이블 확인/생성 완료")

        inspector = inspect(DB_ENGINE)

        # news_articles 컬럼 목록
        existing_cols = {c['name'] for c in inspector.get_columns('news_articles')}

        # 누락 컬럼 자동 추가
        missing = {
            'extracted_keywords': 'TEXT',
            'ai_model_fallback': 'VARCHAR(100)',
        }
        with DB_ENGINE.connect() as conn:
            for col, col_type in missing.items():
                if col not in existing_cols:
                    log_info(f"🔄 DB 스키마 업데이트: {col} 컬럼 추가 중...")
                    conn.execute(text(f"ALTER TABLE news_articles ADD COLUMN {col} {col_type}"))
                    conn.commit()
                    log_info(f"✅ {col} 컬럼 추가 완료!")

        # user_settings 테이블 생성 (없을 때만)
        is_pg = not DB_ENGINE.url.drivername.startswith('sqlite')
        id_col = "SERIAL PRIMARY KEY" if is_pg else "INTEGER PRIMARY KEY AUTOINCREMENT"
        with DB_ENGINE.connect() as conn:
            conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS user_settings (
                    id {id_col},
                    user_email VARCHAR(255) UNIQUE NOT NULL,
                    keywords TEXT,
                    ai_model VARCHAR(50) DEFAULT 'gemini',
                    email_recipients TEXT,
                    schedule_daily BOOLEAN DEFAULT TRUE,
                    schedule_weekly BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.commit()

        log_info("✅ DB 스키마 최신 상태")

    except Exception as e:
        log_warning(f"⚠️ DB 마이그레이션 중 오류: {e}")
        
        

# 전역 DB 세션 초기화
try:
    DB_ENGINE, SessionLocal = init_database()
    log_info("✅ 데이터베이스 연결 성공")
    check_and_migrate_database()
except Exception as e:
    log_error(f"❌ 치명적 오류: 데이터베이스를 초기화할 수 없습니다.")
    log_error(f"   오류 내용: {e}")
    sys.exit(1)

# ==============================================================================
# --- 데이터베이스 세션 관리 (신규 추가) ---
# ==============================================================================

@contextmanager
def get_db_session():
    """
    데이터베이스 세션 컨텍스트 매니저
    
    Usage:
        with get_db_session() as session:
            article = session.query(NewsArticle).first()
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        log_error(f"❌ DB 세션 오류: {e}")
        raise DatabaseError(f"DB 작업 실패: {e}")
    finally:
        session.close()

# ==============================================================================
# --- 데이터베이스 헬퍼 함수 ---
# ==============================================================================

def deduplicate_news(news_list):
    """중복 제거: (1) URL 정규화 → (2) Jaccard 타이틀 유사도"""
    # --- 1단계: URL 정규화 중복 제거 ---
    seen_links = set()
    url_unique = []

    sorted_news = sorted(
        news_list,
        key=lambda x: x.get('published', ''),
        reverse=True
    )

    for item in sorted_news:
        try:
            normalized_link = re.sub(
                r'^https?://(www\.|m\.|amp\.)?',
                '',
                item['link']
            ).rstrip('/').split('?')[0].split('#')[0]

            if normalized_link not in seen_links:
                url_unique.append(item)
                seen_links.add(normalized_link)
        except Exception:
            log_warning(f"URL 정규화 실패: {item.get('link', 'Unknown')}")
            url_unique.append(item)

    # --- 2단계: Jaccard 타이틀 유사도 중복 제거 ---
    threshold_numeric = CONFIG.get('jaccard_threshold_numeric', 0.5)
    threshold_text = CONFIG.get('jaccard_threshold_text', 0.6)

    used_indices = set()
    title_unique = []

    for i, item in enumerate(url_unique):
        if i in used_indices:
            continue

        similar_group = [item]
        for j in range(i + 1, len(url_unique)):
            if j in used_indices:
                continue
            if is_similar_news(item['title'], url_unique[j]['title'],
                               threshold_numeric, threshold_text):
                similar_group.append(url_unique[j])
                used_indices.add(j)

        representative = max(similar_group, key=lambda x: len(x['title']))
        title_unique.append(representative)

    removed = len(url_unique) - len(title_unique)
    if removed > 0:
        log_info(f"  • 타이틀 유사도 중복 제거: {len(url_unique)}개 → {len(title_unique)}개 ({removed}개 제거)")

    return title_unique

def save_news_to_db(news_items):
    """뉴스 아이템을 DB에 저장"""
    if not SessionLocal:
        log_error("❌ DB 세션이 초기화되지 않았습니다.")
        return 0
    
    saved_count = 0
    
    with get_db_session() as session:
        for item in news_items:
            try:
                existing = session.query(NewsArticle).filter_by(link=item['link']).first()
                
                if not existing:
                    pub_date = None
                    if item.get('published'):
                        try:
                            if isinstance(item['published'], str):
                                pub_date = date_parser.parse(item['published'])
                            elif isinstance(item['published'], datetime.datetime):
                                pub_date = item['published']
                        except Exception:
                            pass
                    
                    article = NewsArticle(
                        title=item['title'],
                        link=item['link'],
                        source=item.get('source', '출처 불명'),
                        published=pub_date,
                        content=item.get('content', ''),
                        quality_score=item.get('quality_score', 0.0)
                    )
                    
                    session.add(article)
                    saved_count += 1
            
            except Exception as e:
                log_warning(f"⚠️ DB 저장 실패: {item.get('title', 'Unknown')[:30]}...")
                continue
    
    log_info(f"   💾 {saved_count}개 뉴스가 DB에 저장되었습니다.")
    return saved_count

def load_news_from_db(days=7, is_analyzed=None):
    """DB에서 뉴스 로드"""
    if not SessionLocal:
        log_error("❌ DB 세션이 초기화되지 않았습니다.")
        return []
    
    with get_db_session() as session:
        try:
            query = session.query(NewsArticle)
            
            # ✅ 수정: timezone-aware datetime 사용
            date_from = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
            query = query.filter(NewsArticle.collected_at >= date_from)
            
            if is_analyzed is not None:
                query = query.filter(NewsArticle.is_analyzed == is_analyzed)
            
            articles = query.order_by(NewsArticle.collected_at.desc()).all()
            
            return [{
                'id': a.id,
                'title': a.title,
                'link': a.link,
                'source': a.source,
                'published': a.published.strftime('%Y-%m-%d %H:%M') if a.published else '',
                'content': a.content,
                'quality_score': a.quality_score,
                'is_analyzed': a.is_analyzed,
                'analysis_result': a.analysis_result,
                'extracted_keywords': a.extracted_keywords
            } for a in articles]
            
        except Exception as e:
            log_error(f"❌ DB 조회 실패: {e}")
            return []

def update_analysis_in_db(article_id: int, analysis_result: str, ai_model: str, keywords_json: str = None):
    """분석 결과 DB 업데이트"""
    if not SessionLocal:
        log_error("❌ DB 세션이 초기화되지 않았습니다.")
        return False
    
    with get_db_session() as session:
        try:
            article = session.get(NewsArticle, article_id)
            if article:
                article.is_analyzed = True
                article.analysis_result = analysis_result
                article.ai_model = ai_model
                if keywords_json:
                    article.extracted_keywords = keywords_json
                return True
            return False
        except Exception as e:
            log_error(f"❌ 분석 결과 저장 실패: {e}")
            return False

def get_db_statistics():
    """DB 통계 조회"""
    if not SessionLocal:
        return {'total': 0, 'analyzed': 0, 'pending': 0, 'today': 0}
    
    with get_db_session() as session:
        try:
            total = session.query(NewsArticle).count()
            analyzed = session.query(NewsArticle).filter_by(is_analyzed=True).count()
            
            # ✅ 수정: timezone-aware datetime 사용
            today_start = datetime.datetime.now(datetime.timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            
            today = session.query(NewsArticle).filter(
                NewsArticle.collected_at >= today_start
            ).count()
            
            return {
                'total': total,
                'analyzed': analyzed,
                'pending': total - analyzed,
                'today': today
            }
        except Exception as e:
            log_error(f"❌ 통계 조회 실패: {e}")
            return {'total': 0, 'analyzed': 0, 'pending': 0, 'today': 0}

log_info("✅ 데이터베이스 모듈 초기화 완료")

# ==============================================================================
# --- 뉴스 중복 제거 및 클러스터링 헬퍼 (모듈 레벨) ---
# ==============================================================================

# 미리 컴파일된 regex 패턴 (반복 컴파일 방지)
_RE_HTML_ENTITY = re.compile(r'&[a-zA-Z]+;')
_RE_HTML_TAG = re.compile(r'<[^>]+>')
_RE_SPECIAL_CHARS = re.compile(r'["\'\[\]()…·\-_|<>]')
_RE_WHITESPACE = re.compile(r'\s+')
_RE_NUMBERS = re.compile(r'\d+(?:만|억|조|기|개|대|%)?|\d+[gG]')

# ICT 키워드 하드코딩 기본값 (config.json 로드 실패 시 fallback)
DEFAULT_ICT_KEYWORDS = [
    '통신', '5G', '6G', 'LTE', '이동통신', '무선', '주파수', '스펙트럼', 'spectrum',
    '위성', 'satellite', '저궤도', 'LEO', 'NTN', '비지상', 'starlink', '스타링크',
    '표준', 'standard', '3GPP', 'ITU', 'ETSI', 'IEEE', 'TTA', 'FCC',
    '과기정통부', '방통위', '규제', 'regulation',
    'AI', '인공지능', 'MIMO', 'beamforming', '빔포밍', 'RAN', 'O-RAN', 'Open RAN',
    'NFV', 'SDN', '네트워크', 'network', 'IoT', '사물인터넷',
    '삼성전자', 'LG전자', 'SK텔레콤', 'KT', 'LG유플러스',
    '에릭슨', 'Ericsson', '노키아', 'Nokia', '화웨이', 'Huawei', '퀄컴', 'Qualcomm',
    'ICT', 'IT', '정보통신', '디지털', '반도체', '칩', 'chip', '갈륨',
    'ISAC', 'D2D', 'V2X', '자율주행', '스마트시티',
]

_STOPWORDS = {
    'the', 'a', 'an', '이', '그', '저', '을', '를', '은', '는', '가',
    '에', '의', '로', '으로', '와', '과', '도', '만', '등', '및', '위해',
    '대한', '통해', '따른', '관련', '대해', '에서', '까지', '부터',
}

_CLUSTERING_ENTITIES = [
    '중국', '미국', '한국', '일본', '유럽', 'china', 'us', 'usa',
    'fcc', 'itu', '3gpp', 'etsi', '과기정통부', 'tta',
    '삼성', 'lg', 'sk', 'kt', '화웨이', '노키아', '에릭슨',
    '스타링크', 'starlink', 'spacex', '스페이스x',
    '이란', '백악관', '트럼프', '바이든',
]


def normalize_title(title: str) -> str:
    """Jaccard 비교를 위한 제목 정규화"""
    title = _RE_HTML_ENTITY.sub('', title)
    title = _RE_SPECIAL_CHARS.sub('', title)
    title = _RE_WHITESPACE.sub(' ', title).strip()
    return title.lower()


def get_title_keywords(title: str) -> set:
    """제목에서 핵심 키워드 추출 (불용어 제거, 2글자 이상)"""
    words = set(normalize_title(title).split())
    return {w for w in words - _STOPWORDS if len(w) >= 2}


def is_similar_news(title1: str, title2: str,
                    threshold_numeric: float = 0.5,
                    threshold_text: float = 0.6) -> bool:
    """두 제목이 유사한 뉴스인지 Jaccard 유사도로 판단"""
    nums1 = set(_RE_NUMBERS.findall(title1))
    nums2 = set(_RE_NUMBERS.findall(title2))

    kw1 = get_title_keywords(title1)
    kw2 = get_title_keywords(title2)

    if not kw1 or not kw2:
        return False

    intersection = len(kw1 & kw2)
    union = len(kw1 | kw2)
    similarity = intersection / union if union > 0 else 0

    # 숫자가 겹칠 때는 낮은 임계값(더 공격적), 없거나 다를 때는 높은 임계값
    if nums1 and nums2 and nums1 == nums2:
        return similarity >= threshold_numeric
    return similarity >= threshold_text


def normalize_for_clustering(title: str) -> str:
    """클러스터링을 위한 제목 정규화"""
    title = _RE_HTML_ENTITY.sub('', title)
    title = _RE_HTML_TAG.sub('', title)
    title = _RE_SPECIAL_CHARS.sub(' ', title)
    title = _RE_WHITESPACE.sub(' ', title).strip()
    return title.lower()


def extract_signature(title: str) -> tuple:
    """뉴스 핵심 시그니처 추출 (숫자 + 주요 개체명) — 클러스터링 키로 사용"""
    normalized = normalize_for_clustering(title)
    numbers = tuple(sorted(_RE_NUMBERS.findall(normalized)))
    key_entities = []
    for word in normalized.split():
        for entity in _CLUSTERING_ENTITIES:
            if entity in word:
                key_entities.append(entity)
                break
    return (numbers, tuple(sorted(set(key_entities))))


# ==============================================================================
# --- 설정 관리 ---
# ==============================================================================

def load_config():
    """config.json에서 설정을 로드. 없으면 환경변수 사용 (Streamlit Cloud)."""
    config_file = Path("data/config.json")

    # Streamlit Cloud 환경에서 사용하는 RSS 피드 및 검색 키워드 기본값
    _default_rss = [
        "https://www.google.co.kr/alerts/feeds/14299983816346888060/2091321787487599294",
        "https://www.google.co.kr/alerts/feeds/14299983816346888060/7282625974461397688",
        "https://www.google.co.kr/alerts/feeds/14299983816346888060/2091321787487600193",
        "https://www.google.co.kr/alerts/feeds/14299983816346888060/2091321787487600258",
        "https://www.google.co.kr/alerts/feeds/14299983816346888060/6144919849490706746",
        "https://www.google.co.kr/alerts/feeds/14299983816346888060/13972650129806487379",
        "https://www.google.co.kr/alerts/feeds/14299983816346888060/12348804382892789873",
        "https://www.google.co.kr/alerts/feeds/14299983816346888060/2496376606356182211",
        "https://www.google.co.kr/alerts/feeds/14299983816346888060/2496376606356184244",
        "https://www.google.co.kr/alerts/feeds/14299983816346888060/6144919849490706848",
        "https://www.itu.int/hub/feed/",
        "https://www.etsi.org/?option=com_obrss&task=feed&id=2:rss-news-press&format=feed&Itemid=1094",
        "https://ieeetv.ieee.org/channel_rss/ieee_future_networks/rss",
        "https://ieeetv.ieee.org/channel_rss/series_channel_9/rss",
        "https://api2.fcc.gov/api/exp/v1.0.0/edocspublic/rss/bureaus/SB",
        "https://api2.fcc.gov/api/exp/v1.0.0/edocspublic/rss/bureaus/IB",
        "https://www.msit.go.kr/user/rss/rss.do?bbsSeqNo=94",
    ]
    _default_queries = ["위성통신", "6G", "클라우드", "3GPP", "FCC", "양자", "UAM", "SDV"]

    default_config = {
        'ai_model': 'openai',
        'openai_api_key': os.environ.get('OPENAI_API_KEY', ''),
        'claude_api_key': os.environ.get('CLAUDE_API_KEY', ''),
        'gemini_api_key': os.environ.get('GEMINI_API_KEY', ''),
        'perplexity_api_key': os.environ.get('PERPLEXITY_API_KEY', ''),
        'naver_client_id': os.environ.get('NAVER_CLIENT_ID', ''),
        'naver_client_secret': os.environ.get('NAVER_CLIENT_SECRET', ''),
        'gmail_sender': os.environ.get('GMAIL_SENDER', ''),
        'gmail_password': os.environ.get('GMAIL_PASSWORD', ''),
        'gmail_receivers': (
            [r.strip() for r in os.environ.get('GMAIL_RECEIVERS', '').split(',') if r.strip()]
            or ([os.environ.get('GMAIL_SENDER')] if os.environ.get('GMAIL_SENDER') else [])
        ),
        'google_alerts_rss': _default_rss,
        'naver_queries': _default_queries,
        'schedule_daily': '09:00',
        'schedule_weekly': 'Monday 09:00',
        'schedule_monthly': '1 09:00',
        'google_chat_webhook': '',
        'alert_impact_level': '상',           # 긴급 알림 최소 중요도
        'standards_org_rss': [
            'https://www.3gpp.org/news-events/3gpp-news/feed',
            'https://www.etsi.org/news-events/news/rss',
            'https://www.itu.int/net/pressoffice/RSS/feed.aspx',
        ],
        'ict_keywords': DEFAULT_ICT_KEYWORDS,
        'ict_min_articles': 25,
        'jaccard_threshold_numeric': 0.5,
        'jaccard_threshold_text': 0.6,
    }
    
    if config_file.exists():
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                user_config = json.load(f)
                default_config.update(user_config)
                log_info("✅ config.json에서 설정을 로드했습니다.")
        except Exception as e:
            log_warning(f"⚠️ config.json 로드 실패: {e}")
            log_info("   기본 설정값을 사용합니다.")
    else:
        log_info("ℹ️  config.json이 없습니다. 환경변수(Streamlit Secrets)에서 API 키를 로드합니다.")
    
    return default_config

# 설정 로드
log_info("📋 설정 파일 로드 중...")
CONFIG = load_config()

# 설정값을 전역 변수로 할당
OPENAI_API_KEY = CONFIG.get('openai_api_key', '')
NAVER_CLIENT_ID = CONFIG.get('naver_client_id', '')
NAVER_CLIENT_SECRET = CONFIG.get('naver_client_secret', '')
SENDER_EMAIL = CONFIG.get('gmail_sender', '')
GMAIL_PASSWORD = CONFIG.get('gmail_password', '')
RECEIVER_EMAIL = CONFIG.get('gmail_receivers', [])
GOOGLE_ALERTS_RSS_URLS = CONFIG.get('google_alerts_rss', [])
NAVER_QUERIES = CONFIG.get('naver_queries', [])

NEWS_TIME_WINDOW_HOURS = 24
SCOPES = ['https://www.googleapis.com/auth/documents', 'https://www.googleapis.com/auth/drive']

# 설정 확인 로그
log_info(f"   • OpenAI API: {'✅ 설정됨' if OPENAI_API_KEY else '❌ 미설정'}")
log_info(f"   • Naver API: {'✅ 설정됨' if NAVER_CLIENT_ID else '❌ 미설정'}")
log_info(f"   • Gmail: {'✅ 설정됨' if SENDER_EMAIL else '❌ 미설정'}")
log_info(f"   • RSS 피드: {len(GOOGLE_ALERTS_RSS_URLS)}개")
log_info(f"   • 검색 키워드: {len(NAVER_QUERIES)}개")

# ==============================================================================
# --- AI 클라이언트 초기화 (멀티 모델 지원) ---
# ==============================================================================

# API 키 기반 클라이언트 캐시 (설정 변경 시 자동 갱신)
_clients_cache: Dict[str, object] = {}

# 폴백 우선순위 (설정 모델 실패 시 순서대로 시도)
_MODEL_FALLBACK_ORDER = ['openai', 'claude', 'gemini', 'perplexity']


def get_openai_client():
    """OpenAI 클라이언트 (설정 변경 자동 반영)"""
    api_key = CONFIG.get('openai_api_key', '') or OPENAI_API_KEY
    if not api_key or api_key == "YOUR_OPENAI_API_KEY":
        raise ConfigurationError("OpenAI API 키가 설정되지 않았습니다.")

    cache_key = f"openai_{api_key[:12]}"
    if cache_key not in _clients_cache:
        log_info("🔑 OpenAI 클라이언트 초기화 중...")
        _clients_cache[cache_key] = openai.OpenAI(api_key=api_key)
    return _clients_cache[cache_key]


def get_claude_client():
    """Anthropic Claude 클라이언트 (설정 변경 자동 반영)"""
    api_key = CONFIG.get('claude_api_key', '')
    if not api_key or api_key == "YOUR_CLAUDE_API_KEY":
        raise ConfigurationError("Claude API 키가 설정되지 않았습니다.")

    cache_key = f"claude_{api_key[:12]}"
    if cache_key not in _clients_cache:
        log_info("🔑 Claude 클라이언트 초기화 중...")
        try:
            from anthropic import Anthropic
            _clients_cache[cache_key] = Anthropic(api_key=api_key)
        except ImportError:
            log_error("❌ anthropic 패키지가 설치되지 않았습니다.")
            log_info("   설치 명령: pip install anthropic")
            raise ConfigurationError("anthropic 패키지를 설치하세요.")
    return _clients_cache[cache_key]


def get_perplexity_client():
    """Perplexity 클라이언트 (설정 변경 자동 반영)"""
    api_key = CONFIG.get('perplexity_api_key', '')
    if not api_key or api_key == "YOUR_PERPLEXITY_API_KEY":
        raise ConfigurationError("Perplexity API 키가 설정되지 않았습니다.")

    cache_key = f"perplexity_{api_key[:12]}"
    if cache_key not in _clients_cache:
        log_info("🔑 Perplexity 클라이언트 초기화 중...")
        import httpx
        _clients_cache[cache_key] = openai.OpenAI(
            api_key=api_key,
            base_url="https://api.perplexity.ai",
            http_client=httpx.Client(verify=False),
        )
    return _clients_cache[cache_key]


def get_gemini_client():
    """Google Gemini 클라이언트 (설정 변경 자동 반영)"""
    api_key = CONFIG.get('gemini_api_key', '')
    if not api_key or api_key == "YOUR_GEMINI_API_KEY":
        raise ConfigurationError("Gemini API 키가 설정되지 않았습니다.")

    cache_key = f"gemini_{api_key[:12]}"
    if cache_key not in _clients_cache:
        log_info("🔑 Gemini 클라이언트 초기화 중...")
        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            # FIX: 하드코딩된 모델명을 상수로 교체
            _clients_cache[cache_key] = genai.GenerativeModel(GEMINI_MODEL_DEFAULT)
        except ImportError:
            log_error("❌ google-generativeai 패키지가 설치되지 않았습니다.")
            log_info("   설치 명령: pip install google-generativeai")
            raise ConfigurationError("google-generativeai 패키지를 설치하세요.")
    return _clients_cache[cache_key]


def clear_clients_cache():
    """API 키 변경 후 클라이언트 캐시 초기화"""
    _clients_cache.clear()
    log_info("🔄 AI 클라이언트 캐시 초기화 완료")


def check_model_health(model_name: str) -> tuple:
    """
    AI 모델 연결 상태를 실제 API 호출로 확인 (최소 토큰 사용)

    Returns:
        (is_healthy: bool, message: str)
    """
    try:
        if model_name == 'openai':
            client = get_openai_client()
            client.chat.completions.create(
                # FIX: 하드코딩된 모델명을 상수로 교체
                model=OPENAI_MODEL_DEFAULT,
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=3,
            )
            return True, "정상"

        elif model_name == 'claude':
            client = get_claude_client()
            client.messages.create(
                # FIX: 하드코딩된 모델명을 상수로 교체
                model=CLAUDE_MODEL_DEFAULT,
                max_tokens=3,
                messages=[{"role": "user", "content": "hi"}]
            )
            return True, "정상"

        elif model_name == 'gemini':
            client = get_gemini_client()
            client.generate_content(
                "hi",
                generation_config={'max_output_tokens': 3}
            )
            return True, "정상"

        elif model_name == 'perplexity':
            client = get_perplexity_client()
            client.chat.completions.create(
                # FIX: 하드코딩된 모델명을 상수로 교체
                model=PERPLEXITY_MODEL_DEFAULT,
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=3,
            )
            return True, "정상"

        else:
            return False, f"알 수 없는 모델: {model_name}"

    except ConfigurationError as e:
        return False, f"API 키 미설정"
    except Exception as e:
        error_msg = str(e).lower()
        if any(k in error_msg for k in ['authentication', 'api key', 'unauthorized', 'invalid_api_key', 'api_key_invalid', 'permission']):
            return False, "API 키 인증 실패"
        elif any(k in error_msg for k in ['rate', 'quota', 'too many']):
            return False, "API 한도 초과"
        elif any(k in error_msg for k in ['timeout', 'connection', 'network', 'unreachable', 'connect']):
            return False, "네트워크 오류"
        else:
            return False, f"오류: {str(e)[:60]}"


def get_ai_client(model_name: str = 'openai'):
    """
    선택된 AI 모델의 클라이언트를 반환
    
    Args:
        model_name: 'openai', 'claude', 'perplexity', 'gemini' 중 하나
    
    Returns:
        해당 AI 클라이언트 객체
    """
    model_map = {
        'openai': get_openai_client,
        'claude': get_claude_client,
        'perplexity': get_perplexity_client,
        'gemini': get_gemini_client
    }
    
    if model_name not in model_map:
        log_warning(f"⚠️ 알 수 없는 모델: {model_name}. OpenAI로 대체합니다.")
        model_name = 'openai'
    
    try:
        return model_map[model_name]()
    except ConfigurationError as e:
        log_error(f"❌ {model_name} 초기화 실패: {e}")
        log_info("   OpenAI로 대체합니다.")
        # FIX: OpenAI 폴백도 실패할 수 있으므로 try-except 추가
        try:
            return get_openai_client()
        except ConfigurationError as fallback_e:
            log_error(f"❌ OpenAI 폴백도 실패: {fallback_e}")
            raise

# ==============================================================================
# --- 네트워크 안정화 함수 ---
# ==============================================================================
        
def wait_for_network(timeout: int = 60) -> bool:
    """
    네트워크 연결이 활성화될 때까지 대기
    
    Args:
        timeout: 최대 대기 시간 (초)
    
    Returns:
        bool: 네트워크 연결 성공 여부
    """
    import socket
    import time
    
    log_info(f"\n🌐 네트워크 연결 확인 중... (최대 {timeout}초 대기)")
    
    start_time = time.time()
    test_hosts = [
        ('www.google.com', 80),
        ('openapi.naver.com', 443),
        ('www.itu.int', 80)
    ]
    
    while time.time() - start_time < timeout:
        for host, port in test_hosts:
            try:
                socket.create_connection((host, port), timeout=5)
                log_info(f"   ✅ 네트워크 연결 성공: {host}")
                return True
            except (socket.timeout, socket.error, OSError):
                continue
        
        # 1초 대기 후 재시도
        time.sleep(1)
        elapsed = int(time.time() - start_time)
        log_info(f"   ⏳ 대기 중... ({elapsed}/{timeout}초)")
    
    log_warning(f"   ❌ 네트워크 연결 실패 (타임아웃: {timeout}초)")
    return False       
        
        
# ==============================================================================
# --- 뉴스 수집 헬퍼 함수 ---
# ==============================================================================

def configure_ssl_warnings(suppress_warnings=True):
    """SSL 관련 경고 제어"""
    if suppress_warnings:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        warnings.filterwarnings('ignore', message='Unverified HTTPS request')
    else:
        warnings.resetwarnings()

def is_within_time_window(date_str, hours=24):
    """주어진 날짜가 지정된 시간 범위 내에 있는지 확인"""
    try:
        if isinstance(date_str, datetime.datetime):
            article_date = date_str
        elif isinstance(date_str, str):
            if '+' in date_str or '-' in date_str[-6:]:
                article_date = datetime.datetime.strptime(
                    date_str, 
                    '%a, %d %b %Y %H:%M:%S %z'
                )
            else:
                article_date = date_parser.parse(date_str)
        elif hasattr(date_str, 'tm_year'):
            article_date = datetime.datetime(
                date_str.tm_year,
                date_str.tm_mon,
                date_str.tm_mday,
                date_str.tm_hour,
                date_str.tm_min,
                date_str.tm_sec
            )
        else:
            log_warning(f"알 수 없는 날짜 형식: {type(date_str)}")
            return True
        
        # FIX: pytz.UTC 대신 datetime.timezone.utc로 통일
        if article_date.tzinfo is None:
            article_date = article_date.replace(tzinfo=datetime.timezone.utc)

        current_time = datetime.datetime.now(datetime.timezone.utc)
        time_diff = current_time - article_date
        
        return time_diff.total_seconds() <= (hours * 3600)
        
    except Exception as e:
        log_warning(f"날짜 파싱 실패: {date_str}, 오류: {str(e)}")
        return True

def extract_google_alerts_url(google_url: str) -> str:
    """구글 알리미 RSS의 복잡한 링크에서 실제 뉴스 URL 추출"""
    try:
        if "&url=" in google_url:
            extracted_url = google_url.split("&url=")[1]
            extracted_url = urllib.parse.unquote(extracted_url)
            if "&" in extracted_url:
                extracted_url = extracted_url.split("&")[0]
            return extracted_url
        
        if "q=" in google_url:
            parsed = urlparse(google_url)
            query_params = parse_qs(parsed.query)
            if 'q' in query_params:
                potential_url = query_params['q'][0]
                if potential_url.startswith('http'):
                    return potential_url
        
        if google_url.startswith('http') and 'google.com' not in google_url:
            return google_url
            
        return google_url
        
    except Exception as e:
        log_warning(f"URL 추출 실패: {str(e)[:100]}")
        return google_url

def get_final_url_and_source(url: str, max_retries: int = 2) -> tuple:
    """리디렉션을 따라가 최종 URL을 찾고 출처를 추출"""
    for attempt in range(max_retries + 1):
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9',
                'Accept-Language': 'ko-KR,ko;q=0.8,en-US;q=0.5,en;q=0.3',
            }
            
            try:
                # FIX: SSL 검증 기본 활성화(verify=True). SSLError 발생 시에만 verify=False로 fallback
                response = requests.get(url, headers=headers, allow_redirects=True,
                                        timeout=(5, 10), verify=True)
            except requests.exceptions.SSLError:
                response = requests.get(url, headers=headers, allow_redirects=True,
                                        timeout=(5, 10), verify=False)
            
            final_url = response.url
            parsed_url = urlparse(final_url)
            domain = parsed_url.netloc
            
            domain_clean = domain.replace('www.', '').replace('m.', '')
            source_parts = domain_clean.split('.')
            
            source_mapping = {
                'chosun': '조선일보', 'donga': '동아일보', 'joongang': '중앙일보',
                'hankyoreh': '한겨레', 'hani': '한겨레', 'khan': '경향신문',
                'mt': '머니투데이', 'mk': '매일경제', 'seoul': '서울신문',
                'ytn': 'YTN', 'sbs': 'SBS', 'kbs': 'KBS', 'mbc': 'MBC',
                'reuters': 'Reuters', 'bloomberg': 'Bloomberg', 'ft': 'Financial Times',
                'wsj': 'Wall Street Journal', 'nytimes': 'New York Times',
                'washingtonpost': 'Washington Post', 'bbc': 'BBC',
                'zdnet': 'ZDNet', 'techcrunch': 'TechCrunch', 'wired': 'Wired'
            }
            
            source_name = source_mapping.get(source_parts[0].lower(), source_parts[0].capitalize())
            
            return final_url, source_name, True
            
        except requests.exceptions.Timeout:
            if attempt < max_retries:
                time.sleep(1)
                continue
                
        except requests.exceptions.RequestException as e:
            if attempt < max_retries:
                time.sleep(1)
                continue
                
        except Exception as e:
            break
    
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.replace('www.', '').replace('m.', '')
        fallback_source = domain.split('.')[0].capitalize() if domain else "출처 불명"
        return url, fallback_source, False
    except Exception:
        return url, "출처 불명", False

def get_article_content(url: str, max_length: int = 3000) -> str:
    """주어진 URL에서 뉴스 기사 본문을 추출"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        try:
            # FIX: SSL 검증 기본 활성화(verify=True). SSLError 발생 시에만 verify=False로 fallback
            response = requests.get(url, headers=headers, timeout=10, verify=True)
        except requests.exceptions.SSLError:
            response = requests.get(url, headers=headers, timeout=10, verify=False)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'lxml')

        for element in soup(["script", "style", "header", "footer", "nav", "aside"]):
            element.decompose()

        article_body = soup.find('article') or \
                       soup.find('div', id=re.compile(r'content|article|main', re.I)) or \
                       soup.find('main')
        
        if article_body:
            text = article_body.get_text(separator='\n', strip=True)
        else:
            paragraphs = soup.find_all('p')
            text = '\n'.join(p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 50)
            if not text:
                text = soup.body.get_text(separator='\n', strip=True) if soup.body else ""

        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        cleaned_text = '\n'.join(chunk for chunk in chunks if chunk)
        
        if not cleaned_text:
            return "기사 본문을 추출하지 못했습니다."

        cleaned_text = cleaned_text[:max_length]
        
        if len(cleaned_text) < 200:
            return "본문이 너무 짧아 분석할 수 없습니다."
        
        sentences = [s.strip() for s in cleaned_text.split('.') if len(s.strip()) > 20]
        if len(sentences) < 3:
            return "본문 품질이 낮아 분석할 수 없습니다."
        
        return cleaned_text

    except requests.exceptions.RequestException as e:
        return f"본문 수집 실패 (네트워크 오류): {e}"
    except Exception as e:
        return f"본문 수집 실패 (알 수 없는 오류): {e}"

# ==============================================================================
# --- 뉴스 수집 메인 함수 ---
# ==============================================================================

@performance_monitor
def get_news_data():
    """여러 RSS 피드와 키워드에서 뉴스를 수집하고 24시간 이내 뉴스만 필터링"""
    news_list = []
    failed_urls = []
    
    stats = {
        'google_alerts': {'total': 0, 'success': 0, 'failed': 0, 'filtered_out': 0},
        'naver': {'total': 0, 'success': 0, 'failed': 0, 'filtered_out': 0}
    }
    
    # FIX: pytz.UTC 대신 datetime.timezone.utc로 통일
    time_threshold = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=NEWS_TIME_WINDOW_HOURS)
    
    log_info(f"\n🔍 Google Alerts에서 최근 {NEWS_TIME_WINDOW_HOURS}시간 이내 뉴스를 수집합니다...")
    log_info(f"   기준 시간: {time_threshold.strftime('%Y-%m-%d %H:%M:%S')} UTC 이후")
    
    # ===== Google Alerts 처리 (병렬 피드 수집) =====
    valid_rss_urls = [(i, url) for i, url in enumerate(GOOGLE_ALERTS_RSS_URLS, 1) if url.strip()]
    n_feeds = len(valid_rss_urls)
    # 모든 피드를 동시에 fetch (I/O bound이므로 피드 수만큼 worker 사용)
    max_feed_workers = max(n_feeds, 1)
    log_info(f"\n  📡 {n_feeds}개 RSS 피드 병렬 수집 시작... (동시 {max_feed_workers}개)")

    def _extract_feed_keyword(feed) -> str:
        """feedparser 객체에서 Google Alerts 키워드 추출"""
        try:
            raw_title = feed.feed.get('title', '')
            # "Google Alerts - {keyword}" 형식에서 키워드 추출
            if ' - ' in raw_title:
                return raw_title.split(' - ', 1)[1].strip()
            return raw_title.strip() or '알 수 없음'
        except Exception:
            return '알 수 없음'

    def _fetch_single_feed(args):
        idx, url = args
        try:
            feed = feedparser.parse(url)
            keyword = _extract_feed_keyword(feed)
            return idx, url, feed, keyword
        except Exception as e:
            log_error(f"  ❌ RSS 피드 수집 실패 [{idx}]: {str(e)[:80]}")
            return idx, url, None, '알 수 없음'

    with ThreadPoolExecutor(max_workers=max_feed_workers) as executor:
        feed_results = list(executor.map(_fetch_single_feed, valid_rss_urls))

    # 수집 완료 후 키워드 요약 출력
    log_info(f"  ✅ 피드 수집 완료. 키워드 목록:")
    for i, rss_url, feed, keyword in sorted(feed_results, key=lambda x: x[0]):
        entry_count = len(feed.entries) if feed and feed.entries else 0
        log_info(f"     [{i:02d}] 🔑 {keyword} → {entry_count}개 항목")

    for i, rss_url, feed, keyword in sorted(feed_results, key=lambda x: x[0]):
        log_info(f"\n  📡 RSS 피드 {i}/{n_feeds} [🔑 {keyword}]: {rss_url[:60]}...")

        try:
            if feed is None or not feed.entries:
                log_warning(f"    ⚠️  피드가 비어있거나 수집에 실패했습니다.")
                continue

            log_info(f"    📰 {len(feed.entries)}개 항목 발견")
            
            # 배치 처리 (50개씩)
            BATCH_SIZE = 50
            
            for batch_start in range(0, len(feed.entries), BATCH_SIZE):
                batch_end = min(batch_start + BATCH_SIZE, len(feed.entries))
                batch_entries = feed.entries[batch_start:batch_end]
                
                log_info(f"    🔄 배치 처리 중: {batch_start+1}~{batch_end}/{len(feed.entries)}")
                
                # 개별 항목 처리
                for j, entry in enumerate(batch_entries, 1):
                    stats['google_alerts']['total'] += 1
                    
                    try:
                        # 제목 추출
                        title_preview = entry.title[:60] if hasattr(entry, 'title') else 'No Title'
                        
                        # 날짜 확인
                        if hasattr(entry, 'published_parsed') and entry.published_parsed:
                            if not is_within_time_window(entry.published_parsed, NEWS_TIME_WINDOW_HOURS):
                                stats['google_alerts']['filtered_out'] += 1
                                
                                try:
                                    article_date = datetime.datetime(*entry.published_parsed[:6])
                                    current_time = datetime.datetime.now()
                                    hours_ago = (current_time - article_date).total_seconds() / 3600
                                    
                                    current_idx = batch_start + j
                                    log_info(f"        ⏭️  [{current_idx}/{len(feed.entries)}] 시간 초과 ({hours_ago:.0f}h 전): {title_preview}...")
                                except Exception:
                                    log_info(f"        ⏭️  시간 초과: {title_preview}...")
                                
                                continue
                            
                            published_date = datetime.datetime(*entry.published_parsed[:6]).strftime('%Y-%m-%d %H:%M')
                        else:
                            published_date = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
                        
                        current_idx = batch_start + j
                        log_info(f"        🔄 [{current_idx}/{len(feed.entries)}] {title_preview}...")
                        
                        # URL 추출 및 처리
                        try:
                            extracted_url = extract_google_alerts_url(entry.link)
                            
                            if len(extracted_url) > 500:
                                log_warning(f"           ❌ URL 너무 김")
                                stats['google_alerts']['failed'] += 1
                                continue
                            
                            final_link, source, success = get_final_url_and_source(extracted_url)
                            
                            if success:
                                stats['google_alerts']['success'] += 1
                                log_info(f"           ✅ 수집: {source}")
                            else:
                                stats['google_alerts']['failed'] += 1
                                failed_urls.append(extracted_url)
                                log_warning(f"           ❌ 실패: URL 추출 오류")
                            
                            news_list.append({
                                "title": entry.title,
                                "link": final_link,
                                "published": published_date,
                                "source": source,
                                "extraction_success": success
                            })
                            
                            time.sleep(0.3)
                            
                        except Exception as url_error:
                            stats['google_alerts']['failed'] += 1
                            failed_urls.append(getattr(entry, 'link', 'Unknown URL'))
                            log_error(f"           ❌ URL 처리 오류: {str(url_error)[:50]}")
                            continue
                    
                    except Exception as entry_error:
                        stats['google_alerts']['failed'] += 1
                        log_error(f"        ❌ 항목 처리 실패: {str(entry_error)[:50]}")
                        continue
                
                # 배치 완료 후 메모리 정리
                if batch_start % 50 == 0 and batch_start > 0:
                    log_info(f"    🧹 메모리 정리 중... (현재 {len(news_list)}개 수집)")
                    import gc
                    gc.collect()
        
        except Exception as feed_error:
            log_error(f"  ❌ RSS 피드 전체 처리 실패: {str(feed_error)[:100]}")
            continue
    
    log_info(f"\n📊 Google Alerts 통계:")
    log_info(f"    • 총 처리: {stats['google_alerts']['total']}개")
    log_info(f"    • 시간 범위 내 뉴스: {stats['google_alerts']['total'] - stats['google_alerts']['filtered_out']}개")
    log_info(f"    • 성공: {stats['google_alerts']['success']}개")
    log_info(f"    • 실패: {stats['google_alerts']['failed']}개")
    log_info(f"    • 시간 초과로 제외: {stats['google_alerts']['filtered_out']}개 ⏰")
    
    # ===== Naver 뉴스 처리 =====
    log_info(f"\n🔍 Naver News에서 최근 {NEWS_TIME_WINDOW_HOURS}시간 이내 뉴스를 수집합니다...")
    
    for i, query in enumerate(NAVER_QUERIES, 1):
        if not query.strip(): 
            continue
            
        log_info(f"  🔍 검색어 {i}/{len(NAVER_QUERIES)}: '{query}'")
        
        try:
            naver_url = "https://openapi.naver.com/v1/search/news.json"
            headers = {
                "X-Naver-Client-Id": NAVER_CLIENT_ID, 
                "X-Naver-Client-Secret": NAVER_CLIENT_SECRET
            }
            params = {"query": query, "display": 30, "sort": "date"}
            
            response = requests.get(naver_url, headers=headers, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()
            
            items = data.get("items", [])
            log_info(f"    📰 {len(items)}개 발견")
            
            for j, item in enumerate(items, 1):
                stats['naver']['total'] += 1
                
                try:
                    # 제목 추출
                    clean_title = re.sub('<[^>]*>', '', item["title"])
                    title_preview = clean_title[:60]
                    
                    # 날짜 확인
                    pub_date_raw = item.get('pubDate')
                    
                    if isinstance(pub_date_raw, str):
                        pub_date = datetime.datetime.strptime(
                            pub_date_raw, '%a, %d %b %Y %H:%M:%S +0900'
                        )
                    elif isinstance(pub_date_raw, datetime.datetime):
                        pub_date = pub_date_raw
                    else:
                        pub_date = datetime.datetime.now()
                    
                    if not is_within_time_window(pub_date, NEWS_TIME_WINDOW_HOURS):
                        stats['naver']['filtered_out'] += 1
                        
                        hours_ago = (datetime.datetime.now() - pub_date).total_seconds() / 3600
                        log_info(f"        ⏭️  [{j}/{len(items)}] 시간 초과 ({hours_ago:.0f}h 전): {title_preview}...")
                        continue
                    
                    published_date = pub_date.strftime('%Y-%m-%d %H:%M')
                    
                    log_info(f"        🔄 [{j}/{len(items)}] {title_preview}...")
                    
                    try:
                        raw_link = item.get("originallink", item["link"])
                        
                        if not raw_link.startswith('http'):
                            log_info(f"           ❌ 잘못된 URL")
                            stats['naver']['failed'] += 1
                            continue
                        
                        final_link, source, success = get_final_url_and_source(raw_link)
                        
                        if success:
                            stats['naver']['success'] += 1
                            log_info(f"           ✅ 수집: {source}")
                        else:
                            stats['naver']['failed'] += 1
                            failed_urls.append(raw_link)
                            log_info(f"           ❌ 실패: URL 추출 오류")
                        
                        news_list.append({
                            "title": clean_title,
                            "link": final_link,
                            "published": published_date,
                            "source": source,
                            "extraction_success": success
                        })
                        
                        time.sleep(0.2)
                        
                    except Exception as url_error:
                        stats['naver']['failed'] += 1
                        log_info(f"           ❌ URL 오류: {str(url_error)[:50]}")
                        continue
                        
                except Exception as item_error:
                    stats['naver']['failed'] += 1
                    log_info(f"           ❌ 오류: {str(item_error)[:50]}")
                    continue
                    
        except Exception as e:
            log_info(f"  ❌ 네이버 뉴스 API 실패: {str(e)[:100]}")
            continue

    log_info(f"\n📊 Naver News 통계:")
    log_info(f"    • 총 처리: {stats['naver']['total']}개")
    log_info(f"    • 시간 범위 내 뉴스: {stats['naver']['total'] - stats['naver']['filtered_out']}개")
    log_info(f"    • 성공: {stats['naver']['success']}개")
    log_info(f"    • 실패: {stats['naver']['failed']}개")
    log_info(f"    • 시간 초과로 제외: {stats['naver']['filtered_out']}개 ⏰")

    # ===== 중복 제거 및 최종 결과 =====
    log_info(f"\n🔄 중복 제거 전: {len(news_list)}개 뉴스")
    unique_news_items = deduplicate_news(news_list)
    log_info(f"🎯 중복 제거 후: {len(unique_news_items)}개 뉴스")
    
    total_items = stats['google_alerts']['total'] + stats['naver']['total']
    total_filtered = stats['google_alerts']['filtered_out'] + stats['naver']['filtered_out']
    total_success = stats['google_alerts']['success'] + stats['naver']['success']
    
    if total_items > 0:
        filter_rate = (total_filtered / total_items * 100) if total_items > 0 else 0
        success_rate = (total_success / (total_items - total_filtered) * 100) if (total_items - total_filtered) > 0 else 0
        
        log_info(f"\n📈 최종 결과:")
        log_info(f"    • 전체 발견: {total_items}개")
        log_info(f"    • 시간 필터 제외: {total_filtered}개 ({filter_rate:.1f}%) ⏰")
        log_info(f"    • 수집 대상: {total_items - total_filtered}개")
        log_info(f"    • 수집 성공: {total_success}개 ({success_rate:.1f}%)")
    
    return unique_news_items


# ==============================================================================
# --- AI 분석 함수 ---
# ==============================================================================

def is_valid_analysis(analysis_result):
    """AI 분석 결과가 유효한지 검증"""
    failure_keywords = [
        "주요내용 정보를 찾을 수 없습니다",
        "시사점 정보를 찾을 수 없습니다",
        "본문 수집 실패",
        "기사 내용 요약이 불가능",
        "기사 본문이 제공되지 않아",
        "분석할 수 없음",
        "AI 심층 분석에 실패했습니다",
        "OpenAI API 키가 설정되지 않아"
    ]
    
    if len(analysis_result) < 100:
        return False
    
    for keyword in failure_keywords:
        if keyword in analysis_result:
            return False
    
    has_main_content = any([
        "주요 내용 요약" in analysis_result,
        "주요 내용" in analysis_result,
        "Main Content" in analysis_result
    ])
    
    has_implications = any([
        "시사점 및 전망" in analysis_result,
        "시사점" in analysis_result,
        "Implications" in analysis_result
    ])
    
    return has_main_content or has_implications


def validate_analysis_output(analysis_text: str, model_name: str = '') -> list:
    """
    Phase 5: is_valid_analysis() 래핑 + 섹션별 세부 검증.
    반환값: 누락 섹션 목록 (빈 리스트 = 완전한 응답)
    """
    if not is_valid_analysis(analysis_text):
        return ['주요 내용 요약', '시사점 및 전망']

    missing = []
    if not any(p in analysis_text for p in ['주요 내용 요약', '주요 내용', 'Main Content']):
        missing.append('주요 내용 요약')
    if not any(p in analysis_text for p in ['시사점 및 전망', '시사점', 'Implications']):
        missing.append('시사점 및 전망')
    return missing


def _phase5_retry_call(model_name: str, retry_prompt: str) -> str:
    """Phase 5 재호출용 단순 API 호출 (에러 무시, None 반환)."""
    try:
        client = get_ai_client(model_name)
        if model_name in ('openai', 'perplexity'):
            resp = client.chat.completions.create(
                model=OPENAI_MODEL_DEFAULT if model_name == 'openai' else PERPLEXITY_MODEL_DEFAULT,
                messages=[
                    {"role": "system", "content": "당신은 ICT 표준 정책 분석 최고 전문가입니다."},
                    {"role": "user", "content": retry_prompt}
                ],
                temperature=0.3,
                max_tokens=3500,
            )
            return resp.choices[0].message.content or ''
        elif model_name == 'claude':
            resp = client.messages.create(
                model=CLAUDE_MODEL_DEFAULT,
                max_tokens=3500,
                messages=[{"role": "user", "content": retry_prompt}]
            )
            return resp.content[0].text if resp.content else ''
        elif model_name == 'gemini':
            resp = client.generate_content(
                retry_prompt,
                generation_config={'temperature': 0.3, 'max_output_tokens': 8192}
            )
            return resp.text or ''
    except Exception as e:
        log_warning(f"      ⚠️ Phase 5 재호출 실패 ({model_name}): {e}")
    return ''


def filter_news_by_ai(
    news_items: List[Dict], 
    ai_model: str = 'openai', 
    max_results: int = 60
) -> List[Dict]:
    """
    AI를 사용하여 중요한 뉴스 선별 (중복 제거 강화)
    
    Args:
        news_items: 수집된 뉴스 목록
        ai_model: 사용할 AI 모델 ('openai', 'claude', 'perplexity', 'gemini')
        max_results: 최대 선별 개수 (기본값: 60)
    
    Returns:
        선별된 뉴스 목록 (중복 제거 후 최대 max_results개)
    """
    
    log_info("\n[🚀 작업 중] AI가 정책 입안자를 위해 뉴스를 선별하고 있습니다...")
    
    # ✅ 수정: ai_model 변수를 함수 시작 시 즉시 초기화
    if ai_model is None:
        ai_model = CONFIG.get('ai_model', 'openai')
    
    log_info(f"   🤖 사용 모델: {ai_model.upper()}")
    log_info(f"   🎯 목표 선별: 최대 {max_results}개 (중복 제거 후)")
    
    # API 키 확인
    api_key_map = {
        'openai': OPENAI_API_KEY,
        'claude': CONFIG.get('claude_api_key', ''),
        'perplexity': CONFIG.get('perplexity_api_key', ''),
        'gemini': CONFIG.get('gemini_api_key', '')
    }
    
    current_api_key = api_key_map.get(ai_model, '')
    
    if not current_api_key or current_api_key.startswith("YOUR_"):
        log_warning(f"  ⚠️ {ai_model.upper()} API 키가 없어 뉴스 선별을 건너뛰고 최신 뉴스 {max_results}개를 반환합니다.")
        return news_items[:max_results]

    # =========================================================================
    # Stage 1: ICT 키워드 사전 필터
    # =========================================================================
    ict_keywords = CONFIG.get('ict_keywords') or DEFAULT_ICT_KEYWORDS
    ict_keywords_lower = [kw.lower() for kw in ict_keywords]
    ict_min = CONFIG.get('ict_min_articles', 25)

    ict_news = [
        item for item in news_items
        if any(kw in item['title'].lower() for kw in ict_keywords_lower)
    ]
    non_ict_count = len(news_items) - len(ict_news)

    if len(ict_news) < ict_min:
        log_warning(f"  ⚠️ ICT 관련 뉴스 {len(ict_news)}개 < 최소 기준 {ict_min}개. 전체 뉴스({len(news_items)}개)로 대체합니다.")
        ict_news = news_items
    else:
        log_info(f"  • Stage 1 ICT 필터: {len(news_items)}개 → {len(ict_news)}개 (비ICT {non_ict_count}개 제외)")

    # =========================================================================
    # Stage 2: 엔티티 클러스터링 — 유사 뉴스 그룹화 후 대표 기사만 AI에 전달
    # =========================================================================
    clusters: dict = {}
    for item in ict_news:
        sig = extract_signature(item['title'])
        clusters.setdefault(sig, []).append(item)

    representative_news = []
    clustered_count = 0
    for sig, items in clusters.items():
        if len(items) > 1:
            clustered_count += len(items) - 1
            representative = max(items, key=lambda x: len(x['title']))
            representative_news.append(representative)
            if len(items) >= 3:
                log_info(f"    → 클러스터 병합 ({len(items)}개): '{representative['title'][:40]}...'")
        else:
            representative_news.append(items[0])

    log_info(f"  • Stage 2 클러스터링: {len(ict_news)}개 → {len(representative_news)}개 (중복 {clustered_count}개 병합)")

    # AI에 전달할 뉴스 목록 (최대 100개)
    news_for_ai = representative_news[:100]

    # 뉴스 목록 포맷팅
    formatted_news_list = ""
    for i, item in enumerate(news_for_ai):
        clean_title = _RE_HTML_TAG.sub('', item['title'])
        formatted_news_list += f"{i}: {clean_title}\n"

    # ✅ 수정: max_results를 프롬프트에 반영
    target_count = max_results
    
    # ✅ 수정: 중복 제거 강화 프롬프트
    prompt = f"""
당신은 ICT 표준 정책 최고 전문가의 수석 보좌관입니다.
당신의 임무는 아래 뉴스 목록에서 **중복을 철저히 제거**한 뒤, '표준 정책 입안자'의 관점에서 가장 중요한 뉴스 {target_count}개를 선별하는 것입니다.

[작업 절차]
1. **1차 중복 제거 (매우 엄격하게 적용):**
   - 동일한 사건, 정책, 기술을 다루는 기사들을 하나의 그룹으로 묶습니다.
   - 예시:
     * "FCC 위성통신 주파수 승인" 관련 기사 5개 → 대표 1개만 선택
     * "삼성전자 6G 투자" 관련 기사 3개 → 대표 1개만 선택
     * "ITU-R WP5D 회의 결과" 관련 기사 4개 → 대표 1개만 선택
   
   - 각 그룹에서 **가장 포괄적이고 정보가 풍부한 기사 1개**만 남깁니다.
   - 판단 기준:
     * 더 많은 구체적 수치와 날짜 포함
     * 더 많은 이해관계자 언급
     * 더 긴 본문 (제목 길이로 추정)
     * 더 권위 있는 출처 (공식 발표 > 언론 보도)

2. **2차 선별 (중복 제거 후):**
   - 중복이 제거된 목록에서 아래 [선별 최우선 기준]에 따라 최종 {target_count}개를 선별합니다.

[선별 최우선 기준]
정책적 중요도를 최우선으로 고려하며, 특히 아래 주제를 다루는 국내외 뉴스에 높은 가중치를 부여합니다.
- **해외 주요국 정책/규제**: 미국(FCC), 유럽(ETSI) 등 해외 주요국의 ICT 정책, 법안, 규제 변화
- **국제 표준화 동향**: 3GPP, ITU 등 국제 표준화 기구의 주요 결정 및 논의 사항
- **국내 정부 계획 및 발표**: 국내 정부 부처가 발표하는 ICT 정책, 법안, 기술 개발 계획
- **산업계 핵심 동향**: ICT 산업 및 시장 판도에 큰 영향을 미치는 국내외 기업의 기술 개발 및 사업 전략
- **정책 비판 및 대안**: 현재 정책의 문제점을 지적하거나 새로운 대안을 제시하는 기사

[필수 제외 기준]
아래 유형의 뉴스는 ICT/통신/표준화와 직접 관련이 없으므로 반드시 제외합니다.
- 지방선거, 선거 운동, 정치인 발언, 정당 관련 뉴스
- 스포츠, 연예, 방송 프로그램 관련 뉴스
- 여행, 관광, 맛집, 생활 정보 뉴스
- 날씨, 재난, 사건·사고(ICT 인프라와 무관한 것)
- ICT/통신/표준화와 직접 관련 없는 일반 경제·사회 뉴스
→ ICT/통신/표준화 기술 및 정책에 직접 관련된 기사만 선택합니다.

[중복 판단 예시]

**중복으로 판단해야 할 경우:**
- 0: FCC, 위성통신 주파수 28GHz 대역 승인 발표
- 5: FCC의 위성통신 주파수 할당 결정 상세 내용
- 12: 미국 FCC, 위성통신 주파수 정책 변경
→ **대표 기사 1개만 선택** (가장 구체적인 기사)

**중복이 아닌 경우:**
- 3: FCC, 위성통신 주파수 28GHz 승인 (미국 정책)
- 8: 과기정통부, 6G 주파수 대역 연구 착수 (한국 정책)
- 15: 3GPP Release 19, 위성통신 표준 논의 (국제 표준)
→ **모두 별개의 사건이므로 유지**

[뉴스 목록]
{formatted_news_list}

[요청]
위 절차와 기준에 따라 **중복을 철저히 제거**한 뒤, 최종적으로 선별된 뉴스의 번호 {target_count}개만 쉼표(,)로 구분하여 응답해 주십시오.
(설명이나 다른 텍스트는 절대 포함하지 마세요. 번호만 응답해야 합니다.)

**중요:** 동일 사건을 다룬 기사가 여러 개 있으면, 반드시 대표 기사 1개만 선택하세요.
"""

    try:
        # ===== 🔥 모델별 API 호출 =====
        
        if ai_model == 'openai':
            client = get_ai_client('openai')
            response = client.chat.completions.create(
                # FIX: 하드코딩된 모델명을 상수로 교체
                model=OPENAI_MODEL_DEFAULT,
                messages=[
                    {"role": "system", "content": f"당신은 ICT 표준 정책 전문가의 유능한 보좌관입니다. 주어진 뉴스 목록에서 **중복을 철저히 제거**하고, 정책적 중요도가 가장 높은 {target_count}개를 골라 번호만 응답합니다."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.0,
            )
            selected_indices_str = response.choices[0].message.content

        elif ai_model == 'claude':
            client = get_ai_client('claude')
            response = client.messages.create(
                # FIX: 하드코딩된 모델명을 상수로 교체
                model=CLAUDE_MODEL_DEFAULT,
                max_tokens=500,
                temperature=0.0,
                system=f"당신은 ICT 표준 정책 전문가의 유능한 보좌관입니다. 주어진 뉴스 목록에서 **중복을 철저히 제거**하고, 정책적 중요도가 가장 높은 {target_count}개를 골라 번호만 응답합니다.",
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            selected_indices_str = response.content[0].text
        
        elif ai_model == 'perplexity':
            client = get_ai_client('perplexity')
            response = client.chat.completions.create(
                # FIX: 하드코딩된 모델명을 상수로 교체
                model=PERPLEXITY_MODEL_DEFAULT,
                messages=[
                    {"role": "system", "content": f"당신은 ICT 표준 정책 전문가의 유능한 보좌관입니다. 주어진 뉴스 목록에서 **중복을 철저히 제거**하고, 정책적 중요도가 가장 높은 {target_count}개를 골라 번호만 응답합니다."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.0,
            )
            selected_indices_str = response.choices[0].message.content

        elif ai_model == 'gemini':
            client = get_ai_client('gemini')
            full_prompt = f"""당신은 ICT 표준 정책 전문가의 유능한 보좌관입니다. 주어진 뉴스 목록에서 **중복을 철저히 제거**하고, 정책적 중요도가 가장 높은 {target_count}개를 골라 번호만 응답합니다.

{prompt}"""
            response = client.generate_content(
                full_prompt,
                generation_config={'temperature': 0.0, 'max_output_tokens': 500}
            )
            selected_indices_str = response.text
        
        else:
            log_warning(f"⚠️ 지원하지 않는 AI 모델: {ai_model}. OpenAI로 대체합니다.")
            client = get_ai_client('openai')
            response = client.chat.completions.create(
                # FIX: 하드코딩된 모델명을 상수로 교체
                model=OPENAI_MODEL_DEFAULT,
                messages=[
                    {"role": "system", "content": f"당신은 ICT 표준 정책 전문가의 유능한 보좌관입니다. 주어진 뉴스 목록에서 **중복을 철저히 제거**하고, 정책적 중요도가 가장 높은 {target_count}개를 골라 번호만 응답합니다."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.0,
            )
            selected_indices_str = response.choices[0].message.content
        
        # ===== 결과 파싱 =====
        log_info(f"  > AI가 선별한 뉴스 인덱스: {selected_indices_str}")

        numbers = re.findall(r'\d+', selected_indices_str)
        selected_indices = [int(n) for n in numbers if int(n) < len(news_for_ai)]

        selected_news = [news_for_ai[i] for i in selected_indices]

        if not selected_news:
            raise ValueError("AI가 유효한 인덱스를 반환하지 않았습니다.")

        for _item in selected_news:
            _item['quality_score'] = 1.0

        log_info(f"  ✅ AI 선별: {len(selected_news)}개 (중복 제거 완료)")
        return selected_news

    except Exception as e:
        log_warning(f"  ⚠️ AI 뉴스 선별 실패: {e}. 최신 뉴스 {max_results}개로 대체합니다.")
        log_error(traceback.format_exc())
        fallback = news_for_ai[:max_results]
        for _item in fallback:
            _item['quality_score'] = 1.0
        return fallback


def verify_deduplication(selected_news: List[Dict]) -> float:
    """
    선별된 뉴스의 중복도 검증
    
    Returns:
        float: 중복도 점수 (0~1, 낮을수록 좋음)
    """
    from difflib import SequenceMatcher
    
    duplicate_count = 0
    total_pairs = 0
    
    for i in range(len(selected_news)):
        for j in range(i + 1, len(selected_news)):
            title1 = selected_news[i]['title'].lower()
            title2 = selected_news[j]['title'].lower()
            
            similarity = SequenceMatcher(None, title1, title2).ratio()
            
            if similarity > 0.7:  # 70% 이상 유사하면 중복으로 판단
                duplicate_count += 1
            
            total_pairs += 1
    
    duplication_rate = duplicate_count / total_pairs if total_pairs > 0 else 0
    
    return duplication_rate

        
        
def enforce_highlight_limit(analysis_text: str, max_ratio: float = 0.30) -> str:
    """AI 분석 결과에서 강조 비율을 30% 이하로 강제 제한"""
    highlights = re.findall(r'\*\*(.*?)\*\*', analysis_text)
    
    if not highlights:
        return analysis_text
    
    clean_text = re.sub(r'\*\*', '', analysis_text)
    total_length = len(clean_text)
    
    if total_length == 0:
        return analysis_text
    
    highlight_length = sum(len(h) for h in highlights)
    current_ratio = highlight_length / total_length
    
    if current_ratio <= max_ratio:
        log_info(f"      ✅ 하이라이트 비율 적정: {current_ratio:.1%}")
        return analysis_text
    
    log_info(f"      ⚠️ 하이라이트 비율 초과: {current_ratio:.1%} → 조정 중...")
    
    target_length = int(total_length * max_ratio)
    
    scored_highlights = []
    for h in highlights:
        score = len(h) * 0.5
        
        high_keywords = ['승인', '결정', '발표', '투자', '계약', '표준', '정책', '규제']
        if any(kw in h for kw in high_keywords):
            score += 50
        
        if re.search(r'\d+', h):
            score += 30
        
        scored_highlights.append((h, score))
    
    scored_highlights.sort(key=lambda x: x[1], reverse=True)
    
    kept_highlights = set()
    current_length = 0
    
    for highlight_text, score in scored_highlights:
        if current_length + len(highlight_text) <= target_length:
            kept_highlights.add(highlight_text)
            current_length += len(highlight_text)
    
    for highlight_text, _ in scored_highlights:
        if highlight_text not in kept_highlights:
            analysis_text = analysis_text.replace(f'**{highlight_text}**', highlight_text)
    
    final_ratio = current_length / total_length if total_length > 0 else 0
    log_info(f"      ✅ 조정 완료: {current_ratio:.1%} → {final_ratio:.1%}")
    
    return analysis_text


def _extract_keyword_json(text: str) -> Optional[str]:
    """
    AI 응답에서 keywords JSON 블록을 안전하게 추출.
    비탐욕 정규식 대신 괄호 카운팅을 사용해 중첩 {} 처리.
    """
    # 1) 코드블록 형식 먼저 시도: ```json { ... } ```
    code_match = re.search(r'```(?:json)?\s*(\{[^`]+\})\s*```', text, re.DOTALL | re.IGNORECASE)
    if code_match:
        candidate = code_match.group(1).strip()
        if '"keywords"' in candidate:
            return candidate

    # 2) "keywords" 키 위치 기준으로 바깥 { } 를 괄호 카운팅으로 찾기
    kw_pos = text.find('"keywords"')
    if kw_pos == -1:
        return None

    brace_start = text.rfind('{', 0, kw_pos)
    if brace_start == -1:
        return None

    depth = 0
    in_string = False
    escape_next = False
    for i, ch in enumerate(text[brace_start:], brace_start):
        if escape_next:
            escape_next = False
            continue
        if ch == '\\' and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return text[brace_start:i + 1]
    return None


@performance_monitor
def analyze_news_with_ai(news_item, max_retries=3, ai_model: str = None):
    """
    AI 분석 (멀티 모델 지원, 자동 폴백 체인 포함)

    설정된 모델이 실패하면 나머지 모델을 순서대로 시도합니다.
    Args:
        news_item: 분석할 뉴스 아이템
        max_retries: 모델별 최대 재시도 횟수
        ai_model: 우선 사용할 AI 모델 (None이면 CONFIG에서 읽음)
    """
    # ── 본문 사전 검사 (모델 무관) ──────────────────────────────────────
    content = news_item.get('content', '')
    if len(content) < 100:
        return "본문이 충분하지 않아 분석할 수 없습니다."

    # ── 프롬프트 (모델 공통, 루프 밖에서 한 번만 생성) ──────────────────
    _today = datetime.date.today()
    _current_year = _today.year
    prompt = f"""
# Mission
당신은 주어진 뉴스 기사 1개를 분석하여, ICT 표준·정책 전문가를 위한 '심층 분석 보고서'를 생성하는 AI 애널리스트입니다.
보고서의 모든 내용은 반드시 기사 본문에 명시된 사실, 데이터, 인용에 근거해야 하며, 당신의 사전 지식이나 외부 정보를 추가해서는 안 됩니다.

**현재 날짜: {_today.strftime('%Y년 %m월 %d일')}** — TTA 조치 사항 작성 시 이 날짜 이후의 미래 시점 또는 현재 기준으로 서술할 것.

**중요**: 전체 분석 내용 중 **가장 핵심적인 30% 이내**만 별표로 강조하세요.

# Persona
- **정체성:** 20년 경력의 ICT 표준·정책 전문 애널리스트.
- **전문성:** 기사 속 데이터와 인용문을 근거로, 기술적·정책적·시장적 인과관계를 분석하고 실질적인 파급효과를 예측하는 데 능숙함.
- **핵심 원칙:** 철저한 '기사 기반(Article-Based)' 분석. 모든 분석과 전망은 기사의 특정 문장이나 수치에 기반하여 논리를 전개함.

# ⚠️ 하이라이트 제한 규칙 (매우 중요)

## 강조 비율 제한:
- **전체 텍스트의 30% 이내만 강조** (매우 엄격하게 적용)
- 각 문단에서 1-2개의 가장 중요한 구문만 선택
- 일반적인 설명이나 배경 정보는 강조하지 않음

## 강조 우선순위 (높은 순서대로):
1. **최우선**: 핵심 의사결정, 정책 변경, 규제 승인
   - 예: "**FCC가 위성통신 주파수 28GHz 대역 승인 결정**"

2. **우선**: 대규모 투자, 중요 계약, 전략적 제휴
   - 예: "**1조원 규모 6G 개발 투자 확정**"

3. **중요**: 기술 돌파구, 성능 개선 수치, 일정 확정
   - 예: "**2025년 3월 표준화 완료 예정**"

4. **보통**: 일반적인 계획, 예상, 전망 (대부분 강조하지 않음)

## 강조하지 말아야 할 내용:
- 일반적인 배경 설명
- 부가적인 정보나 세부사항
- 이미 알려진 사실의 반복
- 단순 나열이나 리스트
- 접속사, 전치사, 일반 동사

## 강조 예시:

### 좋은 예시 ✅ (전체의 30% 이내):
"과기정통부는 **6G 개발에 2025년까지 1조원을 투자**하기로 결정했다. 이번 투자는 민간 기업과의 협력을 통해 진행되며, **주요 연구 분야는 테라헤르츠 통신, AI 기반 네트워크, 위성 통합 기술** 등이다. 삼성전자와 LG전자가 핵심 파트너로 참여하며, 2030년 상용화를 목표로 한다."
→ 전체 3문장 중 2개 구문만 강조 (약 30%)

### 나쁜 예시 ❌ (과도한 강조):
"**과기정통부**는 **6G 개발에 2025년까지 1조원을 투자**하기로 **결정**했다. 이번 **투자**는 **민간 기업과의 협력**을 통해 진행되며, 주요 연구 분야는 **테라헤르츠 통신**, **AI 기반 네트워크**, **위성 통합 기술** 등이다. **삼성전자**와 **LG전자**가 **핵심 파트너로 참여**하며, **2030년 상용화**를 목표로 한다."
→ 거의 모든 내용을 강조 (70% 이상)

# Process (Step-by-Step)
1.  **[1단계: 핵심 정보 추출]**
- 기사에서 '누가, 언제, 어디서, 무엇을, 어떻게, 왜'에 해당하는 6하 원칙 기반의 핵심 사실(fact)을 모두 추출하여 목록화합니다.
- 기사에 언급된 모든 구체적인 수치, 통계, 일정, 고유명사(인물, 기업, 기관, 기술명)를 정확히 식별합니다.
- 주요 이해관계자들의 발언을 인용문 형태로 그대로 추출합니다.

2.  **[2단계: 분석 및 보고서 작성]**
- 아래 **[OUTPUT FORMAT]**에 정의된 구조에 따라 보고서를 작성합니다.
- **[주요 내용 요약]** 파트: 1단계에서 추출한 객관적 사실만을 사용하여 기사의 핵심 내용을 재구성합니다. 어떠한 주관적 해석이나 외부 정보도 포함하지 않습니다.
- **[시사점 및 전망]** 파트: **[주요 내용 요약]**에서 정리된 특정 사실이나 발언을 직접 인용하며, 그것이 왜 중요한지, 어떤 구체적인 영향을 미칠 것인지를 논리적으로 연결하여 분석합니다. "A라는 발언은 B라는 기술 표준 논의에 C와 같은 영향을 미칠 것"과 같이 명확하게 서술합니다.
- 문장은 '~로 분석됨', '~로 판단됨', '~를 시사함' 등 **전문가적 판단을 가미한 서술형 문체**로 작성할 것.

# CONSTRAINTS
- **30% 규칙 엄수:** 전체 텍스트의 30% 이내만 강조 (절대 초과 금지)
- **엄격한 근거 제시:** 모든 분석과 전망은 "기사에 따르면...", "OOO의 발언을 통해 볼 때..." 와 같이 명확한 근거를 제시해야 합니다.
- **추론 금지:** 기사에 명시되지 않은 내용은 절대 언급하지 마십시오.
- **구체성:** "큰 영향을 미칠 것"과 같은 추상적 표현 대신, "어떤 가치사슬(e.g., 칩셋, 단말, 플랫폼)에 어떤 변화를 유발할 것"처럼 구체적으로 서술하십시오.
- **전문가적 문체:** '~로 판단됨', '~를 의미함', '~가 예상됨' 등 전문가의 분석적 어조를 일관되게 사용하십시오.

# Input Data
- 뉴스 제목: {news_item['title']}
- 원문 링크: {news_item['link']}
- 뉴스 본문:
---
{content}
---

# OUTPUT FORMAT

## **뉴스 심층 분석 보고서**

### **1. 주요 내용 요약**
ㅇ [핵심 내용 요약. 가장 중요한 1개 구문만 **강조**]
ㅇ [주요 발언이나 공식 입장. 핵심 결정사항만 **강조**]
ㅇ [기사 본문을 기반으로 핵심 내용을 1-2개의 문장으로 요약. 누가, 무엇을 했는가에 초점을 맞추고, 문장을 'ㅇ'으로 시작하는 글머리 기호로 작성]
ㅇ [기사에 나타난 사건의 배경과 원인을 객관적으로 서술. 문장을 'ㅇ'으로 시작하는 글머리 기호로 작성, 해당 내용이 없으면 해당 섹션을 생략]
ㅇ [기사에 언급된 핵심 수치, 일정, 데이터를 인용하고 그것이 의미하는 팩트를 설명. 문장을 'ㅇ'으로 시작하는 글머리 기호로 작성, 해당 내용이 없으면 해당 섹션을 생략]
ㅇ [주요 인물 또는 기관의 발언이나 공식 입장을 인용하여 정리. 문장을 'ㅇ'으로 시작하는 글머리 기호로 작성, 해당 내용이 없으면 해당 섹션을 생략]

### **2. 시사점 및 전망**
ㅇ [ICT 기술, 표준, 정책, 산업에 미치는 영향. 영향의 주체와 결과를 구문으로 **강조**]
ㅇ [향후 전망과 예상되는 변화. 구체적인 변화 내용을 의미 단위로 **강조**]
ㅇ [기사 내용이 ICT 기술, 표준, 정책, 산업에 미치는 영향과 전망을 'ㅇ'으로 시작하는 글머리 기호로 1~2문장으로 압축하여 서술, 일부 해당 내용이 없으면 해당 섹션을 생략]

### **3. 핵심 키워드 및 영향도 분석**
[JSON 형식으로 아래와 같이 출력하세요 — 키워드, 심층 엔티티, 영향도 분석 모두 필수]
{{
  "keywords": [
    {{"term": "키워드1", "category": "기술/정책/기업/표준", "importance": "high/medium/low"}},
    {{"term": "키워드2", "category": "기술/정책/기업/표준", "importance": "high/medium/low"}}
  ],
  "related_companies": ["기업명1", "기업명2"],
  "key_technologies": ["기술명1", "기술명2"],
  "target_countries": ["국가명1", "국가명2"],
  "impact_level": "Critical",
  "impact_reason": "영향도 판단 근거를 기사 내용에 근거하여 1~2문장으로 서술",
  "tta_action_item": "TTA 표준화본부가 즉시 취해야 할 구체적인 조치 사항",
  "standardization_gap": "현재 표준화 현황과 기사 내용 간의 격차 분석"
}}

**키워드 및 엔티티 추출 규칙:**
- 엔티티 추출: 기사에서 핵심적인 역할을 하는 기업(`related_companies`), 기술(`key_technologies`), 국가(`target_countries`)의 이름을 각각의 배열에 담습니다. (없으면 빈 배열 [])
- **기술명 통합 규칙**: 동의어나 세부 기술명은 가능한 한 대표 기술명(우산 용어)으로 통합하여 추출합니다. 
  - (예: "저궤도 위성통신", "저궤도", "Satellite Communications" -> "위성통신")
  - (예: "인공지능", "생성형 AI", "GenAI" -> "AI")
  - (예: "6세대 이동통신", "Sixth Generation" -> "6G")
- 기술 용어: 5G, 6G, AI, IoT, NTN, Open RAN, 위성통신 등 대표 용어를 사용
- 정책/규제: FCC, 과학기술정보통신부, ofcom, 주파수 할당 등
- 기업: 삼성전자, Apple, Google 등 정식 명칭 사용
- 국가: 미국, 중국, 유럽연합, 한국 등 한글 정식 국가명 사용
- 표준: Release 18, ITU, 3GPP, IEEE 등
- 키워드(`keywords`) 배열에는 최대 10개까지 종합 추출하며, 중요도는 기사 내 출현 빈도와 문맥상 중요성으로 판단합니다.

**영향도(impact_level) 판단 기준 — 반드시 아래 4개 값 중 하나만 사용:**
- "Critical": TTA가 즉각적인 공식 대응이 필요한 긴급 사안 (신규 규제 발효, 표준화 완료 임박, 핵심 기술 돌파구)
- "High": 6개월 내 전략적 대응이 필요한 중요 동향 (주요 국제 표준 논의, 대형 투자 발표, 정책 방향 전환)
- "Medium": 지속 모니터링이 필요한 일반 업계 동향
- "Low": 참고 수준의 배경 정보성 뉴스

**TTA 조치 사항(tta_action_item) 작성 기준:**
- TTA 표준화본부 관점의 구체적 행동 지침 (예: "3GPP SA2 회의 참여 강화", "ITU-T SG13 의견서 제출 검토")
- 기사 내용에 직접 근거한 실질적 대응 방안
- 반드시 한 문장 이상 기재 (빈 문자열 불허)
- **최소 50자 이상** 작성, 구체적 수치·일정·기구명 포함 필수
- ⚠️ 반드시 기사에서 직접 언급된 기술·기구·이슈를 근거로 TTA 고유 행동 지침을 작성할 것. 아래 예시를 절대 그대로 복사하지 말 것 (예: "{_current_year}년 ITU-T FG-AI4EE 회의에서 에너지 효율 표준화 동향 파악 및 국내 의견서 제출 검토")
- TTA는 **국가** 표준화 기관임. '도내', '지역', '지방' 한정 표현 절대 사용 금지 → '국내 산업계', '국내 기업', '국내 회원사' 등으로 표현
- 이미 지난 과거 시점({_current_year - 1}년 이전) 기준의 조치사항 작성 금지 → 현재({_current_year}년) 또는 미래 시점의 실행 가능한 행동 지침만 기재

**표준화 격차(standardization_gap) 작성 기준:**
- 기사 언급 기술·정책과 현 표준화 진행 수준 간의 차이
- 표준화 완료 여부, 현재 논의 단계, 향후 일정 등을 기술
- 기사에서 표준화 관련 정보가 없으면 "기사에서 표준화 현황 정보 미확인"으로 기재
"""

    # ── 폴백 체인 구성 ────────────────────────────────────────────────
    primary_model = ai_model if ai_model is not None else CONFIG.get('ai_model', 'openai')
    fallback_order = [primary_model] + [m for m in _MODEL_FALLBACK_ORDER if m != primary_model]

    failed_models: list = []   # [(model_name, reason), ...]

    for current_model in fallback_order:
        if current_model != primary_model:
            log_warning(f"   ⚠️ [{primary_model.upper()}] 실패 → [{current_model.upper()}] 폴백 시도")

        log_info(f"      🤖 AI 모델: {current_model.upper()}")

        # ── 모델별 재시도 루프 ──────────────────────────────────────
        for attempt in range(max_retries):
            try:
                analysis = None

                # ===== 모델별 API 호출 =====
                if current_model == 'openai':
                    client = get_ai_client('openai')
                    response = client.chat.completions.create(
                        # FIX: 하드코딩된 모델명을 상수로 교체
                        model=OPENAI_MODEL_DEFAULT,
                        messages=[
                            {"role": "system", "content": "당신은 ICT 표준 정책 분석 최고 전문가입니다. 제공된 기사 본문만을 근거로 분석하며, 중요한 부분은 문맥을 고려하여 의미 단위로 **별표**로 강조합니다. 단편적인 키워드가 아닌 의미 있는 구문 단위로 강조하세요."},
                            {"role": "user", "content": prompt}
                        ],
                        temperature=0.3,
                        max_tokens=4096,
                    )
                    analysis = response.choices[0].message.content
                    usage = response.usage
                    log_info(f"      → 토큰 사용: {usage.total_tokens} "
                             f"(입력: {usage.prompt_tokens}, 출력: {usage.completion_tokens})")

                elif current_model == 'claude':
                    client = get_ai_client('claude')
                    response = client.messages.create(
                        # FIX: 하드코딩된 모델명을 상수로 교체
                        model=CLAUDE_MODEL_DEFAULT,
                        max_tokens=4096,
                        temperature=0.3,
                        system="당신은 ICT 표준 정책 분석 최고 전문가입니다. 제공된 기사 본문만을 근거로 분석하며, 중요한 부분은 문맥을 고려하여 의미 단위로 **별표**로 강조합니다. 단편적인 키워드가 아닌 의미 있는 구문 단위로 강조하세요.",
                        messages=[{"role": "user", "content": prompt}]
                    )
                    analysis = response.content[0].text
                    usage = response.usage
                    log_info(f"      → 토큰 사용: {usage.input_tokens + usage.output_tokens} "
                             f"(입력: {usage.input_tokens}, 출력: {usage.output_tokens})")

                elif current_model == 'perplexity':
                    client = get_ai_client('perplexity')
                    response = client.chat.completions.create(
                        # FIX: 하드코딩된 모델명을 상수로 교체
                        model=PERPLEXITY_MODEL_DEFAULT,
                        messages=[
                            {"role": "system", "content": "당신은 ICT 표준 정책 분석 최고 전문가입니다. 제공된 기사 본문만을 근거로 분석하며, 중요한 부분은 문맥을 고려하여 의미 단위로 **별표**로 강조합니다. 단편적인 키워드가 아닌 의미 있는 구문 단위로 강조하세요."},
                            {"role": "user", "content": prompt}
                        ],
                        temperature=0.3,
                        max_tokens=3500,
                    )
                    analysis = response.choices[0].message.content
                    if hasattr(response, 'usage') and response.usage:
                        log_info(f"      → 토큰 사용: {response.usage.total_tokens}")
                    else:
                        log_info(f"      → 토큰 사용: (정보 없음)")

                elif current_model == 'gemini':
                    client = get_ai_client('gemini')
                    full_prompt = (
                        "당신은 ICT 표준 정책 분석 최고 전문가입니다. 제공된 기사 본문만을 근거로 분석하며, "
                        "중요한 부분은 문맥을 고려하여 의미 단위로 **별표**로 강조합니다. "
                        "단편적인 키워드가 아닌 의미 있는 구문 단위로 강조하세요.\n\n" + prompt
                    )
                    response = client.generate_content(
                        full_prompt,
                        generation_config={'temperature': 0.3, 'max_output_tokens': 8192}
                    )
                    analysis = response.text
                    if hasattr(response, 'usage_metadata'):
                        um = response.usage_metadata
                        log_info(f"      → 토큰 사용: {um.total_token_count} "
                                 f"(입력: {um.prompt_token_count}, 출력: {um.candidates_token_count})")
                    else:
                        log_info(f"      → 토큰 사용: (정보 없음)")

                else:
                    # 알 수 없는 모델명 → 즉시 다음 모델로
                    failed_models.append((current_model, f"지원하지 않는 모델"))
                    break

                # ── 결과 검증 ──────────────────────────────────────
                if not analysis:
                    raise ValueError("AI가 빈 응답을 반환했습니다.")

                # ── 후처리 (강조 비율 제한) ─────────────────────────
                analysis = enforce_highlight_limit(analysis, max_ratio=0.30)

                # ── 키워드 추출 ────────────────────────────────────
                try:
                    keyword_json = _extract_keyword_json(analysis)
                    if keyword_json:
                        parsed = json.loads(keyword_json)
                        # 원문에서 키워드 섹션 제거
                        analysis = re.sub(r'###\s*(?:\*\*)?3\.?\s*핵심\s*키워드.*', '', analysis, flags=re.DOTALL | re.IGNORECASE)
                        news_item['extracted_keywords'] = keyword_json
                        # 새 고도화 항목 저장
                        news_item['impact_level'] = parsed.get('impact_level', 'Medium')
                        news_item['impact_reason'] = parsed.get('impact_reason', '')
                        news_item['tta_action_item'] = parsed.get('tta_action_item', '')
                        news_item['standardization_gap'] = parsed.get('standardization_gap', '')
                        log_info(f"      ✅ 키워드 추출 완료: {len(parsed.get('keywords', []))}개  |  영향도: {news_item['impact_level']}")
                    else:
                        news_item['extracted_keywords'] = json.dumps({"keywords": []})
                        news_item['impact_level'] = 'Medium'
                        news_item['impact_reason'] = ''
                        news_item['tta_action_item'] = ''
                        news_item['standardization_gap'] = ''
                        log_warning(f"      ⚠️ 키워드 섹션 없음 (응답 잘림 가능성)")
                except json.JSONDecodeError as kw_err:
                    log_warning(f"      ⚠️ 키워드 JSON 파싱 오류: {kw_err}")
                    news_item['extracted_keywords'] = json.dumps({"keywords": []})
                    news_item.setdefault('impact_level', 'Medium')
                    news_item.setdefault('impact_reason', '')
                    news_item.setdefault('tta_action_item', '')
                    news_item.setdefault('standardization_gap', '')

                # ── Phase 5: 섹션 누락 시 1회 재호출 ────────────────────
                _missing = validate_analysis_output(analysis, current_model)
                if _missing and not news_item.get('_phase5_retried'):
                    news_item['_phase5_retried'] = True
                    _retry_prompt = (
                        prompt + f"\n\n⚠️ 이전 응답에서 다음 섹션이 누락되었습니다: {', '.join(_missing)}"
                        " — 반드시 모든 섹션을 포함하여 다시 작성하세요."
                    )
                    _retry_text = _phase5_retry_call(current_model, _retry_prompt)
                    if _retry_text and len(_retry_text) > 100:
                        analysis = enforce_highlight_limit(_retry_text, max_ratio=0.30)
                        news_item['ai_model_fallback'] = current_model + "_retry"
                        log_info(f"      🔄 Phase 5 재호출: {', '.join(_missing)} 섹션 보완됨")

                # ── 성공 ───────────────────────────────────────────
                news_item['ai_model'] = current_model  # Bug 1: 실제 사용 모델 명시 저장
                if current_model != primary_model and not news_item.get('ai_model_fallback'):
                    log_info(f"      ✅ 폴백 성공: {current_model.upper()} 모델 사용됨")
                    news_item['ai_model_fallback'] = current_model
                return analysis

            # ── 영구 실패: 즉시 다음 모델로 ──────────────────────────
            except ConfigurationError as e:
                log_error(f"      ❌ {current_model.upper()} 설정 오류: {e}")
                failed_models.append((current_model, f"설정 오류: {str(e)[:40]}"))
                break

            except ImportError as e:
                log_error(f"      ❌ {current_model.upper()} 패키지 미설치: {e}")
                failed_models.append((current_model, "패키지 미설치"))
                break

            except Exception as e:
                error_msg = str(e)
                error_lower = error_msg.lower()

                # 인증 실패 → 재시도 의미 없음, 즉시 다음 모델
                if any(k in error_lower for k in ['authentication', 'api key', 'unauthorized',
                                                   'invalid_api_key', 'api_key_invalid', 'permission']):
                    log_error(f"      ❌ {current_model.upper()} 인증 실패 → 다음 모델로")
                    failed_models.append((current_model, "인증 실패"))
                    break

                # Rate Limit → 재시도 후 소진 시 다음 모델
                elif any(k in error_lower for k in ['rate', 'limit', 'quota', 'too many requests']):
                    if attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 5
                        log_warning(f"      ⚠️ Rate Limit, {wait_time}초 후 재시도... ({attempt+1}/{max_retries})")
                        time.sleep(wait_time)
                        continue
                    log_error(f"      ❌ {current_model.upper()} Rate Limit 소진 → 다음 모델로")
                    failed_models.append((current_model, "Rate Limit 초과"))
                    break

                # 네트워크 오류 → 재시도 후 소진 시 다음 모델
                elif any(k in error_lower for k in ['timeout', 'connection', 'network', 'unreachable']):
                    if attempt < max_retries - 1:
                        log_warning(f"      ⚠️ 네트워크 오류, 2초 후 재시도... ({attempt+1}/{max_retries})")
                        time.sleep(2)
                        continue
                    log_error(f"      ❌ {current_model.upper()} 네트워크 오류 소진 → 다음 모델로")
                    failed_models.append((current_model, "네트워크 오류"))
                    break

                # 기타 → 재시도 후 소진 시 다음 모델
                else:
                    log_error(f"      ❌ {current_model.upper()} {type(e).__name__}: {error_msg[:150]}")
                    if attempt < max_retries - 1:
                        log_info(f"      → 2초 후 재시도... ({attempt+1}/{max_retries})")
                        time.sleep(2)
                        continue
                    failed_models.append((current_model, error_msg[:60]))
                    break

    # ── 모든 모델 실패 ────────────────────────────────────────────────
    summary = ', '.join(f"{m}({r})" for m, r in failed_models)
    log_error(f"   ❌ 모든 AI 모델 분석 실패: {summary}")
    return f"모든 AI 모델 분석 실패 [{summary}]"

def analyze_news_with_replacement(news_to_analyze, all_news_items, target_count=20, ai_model: str = None, progress_callback=None):
    """
    뉴스를 분석하되, 실패한 분석은 다른 뉴스로 대체

    Args:
        news_to_analyze: 우선 분석할 뉴스 목록
        all_news_items: 대체 후보 뉴스 목록
        target_count: 목표 분석 개수
        ai_model: 사용할 AI 모델
        progress_callback: 1건 성공 시 호출되는 함수 (done: int, total: int) — UI 진행률 업데이트용
    """
    # ✅ 추가: AI 모델 결정
    if ai_model is None:
        ai_model = CONFIG.get('ai_model', 'openai')
    
    analyzed_results = []
    analyzed_links = set()
    failed_count = 0

    primary_index = 0      # news_to_analyze 포인터
    replacement_index = 0  # all_news_items(대체 풀) 포인터 — 항상 0부터 시작

    log_info(f"\n🚀 뉴스 심층 분석 시작 (목표: {target_count}개, 모델: {ai_model.upper()})")

    while len(analyzed_results) < target_count:
        # Phase 1: 우선 후보에서 순서대로 꺼냄
        if primary_index < len(news_to_analyze):
            item = news_to_analyze[primary_index]
            primary_index += 1
        # Phase 2: 우선 후보 소진 → 대체 풀에서 순서대로 꺼냄
        elif replacement_index < len(all_news_items):
            item = all_news_items[replacement_index]
            replacement_index += 1
        else:
            log_warning("  ⚠️  더 이상 분석할 뉴스가 없습니다.")
            break

        if item['link'] in analyzed_links:
            continue

        log_info(f"  ({len(analyzed_results)+1}/{target_count}) 분석 중: {item['title'][:50]}...")

        log_info(f"      → 본문 수집 중...")
        item['content'] = get_article_content(item['link'])

        if "실패" in item['content'] or "추출하지 못했습니다" in item['content']:
            log_warning(f"      ❌ 본문 수집 실패, 다른 뉴스로 대체합니다.")
            failed_count += 1
            continue

        if "너무 짧아" in item['content'] or "품질이 낮아" in item['content']:
            log_warning(f"      ❌ 본문 품질 불량, 다른 뉴스로 대체합니다.")
            failed_count += 1
            continue

        log_info(f"      → AI 분석 중 ({ai_model.upper()})...")
        analysis = analyze_news_with_ai(item, ai_model=ai_model)

        if is_valid_analysis(analysis):
            item['analysis_result'] = analysis
            analyzed_results.append(item)
            analyzed_links.add(item['link'])
            with get_db_session() as session:
                article = session.query(NewsArticle).filter_by(link=item['link']).first()
                if article:
                    article.is_analyzed = True  # Bug 6+7: 분석 완료 플래그 저장
                    article.ai_model = item.get('ai_model', ai_model)  # Bug 1: 실제 사용 모델 저장
                    if item.get('ai_model_fallback'):
                        if hasattr(article, 'ai_model_fallback'):
                            article.ai_model_fallback = item['ai_model_fallback']
                    if item.get('extracted_keywords'):
                        article.extracted_keywords = item['extracted_keywords']
                    # 방안 B: 스크래핑 본문을 DB에 저장 → RAG 임베딩 품질 향상
                    scraped = item.get('content', '')
                    if scraped and not article.content:
                        article.content = scraped[:2000]

            log_info(f"      ✅ 분석 성공")
            if progress_callback:
                progress_callback(len(analyzed_results), target_count)
        else:
            log_warning(f"      ❌ 분석 실패, 다른 뉴스로 대체합니다.")
            failed_count += 1

        time.sleep(0.5)
    
    log_info(f"\n📊 분석 완료 통계:")
    log_info(f"    • 성공: {len(analyzed_results)}개")
    log_info(f"    • 실패 및 대체: {failed_count}개")
    log_info(f"    • 최종 분석된 뉴스: {len(analyzed_results)}개")
    log_info(f"    • 사용 모델: {ai_model.upper()}")
    
    return analyzed_results


@performance_monitor
# FIX: 반환 타입 불일치 - None 반환 케이스가 있으므로 Optional[str]로 수정
def save_keyword_summary_to_excel(analyzed_results: List[Dict], output_dir: str = "data/reports") -> Optional[str]:
    """
    키워드 통계를 별도 엑셀 시트로 저장
    
    Args:
        analyzed_results: 분석된 뉴스 목록
        output_dir: 저장 폴더 경로
    
    Returns:
        str: 생성된 엑셀 파일 경로
    """
    if not analyzed_results:
        log_warning("⚠️ 저장할 키워드 데이터가 없습니다.")
        return None
    
    log_info(f"\n📊 키워드 통계를 엑셀로 저장 중...")
    
    try:
        # 키워드 집계
        all_keywords = []
        keyword_by_category = defaultdict(list)
        keyword_by_importance = defaultdict(list)
        
        for item in analyzed_results:
            if item.get('extracted_keywords'):
                try:
                    keywords_data = json.loads(item['extracted_keywords'])
                    keywords_list = keywords_data.get('keywords', [])
                    
                    for kw in keywords_list:
                        term = kw.get('term', '')
                        category = kw.get('category', '기타')
                        importance = kw.get('importance', 'medium')
                        
                        if term:
                            all_keywords.append(term)
                            keyword_by_category[category].append(term)
                            keyword_by_importance[importance].append(term)
                except Exception:
                    pass
        
        # 빈도 계산
        keyword_freq = Counter(all_keywords)
        
        # 파일명 생성
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"keyword_summary_{timestamp}.xlsx"
        filepath = Path(output_dir) / filename
        
        # 엑셀 저장
        with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
            # 시트 1: 전체 키워드 빈도
            df_freq = pd.DataFrame(
                keyword_freq.most_common(100),
                columns=['키워드', '빈도']
            )
            df_freq['순위'] = range(1, len(df_freq) + 1)
            df_freq = df_freq[['순위', '키워드', '빈도']]
            df_freq.to_excel(writer, index=False, sheet_name='전체 키워드')
            
            # 시트 2: 카테고리별 통계
            category_stats = []
            for category, keywords in keyword_by_category.items():
                top_keywords = Counter(keywords).most_common(5)
                category_stats.append({
                    '카테고리': category,
                    '총 개수': len(keywords),
                    'TOP 5 키워드': ', '.join([kw[0] for kw in top_keywords])
                })
            df_category = pd.DataFrame(category_stats)
            df_category.to_excel(writer, index=False, sheet_name='카테고리별 통계')
            
            # 시트 3: 중요도별 통계
            importance_stats = []
            for importance, keywords in keyword_by_importance.items():
                top_keywords = Counter(keywords).most_common(5)
                importance_stats.append({
                    '중요도': importance,
                    '총 개수': len(keywords),
                    'TOP 5 키워드': ', '.join([kw[0] for kw in top_keywords])
                })
            df_importance = pd.DataFrame(importance_stats)
            df_importance.to_excel(writer, index=False, sheet_name='중요도별 통계')
            
            # 스타일 적용
            
            for sheet_name in writer.sheets:
                worksheet = writer.sheets[sheet_name]
                
                # 헤더 스타일
                header_fill = PatternFill(start_color="70AD47", end_color="70AD47", fill_type="solid")
                header_font = Font(bold=True, color="FFFFFF", size=11)
                
                for cell in worksheet[1]:
                    cell.fill = header_fill
                    cell.font = header_font
                    cell.alignment = Alignment(horizontal='center', vertical='center')
                
                # 열 너비 조정
                for column in worksheet.columns:
                    max_length = 0
                    column_letter = column[0].column_letter
                    
                    for cell in column:
                        try:
                            if len(str(cell.value)) > max_length:
                                max_length = len(str(cell.value))
                        except Exception:
                            pass
                    
                    adjusted_width = min(max_length + 2, 60)
                    worksheet.column_dimensions[column_letter].width = adjusted_width
        
        log_info(f"  ✅ 키워드 통계 저장 완료: {filepath}")
        log_info(f"     - 총 {len(keyword_freq)}개 고유 키워드")
        log_info(f"     - 파일 크기: {filepath.stat().st_size / 1024:.1f} KB")
        
        return str(filepath)
        
    except Exception as e:
        log_error(f"❌ 키워드 통계 저장 실패: {e}")
        log_error(traceback.format_exc())
        return None







# ==============================================================================
# --- 구글 문서 생성 함수 ---
# ==============================================================================

def get_google_docs_service():
    """Google Docs와 Drive API 서비스를 인증하고 생성.
    우선순위: 1) 환경변수 GOOGLE_SERVICE_ACCOUNT_JSON
              2) ironage-sa.json 파일
              3) 레거시 OAuth2 token.json (로컬 개발용)
    """
    # ── 우선순위 1: OAuth2 사용자 토큰 (Docs 생성 가능, GitHub Actions용) ──
    token_json_str = os.environ.get('GOOGLE_TOKEN_JSON')
    if not token_json_str:
        try:
            import streamlit as st
            token_json_str = st.secrets.get('GOOGLE_TOKEN_JSON')
        except Exception:
            pass
    if not token_json_str and os.path.exists('token.json'):
        token_json_str = open('token.json').read()

    if token_json_str:
        try:
            token_info = json.loads(token_json_str) if isinstance(token_json_str, str) else dict(token_json_str)
            creds = Credentials.from_authorized_user_info(token_info, SCOPES)
            if not creds.valid:
                if creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    raise ValueError("OAuth2 토큰 만료, 재인증 필요")
            docs_service = build('docs', 'v1', credentials=creds)
            drive_service = build('drive', 'v3', credentials=creds)
            log_info("  ✅ OAuth2 사용자 인증 성공")
            return docs_service, drive_service
        except Exception as e:
            log_warning(f"  ⚠️ OAuth2 인증 실패 ({e}), 서비스 계정으로 폴백")

    # ── 우선순위 2: 서비스 계정 (Docs 생성 불가, Drive 전용) ──────────────
    sa_json_str = os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON')
    if not sa_json_str:
        try:
            import streamlit as st
            sa_json_str = st.secrets.get('GOOGLE_SERVICE_ACCOUNT_JSON')
        except Exception:
            pass

    if sa_json_str:
        try:
            info = json.loads(sa_json_str) if isinstance(sa_json_str, str) else dict(sa_json_str)
            creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
            docs_service = build('docs', 'v1', credentials=creds)
            drive_service = build('drive', 'v3', credentials=creds)
            log_info("  ✅ Service Account 인증 성공")
            return docs_service, drive_service
        except Exception as e:
            log_error(f"  ❌ Service Account 인증 실패: {type(e).__name__}: {e}")
            raise

    if os.path.exists('ironage-sa.json'):
        creds = service_account.Credentials.from_service_account_file(
            'ironage-sa.json', scopes=SCOPES
        )
        docs_service = build('docs', 'v1', credentials=creds)
        drive_service = build('drive', 'v3', credentials=creds)
        return docs_service, drive_service

    # ── 우선순위 3: 브라우저 재인증 (로컬 개발 전용) ───────────────────────
    flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
    creds = flow.run_local_server(port=0)
    with open('token.json', 'w') as f:
        f.write(creds.to_json())

    docs_service = build('docs', 'v1', credentials=creds)
    drive_service = build('drive', 'v3', credentials=creds)
    return docs_service, drive_service

IMPACT_LEVEL_ORDER = {'Critical': 0, 'High': 1, 'Medium': 2, 'Low': 3}
IMPACT_LEVEL_ICON = {'Critical': '🚨', 'High': '⚠️', 'Medium': '📋', 'Low': 'ℹ️'}
IMPACT_LEVEL_COLOR_RGB = {
    'Critical': {'red': 0.85, 'green': 0.13, 'blue': 0.13},
    'High':     {'red': 0.91, 'green': 0.36, 'blue': 0.02},
    'Medium':   {'red': 0.14, 'green': 0.39, 'blue': 0.82},
    'Low':      {'red': 0.42, 'green': 0.45, 'blue': 0.50},
}


def _get_impact_info(data: dict) -> dict:
    """extracted_keywords JSON에서 영향도/TTA 정보를 추출. 항상 딕셔너리를 반환."""
    defaults = {'impact_level': 'Medium', 'impact_reason': '', 'tta_action_item': '', 'standardization_gap': ''}
    # analyze_news_with_ai가 직접 저장한 필드 우선 사용
    if data.get('impact_level'):
        return {
            'impact_level': data.get('impact_level', 'Medium'),
            'impact_reason': data.get('impact_reason', ''),
            'tta_action_item': data.get('tta_action_item', ''),
            'standardization_gap': data.get('standardization_gap', ''),
        }
    # 없으면 extracted_keywords JSON에서 파싱
    try:
        kw_json = data.get('extracted_keywords') or '{}'
        parsed = json.loads(kw_json)
        return {
            'impact_level': parsed.get('impact_level', 'Medium'),
            'impact_reason': parsed.get('impact_reason', ''),
            'tta_action_item': parsed.get('tta_action_item', ''),
            'standardization_gap': parsed.get('standardization_gap', ''),
        }
    except Exception:
        return defaults


# ==============================================================================
# --- user_settings 헬퍼 ---
# ==============================================================================

def load_user_settings(user_email: str) -> dict:
    """사용자 설정 로드. 없으면 빈 dict 반환."""
    from sqlalchemy import text as sa_text
    try:
        with get_db_session() as session:
            row = session.execute(
                sa_text("SELECT keywords, ai_model, email_recipients, "
                        "schedule_daily, schedule_weekly "
                        "FROM user_settings WHERE user_email = :email"),
                {"email": user_email}
            ).fetchone()
        if row is None:
            return {}
        return {
            'keywords': json.loads(row[0] or '[]'),
            'ai_model': row[1] or 'gemini',
            'email_recipients': json.loads(row[2] or '[]'),
            'schedule_daily': bool(row[3]),
            'schedule_weekly': bool(row[4]),
        }
    except Exception as e:
        log_warning(f"load_user_settings 오류: {e}")
        return {}


def save_user_settings(user_email: str, settings: dict):
    """사용자 설정 저장 (upsert)."""
    from sqlalchemy import text as sa_text
    is_pg = not DB_ENGINE.url.drivername.startswith('sqlite')
    upsert_sql = (
        "INSERT INTO user_settings "
        "(user_email, keywords, ai_model, email_recipients, schedule_daily, schedule_weekly, updated_at) "
        "VALUES (:email, :kw, :model, :emails, :daily, :weekly, CURRENT_TIMESTAMP) "
        "ON CONFLICT (user_email) DO UPDATE SET "
        "keywords=EXCLUDED.keywords, ai_model=EXCLUDED.ai_model, "
        "email_recipients=EXCLUDED.email_recipients, schedule_daily=EXCLUDED.schedule_daily, "
        "schedule_weekly=EXCLUDED.schedule_weekly, updated_at=EXCLUDED.updated_at"
    ) if is_pg else (
        "INSERT INTO user_settings "
        "(user_email, keywords, ai_model, email_recipients, schedule_daily, schedule_weekly, updated_at) "
        "VALUES (:email, :kw, :model, :emails, :daily, :weekly, CURRENT_TIMESTAMP) "
        "ON CONFLICT (user_email) DO UPDATE SET "
        "keywords=excluded.keywords, ai_model=excluded.ai_model, "
        "email_recipients=excluded.email_recipients, schedule_daily=excluded.schedule_daily, "
        "schedule_weekly=excluded.schedule_weekly, updated_at=CURRENT_TIMESTAMP"
    )
    try:
        with get_db_session() as session:
            session.execute(sa_text(upsert_sql), {
                "email": user_email,
                "kw": json.dumps(settings.get('keywords', []), ensure_ascii=False),
                "model": settings.get('ai_model', 'gemini'),
                "emails": json.dumps(settings.get('email_recipients', []), ensure_ascii=False),
                "daily": settings.get('schedule_daily', True),
                "weekly": settings.get('schedule_weekly', True),
            })
            session.commit()
    except Exception as e:
        log_warning(f"save_user_settings 오류: {e}")


def _utf16_len(s: str) -> int:
    """Google Docs API는 UTF-16 코드 유닛 기준으로 위치를 계산함. 이모지(U+10000+)는 2유닛."""
    return len(s.encode('utf-16-le')) // 2


@performance_monitor
def generate_google_doc_report(analyzed_data):
    """세련된 디자인의 구글 문서 보고서를 생성"""
    try:
        docs_service, drive_service = get_google_docs_service()
    except FileNotFoundError:
        log_error("  (오류) 'credentials.json' 파일을 찾을 수 없습니다. 구글 인증 설정을 확인하세요.")
        return None, None
    except Exception as e:
        log_error(f"  (오류) 구글 서비스 연결에 실패했습니다: {e}")
        return None, None
        
    current_date = datetime.date.today().strftime('%Y년 %m월 %d일')
    document_title = f"전파·이동통신 동향 보고서 ({current_date})"

    try:
        try:
            document = docs_service.documents().create(body={'title': document_title}).execute()
        except Exception as _docs_create_err:
            _err_str = str(_docs_create_err)
            if '403' in _err_str and 'permission' in _err_str.lower():
                log_error("  ❌ Google Docs 생성 권한 없음 (403). GCP 콘솔 → API 및 서비스 → Google Docs API 활성화 필요.")
            raise
        document_id = document.get('documentId')
        
        permission = {'type': 'anyone', 'role': 'reader'}
        drive_service.permissions().create(fileId=document_id, body=permission).execute()
        log_info("  > 문서 접근 권한을 공개로 설정했습니다.")
        
        document_url = f"https://docs.google.com/document/d/{document_id}/edit"
        log_info(f"  > 새 문서가 생성되었습니다: {document_url}")

        requests_list = []
        index = 1

        # 문서 제목
        title_text = f"{document_title}\n"
        requests_list.append({'insertText': {'location': {'index': index}, 'text': title_text}})
        requests_list.append({
            'updateParagraphStyle': {
                'range': {'startIndex': index, 'endIndex': index + len(title_text)},
                'paragraphStyle': {
                    'alignment': 'CENTER',
                    'spaceAbove': {'magnitude': 10, 'unit': 'PT'},
                    'spaceBelow': {'magnitude': 20, 'unit': 'PT'}
                },
                'fields': 'alignment,spaceAbove,spaceBelow'
            }
        })
        requests_list.append({
            'updateTextStyle': {
                'range': {'startIndex': index, 'endIndex': index + len(title_text) - 1},
                'textStyle': {
                    'fontSize': {'magnitude': 24, 'unit': 'PT'},
                    'bold': True,
                    'foregroundColor': {'color': {'rgbColor': {'red': 0.1, 'green': 0.1, 'blue': 0.3}}}
                },
                'fields': 'fontSize,bold,foregroundColor'
            }
        })
        index += _utf16_len(title_text)
        
        # 부제목
        subtitle_text = f"한국정보통신기술협회(TTA) 표준화본부 이동통신표준팀\n작성일: {datetime.datetime.now().strftime('%Y년 %m월 %d일 %H:%M')}\n"
        requests_list.append({'insertText': {'location': {'index': index}, 'text': subtitle_text}})
        requests_list.append({
            'updateParagraphStyle': {
                'range': {'startIndex': index, 'endIndex': index + len(subtitle_text)},
                'paragraphStyle': {'alignment': 'CENTER'},
                'fields': 'alignment'
            }
        })
        requests_list.append({
            'updateTextStyle': {
                'range': {'startIndex': index, 'endIndex': index + len(subtitle_text)},
                'textStyle': {
                    'fontSize': {'magnitude': 10, 'unit': 'PT'},
                    'foregroundColor': {'color': {'rgbColor': {'red': 0.4, 'green': 0.4, 'blue': 0.4}}}
                },
                'fields': 'fontSize,foregroundColor'
            }
        })
        index += _utf16_len(subtitle_text)
        
        # 구분선
        divider_text = "━" * 50 + "\n\n"
        requests_list.append({'insertText': {'location': {'index': index}, 'text': divider_text}})
        requests_list.append({
            'updateTextStyle': {
                'range': {'startIndex': index, 'endIndex': index + len(divider_text)},
                'textStyle': {
                    'fontSize': {'magnitude': 8, 'unit': 'PT'},
                    'foregroundColor': {'color': {'rgbColor': {'red': 0.7, 'green': 0.7, 'blue': 0.7}}}
                },
                'fields': 'fontSize,foregroundColor'
            }
        })
        index += _utf16_len(divider_text)

        # Phase 7: 전주 대비 급등 키워드 TOP 5 섹션
        try:
            from knowledge_graph import detect_surge_entities
            _now = datetime.datetime.now()
            _prev_start = _now - datetime.timedelta(days=14)
            _prev_end = _now - datetime.timedelta(days=7)
            with get_db_session() as _db:
                _prev_rows = _db.query(NewsArticle).filter(
                    NewsArticle.collected_at >= _prev_start,
                    NewsArticle.collected_at < _prev_end
                ).all()
                _prev_data = [
                    {
                        'title': a.title or '',
                        'analysis_result': a.analysis_result or '',
                        'extracted_keywords': a.extracted_keywords or '',
                    }
                    for a in _prev_rows
                ]
            _surge_entities = detect_surge_entities(analyzed_data, _prev_data)[:5]
            if _surge_entities:
                surge_header = "📈 전주 대비 급등 키워드 TOP 5\n"
                requests_list.append({'insertText': {'location': {'index': index}, 'text': surge_header}})
                requests_list.append({
                    'updateTextStyle': {
                        'range': {'startIndex': index, 'endIndex': index + len(surge_header)},
                        'textStyle': {
                            'fontSize': {'magnitude': 13, 'unit': 'PT'},
                            'bold': True,
                            'foregroundColor': {'color': {'rgbColor': {'red': 0.07, 'green': 0.42, 'blue': 0.07}}}
                        },
                        'fields': 'fontSize,bold,foregroundColor'
                    }
                })
                index += _utf16_len(surge_header)
                for _rank, _ent in enumerate(_surge_entities, 1):
                    _name = _ent.get('name', '')
                    _ntype = _ent.get('node_type', '')
                    _prev_c = _ent.get('prev_count', 0)
                    _curr_c = _ent.get('curr_count', 0)
                    _pct = _ent.get('pct_change', 0)
                    if _pct == float('inf'):
                        _pct_str = "신규 등장"
                    else:
                        _pct_str = f"+{_pct*100:.0f}%" if _pct >= 0 else f"{_pct*100:.0f}%"
                    _row = f"  {_rank}. {_name} ({_ntype})  |  전주 {_prev_c}회 → 이번주 {_curr_c}회  ({_pct_str})\n"
                    requests_list.append({'insertText': {'location': {'index': index}, 'text': _row}})
                    requests_list.append({
                        'updateTextStyle': {
                            'range': {'startIndex': index, 'endIndex': index + len(_row)},
                            'textStyle': {
                                'fontSize': {'magnitude': 11, 'unit': 'PT'},
                                'foregroundColor': {'color': {'rgbColor': {'red': 0.1, 'green': 0.1, 'blue': 0.1}}}
                            },
                            'fields': 'fontSize,foregroundColor'
                        }
                    })
                    index += _utf16_len(_row)
                _surge_gap = "\n"
                requests_list.append({'insertText': {'location': {'index': index}, 'text': _surge_gap}})
                index += _utf16_len(_surge_gap)
        except ImportError:
            log_warning("  ⚠️ knowledge_graph 모듈 없음 — 급등 키워드 섹션 건너뜀")
        except Exception as _phase7_err:
            log_warning(f"  ⚠️ 급등 키워드 섹션 생성 실패: {_phase7_err}")

        # AI 분석 고지
        disclaimer_text = "📌 안내사항\n"
        requests_list.append({'insertText': {'location': {'index': index}, 'text': disclaimer_text}})
        requests_list.append({
            'updateTextStyle': {
                'range': {'startIndex': index, 'endIndex': index + len(disclaimer_text)},
                'textStyle': {
                    'fontSize': {'magnitude': 11, 'unit': 'PT'},
                    'bold': True
                },
                'fields': 'fontSize,bold'
            }
        })
        index += _utf16_len(disclaimer_text)
        
        disclaimer_content = "본 보고서는 IRONAGE AI Analytics System이 자동으로 생성한 분석 보고서입니다.\nAI가 수집한 뉴스를 기반으로 작성되었으며, 개인적인 의견을 포함하지 않습니다.\n\n"
        requests_list.append({'insertText': {'location': {'index': index}, 'text': disclaimer_content}})
        requests_list.append({
            'updateParagraphStyle': {
                'range': {'startIndex': index, 'endIndex': index + len(disclaimer_content)},
                'paragraphStyle': {
                    'indentFirstLine': {'magnitude': 20, 'unit': 'PT'},
                    'shading': {
                        'backgroundColor': {'color': {'rgbColor': {'red': 0.95, 'green': 0.95, 'blue': 0.98}}}
                    }
                },
                'fields': 'indentFirstLine,shading'
            }
        })
        requests_list.append({
            'updateTextStyle': {
                'range': {'startIndex': index, 'endIndex': index + len(disclaimer_content)},
                'textStyle': {
                    'fontSize': {'magnitude': 10, 'unit': 'PT'},
                    'italic': True,
                    'foregroundColor': {'color': {'rgbColor': {'red': 0.3, 'green': 0.3, 'blue': 0.3}}}
                },
                'fields': 'fontSize,italic,foregroundColor'
            }
        })
        index += _utf16_len(disclaimer_content)
        
        # 목차
        toc_header = "📋 목차\n"
        requests_list.append({'insertText': {'location': {'index': index}, 'text': toc_header}})
        requests_list.append({
            'updateTextStyle': {
                'range': {'startIndex': index, 'endIndex': index + len(toc_header)},
                'textStyle': {
                    'fontSize': {'magnitude': 14, 'unit': 'PT'},
                    'bold': True,
                    'foregroundColor': {'color': {'rgbColor': {'red': 0.1, 'green': 0.2, 'blue': 0.4}}}
                },
                'fields': 'fontSize,bold,foregroundColor'
            }
        })
        index += _utf16_len(toc_header)
        
        for i, data in enumerate(analyzed_data[:10], 1):
            toc_item = f"  {i}. {data['title'][:50]}...\n"
            requests_list.append({'insertText': {'location': {'index': index}, 'text': toc_item}})
            requests_list.append({
                'updateTextStyle': {
                    'range': {'startIndex': index, 'endIndex': index + len(toc_item)},
                    'textStyle': {
                        'fontSize': {'magnitude': 10, 'unit': 'PT'},
                        'foregroundColor': {'color': {'rgbColor': {'red': 0.3, 'green': 0.3, 'blue': 0.5}}}
                    },
                    'fields': 'fontSize,foregroundColor'
                }
            })
            index += _utf16_len(toc_item)
        
        toc_end = "\n"
        requests_list.append({'insertText': {'location': {'index': index}, 'text': toc_end}})
        index += _utf16_len(toc_end)

        # ── 영향도 요약 섹션 (Critical / High 우선 노출) ──────────────────
        critical_high = [
            (d, _get_impact_info(d))
            for d in analyzed_data
            if _get_impact_info(d)['impact_level'] in ('Critical', 'High')
        ]
        critical_high.sort(key=lambda x: IMPACT_LEVEL_ORDER.get(x[1]['impact_level'], 2))

        if critical_high:
            impact_header = "🔔 주요 조치 필요 항목 (Critical / High)\n"
            requests_list.append({'insertText': {'location': {'index': index}, 'text': impact_header}})
            requests_list.append({
                'updateTextStyle': {
                    'range': {'startIndex': index, 'endIndex': index + len(impact_header)},
                    'textStyle': {
                        'fontSize': {'magnitude': 14, 'unit': 'PT'},
                        'bold': True,
                        'foregroundColor': {'color': {'rgbColor': {'red': 0.7, 'green': 0.1, 'blue': 0.1}}}
                    },
                    'fields': 'fontSize,bold,foregroundColor'
                }
            })
            index += _utf16_len(impact_header)

            for art, info in critical_high:
                icon = IMPACT_LEVEL_ICON.get(info['impact_level'], '📋')
                level = info['impact_level']
                tta = info['tta_action_item'] or '추가 모니터링 필요'
                summary_line = f"  {icon} [{level}] {art['title'][:60]}\n       → TTA 조치: {tta}\n"
                requests_list.append({'insertText': {'location': {'index': index}, 'text': summary_line}})
                color = IMPACT_LEVEL_COLOR_RGB.get(level, IMPACT_LEVEL_COLOR_RGB['Medium'])
                requests_list.append({
                    'updateTextStyle': {
                        'range': {'startIndex': index, 'endIndex': index + len(summary_line)},
                        'textStyle': {
                            'fontSize': {'magnitude': 10, 'unit': 'PT'},
                            'foregroundColor': {'color': {'rgbColor': color}}
                        },
                        'fields': 'fontSize,foregroundColor'
                    }
                })
                index += _utf16_len(summary_line)

            sep = "\n"
            requests_list.append({'insertText': {'location': {'index': index}, 'text': sep}})
            index += _utf16_len(sep)

        # 각 뉴스 아이템
        for i, data in enumerate(analyzed_data):
            news_header = f"\n【 {i+1} 】 {data['title']}\n"
            requests_list.append({'insertText': {'location': {'index': index}, 'text': news_header}})
            requests_list.append({
                'updateTextStyle': {
                    'range': {'startIndex': index, 'endIndex': index + len(news_header)},
                    'textStyle': {
                        'fontSize': {'magnitude': 16, 'unit': 'PT'},
                        'bold': True,
                        'foregroundColor': {'color': {'rgbColor': {'red': 0.1, 'green': 0.2, 'blue': 0.4}}}
                    },
                    'fields': 'fontSize,bold,foregroundColor'
                }
            })
            requests_list.append({
                'updateParagraphStyle': {
                    'range': {'startIndex': index, 'endIndex': index + len(news_header)},
                    'paragraphStyle': {
                        'spaceAbove': {'magnitude': 15, 'unit': 'PT'},
                        'spaceBelow': {'magnitude': 10, 'unit': 'PT'}
                    },
                    'fields': 'spaceAbove,spaceBelow'
                }
            })
            index += _utf16_len(news_header)
            
            meta_text = f"📰 출처: {data['source']}  |  📅 발행일: {data['published']}\n"
            requests_list.append({'insertText': {'location': {'index': index}, 'text': meta_text}})
            requests_list.append({
                'updateTextStyle': {
                    'range': {'startIndex': index, 'endIndex': index + len(meta_text)},
                    'textStyle': {
                        'fontSize': {'magnitude': 10, 'unit': 'PT'},
                        'foregroundColor': {'color': {'rgbColor': {'red': 0.5, 'green': 0.5, 'blue': 0.5}}}
                    },
                    'fields': 'fontSize,foregroundColor'
                }
            })
            index += _utf16_len(meta_text)
            
            link_text = f"🔗 원문: {data['link']}\n\n"
            requests_list.append({'insertText': {'location': {'index': index}, 'text': link_text}})
            requests_list.append({
                'updateTextStyle': {
                    'range': {'startIndex': index + 5, 'endIndex': index + len(link_text) - 2},
                    'textStyle': {
                        'fontSize': {'magnitude': 9, 'unit': 'PT'},
                        'link': {'url': data['link']},
                        'foregroundColor': {'color': {'rgbColor': {'red': 0.1, 'green': 0.3, 'blue': 0.7}}},
                        'underline': True
                    },
                    'fields': 'fontSize,link,foregroundColor,underline'
                }
            })
            index += _utf16_len(link_text)

            # ── 영향도 배지 + TTA 조치 사항 ────────────────────────────
            impact_info = _get_impact_info(data)
            impact_level = impact_info['impact_level']
            impact_icon = IMPACT_LEVEL_ICON.get(impact_level, '📋')
            impact_color = IMPACT_LEVEL_COLOR_RGB.get(impact_level, IMPACT_LEVEL_COLOR_RGB['Medium'])

            badge_text = f"{impact_icon} 영향도: {impact_level}\n"
            requests_list.append({'insertText': {'location': {'index': index}, 'text': badge_text}})
            requests_list.append({
                'updateTextStyle': {
                    'range': {'startIndex': index, 'endIndex': index + len(badge_text)},
                    'textStyle': {
                        'fontSize': {'magnitude': 11, 'unit': 'PT'},
                        'bold': True,
                        'foregroundColor': {'color': {'rgbColor': impact_color}}
                    },
                    'fields': 'fontSize,bold,foregroundColor'
                }
            })
            index += _utf16_len(badge_text)

            tta = impact_info['tta_action_item']
            if tta:
                tta_label = "▶ TTA 조치 사항\n"
                requests_list.append({'insertText': {'location': {'index': index}, 'text': tta_label}})
                requests_list.append({
                    'updateTextStyle': {
                        'range': {'startIndex': index, 'endIndex': index + len(tta_label)},
                        'textStyle': {'fontSize': {'magnitude': 11, 'unit': 'PT'}, 'bold': True},
                        'fields': 'fontSize,bold'
                    }
                })
                requests_list.append({
                    'updateParagraphStyle': {
                        'range': {'startIndex': index, 'endIndex': index + len(tta_label)},
                        'paragraphStyle': {
                            'shading': {'backgroundColor': {'color': {'rgbColor': {'red': 1.0, 'green': 0.95, 'blue': 0.88}}}},
                            'spaceAbove': {'magnitude': 5, 'unit': 'PT'},
                        },
                        'fields': 'shading,spaceAbove'
                    }
                })
                index += _utf16_len(tta_label)

                tta_body = f"{tta}\n\n"
                requests_list.append({'insertText': {'location': {'index': index}, 'text': tta_body}})
                requests_list.append({
                    'updateParagraphStyle': {
                        'range': {'startIndex': index, 'endIndex': index + len(tta_body)},
                        'paragraphStyle': {
                            'indentFirstLine': {'magnitude': 20, 'unit': 'PT'},
                            'shading': {'backgroundColor': {'color': {'rgbColor': {'red': 1.0, 'green': 0.97, 'blue': 0.92}}}},
                        },
                        'fields': 'indentFirstLine,shading'
                    }
                })
                requests_list.append({
                    'updateTextStyle': {
                        'range': {'startIndex': index, 'endIndex': index + len(tta_body)},
                        'textStyle': {'fontSize': {'magnitude': 10, 'unit': 'PT'}},
                        'fields': 'fontSize'
                    }
                })
                index += _utf16_len(tta_body)

            std_gap = impact_info['standardization_gap']
            if std_gap and std_gap != '기사에서 표준화 현황 정보 미확인':
                gap_label = "▶ 표준화 격차\n"
                requests_list.append({'insertText': {'location': {'index': index}, 'text': gap_label}})
                requests_list.append({
                    'updateTextStyle': {
                        'range': {'startIndex': index, 'endIndex': index + len(gap_label)},
                        'textStyle': {'fontSize': {'magnitude': 11, 'unit': 'PT'}, 'bold': True},
                        'fields': 'fontSize,bold'
                    }
                })
                index += _utf16_len(gap_label)

                gap_body = f"{std_gap}\n\n"
                requests_list.append({'insertText': {'location': {'index': index}, 'text': gap_body}})
                requests_list.append({
                    'updateParagraphStyle': {
                        'range': {'startIndex': index, 'endIndex': index + len(gap_body)},
                        'paragraphStyle': {'indentFirstLine': {'magnitude': 20, 'unit': 'PT'}},
                        'fields': 'indentFirstLine'
                    }
                })
                requests_list.append({
                    'updateTextStyle': {
                        'range': {'startIndex': index, 'endIndex': index + len(gap_body)},
                        'textStyle': {'fontSize': {'magnitude': 10, 'unit': 'PT'}},
                        'fields': 'fontSize'
                    }
                })
                index += _utf16_len(gap_body)

            analysis_text = data.get('analysis_result', '')

            report_match = re.search(r'## \*\*뉴스 심층 분석 보고서\*\*(.*)', analysis_text, re.DOTALL)
            if report_match:
                report_content = report_match.group(1).strip()
            else:
                report_content = analysis_text
            
            sections = re.split(r'### \*\*(.*?)\*\*', report_content)
            
            for k in range(1, len(sections), 2):
                section_title = f"▶ {sections[k].strip()}\n"
                section_body = sections[k+1].strip() + "\n\n"
                
                requests_list.append({'insertText': {'location': {'index': index}, 'text': section_title}})
                requests_list.append({
                    'updateTextStyle': {
                        'range': {'startIndex': index, 'endIndex': index + len(section_title)},
                        'textStyle': {
                            'bold': True,
                            'fontSize': {'magnitude': 12, 'unit': 'PT'}
                        },
                        'fields': 'bold,fontSize'
                    }
                })
                
                if "주요 내용" in section_title:
                    bg_color = {'red': 0.93, 'green': 0.97, 'blue': 1.0}
                    text_color = {'red': 0.1, 'green': 0.3, 'blue': 0.5}
                elif "시사점" in section_title:
                    bg_color = {'red': 1.0, 'green': 0.97, 'blue': 0.93}
                    text_color = {'red': 0.5, 'green': 0.3, 'blue': 0.1}
                else:
                    bg_color = None
                    text_color = {'red': 0.2, 'green': 0.2, 'blue': 0.2}
                
                if bg_color:
                    requests_list.append({
                        'updateParagraphStyle': {
                            'range': {'startIndex': index, 'endIndex': index + len(section_title)},
                            'paragraphStyle': {
                                'shading': {'backgroundColor': {'color': {'rgbColor': bg_color}}},
                                'indentFirstLine': {'magnitude': 10, 'unit': 'PT'},
                                'spaceAbove': {'magnitude': 8, 'unit': 'PT'},
                                'spaceBelow': {'magnitude': 5, 'unit': 'PT'}
                            },
                            'fields': 'shading,indentFirstLine,spaceAbove,spaceBelow'
                        }
                    })
                    requests_list.append({
                        'updateTextStyle': {
                            'range': {'startIndex': index, 'endIndex': index + len(section_title)},
                            'textStyle': {
                                'foregroundColor': {'color': {'rgbColor': text_color}}
                            },
                            'fields': 'foregroundColor'
                        }
                    })
                
                index += _utf16_len(section_title)
                
                requests_list.append({'insertText': {'location': {'index': index}, 'text': section_body}})
                requests_list.append({
                    'updateParagraphStyle': {
                        'range': {'startIndex': index, 'endIndex': index + len(section_body)},
                        'paragraphStyle': {
                            'indentFirstLine': {'magnitude': 20, 'unit': 'PT'},
                            'lineSpacing': 120
                        },
                        'fields': 'indentFirstLine,lineSpacing'
                    }
                })
                requests_list.append({
                    'updateTextStyle': {
                        'range': {'startIndex': index, 'endIndex': index + len(section_body)},
                        'textStyle': {
                            'fontSize': {'magnitude': 11, 'unit': 'PT'}
                        },
                        'fields': 'fontSize'
                    }
                })
                index += _utf16_len(section_body)
            
            if i < len(analyzed_data) - 1:
                separator = "\n" + "─" * 40 + "\n"
                requests_list.append({'insertText': {'location': {'index': index}, 'text': separator}})
                requests_list.append({
                    'updateTextStyle': {
                        'range': {'startIndex': index, 'endIndex': index + len(separator)},
                        'textStyle': {
                            'fontSize': {'magnitude': 8, 'unit': 'PT'},
                            'foregroundColor': {'color': {'rgbColor': {'red': 0.8, 'green': 0.8, 'blue': 0.8}}}
                        },
                        'fields': 'fontSize,foregroundColor'
                    }
                })
                index += _utf16_len(separator)

        # 문서 푸터
        footer_text = f"\n\n{'=' * 60}\n"
        footer_text += f"문서 작성 완료: {datetime.datetime.now().strftime('%Y년 %m월 %d일 %H:%M:%S')}\n"
        footer_text += "한국정보통신기술협회(TTA) 표준화본부 이동통신표준팀\n"
        footer_text += "IRONAGE AI Analytics System v5.0\n"
        footer_text += "© 2024 TTA. All rights reserved.\n"
        
        requests_list.append({'insertText': {'location': {'index': index}, 'text': footer_text}})
        requests_list.append({
            'updateParagraphStyle': {
                'range': {'startIndex': index, 'endIndex': index + len(footer_text)},
                'paragraphStyle': {
                    'alignment': 'CENTER',
                    'spaceAbove': {'magnitude': 30, 'unit': 'PT'}
                },
                'fields': 'alignment,spaceAbove'
            }
        })
        requests_list.append({
            'updateTextStyle': {
                'range': {'startIndex': index, 'endIndex': index + len(footer_text)},
                'textStyle': {
                    'fontSize': {'magnitude': 9, 'unit': 'PT'},
                    'foregroundColor': {'color': {'rgbColor': {'red': 0.5, 'green': 0.5, 'blue': 0.5}}},
                    'italic': True
                },
                'fields': 'fontSize,foregroundColor,italic'
            }
        })
        index += _utf16_len(footer_text)

        # ── Bug 3: requests_list 100개 단위 청크 분할 + 소켓 타임아웃 120초 ─────
        _CHUNK_SIZE = 100
        _chunks = [requests_list[i:i+_CHUNK_SIZE] for i in range(0, len(requests_list), _CHUNK_SIZE)]
        log_info(f"  > batchUpdate: {len(requests_list)}개 요청을 {len(_chunks)}개 청크로 분할 전송...")
        _orig_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(120)
        try:
            for _ci, _chunk in enumerate(_chunks):
                try:
                    docs_service.documents().batchUpdate(
                        documentId=document_id, body={'requests': _chunk}
                    ).execute()
                    log_info(f"    ✅ 청크 {_ci+1}/{len(_chunks)} 완료 ({len(_chunk)}개)")
                except Exception as _chunk_err:
                    log_warning(f"    ⚠️ 청크 {_ci+1} 실패, 5초 후 재시도: {_chunk_err}")
                    time.sleep(5)
                    try:
                        docs_service.documents().batchUpdate(
                            documentId=document_id, body={'requests': _chunk}
                        ).execute()
                        log_info(f"    ✅ 청크 {_ci+1} 재시도 성공")
                    except Exception as _retry_err:
                        log_error(f"    ❌ 청크 {_ci+1} 재시도 실패, 건너뜀 (부분 문서 허용): {_retry_err}")
        finally:
            socket.setdefaulttimeout(_orig_timeout)

        # AI_news 폴더로 이동
        try:
            folder_query = "name='AI_news' and mimeType='application/vnd.google-apps.folder' and trashed=false"
            folder_results = drive_service.files().list(q=folder_query, fields='files(id, name)').execute()
            folders = folder_results.get('files', [])
            if folders:
                folder_id = folders[0]['id']
                drive_service.files().update(
                    fileId=document_id,
                    addParents=folder_id,
                    removeParents='root',
                    fields='id, parents'
                ).execute()
                log_info(f"  > 문서를 'AI_news' 폴더로 이동했습니다.")
            else:
                log_warning("  ⚠️ 'AI_news' 폴더를 찾을 수 없습니다. 내 드라이브 루트에 저장됩니다.")
        except Exception as folder_err:
            log_warning(f"  ⚠️ 폴더 이동 실패 (문서는 정상 생성됨): {folder_err}")

        return document_url, document_title

    except Exception as e:
        log_error(f"  (오류) 구글 문서 생성/스타일링 실패: {e}")
        return None, None

# ==============================================================================
# --- 이메일 발송 함수 ---
# ==============================================================================

def get_weekly_subscribers() -> list:
    """user_settings에서 schedule_weekly=True인 사용자의 email_recipients를 취합.
    등록된 사용자 설정이 없으면 전역 RECEIVER_EMAIL 반환."""
    from sqlalchemy import text as sa_text
    try:
        with get_db_session() as session:
            rows = session.execute(
                sa_text("SELECT email_recipients FROM user_settings WHERE schedule_weekly = TRUE")
            ).fetchall()
        emails = set()
        for row in rows:
            try:
                for addr in json.loads(row[0] or '[]'):
                    addr = addr.strip()
                    if addr and '@' in addr:
                        emails.add(addr)
            except Exception:
                pass
        return sorted(emails) if emails else list(RECEIVER_EMAIL)
    except Exception as e:
        log_warning(f"get_weekly_subscribers 오류: {e}")
        return list(RECEIVER_EMAIL)


def send_gmail_report(report_title, analyzed_data, doc_url, other_news, receivers=None):
    """분석 리포트를 개선된 디자인의 이메일로 전송.
    receivers: 수신자 목록 (None이면 전역 RECEIVER_EMAIL 사용)"""

    # 영향도 우선순위(Critical→High→Medium→Low)로 정렬
    sorted_data = sorted(
        analyzed_data,
        key=lambda d: IMPACT_LEVEL_ORDER.get(_get_impact_info(d)['impact_level'], 2)
    )

    IMPACT_HTML_COLOR = {
        'Critical': '#dc2626',
        'High':     '#ea580c',
        'Medium':   '#2563eb',
        'Low':      '#6b7280',
    }
    IMPACT_HTML_BG = {
        'Critical': '#fff1f2',
        'High':     '#fff7ed',
        'Medium':   '#eff6ff',
        'Low':      '#f9fafb',
    }

    news_items_html = ""
    for i, data in enumerate(sorted_data):
        analysis_text = data.get('analysis_result') or ''
        main_content = None
        implications = "시사점 정보를 찾을 수 없습니다."

        try:
            main_patterns = [
                r'### \*\*1\. 주요 내용 요약\*\*(.*?)### \*\*2\. 시사점 및 전망\*\*',
                r'\*\*1\. 주요 내용 요약\*\*(.*?)\*\*2\. 시사점 및 전망\*\*',
                r'1\. 주요 내용 요약(.*?)2\. 시사점 및 전망'
            ]

            for pattern in main_patterns:
                match = re.search(pattern, analysis_text, re.DOTALL)
                if match:
                    main_content = match.group(1).strip()
                    break

            # 파싱 실패 폴백: 섹션 구조가 없으면 원문 첫 500자 표시
            if main_content is None:
                if analysis_text and len(analysis_text) > 10:
                    main_content = "[파싱 실패 요약] " + analysis_text[:500]
                else:
                    main_content = "주요내용 정보를 찾을 수 없습니다."

            impl_patterns = [
                r'### \*\*2\. 시사점 및 전망\*\*(.*)',
                r'\*\*2\. 시사점 및 전망\*\*(.*)',
                r'2\. 시사점 및 전망(.*)'
            ]

            for pattern in impl_patterns:
                match = re.search(pattern, analysis_text, re.DOTALL)
                if match:
                    implications = match.group(1).strip()
                    break
            
            main_content = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', main_content)
            implications = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', implications)
            
            main_content = main_content.replace('ㅇ', '•').replace('\n', '<br>')
            implications = implications.replace('ㅇ', '•').replace('\n', '<br>')
            
        except Exception as e:
            log_error(f"  (경고) AI 분석 결과 파싱 중 오류 발생: {e}")
            main_content = (main_content or "주요내용 정보를 찾을 수 없습니다.").replace('ㅇ', '•').replace('\n', '<br>')
            implications = (implications or "시사점 정보를 찾을 수 없습니다.").replace('ㅇ', '•').replace('\n', '<br>')

        impact_info = _get_impact_info(data)
        impact_level = impact_info['impact_level']
        impact_icon = IMPACT_LEVEL_ICON.get(impact_level, '📋')
        impact_color = IMPACT_HTML_COLOR.get(impact_level, '#2563eb')
        impact_bg = IMPACT_HTML_BG.get(impact_level, '#eff6ff')
        tta_inline = ""
        if impact_info['tta_action_item']:
            tta_inline = (
                f'<p style="margin-top:10px; padding-top:8px; border-top:1px solid {impact_color}33; '
                f'color:{impact_color}; font-size:13px; font-weight:600;">'
                f'🏛️ <strong>TTA 조치:</strong> {impact_info["tta_action_item"]}</p>'
            )
        std_gap_html = ""
        if impact_info['standardization_gap'] and impact_info['standardization_gap'] != '기사에서 표준화 현황 정보 미확인':
            std_gap_html = f"""
                <div class="analysis-section" style="background:#f0fdf4;border-left:4px solid #16a34a;margin-top:8px;">
                    <div class="section-header">
                        <span class="section-icon">📐</span>
                        <span class="section-title" style="color:#16a34a;">표준화 격차</span>
                    </div>
                    <div class="section-content">{impact_info['standardization_gap']}</div>
                </div>"""

        news_items_html += f"""
        <div class="news-card" style="border-top:3px solid {impact_color};">
            <div class="news-header">
                <div class="news-number" style="background:{impact_color};">{i+1}</div>
                <div class="news-title-container">
                    <div style="margin-bottom:4px;">
                        <span style="display:inline-block;background:{impact_bg};color:{impact_color};border:1px solid {impact_color};border-radius:12px;padding:2px 10px;font-size:12px;font-weight:700;">{impact_icon} {impact_level}</span>
                    </div>
                    <h3 class="news-title">{data['title']}</h3>
                    <div class="news-meta">
                        <span class="meta-item">📰 {data['source']}</span>
                        <span class="meta-item">📅 {data['published']}</span>
                        <a href="{data['link']}" class="news-link" target="_blank">원문 보기 →</a>
                    </div>
                </div>
            </div>

            <div class="analysis-container">
                <div class="analysis-section main-content">
                    <div class="section-header">
                        <span class="section-icon">📋</span>
                        <span class="section-title">주요 내용</span>
                    </div>
                    <div class="section-content">
                        {main_content}
                    </div>
                </div>

                <div class="analysis-section implications">
                    <div class="section-header">
                        <span class="section-icon">💡</span>
                        <span class="section-title">시사점 및 전망</span>
                    </div>
                    <div class="section-content">
                        {implications}
                        {tta_inline}
                    </div>
                </div>
                {std_gap_html}
            </div>
        </div>
        """

    other_news_html = ""
    if other_news:
        other_news_html = """
        <div class="other-news-container">
            <h2 class="other-news-title">📌 추가 수집 뉴스</h2>
            <div class="other-news-grid">
        """
        
        for item in other_news[:20]:
            other_news_html += f"""
            <div class="other-news-item">
                <a href="{item['link']}" target="_blank" class="other-news-link">
                    <span class="other-news-text">{item['title'][:60]}...</span>
                    <span class="other-news-source">{item['source']}</span>
                </a>
            </div>
            """
        
        other_news_html += """
            </div>
        </div>
        """

    current_date = datetime.datetime.now().strftime('%Y년 %m월 %d일')
    
    css_styles = """
        @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700;900&display=swap');
        
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Noto Sans KR', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: #f5f5f5;
            padding: 20px;
        }
        
        .email-wrapper {
            max-width: 900px;
            margin: 0 auto;
            background: white;
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        
        .header {
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
            padding: 35px;
            text-align: center;
            position: relative;
            overflow: hidden;
        }
        
        .header::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: url('data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1440 320"><path fill="%23ffffff" fill-opacity="0.1" d="M0,96L48,112C96,128,192,160,288,160C384,160,480,128,576,112C672,96,768,96,864,112C960,128,1056,160,1152,160C1248,160,1344,128,1392,112L1440,96L1440,320L1392,320C1344,320,1248,320,1152,320C1056,320,960,320,864,320C768,320,672,320,576,320C480,320,384,320,288,320C192,320,96,320,48,320L0,320Z"></path></svg>') no-repeat bottom;
            background-size: cover;
        }
        
        .header h1 {
            font-size: 26px;
            font-weight: 700;
            color: #ffffff;
            margin-bottom: 10px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.2);
            position: relative;
            z-index: 1;
        }
        
        .header-subtitle {
            font-size: 14px;
            color: rgba(255,255,255,0.95);
            font-style: italic;
            background: rgba(255,255,255,0.15);
            padding: 8px 20px;
            border-radius: 20px;
            display: inline-block;
            backdrop-filter: blur(10px);
            position: relative;
            z-index: 1;
        }
        
        .doc-link-section {
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            padding: 25px;
            text-align: center;
            border-bottom: 1px solid #e9ecef;
        }
        
        .doc-link-button {
            display: inline-block;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 12px 35px;
            border-radius: 25px;
            text-decoration: none;
            font-weight: 500;
            font-size: 15px;
            transition: all 0.3s ease;
            box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
        }
        
        .doc-link-button:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(102, 126, 234, 0.5);
        }
        
        .news-container {
            padding: 30px;
        }
        
        .news-card {
            background: white;
            border: 1px solid #e9ecef;
            border-radius: 12px;
            margin-bottom: 25px;
            overflow: hidden;
            transition: all 0.3s ease;
            box-shadow: 0 2px 8px rgba(0,0,0,0.05);
        }
        
        .news-card:hover {
            box-shadow: 0 4px 16px rgba(0,0,0,0.1);
            transform: translateY(-2px);
        }
        
        .news-header {
            display: flex;
            padding: 20px;
            background: #fafbfc;
            border-bottom: 1px solid #e9ecef;
            align-items: center;
        }
        
        .news-number {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            width: 40px;
            height: 40px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 700;
            font-size: 16px;
            margin-right: 15px;
            flex-shrink: 0;
            box-shadow: 0 3px 10px rgba(102, 126, 234, 0.3);
        }
        
        .news-title-container {
            flex: 1;
        }
        
        .news-title {
            font-size: 17px;
            font-weight: 600;
            color: #2c3e50;
            margin-bottom: 8px;
            line-height: 1.4;
        }
        
        .news-meta {
            display: flex;
            gap: 15px;
            font-size: 13px;
            color: #6c757d;
        }
        
        .meta-item {
            display: flex;
            align-items: center;
            gap: 4px;
        }
        
        .news-link {
            color: #667eea;
            text-decoration: none;
            font-weight: 500;
            transition: color 0.3s ease;
        }
        
        .news-link:hover {
            color: #764ba2;
            text-decoration: underline;
        }
        
        .analysis-container {
            padding: 20px;
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 15px;
        }
        
        @media (max-width: 768px) {
            .analysis-container {
                grid-template-columns: 1fr;
            }
        }
        
        .analysis-section {
            background: #f8f9fa;
            border-radius: 10px;
            padding: 18px;
            border-left: 4px solid;
            position: relative;
            overflow: hidden;
        }
        
        .analysis-section::before {
            content: '';
            position: absolute;
            top: 0;
            right: 0;
            width: 100px;
            height: 100px;
            background: radial-gradient(circle, rgba(255,255,255,0.8) 0%, transparent 70%);
            border-radius: 50%;
            transform: translate(30px, -30px);
        }
        
        .analysis-section.main-content {
            border-left-color: #4285f4;
            background: linear-gradient(135deg, #e8f0fe 0%, #f8f9fa 100%);
        }
        
        .analysis-section.implications {
            border-left-color: #f59f00;
            background: linear-gradient(135deg, #fff8e1 0%, #f8f9fa 100%);
        }
        
        .section-header {
            display: flex;
            align-items: center;
            margin-bottom: 12px;
            font-weight: 600;
            color: #495057;
            position: relative;
            z-index: 1;
        }
        
        .section-icon {
            font-size: 18px;
            margin-right: 6px;
        }
        
        .section-title {
            font-size: 14px;
            font-weight: 600;
        }
        
        .section-content {
            font-size: 13px;
            line-height: 1.8;
            color: #495057;
            position: relative;
            z-index: 1;
        }
        
        .section-content strong {
            color: #0d47a1;
            font-weight: 700;
            background: linear-gradient(to bottom, transparent 40%, rgba(255, 235, 59, 0.35) 40%);
            padding: 2px 4px;
            border-radius: 3px;
            display: inline;
            line-height: 1.5;
            position: relative;
        }
        
        .section-content strong:hover {
            background: linear-gradient(to bottom, transparent 30%, rgba(255, 235, 59, 0.5) 30%);
            transition: background 0.3s ease;
        }
        
        .analysis-section.implications .section-content strong {
            color: #bf360c;
            background: linear-gradient(to bottom, transparent 40%, rgba(255, 183, 77, 0.35) 40%);
        }
        
        .other-news-container {
            background: #f8f9fa;
            padding: 30px;
            border-top: 1px solid #e9ecef;
        }
        
        .other-news-title {
            font-size: 20px;
            font-weight: 600;
            color: #2c3e50;
            margin-bottom: 20px;
            text-align: center;
        }
        
        .other-news-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
            gap: 12px;
        }
        
        .other-news-item {
            background: white;
            border-radius: 8px;
            padding: 12px 15px;
            border: 1px solid #dee2e6;
            transition: all 0.2s ease;
        }
        
        .other-news-item:hover {
            border-color: #667eea;
            box-shadow: 0 2px 8px rgba(102, 126, 234, 0.15);
            transform: translateX(3px);
        }
        
        .other-news-link {
            text-decoration: none;
            display: flex;
            flex-direction: column;
            gap: 6px;
        }
        
        .other-news-text {
            color: #495057;
            font-size: 13px;
            line-height: 1.4;
        }
        
        .other-news-source {
            color: #adb5bd;
            font-size: 11px;
            font-weight: 500;
        }
        
        .footer {
            background: linear-gradient(135deg, #2c3e50 0%, #3498db 100%);
            color: white;
            padding: 25px;
            text-align: center;
        }
        
        .footer-content {
            font-size: 13px;
            opacity: 0.95;
            line-height: 1.6;
        }
        
        .footer-divider {
            width: 50px;
            height: 2px;
            background: rgba(255,255,255,0.4);
            margin: 15px auto;
        }
        
        .footer-copyright {
            font-size: 11px;
            opacity: 0.8;
            margin-top: 15px;
        }
        
        @media (max-width: 768px) {
            .section-content strong {
                padding: 3px 5px;
                font-size: 14px;
            }
        }
    """
    
    html_body = f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{report_title}</title>
        <style>
            {css_styles}
        </style>
    </head>
    <body>
        <div class="email-wrapper">
            <div class="header">
                <h1>{report_title}</h1>
                <div class="header-subtitle">
                    ※ 본 보고서의 내용은 IRONAGE AI가 생성한 분석으로, 개인적인 의견을 포함하지 않습니다.
                </div>
            </div>
            
            <div class="doc-link-section">
                {f'<a href="{doc_url}" class="doc-link-button" target="_blank">📄 Google Docs에서 전체 보고서 보기</a>' if doc_url else '<span style="color:#64748b;font-size:14px;">(Google Docs 생성 실패 — 아래 본문 참조)</span>'}
            </div>
            
            <div class="news-container">
                {news_items_html}
            </div>
            
            {other_news_html}
            
            <div class="footer">
                <div class="footer-content">
                    <strong>한국정보통신기술협회(TTA)</strong><br>
                    표준화본부 이동통신표준팀
                </div>
                <div class="footer-divider"></div>
                <div class="footer-copyright">
                    본 리포트는 IRONAGE AI Analytics System을 통해 자동 생성되었습니다.<br>
                    © 2024 TTA. All rights reserved.
                </div>
            </div>
        </div>
    </body>
    </html>
    """

    actual_receivers = list(receivers) if receivers else list(RECEIVER_EMAIL)
    if not actual_receivers:
        log_warning("  ⚠️ 이메일 수신자가 없습니다. 발송 건너뜀.")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[TTA] {report_title}"
    msg["From"] = SENDER_EMAIL
    msg["To"] = ", ".join(actual_receivers)
    msg["Date"] = formatdate(localtime=True)
    msg.attach(MIMEText(html_body, 'html', 'utf-8'))

    try:
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(SENDER_EMAIL, GMAIL_PASSWORD)
            server.sendmail(SENDER_EMAIL, actual_receivers, msg.as_string())
        log_info(f"  > ✅ 이메일이 {len(actual_receivers)}명의 수신자에게 성공적으로 발송되었습니다.")
    except Exception as e:
        log_error(f"  (오류) 이메일 발송에 실패했습니다: {e}")


# ==============================================================================
# --- 주차 계산 헬퍼 함수 ---
# ==============================================================================

def get_week_number(date: datetime.datetime = None) -> Tuple[int, int, str]:
    """
    ISO 주차 계산 (월요일 시작)
    
    Args:
        date: 기준 날짜 (None이면 오늘)
    
    Returns:
        Tuple[int, int, str]: (연도, 주차, 주차 문자열)
        예: (2025, 46, "2025_W46")
    """
    if date is None:
        date = datetime.datetime.now()
    
    # ISO 8601 주차 계산 (월요일 시작)
    iso_calendar = date.isocalendar()
    year = iso_calendar[0]
    week = iso_calendar[1]
    
    week_str = f"{year}_W{week:02d}"
    
    return year, week, week_str


def get_week_date_range(date: datetime.datetime = None) -> Tuple[datetime.datetime, datetime.datetime]:
    """
    해당 주의 월요일과 일요일 날짜 반환
    
    Args:
        date: 기준 날짜 (None이면 오늘)
    
    Returns:
        Tuple[datetime.datetime, datetime.datetime]: (월요일, 일요일)
    """
    if date is None:
        date = datetime.datetime.now()
    
    # 현재 요일 (0=월요일, 6=일요일)
    weekday = date.weekday()
    
    # 이번 주 월요일
    monday = date - datetime.timedelta(days=weekday)
    monday = monday.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # 이번 주 일요일
    sunday = monday + datetime.timedelta(days=6)
    sunday = sunday.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    return monday, sunday


# ==============================================================================
# --- 주간 누적 엑셀 저장 함수 ---
# ==============================================================================

@performance_monitor
# FIX: 반환 타입 불일치 - None 반환 케이스가 있으므로 Optional[str]로 수정
def save_analysis_to_weekly_excel(
    analyzed_results: List[Dict],
    output_dir: str = "data/reports"
) -> Optional[str]:
    """
    분석된 뉴스를 주간 누적 엑셀 파일로 저장
    
    - 같은 주(월~일) 동안은 기존 파일에 추가
    - 월요일에 새로운 파일 자동 생성
    - 파일명 형식: news_analysis_2025_W46.xlsx
    
    Args:
        analyzed_results: 분석된 뉴스 목록
        output_dir: 저장 폴더 경로
    
    Returns:
        str: 생성/업데이트된 엑셀 파일 경로
    """
    if not analyzed_results:
        log_warning("⚠️ 저장할 분석 결과가 없습니다.")
        return None
    
    try:
        # 출력 폴더 생성
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        
        # 현재 주차 정보
        year, week, week_str = get_week_number()
        monday, sunday = get_week_date_range()
        
        # 파일명 생성
        filename = f"news_analysis_{week_str}.xlsx"
        filepath = Path(output_dir) / filename
        
        log_info(f"\n📊 주간 누적 엑셀 저장 중...")
        log_info(f"   📅 분석 주차: {week_str} ({monday.strftime('%Y.%m.%d')} ~ {sunday.strftime('%Y.%m.%d')})")
        log_info(f"   📂 파일: {filepath}")
        
        # 기존 데이터 로드 (파일이 있으면)
        existing_df = None
        existing_links = set()
        
        if filepath.exists():
            try:
                existing_df = pd.read_excel(filepath, sheet_name='뉴스 분석 결과')
                existing_links = set(existing_df['링크'].tolist())
                log_info(f"   📥 기존 데이터 로드: {len(existing_df)}개")
            except Exception as e:
                log_warning(f"   ⚠️ 기존 파일 로드 실패 (새로 생성): {e}")
                existing_df = None
        else:
            log_info(f"   ✨ 신규 파일 생성")
        
        # 새 데이터 준비 (중복 제거)
        new_data = []
        duplicate_count = 0
        
        for item in analyzed_results:
            link = item.get('link', '')
            
            # 중복 체크
            if link in existing_links:
                duplicate_count += 1
                continue
            
            # 키워드 및 영향도 정보 추출
            keywords_str = ""
            impact_info = _get_impact_info(item)
            if item.get('extracted_keywords'):
                try:
                    keywords_data = json.loads(item['extracted_keywords'])
                    keywords_list = [kw.get('term', '') for kw in keywords_data.get('keywords', [])]
                    keywords_str = ", ".join(keywords_list[:10])
                except Exception:
                    keywords_str = ""
            
            # 분석 결과에서 섹션 추출 (다양한 AI 출력 포맷 대응)
            def _extract_section(text: str, section_num: int, section_names: list, next_section_names: list) -> str:
                """섹션 번호·이름 조합을 유연하게 매칭하여 해당 섹션 텍스트 반환."""
                # 헤딩 레벨(##, ###)과 볼드(**)는 선택적으로 매칭
                start_patterns = [
                    rf'#{2,4}\s*\*{{0,2}}{section_num}\.\s*(?:{"| ".join(re.escape(n) for n in section_names)})\*{{0,2}}',
                    rf'#{2,4}\s*(?:{"| ".join(re.escape(n) for n in section_names)})',
                    rf'\*{{1,2}}{section_num}\.\s*(?:{"| ".join(re.escape(n) for n in section_names)})\*{{0,2}}',
                ]
                end_patterns = [
                    rf'#{2,4}\s*\*{{0,2}}{section_num + 1}\.',
                    rf'#{2,4}\s*\*{{0,2}}(?:{"| ".join(re.escape(n) for n in next_section_names)})',
                ]
                for sp in start_patterns:
                    start_m = re.search(sp, text, re.IGNORECASE)
                    if not start_m:
                        continue
                    body = text[start_m.end():]
                    for ep in end_patterns:
                        end_m = re.search(ep, body, re.IGNORECASE)
                        if end_m:
                            return body[:end_m.start()].strip()
                    # 다음 섹션 헤딩을 못 찾으면 JSON 블록 직전까지 반환
                    json_m = re.search(r'\{[\s\S]*?"keywords"', body)
                    if json_m:
                        return body[:json_m.start()].strip()
                    return body.strip()
                return ""

            def _clean_md(text: str) -> str:
                """마크다운 볼드 제거 + ㅇ 글머리 통일."""
                text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
                text = text.replace('ㅇ', '•')
                return text.strip()

            analysis_summary = ""
            implications_summary = ""
            if item.get('analysis_result'):
                raw = item['analysis_result']
                try:
                    analysis_summary = _clean_md(_extract_section(
                        raw, 1,
                        ['주요 내용 요약', '주요 내용', 'Main Content', 'Summary'],
                        ['시사점', 'Implications', 'Impact'],
                    ))
                    implications_summary = _clean_md(_extract_section(
                        raw, 2,
                        ['시사점 및 전망', '시사점', 'Implications', 'Impact'],
                        ['핵심 키워드', 'Keywords', 'TTA'],
                    ))
                except Exception:
                    pass
                # 섹션 추출 실패 시 전체 텍스트 사용 (잘라내지 않음)
                if not analysis_summary:
                    analysis_summary = _clean_md(raw)
            
            # 행 데이터 구성
            row_data = {
                '제목': item.get('title', ''),
                '발행일': item.get('published', ''),
                '출처': item.get('source', ''),
                '링크': link,
                '영향도': impact_info.get('impact_level', 'Medium'),
                '주요 내용 요약': analysis_summary,
                '시사점 및 전망': implications_summary,
                'TTA 조치 사항': impact_info.get('tta_action_item', ''),
                '표준화 격차': impact_info.get('standardization_gap', ''),
                '핵심 키워드': keywords_str,
                'AI 모델': item.get('ai_model', CONFIG.get('ai_model', 'openai')),
                '품질 점수': item.get('quality_score', 0),
                '수집 일시': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
            new_data.append(row_data)
            existing_links.add(link)
        
        if duplicate_count > 0:
            log_info(f"   🔄 중복 제거: {duplicate_count}개")
        
        if not new_data:
            log_warning(f"   ⚠️ 새로 추가할 데이터가 없습니다. (모두 중복)")
            return str(filepath) if filepath.exists() else None
        
        # 새 데이터 DataFrame 생성
        new_df = pd.DataFrame(new_data)
        
        # 기존 데이터와 병합
        if existing_df is not None:
            combined_df = pd.concat([existing_df, new_df], ignore_index=True)
        else:
            combined_df = new_df
        
        # 번호 재정렬 (기존 번호 컨럼 제거 후 삽입)
        if '번호' in combined_df.columns:
            combined_df = combined_df.drop('번호', axis=1)
        combined_df.insert(0, '번호', range(1, len(combined_df) + 1))
        
        # 발행일 기준 정렬 (최신순)
        try:
            combined_df['발행일_정렬용'] = pd.to_datetime(combined_df['발행일'], errors='coerce')
            combined_df = combined_df.sort_values('발행일_정렬용', ascending=False)
            combined_df = combined_df.drop('발행일_정렬용', axis=1)
            combined_df['번호'] = range(1, len(combined_df) + 1)
        except Exception:
            pass
        
        # 엑셀 저장 (스타일 적용)
        def _save_to_excel(path_to_save):
            with pd.ExcelWriter(path_to_save, engine='openpyxl') as writer:
                combined_df.to_excel(writer, index=False, sheet_name='뉴스 분석 결과')
                
                worksheet = writer.sheets['뉴스 분석 결과']
                
                # 열별 고정 너비 설정 (내용 칼럼은 넓게)
                col_widths = {
                    '번호': 6,
                    '제목': 45,
                    '발행일': 14,
                    '출처': 16,
                    '링크': 40,
                    '영향도': 10,
                    '주요 내용 요약': 60,
                    '시사점 및 전망': 60,
                    'TTA 조치 사항': 40,
                    '표준화 격차': 30,
                    '핵심 키워드': 30,
                    'AI 모델': 12,
                    '품질 점수': 10,
                    '수집 일시': 18,
                }
                for col_idx, col in enumerate(worksheet.columns, 1):
                    header_val = worksheet.cell(row=1, column=col_idx).value or ''
                    width = col_widths.get(header_val, 20)
                    worksheet.column_dimensions[col[0].column_letter].width = width

                # 헤더 스타일
                header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
                header_font = Font(bold=True, color="FFFFFF", size=11)

                for cell in worksheet[1]:
                    cell.fill = header_fill
                    cell.font = header_font
                    cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)

                # 데이터 행 스타일 + 행 높이 자동 추정
                for row in worksheet.iter_rows(min_row=2, max_row=worksheet.max_row):
                    max_lines = 1
                    for cell in row:
                        cell.alignment = Alignment(vertical='top', wrap_text=True)
                        if cell.value:
                            # 줄바꿈 수 + 열 너비 기반으로 줄 수 추정
                            col_header = worksheet.cell(row=1, column=cell.column).value or ''
                            col_w = col_widths.get(col_header, 20)
                            text = str(cell.value)
                            newlines = text.count('\n') + 1
                            wrapped = max(1, len(text) // max(col_w, 1))
                            lines = max(newlines, wrapped)
                            max_lines = max(max_lines, lines)
                    # 행 높이: 줄당 약 15pt, 최소 25, 최대 400
                    row[0].parent.row_dimensions[row[0].row].height = min(max(max_lines * 15, 25), 400)
        
        try:
            _save_to_excel(filepath)
        except PermissionError:
            log_warning(f"⚠️ 엑셀 파일이 열려 있어 덮어쓸 수 없습니다: {filepath.name}")
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = filepath.with_name(f"{filepath.stem}_alt_{timestamp}{filepath.suffix}")
            log_info(f"   🔄 대체 파일명으로 저장을 시도합니다: {filepath.name}")
            _save_to_excel(filepath)
        
        log_info(f"   ✅ 엑셀 파일 저장 완료!")
        log_info(f"      - 기존 데이터: {len(existing_df) if existing_df is not None else 0}개")
        log_info(f"      - 신규 추가: {len(new_data)}개")
        log_info(f"      - 최종 합계: {len(combined_df)}개")
        log_info(f"      - 파일 크기: {filepath.stat().st_size / 1024:.1f} KB")
        
        return str(filepath)
        
    except Exception as e:
        log_error(f"❌ 주간 누적 엑셀 저장 실패: {e}")
        log_error(traceback.format_exc())
        return None


@performance_monitor
# FIX: 반환 타입 불일치 - None 반환 케이스가 있으므로 Optional[str]로 수정
def save_keyword_summary_to_weekly_excel(
    output_dir: str = "data/reports"
) -> Optional[str]:
    """
    이번 주 전체 키워드 통계를 엑셀로 저장
    
    - 주간 누적 엑셀 파일에서 키워드 추출
    - 파일명 형식: keyword_summary_2025_W46.xlsx
    
    Args:
        output_dir: 저장 폴더 경로
    
    Returns:
        str: 생성된 엑셀 파일 경로
    """
    try:
        # 현재 주차 정보
        year, week, week_str = get_week_number()
        
        # 주간 누적 엑셀 파일 경로
        news_filename = f"news_analysis_{week_str}.xlsx"
        news_filepath = Path(output_dir) / news_filename
        
        if not news_filepath.exists():
            log_warning(f"⚠️ 주간 뉴스 파일이 없습니다: {news_filepath}")
            return None
        
        log_info(f"\n📊 주간 키워드 통계 생성 중...")
        log_info(f"   📂 원본 파일: {news_filepath}")
        
        # 주간 뉴스 데이터 로드
        df = pd.read_excel(news_filepath, sheet_name='뉴스 분석 결과')
        
        # 키워드 집계
        all_keywords = []
        
        for _, row in df.iterrows():
            keywords_str = row.get('핵심 키워드', '')
            
            if not keywords_str or pd.isna(keywords_str):
                continue
            
            # 간단한 파싱 (쉼표로 구분된 키워드)
            keywords_list = [kw.strip() for kw in str(keywords_str).split(',') if kw.strip()]
            all_keywords.extend(keywords_list)
        
        if not all_keywords:
            log_warning(f"   ⚠️ 추출된 키워드가 없습니다.")
            return None
        
        # 빈도 계산
        keyword_freq = Counter(all_keywords)
        
        # 파일명 생성
        filename = f"keyword_summary_{week_str}.xlsx"
        filepath = Path(output_dir) / filename
        
        # 엑셀 저장
        def _save_summary_to_excel(path_to_save):
            with pd.ExcelWriter(path_to_save, engine='openpyxl') as writer:
                # 시트 1: 전체 키워드 빈도
                df_freq = pd.DataFrame(
                    keyword_freq.most_common(100),
                    columns=['키워드', '빈도']
                )
                df_freq['순위'] = range(1, len(df_freq) + 1)
                df_freq = df_freq[['순위', '키워드', '빈도']]
                df_freq.to_excel(writer, index=False, sheet_name='전체 키워드')
                
                # 시트 2: 주간 통계 요약
                summary_data = {
                    '항목': ['분석 주차', '전체 뉴스 수', '고유 키워드 수', 'TOP 1 키워드', 'TOP 2 키워드', 'TOP 3 키워드'],
                    '값': [
                        week_str,
                        len(df),
                        len(keyword_freq),
                        keyword_freq.most_common(1)[0][0] if len(keyword_freq) >= 1 else '',
                        keyword_freq.most_common(2)[1][0] if len(keyword_freq) >= 2 else '',
                        keyword_freq.most_common(3)[2][0] if len(keyword_freq) >= 3 else ''
                    ]
                }
                df_summary = pd.DataFrame(summary_data)
                df_summary.to_excel(writer, index=False, sheet_name='주간 통계')
                
                # 스타일 적용
                
                for sheet_name in writer.sheets:
                    worksheet = writer.sheets[sheet_name]
                    
                    # 헤더 스타일
                    header_fill = PatternFill(start_color="70AD47", end_color="70AD47", fill_type="solid")
                    header_font = Font(bold=True, color="FFFFFF", size=11)
                    
                    for cell in worksheet[1]:
                        cell.fill = header_fill
                        cell.font = header_font
                        cell.alignment = Alignment(horizontal='center', vertical='center')
                    
                    # 열 너비 조정
                    for column in worksheet.columns:
                        max_length = 0
                        column_letter = column[0].column_letter
                        
                        for cell in column:
                            try:
                                if len(str(cell.value)) > max_length:
                                    max_length = len(str(cell.value))
                            except Exception:
                                pass
                        
                        adjusted_width = min(max_length + 2, 60)
                        worksheet.column_dimensions[column_letter].width = adjusted_width
        
        try:
            _save_summary_to_excel(filepath)
        except PermissionError:
            log_warning(f"⚠️ 키워드 통계 엑셀 파일이 열려 있어 덮어쓸 수 없습니다: {filepath.name}")
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = filepath.with_name(f"{filepath.stem}_alt_{timestamp}{filepath.suffix}")
            log_info(f"   🔄 대체 파일명으로 저장을 시도합니다: {filepath.name}")
            _save_summary_to_excel(filepath)
        
        log_info(f"   ✅ 키워드 통계 저장 완료!")
        log_info(f"      - 고유 키워드: {len(keyword_freq)}개")
        log_info(f"      - 파일 크기: {filepath.stat().st_size / 1024:.1f} KB")
        
        return str(filepath)
        
    except Exception as e:
        log_error(f"❌ 주간 키워드 통계 저장 실패: {e}")
        log_error(traceback.format_exc())
        return None








# ==============================================================================
# --- 구글챗 긴급 알림 ---
# ==============================================================================

def send_google_chat_alert(issue_title: str, issue_desc: str, impact_level: str,
                           related_articles: list = None):
    """
    구글챗 Webhook으로 긴급 이슈 알림 발송.
    config.json 의 google_chat_webhook 이 설정된 경우에만 동작.
    """
    webhook_url = CONFIG.get('google_chat_webhook', '')
    if not webhook_url:
        log_info("  ℹ️ google_chat_webhook 미설정 — 구글챗 알림 생략")
        return

    level_emoji = {'상': '🔴', '중': '🟡', '하': '🟢'}.get(impact_level, '⚪')

    lines = [f"{level_emoji} *[긴급 이슈 알림]* 중요도: *{impact_level}*",
             f"*{issue_title}*", ""]

    # 개조식 설명 처리
    if isinstance(issue_desc, list):
        for item in issue_desc[:3]:
            lines.append(f"• {item.lstrip('ㅇ').strip()}")
    else:
        lines.append(issue_desc[:300])

    if related_articles:
        lines.append("")
        lines.append("📰 관련 뉴스")
        for art in related_articles[:3]:
            if isinstance(art, dict):
                title = art.get('title', '')
                link = art.get('link', '')
                lines.append(f"  - <{link}|{title}>" if link else f"  - {title}")
            else:
                lines.append(f"  - {art}")

    lines += ["", f"_IRONAGE AI Analytics — {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}_"]

    payload = {"text": "\n".join(lines)}
    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        if resp.status_code == 200:
            log_info(f"  ✅ 구글챗 알림 발송 완료: {issue_title[:40]}")
        else:
            log_warning(f"  ⚠️ 구글챗 알림 실패 (status={resp.status_code}): {resp.text[:100]}")
    except Exception as e:
        log_warning(f"  ⚠️ 구글챗 알림 예외: {e}")


# ==============================================================================
# --- 경쟁 기관 (3GPP·ETSI·ITU 등) RSS 수집 ---
# ==============================================================================

@performance_monitor
def get_standards_org_news(days: int = 7) -> List[Dict]:
    """
    3GPP, ETSI, ITU 등 국제 표준화 기구 RSS 피드에서 최신 공지/뉴스 수집.
    CONFIG['standards_org_rss'] 에 URL 목록을 지정한다.
    """
    rss_urls = CONFIG.get('standards_org_rss', [])
    if not rss_urls:
        log_info("  ℹ️ standards_org_rss 미설정 — 경쟁 기관 수집 생략")
        return []

    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
    results = []

    for url in rss_urls:
        try:
            feed = feedparser.parse(url)
            org_name = feed.feed.get('title', url.split('/')[2])
            count = 0
            for entry in feed.entries:
                published = None
                for attr in ('published_parsed', 'updated_parsed'):
                    val = getattr(entry, attr, None)
                    if val:
                        published = datetime.datetime(*val[:6],
                                                      tzinfo=datetime.timezone.utc)
                        break
                if published and published < cutoff:
                    continue

                title = entry.get('title', '').strip()
                link = entry.get('link', '').strip()
                if not title or not link:
                    continue

                results.append({
                    'title': f"[{org_name}] {title}",
                    'link': link,
                    'source': org_name,
                    'published': published.isoformat() if published else '',
                    'content': entry.get('summary', '')[:500],
                    'quality_score': 0.85,          # 공신력 있는 출처로 높은 기본 점수
                    'is_standards_org': True,
                })
                count += 1

            log_info(f"  ✅ {org_name}: {count}개 수집")
        except Exception as e:
            log_warning(f"  ⚠️ 표준화 기관 RSS 수집 실패 ({url}): {e}")

    log_info(f"  📡 경쟁 기관 합계: {len(results)}개")
    return results


# ==============================================================================
# --- Windows 자동 스케줄 등록 ---
# ==============================================================================

def setup_windows_schedule():
    """
    Windows 작업 스케줄러에 daily/weekly/monthly 작업을 자동 등록.
    python news_engine.py setup-schedule 로 실행.
    """
    import subprocess
    import sys

    python_exe = sys.executable
    script_path = str(Path(__file__).resolve())
    log_dir = str(Path("data/logs").resolve())

    daily_time  = CONFIG.get('schedule_daily',   '09:00')
    weekly_day  = CONFIG.get('schedule_weekly',  'Monday 09:00').split()[0]
    weekly_time = CONFIG.get('schedule_weekly',  'Monday 09:00').split()[-1]
    monthly_day = CONFIG.get('schedule_monthly', '1 09:00').split()[0]
    monthly_time= CONFIG.get('schedule_monthly', '1 09:00').split()[-1]

    tasks = [
        {
            'name':     'IRONAGE_Daily',
            'cmd':      f'"{python_exe}" "{script_path}" daily',
            'schedule': f'/SC DAILY /ST {daily_time}',
            'desc':     '일일 뉴스 수집 및 AI 분석',
        },
        {
            'name':     'IRONAGE_Weekly',
            'cmd':      f'"{python_exe}" "{script_path}" weekly',
            'schedule': f'/SC WEEKLY /D {weekly_day.upper()} /ST {weekly_time}',
            'desc':     '주간 트렌드 리포트 생성',
        },
        {
            'name':     'IRONAGE_Monthly',
            'cmd':      f'"{python_exe}" "{script_path}" monthly',
            'schedule': f'/SC MONTHLY /D {monthly_day} /ST {monthly_time}',
            'desc':     '월간 종합 리포트 생성',
        },
    ]

    log_info("=" * 60)
    log_info("⏰ Windows 작업 스케줄러 등록 시작")
    log_info("=" * 60)

    for task in tasks:
        # 기존 동명 작업 삭제 (오류 무시)
        subprocess.run(
            f'schtasks /Delete /TN "{task["name"]}" /F',
            shell=True, capture_output=True
        )

        cmd = (
            f'schtasks /Create /TN "{task["name"]}" '
            f'/TR "{task["cmd"]}" '
            f'{task["schedule"]} '
            f'/RL HIGHEST /F '
            f'/SD {datetime.date.today().strftime("%m/%d/%Y")}'
        )
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            log_info(f"  ✅ {task['name']}: {task['desc']}")
        else:
            log_error(f"  ❌ {task['name']} 등록 실패: {result.stderr.strip()}")

    log_info("=" * 60)
    log_info("⏰ 스케줄 등록 완료!")
    log_info(f"   일일: 매일 {daily_time}")
    log_info(f"   주간: 매주 {weekly_day} {weekly_time}")
    log_info(f"   월간: 매월 {monthly_day}일 {monthly_time}")
    log_info("   확인: schtasks /Query /TN IRONAGE_Daily")
    log_info("=" * 60)


# ==============================================================================
# --- 배치 분석 ---
# ==============================================================================

def run_batch_analysis_on_pending(batch_size: int = 10, ai_model: str = None, progress_callback=None):
    """
    AI 선별(quality_score > 0.5) 미분석 기사를 배치로 AI 분석.
    quality_score 태그가 없는 기존 기사는 ICT 키워드 매칭으로 보완.
    analyze_news_with_replacement()를 재활용하여 스크래핑·DB 저장·임베딩 준비까지 처리.

    Args:
        batch_size: 이번 배치에서 목표로 할 분석 성공 건수
        ai_model: 사용 모델 (None이면 CONFIG 기본값)
        progress_callback: (done, total) → None 형태의 진행률 콜백
    Returns:
        {'analyzed': int, 'failed': int, 'pending_after': int}
    """
    if not SessionLocal:
        log_error("❌ DB 세션이 초기화되지 않았습니다.")
        return {'analyzed': 0, 'failed': 0, 'pending_after': 0}

    pool_size = batch_size * 3
    ict_kw_lower = [kw.lower() for kw in (CONFIG.get('ict_keywords') or DEFAULT_ICT_KEYWORDS)]

    def _to_dict(a):
        return {
            'id': a.id,
            'title': a.title or '',
            'link': a.link,
            'source': a.source or '출처 불명',
            'published': a.published.strftime('%Y-%m-%d %H:%M') if a.published else '',
            'content': a.content or '',
            'quality_score': a.quality_score or 0.0,
            'is_analyzed': a.is_analyzed,
            'analysis_result': a.analysis_result or '',
            'extracted_keywords': a.extracted_keywords or '',
        }

    with get_db_session() as session:
        # ① quality_score 태그 기사 우선 (filter_news_by_ai() 수정 후 수집된 기사)
        tagged_rows = (
            session.query(NewsArticle)
            .filter(NewsArticle.quality_score > 0.5, NewsArticle.is_analyzed != True)
            .order_by(NewsArticle.collected_at.desc())
            .limit(pool_size)
            .all()
        )
        candidates = [_to_dict(a) for a in tagged_rows]

        # ② 부족하면 ICT 키워드 매칭 미분석 기사로 보완 (기존 0점 기사 대응)
        if len(candidates) < pool_size:
            need = pool_size - len(candidates)
            tagged_links = {a.link for a in tagged_rows}
            untagged_rows = (
                session.query(NewsArticle)
                .filter(
                    NewsArticle.is_analyzed != True,
                    NewsArticle.quality_score <= 0.5,
                )
                .order_by(NewsArticle.collected_at.desc())
                .limit(need * 5)   # 키워드 필터 후 부족할 수 있으니 5배 로드
                .all()
            )
            for a in untagged_rows:
                if a.link in tagged_links:
                    continue
                title_lower = (a.title or '').lower()
                if any(kw in title_lower for kw in ict_kw_lower):
                    candidates.append(_to_dict(a))
                    tagged_links.add(a.link)
                    if len(candidates) >= pool_size:
                        break

        # 잔여 대기 건수 계산 (태그 기사 + ICT 키워드 매칭 기사 합산)
        tagged_pending = (
            session.query(NewsArticle)
            .filter(NewsArticle.quality_score > 0.5, NewsArticle.is_analyzed != True)
            .count()
        )

    if not candidates:
        log_info("✅ 배치 분석 대기 기사 없음")
        return {'analyzed': 0, 'failed': 0, 'pending_after': 0}

    log_info(f"🤖 배치 AI 분석 시작: 후보 {len(candidates)}건 → 목표 {batch_size}건 분석")

    results = analyze_news_with_replacement(
        news_to_analyze=candidates[:batch_size],
        all_news_items=candidates,
        target_count=batch_size,
        ai_model=ai_model,
        progress_callback=progress_callback,
    )

    analyzed = len(results) if results else 0
    failed = batch_size - analyzed

    log_info(f"✅ 배치 분석 완료: 성공 {analyzed}건 / 실패 {failed}건 / 태그 잔여 {tagged_pending}건")
    return {'analyzed': analyzed, 'failed': failed, 'pending_after': tagged_pending}


# --- 메인 실행 함수 ---
# ==============================================================================

@performance_monitor
def run_daily_collection(ai_model: str = None):
    """
     일일 뉴스 수집 및 분석 - 주간 누적 저장
    
    Args:
        ai_model: 사용할 AI 모델 ('openai', 'claude', 'perplexity', 'gemini')
                  None이면 CONFIG에서 읽음
    """
    # ✅ 추가: AI 모델 결정
    if ai_model is None:
        ai_model = CONFIG.get('ai_model', 'openai')
    
    log_info("=" * 60)
    log_info("🚀 일일 뉴스 수집 시작")
    log_info(f"🤖 사용 AI 모델: {ai_model.upper()}")
    log_info("=" * 60)

    # 당일 중복 실행 방지: 오늘 이미 분석 완료된 기사가 5개 이상이면 스킵
    try:
        _today_start = datetime.datetime.now(datetime.timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        with get_db_session() as _s:
            _today_analyzed = _s.query(NewsArticle).filter(
                NewsArticle.collected_at >= _today_start,
                NewsArticle.is_analyzed == True
            ).count()
        if _today_analyzed >= 5:
            log_info(f"ℹ️ 오늘 이미 {_today_analyzed}개 기사 분석 완료 — 중복 실행 건너뜀.")
            return []
    except Exception as _dup_err:
        log_warning(f"⚠️ 중복 실행 체크 실패 (계속 진행): {_dup_err}")

    log_info("\n[작업 0/8] 경쟁 기관 (3GPP·ETSI·ITU) 뉴스 수집 중...")
    standards_news = safe_execute(
        lambda: get_standards_org_news(days=1),
        error_msg="경쟁 기관 RSS 수집 실패",
        default_return=[]
    )

    log_info("\n[작업 1/8] 뉴스 수집 중...")
    unique_news_items = safe_execute(
        lambda: get_news_data(),
        error_msg="뉴스 수집 실패",
        default_return=[]
    )
    # 경쟁 기관 뉴스 병합 (중복 링크 제거)
    if standards_news:
        existing_links = {n['link'] for n in unique_news_items}
        new_std = [n for n in standards_news if n['link'] not in existing_links]
        unique_news_items = unique_news_items + new_std
        log_info(f"   📡 경쟁 기관 뉴스 {len(new_std)}개 병합 완료")
    
    if not unique_news_items:
        log_warning("\n⚠️ 수집된 뉴스가 없습니다. 프로그램을 종료합니다.")
        return []

    log_info("\n[작업 2/8] DB 저장 중...")
    saved_count = safe_execute(
        lambda: save_news_to_db(unique_news_items),
        error_msg="DB 저장 실패",
        default_return=0
    )
    log_info(f"   ✅ {saved_count}개 저장 완료")

    log_info(f"\n[작업 3/8] AI 선별 + 중복 제거 중 ({ai_model.upper()})...")
    log_info(f"   📊 수집된 뉴스: {len(unique_news_items)}개")
    
    news_to_analyze = safe_execute(
        lambda: filter_news_by_ai(unique_news_items, ai_model=ai_model, max_results=50),
        error_msg="AI 선별 실패",
        default_return=unique_news_items[:20]
    )
    
    log_info(f"   ✅ AI 선별 완료: {len(news_to_analyze)}개 (중복 제거 후)")
    log_info(f"   🔄 중복 제거율: {(1 - len(news_to_analyze) / 50) * 100:.1f}%")

    log_info(f"\n[작업 4/8] 심층 분석 중 ({ai_model.upper()})...")
    log_info(f"   🎯 목표: 상위 20개 분석")

    # 선별된 50개 중 상위 20개를 먼저 분석 시도.
    # 대체 후보 우선순위: 선별된 나머지 30개(news_to_analyze[20:]) → 전체 수집 뉴스
    _replacement_pool = news_to_analyze[20:] + [
        item for item in unique_news_items
        if item['link'] not in {n['link'] for n in news_to_analyze}
    ]
    analyzed_results = safe_execute(
        lambda: analyze_news_with_replacement(
            news_to_analyze[:20],
            _replacement_pool,
            target_count=20,
            ai_model=ai_model
        ),
        error_msg="뉴스 분석 실패",
        default_return=[]
    )
    
    if not analyzed_results:
        log_error("❌ 분석된 뉴스가 없습니다. 리포트 생성을 건너뜁니다.")
        return []
    
    log_info("\n[작업 5/8] 분석 결과 저장 중...")
    saved_analysis = 0
    for result in analyzed_results:
        try:
            with get_db_session() as session:
                article = session.query(NewsArticle).filter_by(
                    link=result['link']
                ).first()
                
                if article:
                    article.is_analyzed = True
                    article.analysis_result = result.get('analysis_result', '')
                    article.ai_model = result.get('ai_model', ai_model)  # Bug 1: 실제 사용 모델 저장
                    if result.get('extracted_keywords'):
                        article.extracted_keywords = result['extracted_keywords']
                    
                    saved_analysis += 1
        except Exception as e:
            log_warning(f"⚠️ 분석 결과 저장 실패: {result['title'][:30]}...")
            log_error(traceback.format_exc()) 
    
    log_info(f"   ✅ {saved_analysis}개 저장 완료")
    
    log_info("\n[작업 6/8] 리포트 생성 및 발송 중...")

    # 심층 분석된 링크 집합
    analyzed_links = {r['link'] for r in analyzed_results}
    # 추가 수집 뉴스: AI가 선별한 60개 전체 중 분석되지 않은 항목
    # (분석 실패로 대체된 항목 포함, 상위 20개 중 실패분 + 나머지 40개)
    other_news = [item for item in news_to_analyze if item['link'] not in analyzed_links]
    log_info(f"   📋 추가 수집 뉴스 구성: 선별 {len(news_to_analyze)}개 중 미분석 {len(other_news)}개")

    doc_url, report_title = safe_execute(
        lambda: generate_google_doc_report(analyzed_results),
        error_msg="구글 문서 생성 실패",
        default_return=(None, None)
    )

    # Bug 4: Docs 실패 여부와 무관하게 이메일 항상 발송
    report_title = report_title or f"전파·이동통신 동향 보고서 ({datetime.date.today().strftime('%Y년 %m월 %d일')})"
    log_info(f"   📰 추가 수집 뉴스: {len(other_news)}개 (선별된 목록 중 미분석)")
    safe_execute(
        lambda: send_gmail_report(
            report_title,
            analyzed_results,
            doc_url,
            other_news
        ),
        error_msg="이메일 발송 실패",
        default_return=None
    )

    # 구글챗 긴급 알림: 중요도 "상" 이슈 감지 시 즉시 발송
    alert_threshold = CONFIG.get('alert_impact_level', '상')
    _alert_levels = {'상': 3, '중': 2, '하': 1}
    threshold_score = _alert_levels.get(alert_threshold, 3)

    try:
        from trend_analyzer import analyze_weekly_trends as _quick_analyze
        _quick_result = _quick_analyze(analyzed_results)
        for _issue in _quick_result.get('key_issues', []):
            level = _issue.get('impact_level', _issue.get('importance', '하'))
            if _alert_levels.get(level, 0) >= threshold_score:
                send_google_chat_alert(
                    issue_title=_issue.get('title', ''),
                    issue_desc=_issue.get('description', []),
                    impact_level=level,
                    related_articles=_quick_result.get('title_link_map', {}),
                )
    except Exception as _e:
        log_warning(f"⚠️ 긴급 알림 처리 중 오류 (비중요): {_e}")

    # ✅ 수정: 작업 7 - 주간 누적 엑셀 저장
    log_info("\n[작업 7/8] 주간 누적 엑셀 저장 중...")
    excel_path = safe_execute(
        lambda: save_analysis_to_weekly_excel(analyzed_results),
        error_msg="엑셀 저장 실패",
        default_return=None
    )
    
    if excel_path:
        log_info(f"  ✅ 주간 누적 저장: {excel_path}")
    
    # ✅ 수정: 작업 8 - 주간 키워드 통계 저장
    log_info("\n[작업 8/8] 주간 키워드 통계 저장 중...")
    keyword_excel_path = safe_execute(
        lambda: save_keyword_summary_to_weekly_excel(),
        error_msg="키워드 통계 저장 실패",
        default_return=None
    )
    
    if keyword_excel_path:
        log_info(f"  ✅ 키워드 통계 저장: {keyword_excel_path}")
    

    log_info("\n" + "=" * 60)
    log_info(f"✅ 일일 뉴스 수집 및 분석이 완료되었습니다! (사용 모델: {ai_model.upper()})")
    log_info(f"📊 최종 통계:")
    log_info(f"   - 수집: {len(unique_news_items)}개")
    log_info(f"   - AI 선별 (중복 제거 후): {len(news_to_analyze)}개")
    log_info(f"   - 심층 분석: {len(analyzed_results)}개")
    log_info(f"   - 추가 수집 뉴스: {len(other_news)}개")
    log_info("=" * 60)
    
    return analyzed_results

def run_weekly_report():
    """주간 트렌드 리포트 생성 (AI 분석 강화 버전)"""
    log_info("=" * 60)
    log_info("📊 주간 트렌드 리포트 생성 시작")
    log_info("=" * 60)

    # user_settings에서 주간 구독자 이메일 취합
    subscribers = get_weekly_subscribers()
    log_info(f"  📧 주간 구독자: {len(subscribers)}명 — {', '.join(subscribers)}")

    log_info("\n[1/5] 최근 7일간 분석된 뉴스를 불러옵니다...")
    articles = load_news_from_db(days=7, is_analyzed=True)

    if not articles:
        log_warning("⚠️ 주간 리포트를 생성할 데이터가 없습니다.")
        return None

    log_info(f"  ✅ {len(articles)}개의 분석된 뉴스 로드 완료")

    log_info("\n[2/5] AI 트렌드 분석 중...")
    from trend_analyzer import analyze_weekly_trends
    analysis_result = analyze_weekly_trends(articles)

    if not analysis_result or not analysis_result.get('key_issues'):
        log_warning("⚠️ 트렌드 분석에 실패했습니다. 기본 보고서를 생성합니다.")
        report_title = f"전파·이동통신 주간 동향 보고서 ({datetime.date.today().strftime('%Y년 %m월 %d일')})"
        doc_url, _ = generate_google_doc_report(articles)
        send_gmail_report(report_title, articles, doc_url, [], receivers=subscribers)
        return doc_url

    log_info(f"  ✅ AI 분석 완료: {len(analysis_result['key_issues'])}개 핵심 이슈 도출")

    log_info("\n[3/5] 트렌드 리포트 문서 생성 중...")
    try:
        from trend_analyzer import generate_trend_report_doc
        doc_url, report_title = generate_trend_report_doc(analysis_result, report_type='weekly')
    except ImportError:
        log_warning("⚠️ generate_trend_report_doc 미정의 - 기본 문서 생성으로 대체합니다.")
        report_title = f"전파·이동통신 주간 동향 보고서 ({datetime.date.today().strftime('%Y년 %m월 %d일')})"
        doc_url, _ = generate_google_doc_report(articles)

    if not doc_url:
        log_warning("⚠️ 구글 문서 생성에 실패했습니다. 이메일만 발송합니다.")
        _fallback_title = report_title or f"전파·이동통신 주간 동향 보고서 ({datetime.date.today().strftime('%Y년 %m월 %d일')})"
        send_gmail_report(_fallback_title, articles, None, [], receivers=subscribers)
        return None

    log_info(f"  ✅ 문서 생성 완료: {doc_url}")

    log_info("\n[4/5] 이메일 발송 중...")
    try:
        from trend_analyzer import send_trend_report_email
        send_trend_report_email(report_title, analysis_result, doc_url, report_type='weekly',
                                receivers=subscribers)
    except (ImportError, TypeError):
        log_warning("⚠️ send_trend_report_email 미지원 - 기본 이메일 발송으로 대체합니다.")
        send_gmail_report(report_title, articles, doc_url, [], receivers=subscribers)
    
    log_info("\n[5/5] 결과 저장 중...")
    try:
        report_meta = {
            'report_type': 'weekly',
            'generated_at': datetime.datetime.now().isoformat(),
            'doc_url': doc_url,
            'articles_count': len(articles),
            'key_issues_count': len(analysis_result.get('key_issues', [])),
            'trends_count': len(analysis_result.get('trends', []))
        }
        
        Path("data/reports").mkdir(exist_ok=True)
        report_file = f"data/reports/weekly_{datetime.datetime.now().strftime('%Y%m%d')}.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report_meta, f, indent=2, ensure_ascii=False)
        
        log_info(f"  ✅ 메타데이터 저장: {report_file}")
    except Exception as e:
        log_warning(f"⚠️ 메타데이터 저장 실패: {e}")
    
    log_info("\n" + "=" * 60)
    log_info("✅ 주간 리포트 생성 완료!")
    log_info(f"📄 문서 링크: {doc_url}")
    log_info("=" * 60)
    
    return doc_url


def run_monthly_report():
    """월간 종합 리포트 생성 (AI 분석 강화 버전)"""
    log_info("=" * 60)
    log_info("📈 월간 종합 리포트 생성 시작")
    log_info("=" * 60)
    
    log_info("\n[1/5] 최근 30일간 분석된 뉴스를 불러옵니다...")
    articles = load_news_from_db(days=30, is_analyzed=True)
    
    if not articles:
        log_warning("⚠️ 월간 리포트를 생성할 데이터가 없습니다.")
        return None
    
    log_info(f"  ✅ {len(articles)}개의 분석된 뉴스 로드 완료")
    
    log_info("\n[2/5] AI 트렌드 분석 중...")
    from trend_analyzer import analyze_monthly_trends
    analysis_result = analyze_monthly_trends(articles)
    
    if not analysis_result or not analysis_result.get('key_issues'):
        log_warning("⚠️ 트렌드 분석에 실패했습니다. 기본 보고서를 생성합니다.")
        report_title = f"전파·이동통신 월간 동향 보고서 ({datetime.date.today().strftime('%Y년 %m월 %d일')})"
        doc_url, _ = generate_google_doc_report(articles)
        if doc_url:
            send_gmail_report(report_title, articles, doc_url, [])
        return doc_url

    log_info(f"  ✅ AI 분석 완료:")
    log_info(f"     - 핵심 이슈: {len(analysis_result['key_issues'])}개")
    log_info(f"     - 트렌드: {len(analysis_result.get('trends', []))}개")
    log_info(f"     - 기술 하이라이트: {len(analysis_result.get('technology_highlights', []))}개")

    log_info("\n[3/5] 월간 트렌드 리포트 문서 생성 중...")
    # FIX: 존재하지 않을 수 있는 함수 import를 try-except로 감싸기
    try:
        from trend_analyzer import generate_trend_report_doc
        doc_url, report_title = generate_trend_report_doc(analysis_result, report_type='monthly')
    except ImportError:
        log_warning("⚠️ generate_trend_report_doc 미정의 - 기본 문서 생성으로 대체합니다.")
        report_title = f"전파·이동통신 월간 동향 보고서 ({datetime.date.today().strftime('%Y년 %m월 %d일')})"
        doc_url, _ = generate_google_doc_report(articles)

    if not doc_url:
        log_error("❌ 구글 문서 생성에 실패했습니다.")
        return None

    log_info(f"  ✅ 문서 생성 완료: {doc_url}")

    log_info("\n[4/5] 이메일 발송 중...")
    # FIX: 존재하지 않을 수 있는 함수 import를 try-except로 감싸기
    try:
        from trend_analyzer import send_trend_report_email
        send_trend_report_email(report_title, analysis_result, doc_url, report_type='monthly')
    except ImportError:
        log_warning("⚠️ send_trend_report_email 미정의 - 기본 이메일 발송으로 대체합니다.")
        send_gmail_report(report_title, articles, doc_url, [])
    
    log_info("\n[5/5] 결과 저장 및 통계 정리...")
    try:
        stats = analysis_result.get('statistics', {})
        report_meta = {
            'report_type': 'monthly',
            'generated_at': datetime.datetime.now().isoformat(),
            'doc_url': doc_url,
            'articles_count': len(articles),
            'key_issues_count': len(analysis_result.get('key_issues', [])),
            'trends_count': len(analysis_result.get('trends', [])),
            'technology_highlights_count': len(analysis_result.get('technology_highlights', [])),
            'statistics': {
                'total_articles': stats.get('total_articles', 0),
                'avg_quality_score': stats.get('avg_quality_score', 0),
                'top_sources': list(stats.get('source_distribution', {}).keys())[:5],
                'top_keywords': [kw[0] for kw in stats.get('top_keywords', [])[:10]]
            }
        }
        
        Path("data/reports").mkdir(exist_ok=True)
        report_file = f"data/reports/monthly_{datetime.datetime.now().strftime('%Y%m')}.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report_meta, f, indent=2, ensure_ascii=False)
        
        log_info(f"  ✅ 메타데이터 저장: {report_file}")
        
        top_keywords = [kw[0] for kw in stats.get('top_keywords', [])[:10]]
        log_info(f"  📊 월간 TOP 키워드: {', '.join(top_keywords)}")
        
    except Exception as e:
        log_warning(f"⚠️ 메타데이터 저장 실패: {e}")
    
    log_info("\n" + "=" * 60)
    log_info("✅ 월간 리포트 생성 완료!")
    log_info(f"📄 문서 링크: {doc_url}")
    log_info("=" * 60)
    
    return doc_url


# ==============================================================================
# --- CLI 실행 인터페이스 ---
# ==============================================================================

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == "daily":
            run_daily_collection()
        elif command == "weekly":
            run_weekly_report()
        elif command == "monthly":
            run_monthly_report()
        elif command == "test":
            log_info("🧪 테스트 모드")
            stats = get_db_statistics()
            log_info(f"DB 통계: {stats}")
        elif command == "setup-schedule":
            setup_windows_schedule()
        elif command == "standards":
            items = get_standards_org_news(days=7)
            log_info(f"경쟁 기관 수집 결과: {len(items)}개")
            for it in items[:5]:
                log_info(f"  - {it['title'][:80]}")
        else:
            log_info("=" * 60)
            log_info("IRONAGE AI Analytics System v5.0 - CLI")
            log_info("=" * 60)
            log_info("\n사용법:")
            log_info("  python news_engine.py daily           # 일일 뉴스 수집 및 분석")
            log_info("  python news_engine.py weekly          # 주간 트렌드 리포트")
            log_info("  python news_engine.py monthly         # 월간 종합 리포트")
            log_info("  python news_engine.py test            # DB 통계 확인")
            log_info("  python news_engine.py setup-schedule  # Windows 자동 스케줄 등록")
            log_info("  python news_engine.py standards       # 경쟁 기관 RSS 수집 테스트")
            log_info("\n웹 대시보드 실행:")
            log_info("  streamlit run main_app.py")
            log_info("=" * 60)
    else:
        run_daily_collection()

