# -*- coding: utf-8 -*-
"""
news_engine.py 종합 패치 스크립트 (v2)
- 이전 세션 누락 변경사항 + 현재 세션 Google Doc 변경사항
실행: python scripts/_patch_all.py
주의: 읽기/쓰기 모두 기본 모드(CRLF 자동 변환). 매칭 문자열은 LF 기준.
"""
import re, sys, os

TARGET = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'news_engine.py'))

# 읽기: utf-8-sig(BOM 자동 제거) + 기본 모드(CRLF→LF 자동 변환)
with open(TARGET, 'r', encoding='utf-8-sig') as f:
    text = f.read()
if text.startswith('﻿'):
    text = text[1:]
print(f"[read] {len(text)} chars")

def r1(text, old, new, label):
    cnt = text.count(old)
    if cnt != 1:
        raise AssertionError(f"{label}: expected 1, found {cnt}\n  OLD[:80]={repr(old[:80])}")
    print(f"  [OK] {label}")
    return text.replace(old, new, 1)

def rx(text, pattern, new, label, flags=re.DOTALL):
    m = list(re.finditer(pattern, text, flags))
    if len(m) != 1:
        raise AssertionError(f"{label}: expected 1 regex match, got {len(m)}")
    print(f"  [OK] {label}")
    return text[:m[0].start()] + new + text[m[0].end():]

# ══════════════════════════════════════════════════════════════════════════════
# A. 이전 세션 변경사항 (DB 스키마, 필터, 이메일 발송 함수)
# ══════════════════════════════════════════════════════════════════════════════
print("\n=== A. 이전 세션 변경사항 ===")

# A1. user_settings CREATE TABLE에 sender_name, email_subject_prefix 컬럼 추가
text = r1(text,
    "                    google_alerts_rss TEXT DEFAULT '[]',\n"
    "                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,\n"
    "                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
    "                    google_alerts_rss TEXT DEFAULT '[]',\n"
    "                    sender_name TEXT DEFAULT '',\n"
    "                    email_subject_prefix TEXT DEFAULT '',\n"
    "                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,\n"
    "                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
    "A1. CREATE TABLE 컬럼 추가"
)

# A2. missing_us dict에 sender_name, email_subject_prefix 추가
text = r1(text,
    "            missing_us = {\n"
    "                'unit_id':          'INTEGER',\n"
    "                'google_alerts_rss': \"TEXT DEFAULT '[]'\",\n"
    "            }",
    "            missing_us = {\n"
    "                'unit_id':          'INTEGER',\n"
    "                'google_alerts_rss': \"TEXT DEFAULT '[]'\",\n"
    "                'sender_name':         \"TEXT DEFAULT ''\",\n"
    "                'email_subject_prefix': \"TEXT DEFAULT ''\",\n"
    "            }",
    "A2. missing_us dict 수정"
)

# A3a. load_unit_settings _empty 수정
text = r1(text,
    "    _empty = {'keywords': [], 'google_alerts_rss': [], 'email_recipients': []}",
    "    _empty = {'keywords': [], 'google_alerts_rss': [], 'email_recipients': [],\n"
    "              'sender_name': '', 'email_subject_prefix': ''}",
    "A3a. _empty 수정"
)

# A3b. load_unit_settings SQL SELECT 수정
text = r1(text,
    '        with get_db_session() as session:\n'
    '            row = session.execute(\n'
    '                sa_text("SELECT keywords, google_alerts_rss, email_recipients "\n'
    '                        "FROM user_settings WHERE unit_id = :uid "\n'
    '                        "ORDER BY CASE WHEN user_email = :ve THEN 0 ELSE 1 END LIMIT 1"),',
    '        with get_db_session() as session:\n'
    '            row = session.execute(\n'
    '                sa_text("SELECT keywords, google_alerts_rss, email_recipients,"\n'
    '                        " sender_name, email_subject_prefix"\n'
    '                        " FROM user_settings WHERE unit_id = :uid "\n'
    '                        "ORDER BY CASE WHEN user_email = :ve THEN 0 ELSE 1 END LIMIT 1"),',
    "A3b. SQL SELECT 수정"
)

# A3c. load_unit_settings return dict 수정
text = r1(text,
    "        return {\n"
    "            'keywords':          json.loads(row[0] or '[]'),\n"
    "            'google_alerts_rss': json.loads(row[1] or '[]'),\n"
    "            'email_recipients':  json.loads(row[2] or '[]'),\n"
    "        }",
    "        return {\n"
    "            'keywords':              json.loads(row[0] or '[]'),\n"
    "            'google_alerts_rss':     json.loads(row[1] or '[]'),\n"
    "            'email_recipients':      json.loads(row[2] or '[]'),\n"
    "            'sender_name':           row[3] or '',\n"
    "            'email_subject_prefix':  row[4] or '',\n"
    "        }",
    "A3c. return dict 수정"
)

# A4a. save_user_settings SQL upsert 수정
text = r1(text,
    '"(user_email, keywords, ai_model, email_recipients, schedule_daily, schedule_weekly, google_alerts_rss, updated_at) "\n'
    '        "VALUES (:email, :kw, :model, :emails, :daily, :weekly, :rss, CURRENT_TIMESTAMP) "\n'
    '        "ON CONFLICT (user_email) DO UPDATE SET "\n'
    '        "keywords=EXCLUDED.keywords, ai_model=EXCLUDED.ai_model, "\n'
    '        "email_recipients=EXCLUDED.email_recipients, schedule_daily=EXCLUDED.schedule_daily, "\n'
    '        "schedule_weekly=EXCLUDED.schedule_weekly, google_alerts_rss=EXCLUDED.google_alerts_rss, "\n'
    '        "updated_at=EXCLUDED.updated_at"\n'
    '    ) if is_pg else (\n'
    '        "INSERT INTO user_settings "\n'
    '        "(user_email, keywords, ai_model, email_recipients, schedule_daily, schedule_weekly, google_alerts_rss, updated_at) "\n'
    '        "VALUES (:email, :kw, :model, :emails, :daily, :weekly, :rss, CURRENT_TIMESTAMP) "\n'
    '        "ON CONFLICT (user_email) DO UPDATE SET "\n'
    '        "keywords=excluded.keywords, ai_model=excluded.ai_model, "\n'
    '        "email_recipients=excluded.email_recipients, schedule_daily=excluded.schedule_daily, "\n'
    '        "schedule_weekly=excluded.schedule_weekly, google_alerts_rss=excluded.google_alerts_rss, "\n'
    '        "updated_at=CURRENT_TIMESTAMP"\n'
    '    )',
    '"(user_email, keywords, ai_model, email_recipients, schedule_daily, schedule_weekly,"\n'
    '        " google_alerts_rss, sender_name, email_subject_prefix, updated_at) "\n'
    '        "VALUES (:email, :kw, :model, :emails, :daily, :weekly, :rss, :sname, :esubj, CURRENT_TIMESTAMP) "\n'
    '        "ON CONFLICT (user_email) DO UPDATE SET "\n'
    '        "keywords=EXCLUDED.keywords, ai_model=EXCLUDED.ai_model, "\n'
    '        "email_recipients=EXCLUDED.email_recipients, schedule_daily=EXCLUDED.schedule_daily, "\n'
    '        "schedule_weekly=EXCLUDED.schedule_weekly, google_alerts_rss=EXCLUDED.google_alerts_rss, "\n'
    '        "sender_name=EXCLUDED.sender_name, email_subject_prefix=EXCLUDED.email_subject_prefix, "\n'
    '        "updated_at=EXCLUDED.updated_at"\n'
    '    ) if is_pg else (\n'
    '        "INSERT INTO user_settings "\n'
    '        "(user_email, keywords, ai_model, email_recipients, schedule_daily, schedule_weekly,"\n'
    '        " google_alerts_rss, sender_name, email_subject_prefix, updated_at) "\n'
    '        "VALUES (:email, :kw, :model, :emails, :daily, :weekly, :rss, :sname, :esubj, CURRENT_TIMESTAMP) "\n'
    '        "ON CONFLICT (user_email) DO UPDATE SET "\n'
    '        "keywords=excluded.keywords, ai_model=excluded.ai_model, "\n'
    '        "email_recipients=excluded.email_recipients, schedule_daily=excluded.schedule_daily, "\n'
    '        "schedule_weekly=excluded.schedule_weekly, google_alerts_rss=excluded.google_alerts_rss, "\n'
    '        "sender_name=excluded.sender_name, email_subject_prefix=excluded.email_subject_prefix, "\n'
    '        "updated_at=CURRENT_TIMESTAMP"\n'
    '    )',
    "A4a. SQL upsert 수정"
)

# A4b. save_user_settings 파라미터 추가
text = r1(text,
    '                "email": user_email,\n'
    '                "kw":    json.dumps(settings.get(\'keywords\', []), ensure_ascii=False),\n'
    '                "model": settings.get(\'ai_model\', \'gemini\'),\n'
    '                "emails": json.dumps(settings.get(\'email_recipients\', []), ensure_ascii=False),\n'
    '                "daily":  settings.get(\'schedule_daily\', True),\n'
    '                "weekly": settings.get(\'schedule_weekly\', True),\n'
    '                "rss":    json.dumps(settings.get(\'google_alerts_rss\', []), ensure_ascii=False),',
    '                "email": user_email,\n'
    '                "kw":    json.dumps(settings.get(\'keywords\', []), ensure_ascii=False),\n'
    '                "model": settings.get(\'ai_model\', \'gemini\'),\n'
    '                "emails": json.dumps(settings.get(\'email_recipients\', []), ensure_ascii=False),\n'
    '                "daily":  settings.get(\'schedule_daily\', True),\n'
    '                "weekly": settings.get(\'schedule_weekly\', True),\n'
    '                "rss":    json.dumps(settings.get(\'google_alerts_rss\', []), ensure_ascii=False),\n'
    '                "sname":  settings.get(\'sender_name\', \'\') or \'\',\n'
    '                "esubj":  settings.get(\'email_subject_prefix\', \'\') or \'\',',
    "A4b. 파라미터 추가"
)

# A5. save_unit_settings sender_name, email_subject_prefix 전달
text = r1(text,
    "        save_user_settings(virtual_email, {\n"
    "            'keywords':          settings.get('keywords', []),\n"
    "            'google_alerts_rss': settings.get('google_alerts_rss', []),\n"
    "            'email_recipients':  settings.get('email_recipients', []),\n"
    "            'ai_model':          'gemini',\n"
    "            'schedule_daily':    True,\n"
    "            'schedule_weekly':   True,\n"
    "        })",
    "        save_user_settings(virtual_email, {\n"
    "            'keywords':              settings.get('keywords', []),\n"
    "            'google_alerts_rss':     settings.get('google_alerts_rss', []),\n"
    "            'email_recipients':      settings.get('email_recipients', []),\n"
    "            'sender_name':           settings.get('sender_name', ''),\n"
    "            'email_subject_prefix':  settings.get('email_subject_prefix', ''),\n"
    "            'ai_model':              'gemini',\n"
    "            'schedule_daily':        True,\n"
    "            'schedule_weekly':       True,\n"
    "        })",
    "A5. save_unit_settings 수정"
)

# A6a. filter_news_by_ai 시그니처 수정
text = r1(text,
    "def filter_news_by_ai(\n"
    "    news_items: List[Dict], \n"
    "    ai_model: str = 'openai', \n"
    "    max_results: int = 60\n"
    ") -> List[Dict]:",
    "def filter_news_by_ai(\n"
    "    news_items: List[Dict],\n"
    "    ai_model: str = 'openai',\n"
    "    max_results: int = 60,\n"
    "    unit_keywords: List[str] = None,\n"
    "    unit_display: str = None,\n"
    ") -> List[Dict]:",
    "A6a. filter_news_by_ai 시그니처"
)

# A6b. filter_news_by_ai Stage 1 이중 게이트 추가
OLD_STAGE1 = (
    "    ict_keywords = CONFIG.get('ict_keywords') or DEFAULT_ICT_KEYWORDS\n"
    "    ict_keywords_lower = [kw.lower() for kw in ict_keywords]\n"
    "    ict_min = CONFIG.get('ict_min_articles', 25)\n"
    "\n"
    "    ict_news = [\n"
    "        item for item in news_items\n"
    "        if any(kw in item['title'].lower() for kw in ict_keywords_lower)\n"
    "    ]\n"
    "    non_ict_count = len(news_items) - len(ict_news)\n"
    "\n"
    "    if len(ict_news) < ict_min:\n"
    "        log_warning(f\"  ⚠️ ICT 관련 뉴스 {len(ict_news)}개 < 최소 기준 {ict_min}개. 전체 뉴스({len(news_items)}개)로 대체합니다.\")\n"
    "        ict_news = news_items\n"
    "    else:\n"
    "        log_info(f\"  • Stage 1 ICT 필터: {len(news_items)}개 → {len(ict_news)}개 (비ICT {non_ict_count}개 제외)\")"
)
NEW_STAGE1 = (
    "    ict_keywords = CONFIG.get('ict_keywords') or DEFAULT_ICT_KEYWORDS\n"
    "    ict_keywords_lower = [kw.lower() for kw in ict_keywords]\n"
    "    ict_min = CONFIG.get('ict_min_articles', 25)\n"
    "\n"
    "    # 단별 키워드 기반 이중 게이트 필터 (unit_keywords 지정 시)\n"
    "    if unit_keywords:\n"
    "        unit_kws_lower = [kw.lower() for kw in unit_keywords]\n"
    "        CORE_ICT_MARKERS = [\n"
    "            '통신', '5g', '6g', 'lte', '이동통신', '주파수', '3gpp', 'itu', 'etsi', 'ict',\n"
    "            '정보통신', '표준화', '국제표준', '과기정통부', '전파', 'horizon europe', '호라이젠',\n"
    "            '인공지능', '반도체', '사이버보안', '클라우드', '메타버스', '양자',\n"
    "            '위성', '자율주행', '스마트', '디지털', '네트워크', '플랫폼',\n"
    "        ]\n"
    "        SPECIFIC_UNIT_KWS = [\n"
    "            kw for kw in unit_kws_lower if len(kw) >= 4 and kw not in {'표준', 'ai', 'ict'}\n"
    "        ]\n"
    "        unit_ict_confirmed, unit_specific_only, ict_only = [], [], []\n"
    "        for item in news_items:\n"
    "            tl = item['title'].lower()\n"
    "            has_unit    = any(kw in tl for kw in unit_kws_lower)\n"
    "            has_spec    = any(kw in tl for kw in SPECIFIC_UNIT_KWS)\n"
    "            has_ict     = any(mk in tl for mk in CORE_ICT_MARKERS)\n"
    "            if has_unit and has_ict:\n"
    "                unit_ict_confirmed.append(item)\n"
    "            elif has_spec:\n"
    "                unit_specific_only.append(item)\n"
    "            elif has_ict:\n"
    "                ict_only.append(item)\n"
    "        ict_news = unit_ict_confirmed + unit_specific_only + ict_only\n"
    "        log_info(f\"  • Stage 1 단별 이중 게이트 [{unit_display or '?'}]: {len(news_items)}개 → {len(ict_news)}개 \"\n"
    "                 f\"(단+ICT {len(unit_ict_confirmed)}, 단특화 {len(unit_specific_only)}, ICT전용 {len(ict_only)})\")\n"
    "        if not ict_news:\n"
    "            log_warning(f\"  ⚠️ [{unit_display}] 단별 필터 결과 없음. 전체 뉴스로 대체.\")\n"
    "            ict_news = news_items\n"
    "        ict_min = 5  # 단별 실행 시 최소 기준 완화\n"
    "    else:\n"
    "        ict_news = [\n"
    "            item for item in news_items\n"
    "            if any(kw in item['title'].lower() for kw in ict_keywords_lower)\n"
    "        ]\n"
    "        non_ict_count = len(news_items) - len(ict_news)\n"
    "        if len(ict_news) < ict_min:\n"
    "            log_warning(f\"⚠️ ICT 관련 뉴스 {len(ict_news)}개 < 최소 기준 {ict_min}개. 전체 뉴스({len(news_items)}개)로 대체합니다.\")\n"
    "            ict_news = news_items\n"
    "        else:\n"
    "            log_info(f\"  • Stage 1 ICT 필터: {len(news_items)}개 → {len(ict_news)}개 (비ICT {non_ict_count}개 제외)\")"
)
text = r1(text, OLD_STAGE1, NEW_STAGE1, "A6b. Stage 1 이중 게이트")

# A7a. _UNIT_EMAIL_SUBJECT_MAP 상수 + run_all_units_daily 시그니처 수정
text = r1(text,
    "def run_all_units_daily(ai_model: str = None) -> dict:",
    "# 단 name → 이메일 제목 본문 (날짜는 run_all_units_daily에서 동적으로 붙임)\n"
    "_UNIT_EMAIL_SUBJECT_MAP = {\n"
    "    'standards_planning':   '표준전략 동향 보고서',\n"
    "    'standards_innovation': '표준혁신 동향 보고서',\n"
    "    'ai_convergence':       'AI 융합 동향 보고서',\n"
    "    'radio_network':        '전파·네트워크 동향 보고서',\n"
    "}\n"
    "\n"
    "\n"
    "def run_all_units_daily(ai_model: str = None, target_unit_id: int = None) -> dict:",
    "A7a. _UNIT_EMAIL_SUBJECT_MAP + 시그니스"
)

# A7b. run_all_units_daily 내부 — target_unit_id 처리 (rx: 유연한 패턴)
text = rx(text,
    r'    log_info\("=" \* 60\)\n'
    r'    log_info\("[^"]+\[전체 단\][^"]+"\)\n'
    r'    log_info\(f"[^"]+AI 모델[^"]+"\)\n'
    r'    log_info\("=" \* 60\)\n'
    r'\n'
    r'    all_units = get_all_units\(\)\n'
    r'    summary = \{\}',
    "    if target_unit_id is not None:\n"
    "        log_info(\"=\" * 60)\n"
    "        log_info(f\"\U0001f680 [단별 실행] unit_id={target_unit_id} 수집·분析 파이프라인 시작\")\n"
    "        log_info(f\"\U0001f916 AI 모델: {ai_model.upper()}\")\n"
    "        log_info(\"=\" * 60)\n"
    "    else:\n"
    "        log_info(\"=\" * 60)\n"
    "        log_info(\"\U0001f680 [전체 단] 일일 수집·분析 파이프라인 시작\")\n"
    "        log_info(f\"\U0001f916 AI 모델: {ai_model.upper()}\")\n"
    "        log_info(\"=\" * 60)\n"
    "\n"
    "    all_units = get_all_units()\n"
    "    if target_unit_id is not None:\n"
    "        all_units = [u for u in all_units if u['id'] == target_unit_id]\n"
    "    summary = {}",
    "A7b. target_unit_id 처리"
)

# A7c. unit_cfg에서 sender_name, email_subject_prefix 로드
text = r1(text,
    "        rss_urls     = unit_cfg.get('google_alerts_rss', [])\n"
    "        keywords     = unit_cfg.get('keywords', [])\n"
    "        email_rcpts  = unit_cfg.get('email_recipients', [])",
    "        rss_urls             = unit_cfg.get('google_alerts_rss', [])\n"
    "        keywords             = unit_cfg.get('keywords', [])\n"
    "        email_rcpts          = unit_cfg.get('email_recipients', [])\n"
    "        sender_name          = unit_cfg.get('sender_name', '') or f'{unit_display} AI뉴스봇'\n"
    "        email_subject_prefix = unit_cfg.get('email_subject_prefix', '') or f'[TTA {unit_display}]'",
    "A7c. sender_name/email_subject_prefix 로드"
)

# A7d. filter_news_by_ai 호출에 unit_keywords, unit_display 추가
text = r1(text,
    '            selected = filter_news_by_ai(news_items, ai_model=ai_model, max_results=50)',
    '            selected = filter_news_by_ai(\n'
    '                news_items,\n'
    '                ai_model=ai_model,\n'
    '                max_results=50,\n'
    '                unit_keywords=keywords,\n'
    '                unit_display=unit_display,\n'
    '            )',
    "A7d. filter_news_by_ai 단별 파라미터"
)

# A7e. 이메일 제목 생성 + generate_google_doc_report 인수 추가
text = rx(text,
    r"        # ── 6\. 리포트 생성 [─]+\n"
    r"        doc_url, report_title = safe_execute\(\n"
    r"            lambda: generate_google_doc_report\(analyzed\),",
    "        # ── 5-b. 메일 제목 생성 (단별 고정 형식) ───────────\n"
    "        import pytz as _pytz\n"
    "        _kst_tz   = _pytz.timezone('Asia/Seoul')\n"
    "        _kst_date = datetime.datetime.now(_kst_tz).strftime('%Y년 %m월 %d일')\n"
    "        _subj_body = _UNIT_EMAIL_SUBJECT_MAP.get(unit_name, f'{unit_display} 동향 보고서')\n"
    "        _email_subject = f'[TTA] {_subj_body} ({_kst_date})'\n"
    "\n"
    "        # ── 6. 리포트 생성 ──────────────────────────────────────────\n"
    "        doc_url, report_title = safe_execute(\n"
    "            lambda: generate_google_doc_report(\n"
    "                analyzed, unit_name=unit_name, unit_display=unit_display\n"
    "            ),",
    "A7e. 메일 제목 생성 + gdoc 인수"
)

# A7f. send_gmail_report 호출 업데이트
text = r1(text,
    "            lambda: send_gmail_report(report_title, analyzed, doc_url, other_news, receivers=receivers),",
    "            lambda: send_gmail_report(\n"
    "                report_title, analyzed, doc_url, other_news,\n"
    "                receivers=receivers,\n"
    "                sender_name=sender_name,\n"
    "                unit_display=unit_display,\n"
    "                email_subject_prefix=email_subject_prefix,\n"
    "                email_subject_override=_email_subject,\n"
    "            ),",
    "A7f. send_gmail_report 호출 업데이트"
)

# A8a. send_gmail_report 시그니처 수정
text = r1(text,
    "def send_gmail_report(report_title, analyzed_data, doc_url, other_news, receivers=None):\n"
    '    """분석 리포트를 개선된 디자인의 이메일로 전송.\n'
    '    receivers: 수신자 목록 (None이면 전역 RECEIVER_EMAIL 사용)"""',
    "def send_gmail_report(\n"
    "    report_title, analyzed_data, doc_url, other_news,\n"
    "    receivers=None,\n"
    "    sender_name: str = None,\n"
    "    unit_display: str = None,\n"
    "    email_subject_prefix: str = None,\n"
    "    email_subject_override: str = None,\n"
    "):\n"
    '    """분석 리포트를 개선된 디자인의 이메일로 전송.\n'
    '    receivers: 수신자 목록 (None이면 전역 RECEIVER_EMAIL 사용)\n'
    '    email_subject_override: 이 값이 있으면 제목 완전 대체\n'
    '    """',
    "A8a. send_gmail_report 시그니처"
)

# A8b. 제목/발신자 설정 수정
text = r1(text,
    '    msg = MIMEMultipart("alternative")\n'
    '    msg["Subject"] = f"[TTA] {report_title}"\n'
    '    msg["From"] = SENDER_EMAIL',
    "    _unit_label = unit_display or 'TTA'\n"
    "    _from_display = (sender_name.strip() if sender_name else '') or f'{_unit_label} AI'\n"
    "    _from_header = f'{_from_display} <{SENDER_EMAIL}>'\n"
    "    if email_subject_override:\n"
    "        _subject = email_subject_override.strip()\n"
    "    elif email_subject_prefix:\n"
    "        _subject = f'{email_subject_prefix.strip()} {report_title}'\n"
    "    elif unit_display:\n"
    "        _subject = f'[TTA {unit_display}] {report_title}'\n"
    "    else:\n"
    "        _subject = f'[TTA] {report_title}'\n"
    '    msg = MIMEMultipart("alternative")\n'
    '    msg["Subject"] = _subject\n'
    '    msg["From"] = _from_header',
    "A8b. 제목/발신자 수정"
)

# A8c. 이메일 HTML 푸터 단 명칭 반영
text = r1(text,
    "                    <strong>한국정보통신기술협회(TTA)</strong><br>\n"
    "                    표준화본부 이동통신표준팀",
    "                    <strong>한국정보통신기술협회(TTA)</strong><br>\n"
    "                    {unit_display or '표준화본부'}",
    "A8c. HTML 푸터 단 명칭"
)

# ══════════════════════════════════════════════════════════════════════════════
# B. Google Docs 변경사항
# ══════════════════════════════════════════════════════════════════════════════
print("\n=== B. Google Docs 변경사항 ===")

# B1. generate_google_doc_report 함수 시그니처
text = r1(text,
    'def generate_google_doc_report(analyzed_data):',
    'def generate_google_doc_report(analyzed_data, unit_name=None, unit_display=None):',
    "B1. generate_google_doc_report 시그니처"
)

# B2. 문서 제목 — KST + 단별 이메일 제목 형식
text = rx(text,
    r"current_date = datetime\.date\.today\(\)\.strftime\([^\n]+\n"
    r"    document_title = [^\n]+",
    "_kst_tz_doc = pytz.timezone('Asia/Seoul')\n"
    "    _kst_now_doc = datetime.datetime.now(_kst_tz_doc)\n"
    "    _kst_date_doc = _kst_now_doc.strftime('%Y년 %m월 %d일')\n"
    "    _subj_body_doc = (\n"
    "        _UNIT_EMAIL_SUBJECT_MAP.get(unit_name or '', '')\n"
    "        or f'{(unit_display or \"\").strip()} 동향 보고서'.strip()\n"
    "    )\n"
    "    document_title = f\"[TTA] {_subj_body_doc} ({_kst_date_doc})\"",
    "B2. 문서 제목 KST"
)

# B3. 부제목 — 단 명칭 + KST
text = rx(text,
    r"subtitle_text = f\"한국정보통신기술협회\(TTA\)[^\n]+\n",
    "_unit_subtitle = unit_display or '표준화본부'\n"
    "        subtitle_text = (\n"
    "            f'한국정보통신기술협회(TTA) {_unit_subtitle}\\n'\n"
    "            f'작성일: {_kst_now_doc.strftime(\"%Y년 %m월 %d일 %H:%M\")} (KST)\\n'\n"
    "        )\n",
    "B3. 부제목 단 명칭+KST"
)

# B4. Phase 7 (급등 키워드 TOP5) 섹션 삭제
text = rx(text,
    r"[ \t]+# Phase 7: 전주 대비 급등 키워드 TOP 5 섹션\r?\n"
    r".*?log_warning\(f\"[^\"]*_phase7_err[^\"]*\"\)\r?\n",
    '',
    "B4. Phase7 섹션 삭제"
)

# B5. 주요 조치 필요 항목 (Critical/High) 섹션 삭제
text = rx(text,
    r"[ \t]+# ── 영향도 요약 섹션 \(Critical / High 우선 노출\).*?(?=[ \t]+# 각 뉴스 아이템)",
    '',
    "B5. Critical/High 섹션 삭제"
)

# B6. 목차 10 → 20
text = r1(text,
    'for i, data in enumerate(analyzed_data[:10], 1):',
    'for i, data in enumerate(analyzed_data[:20], 1):',
    "B6. 목차 20개"
)

# B7a. 배지 코멘트 수정
text = r1(text,
    '# ── 영향도 배지 + TTA 조치 사항 ────────────────────────────',
    '# ── 영향도 배지 ────────────────────────────',
    "B7a. 배지 코멘트 수정"
)

# B7b. TTA 블록 추출 + 원래 위치 제거
m_tta = re.search(
    r"( {12}tta = impact_info\['tta_action_item'\]\r?\n"
    r"            if tta:.*?index \+= _utf16_len\(tta_body\)\r?\n"
    r"(?:\r?\n)?)",
    text, re.DOTALL
)
if not m_tta:
    raise AssertionError("B7b: TTA block not found")
tta_block = m_tta.group(0)
text = text[:m_tta.start()] + text[m_tta.end():]
print("  [OK] B7b. TTA 블록 원래 위치 제거")

# B7c. TTA 블록을 뉴스 마지막(separator 직전)에 삽입
sep_anchor = "            if i < len(analyzed_data) - 1:\n"
if sep_anchor not in text:
    raise AssertionError("B7c: separator anchor not found")
tta_insert = (
    "            # ── TTA 조치사항 (뉴스 마지막 배치) ────────────────\n"
    + tta_block + "\n"
)
text = text.replace(sep_anchor, tta_insert + sep_anchor, 1)
print("  [OK] B7c. TTA 블록 뉴스 마지막에 삽입")

# B8a. 푸터 — _footer_unit 선언 추가
FOOTER_FIRST = "        footer_text = f\"\\n\\n{'=' * 60}\\n\"\n"
if FOOTER_FIRST not in text:
    raise AssertionError(f"B8a: footer first line not found. text has {text.count('footer_text')} 'footer_text'")
text = r1(text, FOOTER_FIRST,
    "        _footer_unit = unit_display or '표준화본부'\n" + FOOTER_FIRST,
    "B8a. _footer_unit 선언")

# B8b. 푸터 datetime KST로 수정
text = rx(text,
    r'footer_text \+= f"문서 작성 완료: \{datetime\.datetime\.now\(\)\.strftime\([^)]+\)\}\\n"',
    "footer_text += f\"문서 작성 완료: {_kst_now_doc.strftime('%Y년 %m월 %d일 %H:%M:%S')} (KST)\\n\"",
    "B8b. 푸터 datetime KST"
)

# B8c. 푸터 단 명칭 수정
text = rx(text,
    r'footer_text \+= "한국정보통신기술협회\(TTA\) 표준화본부 이동통신표준팀\\n"',
    'footer_text += f"한국정보통신기술협회(TTA) {_footer_unit}\\n"',
    "B8c. 푸터 단 명칭"
)

# B9a. DAILY_SUBFOLDER_NAME 상수 추가
text = r1(text,
    'REPORT_FOLDER_ID = "15YV7XuiWW2DJiY_ur_ZweHphSvciRjzT"',
    'REPORT_FOLDER_ID = "15YV7XuiWW2DJiY_ur_ZweHphSvciRjzT"\n'
    '# 일일 동향 보고서 저장 하위 폴더명 (REPORT_FOLDER_ID 안에 자동 생성)\n'
    'DAILY_SUBFOLDER_NAME = "99_일일동향"',
    "B9a. DAILY_SUBFOLDER_NAME 상수"
)

# B9b. _get_or_create_subfolder 헬퍼 함수 추가
helper_fn = (
    "\n"
    "\n"
    "def _get_or_create_subfolder(drive_service, parent_id: str, folder_name: str) -> str:\n"
    '    """parent_id 안에 folder_name 폴더를 찾아 반환. 없으면 생성 후 반환."""\n'
    "    try:\n"
    "        q = (\n"
    "            f\"name='{folder_name}' and mimeType='application/vnd.google-apps.folder'\"\n"
    "            f\" and '{parent_id}' in parents and trashed=false\"\n"
    "        )\n"
    "        results = drive_service.files().list(\n"
    "            q=q,\n"
    "            fields='files(id, name)',\n"
    "            supportsAllDrives=True,\n"
    "            includeItemsFromAllDrives=True,\n"
    "        ).execute()\n"
    "        files = results.get('files', [])\n"
    "        if files:\n"
    "            return files[0]['id']\n"
    "        meta = {\n"
    "            'name': folder_name,\n"
    "            'mimeType': 'application/vnd.google-apps.folder',\n"
    "            'parents': [parent_id],\n"
    "        }\n"
    "        folder = drive_service.files().create(\n"
    "            body=meta, supportsAllDrives=True, fields='id',\n"
    "        ).execute()\n"
    "        log_info(f\"  > 하위 폴더 생성: {folder_name}\")\n"
    "        return folder['id']\n"
    "    except Exception as e:\n"
    "        log_warning(f\"  ⚠️ 하위 폴더 조회/생성 실패 ({folder_name}): {e}\")\n"
    "        return parent_id\n"
    "\n"
)
text = rx(text,
    r'\r?\ndef _utf16_len\(s: str\) -> int:',
    helper_fn + '\ndef _utf16_len(s: str) -> int:',
    "B9b. _get_or_create_subfolder 헬퍼"
)

# B9c. 문서 저장 폴더를 99_일일동향으로 변경
text = rx(text,
    r"( +)# 공유 드라이브 폴더에 직접 생성 \(Drive API files\(\)\.create 사용\)\r?\n"
    r"( +)file_meta = \{\r?\n"
    r"( +)'name': document_title,\r?\n"
    r"( +)'mimeType': 'application/vnd\.google-apps\.document',\r?\n"
    r"( +)'parents': \[REPORT_FOLDER_ID\],\r?\n"
    r"( +)\}",
    "            # 99_일일동향 하위 폴더에 저장\n"
    "            _daily_folder_id = _get_or_create_subfolder(\n"
    "                drive_service, REPORT_FOLDER_ID, DAILY_SUBFOLDER_NAME\n"
    "            )\n"
    "            file_meta = {\n"
    "                'name': document_title,\n"
    "                'mimeType': 'application/vnd.google-apps.document',\n"
    "                'parents': [_daily_folder_id],\n"
    "            }",
    "B9c. 저장 폴더 변경"
)

# ══════════════════════════════════════════════════════════════════════════════
# 최종 검증
# ══════════════════════════════════════════════════════════════════════════════
print("\n=== 검증 ===")
checks = [
    # A
    ("sender_name TEXT DEFAULT ''",            1),
    ("email_subject_prefix TEXT DEFAULT ''",   1),
    ("'sender_name':           row[3]",        1),
    ("'email_subject_prefix':  row[4]",        1),
    ("unit_keywords: List[str] = None",        1),
    ("unit_display: str = None",               2),
    ("CORE_ICT_MARKERS",                       2),
    ("_UNIT_EMAIL_SUBJECT_MAP",                3),
    ("target_unit_id: int = None",             1),
    ("email_subject_override",                 5),
    ("_from_header",                           2),
    # B
    ("DAILY_SUBFOLDER_NAME",                   2),
    ("_get_or_create_subfolder",               2),
    ("_daily_folder_id",                       2),
    ("_kst_tz_doc",                            2),
    ("_subj_body_doc",                         2),
    ("_unit_subtitle",                         2),
    ("analyzed_data[:20]",                     1),
    ("TTA 조치사항 (뉴스 마지막 배치)", 1),
    ("tta = impact_info['tta_action_item']",   1),
    ("Phase 7",                                0),
]
all_ok = True
for k, expected in checks:
    count = text.count(k)
    ok = (count == expected)
    if not ok:
        all_ok = False
    print(f"  [{'OK' if ok else 'FAIL'}] {k[:50]!r} = {count} (exp {expected})")

if not all_ok:
    print("\nFAIL: 검증 실패 -- 저장 안 함")
    sys.exit(1)

# 쓰기: BOM 없는 UTF-8, 기본 모드(LF→CRLF 자동)
with open(TARGET, 'w', encoding='utf-8') as f:
    f.write(text)
print(f"\nSUCCESS: news_engine.py 저장 ({len(text)} chars)")
