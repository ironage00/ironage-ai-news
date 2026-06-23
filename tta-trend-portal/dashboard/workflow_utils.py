from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from db import is_postgres
from artifact_utils import table_exists


ACTION_COLUMNS = ["관련 기사", "담당 단", "검토 상태", "조치 메모", "updated_at"]
STATUS_OPTIONS = ["미검토", "검토중", "조치필요", "조치완료", "보류"]


def portal_root() -> Path:
    return Path(__file__).resolve().parents[1]


def issue_actions_path() -> Path:
    return portal_root() / "data" / "issue_actions.csv"


def load_issue_actions() -> pd.DataFrame:
    path = issue_actions_path()
    if not path.exists():
        return pd.DataFrame(columns=ACTION_COLUMNS)
    df = pd.read_csv(path)
    for col in ACTION_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    return df[ACTION_COLUMNS]


def load_issue_actions_from_db(engine: Engine) -> pd.DataFrame:
    if not is_postgres(engine) or not table_exists(engine, "issue_actions"):
        return pd.DataFrame(columns=ACTION_COLUMNS)
    sql = """
        SELECT
            article_link AS "관련 기사",
            owner_unit AS "담당 단",
            review_status AS "검토 상태",
            action_memo AS "조치 메모",
            updated_at
        FROM issue_actions
        ORDER BY updated_at DESC
    """
    try:
        df = pd.read_sql(text(sql), engine)
    except Exception:
        return pd.DataFrame(columns=ACTION_COLUMNS)
    for col in ACTION_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    return df[ACTION_COLUMNS]


def load_issue_actions_for_engine(engine: Engine) -> tuple[pd.DataFrame, str]:
    db_actions = load_issue_actions_from_db(engine)
    if not db_actions.empty:
        return db_actions, "database"
    csv_actions = load_issue_actions()
    return csv_actions, str(issue_actions_path())


def merge_issue_actions(board: pd.DataFrame, engine: Engine) -> tuple[pd.DataFrame, str]:
    if board.empty:
        return board, "empty"
    actions, source = load_issue_actions_for_engine(engine)
    merged = board.copy()
    if not actions.empty:
        merged = merged.merge(actions, on="관련 기사", how="left", suffixes=("", "_saved"))
        for col in ["담당 단", "검토 상태", "조치 메모"]:
            saved = f"{col}_saved"
            if saved in merged.columns:
                merged[col] = merged[saved].where(merged[saved].astype(str).str.strip() != "", merged.get(col, ""))
                merged = merged.drop(columns=[saved])
        if "updated_at_saved" in merged.columns:
            merged["updated_at"] = merged["updated_at_saved"]
            merged = merged.drop(columns=["updated_at_saved"])
    for col in ACTION_COLUMNS:
        if col not in merged.columns:
            merged[col] = ""
    merged["검토 상태"] = merged["검토 상태"].replace("", "미검토").fillna("미검토")
    merged["담당 단"] = merged["담당 단"].replace("", "공통").fillna("공통")
    return merged, source


def normalize_issue_actions(edited: pd.DataFrame) -> pd.DataFrame:
    actions = edited.copy()
    for col in ACTION_COLUMNS:
        if col not in actions.columns:
            actions[col] = ""
    actions = actions[ACTION_COLUMNS]
    actions["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    actions = actions.dropna(subset=["관련 기사"])
    actions = actions[actions["관련 기사"].astype(str).str.strip() != ""]
    actions = actions.drop_duplicates(subset=["관련 기사"], keep="last")
    return actions


def save_issue_actions_to_csv(actions: pd.DataFrame) -> Path:
    path = issue_actions_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    actions.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def save_issue_actions_to_db(engine: Engine, actions: pd.DataFrame, updated_by: str = "") -> bool:
    if not is_postgres(engine) or not table_exists(engine, "issue_actions"):
        return False
    sql = text(
        """
        INSERT INTO issue_actions (
            article_link,
            owner_unit,
            review_status,
            action_memo,
            updated_by,
            updated_at
        )
        VALUES (
            :article_link,
            :owner_unit,
            :review_status,
            :action_memo,
            :updated_by,
            NOW()
        )
        ON CONFLICT (article_link) DO UPDATE SET
            owner_unit = EXCLUDED.owner_unit,
            review_status = EXCLUDED.review_status,
            action_memo = EXCLUDED.action_memo,
            updated_by = EXCLUDED.updated_by,
            updated_at = NOW()
        """
    )
    rows = [
        {
            "article_link": row["관련 기사"],
            "owner_unit": row["담당 단"],
            "review_status": row["검토 상태"],
            "action_memo": row["조치 메모"],
            "updated_by": updated_by,
        }
        for _, row in actions.iterrows()
    ]
    if not rows:
        return True
    try:
        with engine.begin() as conn:
            conn.execute(sql, rows)
        return True
    except Exception:
        return False


def save_issue_actions(engine: Engine, edited: pd.DataFrame, updated_by: str = "") -> tuple[str, str]:
    actions = normalize_issue_actions(edited)
    csv_path = save_issue_actions_to_csv(actions)
    if save_issue_actions_to_db(engine, actions, updated_by=updated_by):
        return "database", "Supabase issue_actions and local CSV updated"
    return "csv", str(csv_path)
