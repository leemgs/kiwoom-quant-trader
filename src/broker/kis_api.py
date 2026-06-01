import os
import mojito as kis
import logging
import pickle
import datetime
import requests

# =====================================================================
# MONKEYPATCH: KIS API (mojito) Robustness & Self-Healing Patches
# =====================================================================

def patched_fetch_balance_domestic(self, ctx_area_fk100: str = "", ctx_area_nk100: str = "") -> dict:
    path = "uapi/domestic-stock/v1/trading/inquire-balance"
    url = f"{self.base_url}/{path}"
    
    def do_request():
        headers = {
           "content-type": "application/json",
           "authorization": self.access_token,
           "appKey": self.api_key,
           "appSecret": self.api_secret,
           "tr_id": "VTTC8434R" if self.mock else "TTTC8434R"
        }
        params = {
            'CANO': self.acc_no_prefix,
            'ACNT_PRDT_CD': self.acc_no_postfix,
            'AFHR_FLPR_YN': 'N',
            'OFL_YN': 'N',
            'INQR_DVSN': '01',
            'UNPR_DVSN': '01',
            'FUND_STTL_ICLD_YN': 'N',
            'FNCG_AMT_AUTO_RDPT_YN': 'N',
            'PRCS_DVSN': '01',
            'CTX_AREA_FK100': ctx_area_fk100,
            'CTX_AREA_NK100': ctx_area_nk100
        }
        res = requests.get(url, headers=headers, params=params)
        data = res.json()
        data['tr_cont'] = res.headers.get('tr_cont', res.headers.get('tr-cont', ''))
        return res, data

    try:
        res, data = do_request()
    except Exception as e:
        return {
            'rt_cd': '9',
            'msg1': f'HTTP Request failed: {str(e)}',
            'output1': [],
            'output2': [],
            'tr_cont': ''
        }

    # Self-healing token refresh!
    if data.get('msg_cd') == 'EGW00123' or '만료된 token' in data.get('msg1', ''):
        logging.warning("⚠️ KIS Token expired. Self-healing and re-issuing a new token...")
        if os.path.exists("token.dat"):
            try:
                os.remove("token.dat")
            except:
                pass
        try:
            self.issue_access_token()
            res, data = do_request()
        except Exception as e:
            return {
                'rt_cd': '9',
                'msg1': f'Token refresh failed: {str(e)}',
                'output1': [],
                'output2': [],
                'tr_cont': ''
            }

    if 'output1' not in data:
        data['output1'] = []
    if 'output2' not in data:
        data['output2'] = []
    return data

def patched_fetch_balance_oversea(self, ctx_area_fk200: str = "", ctx_area_nk200: str = "") -> dict:
    path = "/uapi/overseas-stock/v1/trading/inquire-balance"
    url = f"{self.base_url}/{path}"
    
    def do_request():
        resp = self.fetch_oversea_day_night()
        psbl = resp.get('output', {}).get('PSBL_YN', 'N')

        if self.mock:
            tr_id = "VTTS3012R" if psbl == 'N' else 'VTTT3012R'
        else:
            tr_id = "TTTS3012R" if psbl == 'N' else 'JTTT3012R'

        headers = {
           "content-type": "application/json",
           "authorization": self.access_token,
           "appKey": self.api_key,
           "appSecret": self.api_secret,
           "tr_id": tr_id
        }

        from mojito.koreainvestment import EXCHANGE_CODE2, CURRENCY_CODE
        exchange_cd = EXCHANGE_CODE2[self.exchange]
        currency_cd = CURRENCY_CODE[self.exchange]

        params = {
            'CANO': self.acc_no_prefix,
            'ACNT_PRDT_CD': self.acc_no_postfix,
            'OVRS_EXCG_CD': exchange_cd,
            'TR_CRCY_CD': currency_cd,
            'CTX_AREA_FK200': ctx_area_fk200,
            'CTX_AREA_NK200': ctx_area_nk200
        }

        res = requests.get(url, headers=headers, params=params)
        data = res.json()
        data['tr_cont'] = res.headers.get('tr_cont', res.headers.get('tr-cont', ''))
        return res, data

    try:
        res, data = do_request()
    except Exception as e:
        return {
            'rt_cd': '9',
            'msg1': f'HTTP Request failed: {str(e)}',
            'output1': [],
            'output2': [],
            'tr_cont': ''
        }

    # Self-healing token refresh!
    if data.get('msg_cd') == 'EGW00123' or '만료된 token' in data.get('msg1', ''):
        logging.warning("⚠️ KIS Token expired. Self-healing and re-issuing a new token...")
        if os.path.exists("token.dat"):
            try:
                os.remove("token.dat")
            except:
                pass
        try:
            self.issue_access_token()
            res, data = do_request()
        except Exception as e:
            return {
                'rt_cd': '9',
                'msg1': f'Token refresh failed: {str(e)}',
                'output1': [],
                'output2': [],
                'tr_cont': ''
            }

    if 'output1' not in data:
        data['output1'] = []
    if 'output2' not in data:
        data['output2'] = []
    return data

def patched_fetch_balance(self) -> dict:
    if self.exchange == '서울':
        output = {'output1': [], 'output2': [], 'rt_cd': '0', 'msg1': ''}
        data = self.fetch_balance_domestic()
        
        if data.get('rt_cd') != '0':
            output['rt_cd'] = data.get('rt_cd', '1')
            output['msg1'] = data.get('msg1', '조회 실패')
            return output
            
        output['output1'] = data.get('output1', [])
        output['output2'] = data.get('output2', [])

        while data.get('tr_cont') == 'M':
            fk100 = data.get('ctx_area_fk100', '')
            nk100 = data.get('ctx_area_nk100', '')
            if not fk100 and not nk100:
                break
            data = self.fetch_balance_domestic(fk100, nk100)
            if data.get('rt_cd') != '0':
                break
            output['output1'].extend(data.get('output1', []))
            output['output2'].extend(data.get('output2', []))

        return output
    else:
        output = {'output1': [], 'output2': [], 'rt_cd': '0', 'msg1': ''}
        data = self.fetch_balance_oversea()
        
        if data.get('rt_cd') != '0':
            output['rt_cd'] = data.get('rt_cd', '1')
            output['msg1'] = data.get('msg1', '조회 실패')
            return output
            
        output['output1'] = data.get('output1', [])
        output['output2'] = data.get('output2', [])

        while data.get('tr_cont') == 'M':
            fk200 = data.get('ctx_area_fk200', '')
            nk200 = data.get('ctx_area_nk200', '')
            if not fk200 and not nk200:
                break
            data = self.fetch_balance_oversea(fk200, nk200)
            if data.get('rt_cd') != '0':
                break
            output['output1'].extend(data.get('output1', []))
            output['output2'].extend(data.get('output2', []))

        return output

# Apply Patches to Mojito
kis.KoreaInvestment.fetch_balance_domestic = patched_fetch_balance_domestic
kis.KoreaInvestment.fetch_balance_oversea = patched_fetch_balance_oversea
kis.KoreaInvestment.fetch_balance = patched_fetch_balance

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
            res = self.api.create_limit_buy_order(code, price, qty)
        return res

    def send_sell_order(self, code, qty, price, order_type="01"):
        """매도 주문 전송"""
        if order_type == "01":
            res = self.api.create_market_sell_order(code, qty)
        else:
            res = self.api.create_limit_sell_order(code, price, qty)
        return res
