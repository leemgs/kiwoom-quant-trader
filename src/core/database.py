import sqlite3
import pandas as pd
from datetime import datetime


class TradeDatabase:
    def __init__(self, db_path="data/trading_history.db"):
        self.db_path = db_path
        self._create_table()

    def _create_table(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME,
                    code TEXT,
                    type TEXT,
                    qty INTEGER,
                    price INTEGER,
                    profit REAL
                )
            """)
            conn.commit()

    def log_trade(self, code, type, qty, price, profit=0):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO trades (timestamp, code, type, qty, price, profit)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (datetime.now(), code, type, qty, price, profit))
            conn.commit()

    def get_all_trades(self, limit: int = 500):
        """최근 거래 내역 조회. limit으로 메모리 사용량을 제한한다."""
        with sqlite3.connect(self.db_path) as conn:
            return pd.read_sql(
                f"SELECT * FROM trades ORDER BY timestamp DESC LIMIT {int(limit)}",
                conn
            )

    def get_total_profit(self):
        """누적 실현 손익의 합계를 반환 (SQL 집계 사용으로 pandas 로드 불필요)."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COALESCE(SUM(profit), 0) FROM trades WHERE type = 'SELL'")
                row = cursor.fetchone()
                return float(row[0]) if row else 0.0
        except Exception as e:
            print(f"Error fetching total profit: {e}")
            return 0.0

    def get_open_positions_cost(self):
        """현재 보유 중인 포지션의 매수 원금 합계를 계산한다.
        각 종목의 매매 내역을 시간순으로 추적하여 미청산 수량에 평단가를 곱한 값을 합산합니다.
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                df = pd.read_sql("SELECT code, type, qty, price FROM trades ORDER BY timestamp ASC", conn)
            
            if df.empty:
                return 0.0

            holdings = {}
            for _, row in df.iterrows():
                code = row['code']
                trade_type = row['type']
                qty = int(row['qty'])
                price = float(row['price'])

                if code not in holdings:
                    holdings[code] = {'qty': 0, 'total_cost': 0.0}

                if trade_type == 'BUY':
                    holdings[code]['qty'] += qty
                    holdings[code]['total_cost'] += qty * price
                elif trade_type == 'SELL':
                    if holdings[code]['qty'] > 0:
                        avg_price = holdings[code]['total_cost'] / holdings[code]['qty']
                        holdings[code]['qty'] = max(0, holdings[code]['qty'] - qty)
                        holdings[code]['total_cost'] = holdings[code]['qty'] * avg_price

            total_cost = sum(h['total_cost'] for h in holdings.values() if h['qty'] > 0)
            return float(total_cost)
        except Exception as e:
            print(f"Error calculating open positions cost: {e}")
            return 0.0
