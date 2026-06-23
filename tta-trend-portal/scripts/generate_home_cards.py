#!/usr/bin/env python3
"""
Generate tta-trend-portal/embeds/home-cards.html from live Supabase data.
Run daily via GitHub Actions after daily_sync.py completes.

Required env:
  DATABASE_URL      Supabase PostgreSQL connection string
Optional env:
  STREAMLIT_URL     Deployed Streamlit app URL (default: https://tta-radar.streamlit.app)
  WEEKLY_DOC_URL    Latest weekly brief Google Docs URL
  EXCEL_URL         Evidence table Google Sheets URL
"""
from __future__ import annotations

import json
import os
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg2

# ── Config ────────────────────────────────────────────────────────────────────
DATABASE_URL = os.environ["DATABASE_URL"]
STREAMLIT_URL = os.environ.get("STREAMLIT_URL", "https://tta-radar.streamlit.app")
WEEKLY_DOC_URL = os.environ.get(
    "WEEKLY_DOC_URL",
    "https://docs.google.com/document/d/1315EoXpg5fqime4_Ib_Q_bq-nEOSfHRlIoey6XRUA_8/edit",
)
EXCEL_URL = os.environ.get(
    "EXCEL_URL",
    "https://docs.google.com/spreadsheets/d/1sEgS1W0fjnTHnjN1c37QvoCa3wrpMQIn/edit",
)

OUTPUT_PATH = Path(__file__).parent.parent / "embeds" / "home-cards.html"


# ── DB helpers ────────────────────────────────────────────────────────────────
def get_stats(cur) -> dict:
    cur.execute("SELECT COUNT(*) FROM news_articles")
    articles = cur.fetchone()[0]
    cur.execute(
        "SELECT COUNT(*) FROM news_articles WHERE is_analyzed = TRUE"
    )
    analyzed = cur.fetchone()[0]
    try:
        cur.execute("SELECT COUNT(*) FROM article_embeddings")
        embeddings = cur.fetchone()[0]
    except Exception:
        embeddings = 0
    return {"articles": articles, "analyzed": analyzed, "embeddings": embeddings}


def _parse_keywords(kw_text: str) -> list[str]:
    if not kw_text:
        return []
    try:
        items = json.loads(kw_text)
        if isinstance(items, list):
            return [k.strip() for k in items if isinstance(k, str) and k.strip()]
    except Exception:
        pass
    return [k.strip() for k in re.split(r"[,，\n]+", kw_text) if 1 < len(k.strip()) <= 30]


def get_trending_keywords(cur, recent_days: int = 7, top_n: int = 8) -> list[dict]:
    now = datetime.now(timezone.utc)
    recent_start = now - timedelta(days=recent_days)
    baseline_start = now - timedelta(days=recent_days * 2)

    def fetch(start, end) -> Counter:
        cur.execute(
            """
            SELECT extracted_keywords FROM news_articles
            WHERE collected_at >= %s AND collected_at < %s
              AND extracted_keywords IS NOT NULL AND extracted_keywords <> ''
            """,
            (start, end),
        )
        c: Counter = Counter()
        for (kw_text,) in cur.fetchall():
            c.update(_parse_keywords(kw_text))
        return c

    recent = fetch(recent_start, now)
    baseline = fetch(baseline_start, recent_start)

    signals: list[dict] = []
    for kw, count in recent.most_common(40):
        base = baseline.get(kw, 0)
        if base == 0:
            change_type, label = "new", "신규 등장"
        else:
            pct = round((count - base) / max(base, 1) * 100)
            if pct >= 30:
                change_type, label = "hot", f"+{pct}%"
            elif pct >= 10:
                change_type, label = "up", f"+{pct}%"
            elif pct <= -20:
                change_type, label = "down", f"{pct}%"
            else:
                change_type, label = "stable", "유지"
        signals.append({"kw": kw, "count": count, "change_type": change_type, "label": label})
        if len(signals) >= top_n:
            break
    return signals


def get_action_board_counts(cur) -> dict:
    try:
        cur.execute(
            "SELECT status, COUNT(*) FROM issue_actions WHERE status IS NOT NULL GROUP BY status"
        )
        counts = {row[0]: row[1] for row in cur.fetchall()}
        return {
            "urgent":    counts.get("긴급", 0),
            "in_review": counts.get("검토중", 0),
            "done":      counts.get("완료", 0),
        }
    except Exception:
        return {"urgent": 0, "in_review": 0, "done": 0}


# ── HTML builders ─────────────────────────────────────────────────────────────
_CHIP_STYLE: dict[str, tuple[str, str]] = {
    "hot":    ("background:#1a1000;color:#fbbf24;", "🔥"),
    "new":    ("background:#1e1b4b;color:#a5b4fc;", "★"),
    "up":     ("background:#14532d;color:#86efac;", "↑"),
    "down":   ("background:#3f1f1f;color:#fca5a5;", "↓"),
    "stable": ("background:#1e293b;color:#94a3b8;", "→"),
}


def _signal_chip(s: dict) -> str:
    style, icon = _CHIP_STYLE.get(s["change_type"], _CHIP_STYLE["stable"])
    return (
        f'<span style="display:inline-flex;align-items:center;gap:5px;'
        f'padding:6px 12px;border-radius:8px;font-size:12px;font-weight:700;{style}">'
        f'{icon} {s["kw"]} {s["label"]}</span>'
    )


def _action_chip(label: str, count: int, bg: str, color: str) -> str:
    if count == 0:
        return ""
    return (
        f'<span style="padding:4px 10px;border-radius:6px;font-size:11px;font-weight:700;'
        f'background:{bg};color:{color};">{label} {count}건</span>'
    )


def _query_chip(kw: str) -> str:
    return (
        f'<span style="padding:7px 10px;border-radius:999px;background:#1e293b;'
        f'color:#dbeafe;font-size:12px;">{kw}</span>'
    )


def render_html(stats: dict, signals: list[dict], board: dict, now: datetime) -> str:
    week_num   = now.isocalendar()[1]
    week_label = f"{now.year}년 {week_num}주차"
    date_label = now.strftime("%Y.%m.%d")
    gen_label  = now.strftime("%Y-%m-%d %H:%M KST")

    # Signal strip (up to 6 chips)
    signal_html = "\n          ".join(_signal_chip(s) for s in signals[:6])
    if not signal_html:
        signal_html = '<span style="color:#64748b;font-size:12px;">데이터 수집 중 — 내일 갱신됩니다.</span>'

    # Action board chips
    chips = [
        _action_chip("긴급",   board["urgent"],    "#fff7ed", "#c2410c"),
        _action_chip("검토중", board["in_review"], "#fefce8", "#a16207"),
        _action_chip("완료",   board["done"],      "#f0fdf4", "#15803d"),
    ]
    board_chips = "\n          ".join(c for c in chips if c)
    if not board_chips:
        board_chips = '<span style="font-size:11px;color:#94a3b8;">대시보드에서 확인</span>'

    # Query chips: use trending keywords or defaults
    top_kws = [s["kw"] for s in signals[:6]] or [
        "AI-RAN 표준화", "NTN 위성통신", "6G 국제표준", "양자통신", "오픈랜 정책", "B5G 주파수"
    ]
    query_chips = "\n          ".join(_query_chip(k) for k in top_kws)

    return f"""<!--
  Auto-generated by generate_home_cards.py on {gen_label}
  Google Sites > Insert > Embed > Embed code
-->
<section style="font-family:Inter,'Segoe UI',Arial,sans-serif;color:#0f172a;background:#f6f8fb;border:1px solid #d8e0ea;border-radius:18px;overflow:hidden;">

  <!-- ── Hero ── -->
  <div style="background:linear-gradient(135deg,#071427 0%,#0e2b52 52%,#155e75 100%);color:white;padding:32px 32px 26px 32px;">
    <div style="display:inline-block;padding:5px 11px;border:1px solid rgba(255,255,255,.26);border-radius:999px;color:#b9e6ff;font-size:11px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;margin-bottom:13px;">TTA Intelligence Radar · {week_label}</div>
    <h1 style="margin:0 0 10px 0;font-size:36px;line-height:1.12;font-weight:900;">오늘의 ICT 표준화 신호를 한 화면에서 읽습니다</h1>
    <p style="margin:0 0 22px 0;max-width:780px;color:#d7e6f5;font-size:15px;line-height:1.7;">뉴스 원장, AI 분석 결과, 표준화 대응 후보, 관계 맵, 주간 보고서를 연결해 TTA 직원이 바로 판단할 수 있는 내부 인텔리전스 포털입니다.</p>
    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;">
      <div style="background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.18);border-radius:13px;padding:13px 15px;">
        <div style="font-size:11px;color:#b9e6ff;font-weight:700;text-transform:uppercase;letter-spacing:.06em;">전체 기사</div>
        <div style="font-size:24px;font-weight:900;margin-top:4px;">{stats['articles']:,}</div>
        <div style="font-size:11px;color:#c9d8e8;margin-top:4px;">누적 수집 원장</div>
      </div>
      <div style="background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.18);border-radius:13px;padding:13px 15px;">
        <div style="font-size:11px;color:#b9e6ff;font-weight:700;text-transform:uppercase;letter-spacing:.06em;">AI 분석</div>
        <div style="font-size:24px;font-weight:900;margin-top:4px;">{stats['analyzed']:,}</div>
        <div style="font-size:11px;color:#c9d8e8;margin-top:4px;">GPT 분석 완료</div>
      </div>
      <div style="background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.18);border-radius:13px;padding:13px 15px;">
        <div style="font-size:11px;color:#b9e6ff;font-weight:700;text-transform:uppercase;letter-spacing:.06em;">RAG 임베딩</div>
        <div style="font-size:24px;font-weight:900;margin-top:4px;">{stats['embeddings']:,}</div>
        <div style="font-size:11px;color:#c9d8e8;margin-top:4px;">의미 검색 가능</div>
      </div>
      <div style="background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.18);border-radius:13px;padding:13px 15px;">
        <div style="font-size:11px;color:#b9e6ff;font-weight:700;text-transform:uppercase;letter-spacing:.06em;">최신 보고서</div>
        <div style="font-size:18px;font-weight:900;margin-top:4px;">{week_label}</div>
        <div style="font-size:11px;color:#c9d8e8;margin-top:4px;">{date_label} 발행</div>
      </div>
    </div>
  </div>

  <!-- ── 이번 주 핵심 신호 ── -->
  <div style="background:#0c1523;padding:13px 24px;display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
    <span style="font-size:10px;color:#64748b;font-weight:700;text-transform:uppercase;letter-spacing:.07em;white-space:nowrap;margin-right:4px;">이번 주 핵심 신호</span>
    {signal_html}
  </div>

  <!-- ── Body ── -->
  <div style="padding:20px 22px 24px 22px;">

    <!-- Action cards 2×2 -->
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px;margin-bottom:14px;">

      <a href="{STREAMLIT_URL}" target="_blank" style="display:block;text-decoration:none;color:#0f172a;background:white;border:1px solid #dbe3ee;border-radius:14px;padding:17px 18px;box-shadow:0 10px 24px rgba(15,23,42,.05);">
        <div style="font-size:11px;color:#0369a1;font-weight:900;text-transform:uppercase;letter-spacing:.07em;">Live Radar</div>
        <div style="font-size:20px;font-weight:900;margin:7px 0 7px 0;">오늘의 레이더</div>
        <div style="font-size:13px;line-height:1.55;color:#475569;margin-bottom:10px;">급등 키워드, 신규 엔티티, 단별 추천 이슈를 AI가 자동 분류합니다.</div>
        <div style="display:flex;flex-wrap:wrap;gap:5px;">
          {" ".join(f'<span style="padding:3px 9px;border-radius:6px;font-size:11px;font-weight:700;background:#eff6ff;color:#1d4ed8;">{s["kw"]}</span>' for s in signals[:3])}
        </div>
      </a>

      <a href="{STREAMLIT_URL}" target="_blank" style="display:block;text-decoration:none;color:#0f172a;background:white;border:1px solid #dbe3ee;border-radius:14px;padding:17px 18px;box-shadow:0 10px 24px rgba(15,23,42,.05);">
        <div style="font-size:11px;color:#7c2d12;font-weight:900;text-transform:uppercase;letter-spacing:.07em;">Action Board</div>
        <div style="font-size:20px;font-weight:900;margin:7px 0 7px 0;">표준화 대응 보드</div>
        <div style="font-size:13px;line-height:1.55;color:#475569;margin-bottom:10px;">영향도·긴급도 기반 후보를 검토하고 조치 메모를 기록합니다.</div>
        <div style="display:flex;flex-wrap:wrap;gap:5px;">
          {board_chips}
        </div>
      </a>

      <a href="{WEEKLY_DOC_URL}" target="_blank" style="display:block;text-decoration:none;color:#0f172a;background:white;border:1px solid #dbe3ee;border-radius:14px;padding:17px 18px;box-shadow:0 10px 24px rgba(15,23,42,.05);">
        <div style="font-size:11px;color:#047857;font-weight:900;text-transform:uppercase;letter-spacing:.07em;">Weekly Brief</div>
        <div style="font-size:20px;font-weight:900;margin:7px 0 7px 0;">최신 주간 보고서</div>
        <div style="font-size:13px;line-height:1.55;color:#475569;margin-bottom:10px;">{week_label} ICT 동향 보고서를 엽니다.</div>
        <div style="display:flex;flex-wrap:wrap;gap:5px;">
          <span style="padding:3px 9px;border-radius:6px;font-size:11px;font-weight:700;background:#f0fdf4;color:#15803d;">Google Docs</span>
          <span style="padding:3px 9px;border-radius:6px;font-size:11px;font-weight:700;background:#f0fdf4;color:#15803d;">{date_label}</span>
        </div>
      </a>

      <a href="{EXCEL_URL}" target="_blank" style="display:block;text-decoration:none;color:#0f172a;background:white;border:1px solid #dbe3ee;border-radius:14px;padding:17px 18px;box-shadow:0 10px 24px rgba(15,23,42,.05);">
        <div style="font-size:11px;color:#6d28d9;font-weight:900;text-transform:uppercase;letter-spacing:.07em;">Evidence Table</div>
        <div style="font-size:20px;font-weight:900;margin:7px 0 7px 0;">뉴스 분석 Excel</div>
        <div style="font-size:13px;line-height:1.55;color:#475569;margin-bottom:10px;">기사 원자료, GPT 분석 결과, 키워드 추출 테이블을 확인합니다.</div>
        <div style="display:flex;flex-wrap:wrap;gap:5px;">
          <span style="padding:3px 9px;border-radius:6px;font-size:11px;font-weight:700;background:#faf5ff;color:#7e22ce;">Google Sheets</span>
          <span style="padding:3px 9px;border-radius:6px;font-size:11px;font-weight:700;background:#faf5ff;color:#7e22ce;">{stats['analyzed']:,}행</span>
        </div>
      </a>

    </div>

    <!-- Bottom panels -->
    <div style="display:grid;grid-template-columns:1.2fr .8fr;gap:12px;">
      <div style="background:#ffffff;border:1px solid #dbe3ee;border-radius:14px;padding:17px 18px;">
        <div style="font-size:14px;font-weight:900;margin-bottom:12px;">직원이 바로 쓰는 판단 흐름</div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
          <div style="border-left:4px solid #0284c7;border-radius:0;padding-left:10px;color:#475569;font-size:13px;line-height:1.5;"><strong style="color:#0f172a;">1. 감지</strong><br>오늘 급등한 기술과 엔티티 확인</div>
          <div style="border-left:4px solid #b45309;border-radius:0;padding-left:10px;color:#475569;font-size:13px;line-height:1.5;"><strong style="color:#0f172a;">2. 선별</strong><br>영향도·긴급도 기준 후보 분류</div>
          <div style="border-left:4px solid #047857;border-radius:0;padding-left:10px;color:#475569;font-size:13px;line-height:1.5;"><strong style="color:#0f172a;">3. 근거</strong><br>RAG 검색으로 관련 기사 확인</div>
          <div style="border-left:4px solid #6d28d9;border-radius:0;padding-left:10px;color:#475569;font-size:13px;line-height:1.5;"><strong style="color:#0f172a;">4. 공유</strong><br>보고서와 조치 메모로 확산</div>
        </div>
      </div>
      <div style="background:#0f172a;color:white;border-radius:14px;padding:17px 18px;">
        <div style="font-size:12px;color:#93c5fd;font-weight:800;text-transform:uppercase;letter-spacing:.06em;margin-bottom:10px;">이번 주 추천 검색어</div>
        <div style="display:flex;flex-wrap:wrap;gap:7px;">
          {query_chips}
        </div>
      </div>
    </div>

    <div style="margin-top:12px;text-align:right;font-size:11px;color:#94a3b8;">자동 생성 · {gen_label} · Supabase 기준</div>
  </div>
</section>
"""


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    now = datetime.now(timezone.utc).astimezone()

    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            stats   = get_stats(cur)
            signals = get_trending_keywords(cur)
            board   = get_action_board_counts(cur)
    finally:
        conn.close()

    html = render_html(stats, signals, board, now)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(html, encoding="utf-8")

    print(f"✅ home-cards.html generated → {OUTPUT_PATH}")
    print(f"   articles={stats['articles']:,}  analyzed={stats['analyzed']:,}  embeddings={stats['embeddings']:,}")
    print(f"   signals ({len(signals)}): {[s['kw'] for s in signals]}")


if __name__ == "__main__":
    main()
