import requests
import logging

class SlackNotifier:
    def __init__(self, token, channel_id):
        self.token = token
        self.channel_id = channel_id
        self.enabled = True if token and channel_id else False

    def send_message(self, message):
        if not self.enabled:
            return

        url = "https://slack.com/api/chat.postMessage"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        data = {
            "channel": self.channel_id,
            "text": f"🚀 *[Antigravity Trader]*\n{message}"
        }
        
        try:
            response = requests.post(url, headers=headers, json=data)
            if response.status_code != 200 or not response.json().get('ok', False):
                logging.error(f"Slack 알림 전송 실패: {response.text}")
        except Exception as e:
            logging.error(f"Slack 알림 에러: {str(e)}")

    def notify_order(self, code, type, qty, price):
        msg = (f"🔔 *주문 체결 알림*\n"
               f"- 종목: `{code}`\n"
               f"- 구분: {'🔴 매수' if type == 'BUY' else '🔵 매도'}\n"
               f"- 수량: {qty}주\n"
               f"- 단가: {price:,}원")
        self.send_message(msg)
