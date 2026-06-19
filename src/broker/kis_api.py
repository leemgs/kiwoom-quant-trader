import os
import time
import threading
import mojito as kis
import logging
import pickle
import datetime
import requests

# =====================================================================
# GLOBAL RATE LIMITER
# ---------------------------------------------------------------------
# KIS 실전 API는 초당 호출 건수 제한이 있어 짧은 시간에 몰아치면
# "원장에서 허용 가능한 초당 거래건수를 초과하였습니다" 오류가 발생한다.
# 모든 REST 호출 직전에 _throttle()을 호출하여 호출 간 최소 간격을 보장한다.
# (KIS_MIN_REQUEST_INTERVAL 초, 기본 0.2초 ≈ 초당 5회로 안전하게 제한)
# =====================================================================
_RATE_LOCK = threading.Lock()
_LAST_CALL = {'t': 0.0}
_MIN_INTERVAL = float(os.getenv('KIS_MIN_REQUEST_INTERVAL', '0.2'))


def _throttle():
    """모든 KIS REST 호출 직전에 호출 간 최소 간격을 강제한다."""
    with _RATE_LOCK:
        now = time.time()
        wait = _MIN_INTERVAL - (now - _LAST_CALL['t'])
        if wait > 0:
            time.sleep(wait)
        _LAST_CALL['t'] = time.time()


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
        _throttle()
        res = requests.get(url, headers=headers, params=params, timeout=10)
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

        _throttle()
        res = requests.get(url, headers=headers, params=params, timeout=10)
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

def patched_fetch_price(self, symbol: str) -> dict:
    """현재가 조회 (self-healing 토큰 + 레이트리밋 throttle 적용).

    mojito 기본 fetch_price는 토큰 만료/레이트리밋 응답을 복구하지 못해
    'output' 키가 없는 dict를 반환 → 상위에서 KeyError가 발생했다.
    이 패치는 토큰 만료 시 자동 재발급 후 1회 재시도하고, 어떤 경우에도
    'output' 키가 보장된 dict를 반환한다(없으면 빈 dict).
    """
    path = "uapi/domestic-stock/v1/quotations/inquire-price"
    url = f"{self.base_url}/{path}"

    def do_request():
        _throttle()
        headers = {
            "content-type": "application/json",
            "authorization": self.access_token,
            "appKey": self.api_key,
            "appSecret": self.api_secret,
            "tr_id": "FHKST01010100",
        }
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": symbol,
        }
        res = requests.get(url, headers=headers, params=params, timeout=5)
        return res, res.json()

    try:
        res, data = do_request()
    except Exception as e:
        return {'rt_cd': '9', 'msg1': f'HTTP Request failed: {str(e)}', 'output': {}}

    # Self-healing token refresh
    if data.get('msg_cd') == 'EGW00123' or '만료된 token' in data.get('msg1', ''):
        logging.warning("⚠️ KIS Token expired (price). Self-healing and re-issuing a new token...")
        if os.path.exists("token.dat"):
            try:
                os.remove("token.dat")
            except Exception:
                pass
        try:
            self.issue_access_token()
            res, data = do_request()
        except Exception as e:
            return {'rt_cd': '9', 'msg1': f'Token refresh failed: {str(e)}', 'output': {}}

    if 'output' not in data or data.get('output') is None:
        data['output'] = {}
    return data


# Apply Patches to Mojito
kis.KoreaInvestment.fetch_balance_domestic = patched_fetch_balance_domestic
kis.KoreaInvestment.fetch_balance_oversea = patched_fetch_balance_oversea
kis.KoreaInvestment.fetch_balance = patched_fetch_balance
kis.KoreaInvestment.fetch_price = patched_fetch_price

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

    def get_quote(self, code, retries=2):
        """현재가/시가/고저/전일대비 등 시세 dict 반환. 실패 시 None.

        반환: {'price', 'open', 'high', 'low', 'change_pct'} (모두 float)
        - 'output'이 없거나 비어 있으면(토큰/레이트리밋/일시오류) 백오프 후 재시도.
        - 최종 실패 시 예외를 던지지 않고 None을 반환하여 호출부가 안전하게 스킵한다.
        """
        last_err = ''
        for attempt in range(retries + 1):
            res = None
            try:
                res = self.api.fetch_price(code)
            except Exception as e:
                last_err = str(e)

            if isinstance(res, dict):
                out = res.get('output') or {}
                prpr = out.get('stck_prpr')
                if prpr not in (None, '', '0'):
                    try:
                        price = float(prpr)
                        return {
                            'price': price,
                            'open': float(out.get('stck_oprc') or prpr),
                            'high': float(out.get('stck_hgpr') or prpr),
                            'low': float(out.get('stck_lwpr') or prpr),
                            'change_pct': float(out.get('prdy_ctrt') or 0.0),
                            'volume': float(out.get('acml_vol') or 0.0),
                            'prev_volume': float(out.get('prdy_vol') or 0.0),
                        }
                    except (TypeError, ValueError):
                        last_err = 'price parse error'
                else:
                    last_err = res.get('msg1') or 'empty output'

            # 레이트리밋/일시 오류: 점증 백오프 후 재시도
            if attempt < retries:
                time.sleep(0.3 * (attempt + 1))

        logging.debug(f"[{code}] 시세 조회 최종 실패: {last_err}")
        return None

    def get_price(self, code):
        """현재가(float) 반환. 실패 시 None (호출부에서 falsy 처리)."""
        quote = self.get_quote(code)
        return quote['price'] if quote else None

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
