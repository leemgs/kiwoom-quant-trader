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
        return "할당량(quota) 초과 또는 요청 rate limit 도달"
    if "not found" in low or "404" in low or "is not found" in low or "unsupported" in low:
        return "요청한 모델을 사용할 수 없음 (API 버전/모델명 불일치)"
    if "timeout" in low or "timed out" in low or "connection" in low or "network" in low or "dns" in low or "getaddrinfo" in low:
        return "네트워크 오류 (연결 실패/타임아웃)"
    return None


class AITradingJournal:
    # AI 복기에 필요한 최소 거래 건수
    MIN_TRADES = 1

    def __init__(self, api_key):
        self.api_key = (api_key or "").strip()
        self.model = None
        self.model_name = None
        self.init_error = None   # 초기화 실패 시 사람이 읽을 수 있는 사유

        # 1) 패키지 미설치
        if genai is None:
            self.init_error = (
                f"google-generativeai 패키지가 설치되지 않았습니다 "
                f"(pip install google-generativeai). 상세: {_IMPORT_ERROR}"
            )
        # 2) API 키 미설정
        elif not self.api_key:
            self.init_error = "GEMINI_API_KEY가 설정되지 않았습니다 (.env 파일에 키를 추가하세요)"
        else:
            # 3) 키가 있으면 모델 초기화 시도 (여러 모델을 순차 시도)
            try:
                genai.configure(api_key=self.api_key)
            except Exception as e:  # noqa: BLE001
                self.init_error = f"Gemini 초기화(configure) 실패: {type(e).__name__}: {e}"

            if self.init_error is None:
                attempts = []
                for model_name in ['gemini-2.0-flash', 'gemini-1.5-flash', 'gemini-pro', 'gemini-1.0-pro']:
                    try:
                        m = genai.GenerativeModel(model_name)
                        m.generate_content("test")
                        self.model = m
                        self.model_name = model_name
                        logging.info(f"Gemini AI 모델 초기화 성공: {model_name}")
                        break
                    except Exception as e:  # noqa: BLE001
                        attempts.append(f"{model_name} → {type(e).__name__}: {e}")
                        logging.warning(f"모델 {model_name} 사용 불가: {e}")

                if self.model is None:
                    # 마지막 시도의 예외에서 원인 힌트 추출
                    last_msg = attempts[-1] if attempts else ""
                    hint = _classify_error(last_msg)
                    detail = " | ".join(attempts) if attempts else "시도 기록 없음"
                    self.init_error = (
                        (f"{hint}. " if hint else "")
                        + f"사용 가능한 Gemini 모델을 찾지 못했습니다. 상세: {detail}"
                    )

        self.enabled = self.model is not None

    def generate_review(self, trade_df, macro_status):
        """최근 거래 내역과 거시 지표를 분석하여 복기 리포트 생성.

        실패 시 원인을 특정할 수 있는 구체적 메시지를 반환한다.
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

        # ── 3. 실제 생성 호출 (모델명 및 구체적 오류 보고) ──────────────────
        try:
            response = self.model.generate_content(prompt)
            text = getattr(response, 'text', None)
            if not text:
                return (
                    "⚠️ Gemini가 빈 응답을 반환했습니다 "
                    "(안전 필터 차단 또는 응답 없음). 잠시 후 다시 시도해 주세요."
                )
            return text
        except Exception as e:  # noqa: BLE001
            logging.error(f"AI 복기 생성 에러: {str(e)}")
            hint = _classify_error(str(e))
            hint_str = f"\n원인 추정: {hint}" if hint else ""
            return (
                f"❌ AI 복기 생성 중 오류가 발생했습니다 (모델: {self.model_name}).\n"
                f"{type(e).__name__}: {e}{hint_str}"
            )
