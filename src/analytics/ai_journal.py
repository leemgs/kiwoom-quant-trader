import re
import logging

# google-generativeai 패키지 미설치 시에도 대시보드가 죽지 않도록 임포트를 방어한다.
try:
    import google.generativeai as genai
    _IMPORT_ERROR = None
except Exception as e:  # noqa: BLE001
    genai = None
    _IMPORT_ERROR = e


def _classify_error(msg: str):
    """Gemini/네트워크 예외 메시지에서 사람이 이해하기 쉬운 원인 힌트를 추출."""
    low = (msg or "").lower()
    if "api_key" in low or "api key" in low or ("invalid" in low and "key" in low) or "api_key_invalid" in low:
        return "API 키가 유효하지 않습니다 (GEMINI_API_KEY 값이 잘못됨)"
    if "permission" in low or "denied" in low or "403" in low:
        return "권한 거부 (키에 Gemini API 사용 권한/결제 설정이 없음)"
    if "quota" in low or "exhaust" in low or "429" in low or "rate limit" in low or "resource" in low:
        return "할당량(quota) 초과 또는 요청 rate limit 도달 (무료 티어 소진 가능)"
    if "not found" in low or "404" in low or "is not found" in low or "unsupported" in low:
        return "요청한 모델을 사용할 수 없음 (API 버전/모델명 불일치)"
    if "timeout" in low or "timed out" in low or "connection" in low or "network" in low or "dns" in low or "getaddrinfo" in low:
        return "네트워크 오류 (연결 실패/타임아웃)"
    return None


class AITradingJournal:
    # AI 복기에 필요한 최소 거래 건수
    MIN_TRADES = 1

    # 선호 순서: 최신·고품질(pro) → 하위·안정(flash/lite, 무료 쿼터 여유) 순으로 시도.
    # 실제 사용 가능 여부는 list_models()로 검증하므로, 여기 없는 모델이 있어도 무방하다.
    PREFERRED = [
        "gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.5-flash-lite",
        "gemini-2.0-pro", "gemini-2.0-flash", "gemini-2.0-flash-lite",
        "gemini-1.5-pro", "gemini-1.5-flash", "gemini-1.5-flash-8b",
        "gemini-pro-latest", "gemini-flash-latest",
    ]

    def __init__(self, api_key):
        self.api_key = (api_key or "").strip()
        self.candidates = []       # 시도할 모델명 목록(선호 순)
        self.init_error = None     # 초기화 실패 시 사람이 읽을 수 있는 사유
        self.last_used_model = None

        if genai is None:
            self.init_error = (
                f"google-generativeai 패키지가 설치되지 않았습니다 "
                f"(pip install google-generativeai). 상세: {_IMPORT_ERROR}"
            )
        elif not self.api_key:
            self.init_error = "GEMINI_API_KEY가 설정되지 않았습니다 (.env 파일에 키를 추가하세요)"
        else:
            try:
                genai.configure(api_key=self.api_key)
            except Exception as e:  # noqa: BLE001
                self.init_error = f"Gemini 초기화(configure) 실패: {type(e).__name__}: {e}"

            if self.init_error is None:
                # ⚠️ 쿼터 절약: init 단계에서 generate_content 테스트 호출을 하지 않는다.
                #    (과거에는 모델마다 test 호출을 해 무료 쿼터를 소진시켰다.)
                #    대신 list_models()로 사용 가능한 모델만 선호 순으로 확보한다.
                self.candidates = self._discover_models()
                if not self.candidates:
                    self.init_error = (
                        "generateContent를 지원하는 Gemini 모델을 찾지 못했습니다 "
                        "(list_models 접근 실패 또는 사용 가능 모델 없음)"
                    )

        self.enabled = bool(self.candidates)

    @staticmethod
    def _version_key(name: str):
        """모델명에서 버전(예: 2.5)을 추출하여 정렬 키로 사용. 없으면 (0,0)."""
        m = re.search(r"(\d+)\.(\d+)", name)
        return (int(m.group(1)), int(m.group(2))) if m else (0, 0)

    def _discover_models(self):
        """list_models()로 generateContent 지원 모델을 조회하고 선호 순으로 정렬.

        - 404(존재하지 않는 모델) 회피: 실제 존재하는 모델만 후보로 삼는다.
        - 선호 목록(PREFERRED)에 있는 모델을 우선 배치(최신·고품질 순).
        - 선호 목록에 없지만 사용 가능한 gemini 모델은 버전 내림차순으로 뒤에 덧붙인다.
        - list_models 자체가 실패하면 선호 목록을 그대로 반환(생성 시 404는 폴백으로 처리).
        """
        try:
            available = []
            for m in genai.list_models():
                methods = getattr(m, "supported_generation_methods", []) or []
                if "generateContent" in methods:
                    available.append(m.name.split("/")[-1])  # 'models/gemini-2.5-flash' -> 'gemini-2.5-flash'
        except Exception as e:  # noqa: BLE001
            logging.warning(f"Gemini list_models 실패 → 선호 목록으로 대체 시도: {e}")
            return list(self.PREFERRED)

        available_set = set(available)
        ordered = [n for n in self.PREFERRED if n in available_set]
        # 선호 목록에 없지만 사용 가능한 gemini 모델을 버전 내림차순으로 추가 (실험/신규 모델 대응)
        extras = sorted(
            (n for n in available if n.startswith("gemini") and n not in ordered),
            key=self._version_key,
            reverse=True,
        )
        ordered.extend(extras)
        logging.info(f"Gemini 사용 가능 모델(시도 순): {ordered}")
        return ordered

    def generate_review(self, trade_df, macro_status):
        """최근 거래 내역과 거시 지표를 분석하여 복기 리포트 생성.

        최신·고품질 모델부터 시도하고, 실패(429 쿼터/404 등) 시 하위 모델로 자동
        폴백한다. 실패 시 원인을 특정할 수 있는 구체적 메시지를 반환한다.
        (앞에 '❌'/'⚠️'가 붙으면 오류/경고, 그 외에는 정상 결과)
        """
        # ── 1. 초기화 단계 실패 원인 우선 보고 ──────────────────────────────
        if not self.enabled:
            return f"❌ AI 분석을 시작할 수 없습니다.\n원인: {self.init_error}"

        # ── 2. 분석용 데이터 부족 (정확한 건수 명시) ────────────────────────
        n_trades = 0 if trade_df is None else len(trade_df)
        if n_trades < self.MIN_TRADES:
            return (
                f"❌ 분석용 거래 데이터가 부족합니다. "
                f"현재 {n_trades}건 / 최소 {self.MIN_TRADES}건 필요. "
                f"(시스템이 매매를 시작해 거래 기록이 쌓이면 분석이 가능합니다.)"
            )

        # 최근 5건의 거래 요약
        recent_trades = trade_df.sort_values('timestamp', ascending=False).head(5)
        trade_summary = recent_trades[['code', 'type', 'profit']].to_string()
        prompt = (
            f"주식 투자 전문가로서 아래의 최근 매매 내역과 시장 상황을 분석해서 '한 줄 복기'와 '내일의 조언'을 해줘.\n\n"
            f"[최근 매매 내역]\n{trade_summary}\n\n"
            f"[시장 상황 (미국지수 등락)]\n{macro_status}\n\n"
            f"답변은 아주 친절하고 전문적인 말투로 해줘."
        )

        # ── 3. 최신→하위 모델 순차 시도 (품질 우선 + 실패 시 안정적 폴백) ───
        attempts = []
        for name in self.candidates:
            try:
                model = genai.GenerativeModel(name)
                response = model.generate_content(prompt)
                text = getattr(response, "text", None)
                if not text:
                    attempts.append(f"{name} → 빈 응답(안전 필터 차단 가능)")
                    continue
                self.last_used_model = name
                logging.info(f"AI 복기 생성 성공 (모델: {name})")
                return f"🧠 **AI 복기** _(모델: {name})_\n\n{text}"
            except Exception as e:  # noqa: BLE001
                attempts.append(f"{name} → {type(e).__name__}: {str(e).splitlines()[0][:140]}")
                logging.warning(f"모델 {name} 생성 실패, 다음 후보로 폴백: {e}")
                continue

        # ── 4. 모든 후보 실패 → 원인 힌트 + 상세 ────────────────────────────
        joined = " ".join(attempts)
        hint = _classify_error(joined)
        hint_str = f"\n원인 추정: {hint}" if hint else ""
        detail = "\n".join(f" - {a}" for a in attempts)
        return (
            f"❌ 사용 가능한 모든 Gemini 모델 시도에 실패했습니다.{hint_str}\n"
            f"시도한 모델({len(attempts)}개):\n{detail}"
        )
