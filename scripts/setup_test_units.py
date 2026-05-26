#!/usr/bin/env python3
"""
멀티유닛 테스트 환경 셋업 스크립트
=====================================
로컬 SQLite DB에 units 테이블과 테스트용 user_settings 데이터를 생성합니다.
실행: python scripts/setup_test_units.py

생성되는 테스트 계정:
  ironage@tta.or.kr     → 관리자 (admin, unit 없음)
  planning@tta.or.kr    → 표준기획단 담당자
  innovation@tta.or.kr  → 표준혁신단 담당자
  ai@tta.or.kr          → AI융합표준단 담당자
  radio@tta.or.kr       → 전파네트워크표준단 담당자
"""

import json
import sqlite3
import os
import sys

# 프로젝트 루트 기준
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT, "data", "news.db")


def run_setup():
    print(f"🗄️  DB 경로: {DB_PATH}")
    if not os.path.exists(DB_PATH):
        print("❌ data/news.db 없음. Streamlit 앱을 한 번 실행하거나 news_engine.py를 먼저 실행하세요.")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = OFF")  # 마이그레이션 중 FK 무시
    c = conn.cursor()

    # ── 1. units 테이블 ──────────────────────────────────────────────────────
    print("\n1️⃣  units 테이블 생성...")
    c.execute("""
        CREATE TABLE IF NOT EXISTS units (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(50) UNIQUE NOT NULL,
            display_name VARCHAR(100) NOT NULL,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    units = [
        ("standards_planning",  "표준기획단",       "ICT 표준화 기획 및 정책"),
        ("standards_innovation","표준혁신단",       "표준화 혁신 및 신기술"),
        ("ai_convergence",      "AI융합표준단",     "AI·SW 융합 표준화"),
        ("radio_network",       "전파네트워크표준단","전파·통신망 표준화"),
    ]
    for name, display_name, desc in units:
        c.execute("""
            INSERT OR IGNORE INTO units (name, display_name, description)
            VALUES (?, ?, ?)
        """, (name, display_name, desc))
    conn.commit()
    c.execute("SELECT id, name, display_name FROM units ORDER BY id")
    for row in c.fetchall():
        print(f"   ✅ [{row[0]}] {row[2]} ({row[1]})")

    # ── 2. user_settings 테이블 ──────────────────────────────────────────────
    print("\n2️⃣  user_settings 테이블 생성...")
    c.execute("""
        CREATE TABLE IF NOT EXISTS user_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email VARCHAR(255) UNIQUE NOT NULL,
            keywords TEXT DEFAULT '[]',
            ai_model VARCHAR(50) DEFAULT 'gemini',
            email_recipients TEXT DEFAULT '[]',
            schedule_daily BOOLEAN DEFAULT 1,
            schedule_weekly BOOLEAN DEFAULT 1,
            unit_id INTEGER REFERENCES units(id),
            google_alerts_rss TEXT DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()

    # 기존 user_settings에 unit_id/google_alerts_rss 컬럼 없으면 추가
    c.execute("PRAGMA table_info(user_settings)")
    existing_cols = {r[1] for r in c.fetchall()}
    if "unit_id" not in existing_cols:
        c.execute("ALTER TABLE user_settings ADD COLUMN unit_id INTEGER REFERENCES units(id)")
        print("   ➕ unit_id 컬럼 추가")
    if "google_alerts_rss" not in existing_cols:
        c.execute("ALTER TABLE user_settings ADD COLUMN google_alerts_rss TEXT DEFAULT '[]'")
        print("   ➕ google_alerts_rss 컬럼 추가")
    conn.commit()

    # ── 3. news_articles에 unit_id 컬럼 추가 ────────────────────────────────
    print("\n3️⃣  news_articles.unit_id 컬럼 추가...")
    c.execute("PRAGMA table_info(news_articles)")
    existing_cols = {r[1] for r in c.fetchall()}
    if "unit_id" not in existing_cols:
        c.execute("ALTER TABLE news_articles ADD COLUMN unit_id INTEGER")
        print("   ➕ news_articles.unit_id 컬럼 추가")
    else:
        print("   ✅ 이미 존재")
    conn.commit()

    # ── 4. 테스트용 사용자 데이터 삽입 ──────────────────────────────────────
    print("\n4️⃣  테스트용 @tta.or.kr 사용자 생성...")

    # unit id 조회
    c.execute("SELECT id, name FROM units")
    unit_map = {row[1]: row[0] for row in c.fetchall()}

    test_users = [
        {
            "email": "planning@tta.or.kr",
            "unit_name": "standards_planning",
            "keywords": ["ICT 표준", "TTA 표준화", "ITU-T", "3GPP 표준", "국제표준"],
            "rss": ["https://www.google.co.kr/alerts/feeds/sample_planning"],
            "recipients": ["planning@tta.or.kr"],
        },
        {
            "email": "innovation@tta.or.kr",
            "unit_name": "standards_innovation",
            "keywords": ["디지털 전환", "혁신 기술", "클라우드 네이티브", "오픈소스 표준", "블록체인"],
            "rss": ["https://www.google.co.kr/alerts/feeds/sample_innovation"],
            "recipients": ["innovation@tta.or.kr"],
        },
        {
            "email": "ai@tta.or.kr",
            "unit_name": "ai_convergence",
            "keywords": ["AI 표준", "생성형AI", "LLM", "AI 안전성", "AI 윤리"],
            "rss": ["https://www.google.co.kr/alerts/feeds/sample_ai"],
            "recipients": ["ai@tta.or.kr"],
        },
        {
            "email": "radio@tta.or.kr",
            "unit_name": "radio_network",
            "keywords": ["5G 표준", "6G", "위성통신", "스펙트럼", "전파"],
            "rss": ["https://www.google.co.kr/alerts/feeds/sample_radio"],
            "recipients": ["radio@tta.or.kr"],
        },
    ]

    for u in test_users:
        unit_id = unit_map.get(u["unit_name"])
        c.execute("""
            INSERT INTO user_settings (user_email, keywords, email_recipients, unit_id, google_alerts_rss)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_email) DO UPDATE SET
                unit_id = excluded.unit_id,
                keywords = excluded.keywords,
                google_alerts_rss = excluded.google_alerts_rss,
                updated_at = CURRENT_TIMESTAMP
        """, (
            u["email"],
            json.dumps(u["keywords"], ensure_ascii=False),
            json.dumps(u["recipients"], ensure_ascii=False),
            unit_id,
            json.dumps(u["rss"], ensure_ascii=False),
        ))
        c.execute("SELECT display_name FROM units WHERE id=?", (unit_id,))
        unit_display = c.fetchone()[0]
        print(f"   ✅ {u['email']} → {unit_display}")

    # 관리자 계정 (unit 없음)
    for admin_email in ["ironage@tta.or.kr", "local@tta.or.kr"]:
        c.execute("""
            INSERT INTO user_settings (user_email, unit_id)
            VALUES (?, NULL)
            ON CONFLICT(user_email) DO NOTHING
        """, (admin_email,))
        print(f"   👑 {admin_email} → 관리자 (unit 미배정)")

    conn.commit()
    conn.close()

    # ── 5. 결과 요약 ─────────────────────────────────────────────────────────
    print("\n" + "="*60)
    print("✅ 테스트 환경 셋업 완료!")
    print("="*60)
    print()
    print("로컬에서 테스트하는 방법:")
    print()
    print("  1. 앱 실행:")
    print("     streamlit run main_app.py")
    print()
    print("  2. 사이드바 하단 '🧪 테스트 유저 전환' 에서 이메일 선택:")
    print("     ironage@tta.or.kr   → 관리자 (전체 설정 접근)")
    print("     planning@tta.or.kr  → 표준기획단")
    print("     innovation@tta.or.kr → 표준혁신단")
    print("     ai@tta.or.kr        → AI융합표준단")
    print("     radio@tta.or.kr     → 전파네트워크표준단")
    print()
    print("  ⚠️  테스트 유저 전환은 로컬 모드(_auth_enabled=False)에서만 표시됩니다.")
    print()


if __name__ == "__main__":
    run_setup()
