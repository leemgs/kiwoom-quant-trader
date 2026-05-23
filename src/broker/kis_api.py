import os
import mojito as kis
import logging

class KISBroker:
    def __init__(self, config):
        self.app_key = config['auth']['kis_app_key']
        self.app_secret = config['auth']['kis_app_secret']
        self.account_no = config['auth']['kis_account_no']
        self.account_suffix = config['auth']['kis_account_suffix']
        self.is_virtual = config['auth']['kis_virtual_trading']
        
        # KIS API 초기화
        self.api = kis.KoreaInvestment(
            api_key=self.app_key,
            api_secret=self.app_secret,
            acc_no=f"{self.account_no}-{self.account_suffix}",
            mock=self.is_virtual
        )
        logging.info("KIS API Broker initialized.")

    def get_price(self, code):
        """현재가 조회"""
        res = self.api.fetch_price(code)
        return float(res['output']['stck_prpr'])

    def get_balance(self):
        """계좌 잔고 조회"""
        res = self.api.fetch_balance()
        return res['output1']

    def send_order(self, code, qty, price, order_type="01"):
        """
        주문 전송
        order_type: "01"(시장가), "00"(지정가)
        """
        if order_type == "01":
            res = self.api.create_market_buy_order(code, qty)
        else:
            res = self.api.create_limit_buy_order(code, qty, price)
        return res

    def send_sell_order(self, code, qty, price, order_type="01"):
        """매도 주문 전송"""
        if order_type == "01":
            res = self.api.create_market_sell_order(code, qty)
        else:
            res = self.api.create_limit_sell_order(code, qty, price)
        return res
