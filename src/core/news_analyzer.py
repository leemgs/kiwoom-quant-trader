import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
import logging

class NewsSentimentAnalyzer:
    def __init__(self, api_key):
        self.api_key = api_key
        if api_key:
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel('gemini-1.5-flash')
        self.enabled = True if api_key else False

    def get_latest_news(self, code):
        """특정 종목의 최신 뉴스 제목 가져오기 (네이버 금융 기준)"""
        url = f"https://finance.naver.com/item/news_news.naver?code={code}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        
        try:
            res = requests.get(url, headers=headers)
            soup = BeautifulSoup(res.text, 'html.parser')
            titles = soup.select('.title a')
            return [t.get_text().strip() for t in titles[:3]] # 최신 3건
        except Exception as e:
            logging.error(f"뉴스 수집 에러: {str(e)}")
            return []

    def analyze_sentiment(self, titles):
        """Gemini AI를 이용한 뉴스 제목 감성 분석"""
        if not self.enabled or not titles:
            return 0 # Neutral

        combined_titles = "\n".join(titles)
        prompt = (
            f"주식 투자 전문가로서 다음 뉴스 제목들이 해당 종목 주가에 미칠 영향을 분석해줘.\n"
            f"뉴스 제목:\n{combined_titles}\n\n"
            f"결과는 반드시 '점수: [숫자]' 형식으로만 답변해.\n"
            f"- 아주 큰 호재면 100, 아주 큰 악재면 -100, 중립이면 0으로 평가해줘."
        )

        try:
            response = self.model.generate_content(prompt)
            result = response.text
            # "점수: 80" 형태에서 숫자만 추출
            score = int(''.join(filter(lambda x: x.isdigit() or x == '-', result.split(':')[-1])))
            return score
        except Exception as e:
            logging.error(f"AI 분석 에러: {str(e)}")
            return 0
