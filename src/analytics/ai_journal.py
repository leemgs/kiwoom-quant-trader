import google.generativeai as genai
import logging
import pandas as pd

class AITradingJournal:
    def __init__(self, api_key):
        self.api_key = api_key
        if api_key:
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel('gemini-1.5-flash')
        self.enabled = True if api_key else False

    def generate_review(self, trade_df, macro_status):
        """최근 거래 내역과 거시 지표를 분석하여 복기 리포트 생성"""
        if not self.enabled or trade_df.empty:
            return "AI 분석을 위한 데이터가 부족하거나 API 키가 설정되지 않았습니다."

        # 최근 5건의 거래 요약
        recent_trades = trade_df.sort_values('timestamp', ascending=False).head(5)
        trade_summary = recent_trades[['code', 'type', 'profit']].to_string()
        
        prompt = (
            f"주식 투자 전문가로서 아래의 최근 매매 내역과 시장 상황을 분석해서 '한 줄 복기'와 '내일의 조언'을 해줘.\n\n"
            f"[최근 매매 내역]\n{trade_summary}\n\n"
            f"[시장 상황 (미국지수 등락)]\n{macro_status}\n\n"
            f"답변은 아주 친절하고 전문적인 말투로 해줘."
        )

        try:
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            logging.error(f"AI 복기 생성 에러: {str(e)}")
            return "AI 분석 중 오류가 발생했습니다."
