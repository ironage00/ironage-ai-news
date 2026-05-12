"""
IRONAGE AI Analytics System v5.0
4개 AI 제공사 모델 연결 상태 테스트 스크립트

실행 (기본 - 제공사별 대표 모델):
  python test_ai_models.py

실행 (전체 탐색 - 운영 가능한 모델 목록 탐색):
  python test_ai_models.py --discover

실행 (특정 제공사만):
  python test_ai_models.py --only openai
  python test_ai_models.py --only claude
  python test_ai_models.py --only gemini
  python test_ai_models.py --only perplexity
"""

import sys
import json
import time
import datetime
import argparse
from pathlib import Path

# Windows 터미널 UTF-8 강제 설정
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ==============================================================================
# --- 모델 목록 ---
# ==============================================================================

# 기본 테스트용 대표 모델 (빠른 검증)
DEFAULT_MODELS = {
    "openai":     "gpt-4o",
    "claude":     "claude-sonnet-4-6",
    "gemini":     "gemini-2.5-flash",   # 2.0은 신규 사용자 제한 → 2.5로 변경
    "perplexity": "sonar-pro",
}

# 탐색 모드 - 제공사별 후보 모델 전체 목록 (2026-04 기준)
DISCOVER_MODELS = {
    "openai": [
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4-turbo",
        "gpt-4",
        "gpt-3.5-turbo",
        "o1-mini",
        "o3-mini",
    ],
    "claude": [
        "claude-opus-4-7",
        "claude-sonnet-4-6",
        "claude-haiku-4-5-20251001",
        "claude-3-5-sonnet-20241022",
        "claude-3-5-haiku-20241022",
        "claude-3-opus-20240229",
    ],
    "gemini": [
        # thinking 모델 (MAX_TOKENS_GEMINI >= 200 필요)
        "gemini-2.5-flash",
        "gemini-2.5-pro",
        # flash 별칭
        "gemini-flash-latest",
        "gemini-pro-latest",
        # 구형 모델 (신규 사용자 제한으로 실패할 수 있음)
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
    ],
    "perplexity": [
        "sonar-pro",
        "sonar",
        "sonar-reasoning-pro",
        "sonar-reasoning",
        "sonar-deep-research",
    ],
}

# Gemini 2.5 thinking 모델은 내부 추론에 토큰을 대량 소비 → 1000 이상 필요
MAX_TOKENS_GEMINI = 1000  # gemini-2.5-flash/pro thinking 모델용
MAX_TOKENS_STD    = 80    # OpenAI / Claude / Perplexity

CONFIG_PATH = Path("data/config.json")
TEST_PROMPT = "5G 네트워크의 핵심 특징을 한 문장으로 설명해주세요."


# ==============================================================================
# --- 설정 로드 ---
# ==============================================================================

def load_config() -> dict:
    if not CONFIG_PATH.exists():
        print(f"[ERROR] {CONFIG_PATH} 파일이 없습니다. data/config.json을 확인하세요.")
        sys.exit(1)
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


# ==============================================================================
# --- 제공사별 호출 함수 ---
# ==============================================================================

def _call_openai(api_key: str, model: str) -> dict:
    import openai
    client = openai.OpenAI(api_key=api_key)
    t0 = time.time()
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": TEST_PROMPT}],
        max_tokens=MAX_TOKENS_STD,
    )
    return {
        "elapsed_s"    : round(time.time() - t0, 2),
        "input_tokens" : resp.usage.prompt_tokens,
        "output_tokens": resp.usage.completion_tokens,
        "response"     : resp.choices[0].message.content.strip()[:120],
    }


def _call_claude(api_key: str, model: str) -> dict:
    from anthropic import Anthropic
    client = Anthropic(api_key=api_key)
    t0 = time.time()
    resp = client.messages.create(
        model=model,
        max_tokens=MAX_TOKENS_STD,
        messages=[{"role": "user", "content": TEST_PROMPT}],
    )
    return {
        "elapsed_s"    : round(time.time() - t0, 2),
        "input_tokens" : resp.usage.input_tokens,
        "output_tokens": resp.usage.output_tokens,
        "response"     : resp.content[0].text.strip()[:120],
    }


def _call_gemini(api_key: str, model: str) -> dict:
    import google.generativeai as genai
    genai.configure(api_key=api_key)
    gm = genai.GenerativeModel(model)
    t0 = time.time()
    resp = gm.generate_content(
        TEST_PROMPT,
        generation_config={"max_output_tokens": MAX_TOKENS_GEMINI},
    )
    elapsed = round(time.time() - t0, 2)
    meta = getattr(resp, "usage_metadata", None)
    # thinking 모델은 candidates[0].content.parts 로 텍스트를 꺼내야 할 수 있음
    try:
        text = resp.text.strip()[:120]
    except (ValueError, IndexError):
        # 응답이 비어있거나 candidates 없음
        parts = []
        if resp.candidates:
            for p in resp.candidates[0].content.parts:
                if hasattr(p, "text"):
                    parts.append(p.text)
        text = " ".join(parts).strip()[:120] or "(응답 없음)"
    return {
        "elapsed_s"    : elapsed,
        "input_tokens" : getattr(meta, "prompt_token_count",     "-") if meta else "-",
        "output_tokens": getattr(meta, "candidates_token_count", "-") if meta else "-",
        "response"     : text,
    }


def _call_perplexity(api_key: str, model: str) -> dict:
    import openai
    import httpx
    # 기업 SSL 프록시 환경에서는 verify=False 필요
    http_client = httpx.Client(verify=False)
    client = openai.OpenAI(
        api_key=api_key,
        base_url="https://api.perplexity.ai",
        http_client=http_client,
    )
    t0 = time.time()
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": TEST_PROMPT}],
        max_tokens=MAX_TOKENS_STD,
    )
    usage = getattr(resp, "usage", None)
    return {
        "elapsed_s"    : round(time.time() - t0, 2),
        "input_tokens" : getattr(usage, "prompt_tokens",     "-") if usage else "-",
        "output_tokens": getattr(usage, "completion_tokens", "-") if usage else "-",
        "response"     : resp.choices[0].message.content.strip()[:120],
    }


PROVIDER_CALLERS = {
    "openai":     _call_openai,
    "claude":     _call_claude,
    "gemini":     _call_gemini,
    "perplexity": _call_perplexity,
}

PROVIDER_LABELS = {
    "openai":     "OpenAI",
    "claude":     "Claude (Anthropic)",
    "gemini":     "Gemini (Google)",
    "perplexity": "Perplexity",
}

IMPORT_HINTS = {
    "openai":     "pip install openai",
    "claude":     "pip install anthropic",
    "gemini":     "pip install google-generativeai",
    "perplexity": "pip install openai",
}


# ==============================================================================
# --- 오류 분류 ---
# ==============================================================================

def _classify_error(e: Exception) -> str:
    msg = str(e).lower()
    if any(k in msg for k in ["authentication", "api key", "unauthorized",
                               "invalid_api_key", "api_key_invalid", "permission"]):
        return f"API 키 인증 실패 | {str(e)[:80]}"
    if any(k in msg for k in ["rate", "quota", "too many"]):
        return f"API 한도 초과 | {str(e)[:80]}"
    if "certificate" in msg or "ssl" in msg or "cert" in msg:
        return "SSL 인증서 오류 (기업 프록시 환경) | " + str(e)[:60]
    if any(k in msg for k in ["timeout", "connection", "network", "unreachable", "connect"]):
        return f"네트워크/연결 오류 | {str(e)[:80]}"
    if "not found" in msg or "does not exist" in msg or "404" in msg:
        return f"모델 없음/접근 불가 | {str(e)[:80]}"
    if "no longer available" in msg:
        return f"모델 서비스 종료 | {str(e)[:80]}"
    if "list index out of range" in msg or "empty" in msg:
        return f"응답 없음 (토큰 부족 가능성) | {str(e)[:60]}"
    return f"{type(e).__name__}: {str(e)[:100]}"


# ==============================================================================
# --- 단일 모델 테스트 ---
# ==============================================================================

def test_model(provider: str, model: str, api_key: str) -> dict:
    base = {
        "provider"    : PROVIDER_LABELS[provider],
        "provider_key": provider,
        "model"       : model,
    }
    try:
        data = PROVIDER_CALLERS[provider](api_key, model)
        return {**base, "success": True, **data}
    except ImportError:
        return {**base, "success": False,
                "error": f"패키지 미설치 ({IMPORT_HINTS[provider]})"}
    except Exception as e:
        return {**base, "success": False, "error": _classify_error(e)}


# ==============================================================================
# --- 출력 ---
# ==============================================================================

def print_result(r: dict, idx: int):
    status = "OK  성공" if r["success"] else "NG  실패"
    print(f"\n  [{idx}] {r['provider']}  /  {r['model']}")
    print(f"       상태     : {status}")
    if r["success"]:
        print(f"       응답시간 : {r['elapsed_s']}s")
        print(f"       토큰     : 입력 {r['input_tokens']} / 출력 {r['output_tokens']}")
        print(f"       응답     : {r['response']}")
    else:
        print(f"       오류     : {r['error']}")
    print("       " + "-" * 58)


def print_summary(results: list, discover: bool):
    label = "전체 모델 탐색" if discover else "기본 모델 연결"
    print("\n" + "=" * 72)
    print(f"  최종 요약 -- {label}")
    print("=" * 72)
    print(f"  {'제공사':<22} {'모델':<32} {'결과':<8} {'응답시간'}")
    print("  " + "-" * 68)
    for r in results:
        status  = "OK 정상" if r["success"] else "NG 실패"
        elapsed = f"{r['elapsed_s']}s" if r.get("elapsed_s") else "-"
        print(f"  {r['provider']:<22} {r['model']:<32} {status:<8} {elapsed}")
    ok = sum(1 for r in results if r["success"])
    print("  " + "-" * 68)
    print(f"  총 {len(results)}개 모델 중 {ok}개 정상 운영")
    if ok < len(results):
        print(f"  >> {len(results) - ok}개 모델 점검 필요")

    if discover and ok > 0:
        print()
        print("  [운영 가능 모델 목록]")
        providers_seen: dict = {}
        for r in results:
            if r["success"]:
                pk = r["provider_key"]
                providers_seen.setdefault(pk, []).append(r["model"])
        for pk, models in providers_seen.items():
            print(f"    {PROVIDER_LABELS[pk]}: {', '.join(models)}")
    print("=" * 72)


# ==============================================================================
# --- 메인 ---
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(description="IRONAGE AI 모델 연결 테스트")
    parser.add_argument(
        "--discover", action="store_true",
        help="제공사별 다수 모델을 순차 검사해 운영 가능한 모델을 탐색"
    )
    parser.add_argument(
        "--only", choices=["openai", "claude", "gemini", "perplexity"],
        help="특정 제공사만 테스트"
    )
    args = parser.parse_args()

    mode_str = "전체 모델 탐색 (--discover)" if args.discover else "기본 모델 연결 테스트"
    print("=" * 72)
    print(f"  IRONAGE AI Analytics -- {mode_str}")
    print(f"  실행 시각 : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 72)

    cfg = load_config()
    api_keys = {
        "openai":     cfg.get("openai_api_key",     ""),
        "claude":     cfg.get("claude_api_key",     ""),
        "gemini":     cfg.get("gemini_api_key",     ""),
        "perplexity": cfg.get("perplexity_api_key", ""),
    }

    providers = ["openai", "claude", "gemini", "perplexity"]
    if args.only:
        providers = [args.only]

    tasks = []
    for p in providers:
        key = api_keys[p]
        if not key or key.startswith("YOUR_"):
            continue
        models = DISCOVER_MODELS[p] if args.discover else [DEFAULT_MODELS[p]]
        for m in models:
            tasks.append((p, m, key))

    if not tasks:
        print("\n  API 키가 설정된 제공사가 없습니다. data/config.json을 확인하세요.")
        return

    total = len(tasks)
    print(f"\n  테스트 프롬프트 : \"{TEST_PROMPT}\"")
    print(f"  검사 모델 수    : {total}개\n")

    results = []
    for i, (provider, model, api_key) in enumerate(tasks, 1):
        print(f"  [{i:02d}/{total:02d}] {PROVIDER_LABELS[provider]} / {model} ...", end=" ", flush=True)
        r = test_model(provider, model, api_key)
        print("OK" if r["success"] else "NG")
        results.append(r)

    print("\n" + "=" * 72)
    print("  상세 결과")
    print("=" * 72)
    for idx, r in enumerate(results, 1):
        print_result(r, idx)

    print_summary(results, args.discover)

    log_path = Path(f"data/logs/model_test_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(
            {"timestamp": datetime.datetime.now().isoformat(), "results": results},
            f, ensure_ascii=False, indent=2
        )
    print(f"\n  결과 저장 : {log_path}")


if __name__ == "__main__":
    main()
