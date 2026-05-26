import sqlite3
import pandas as pd
from datetime import datetime

class TradeDatabase:
    def __init__(self, db_path="data/trading_history.db"):
        self.db_path = db_path
        self._create_table()

    def _create_table(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
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
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO trades (timestamp, code, type, qty, price, profit)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (datetime.now(), code, type, qty, price, profit))
            conn.commit()

    def get_all_trades(self):
        with sqlite3.connect(self.db_path) as conn:
            return pd.read_sql("SELECT * FROM trades", conn)

    def get_total_profit(self):
        """누적 실현 손익의 합계를 반환"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT SUM(profit) FROM trades WHERE type = 'SELL'")
                row = cursor.fetchone()
                return float(row[0]) if row and row[0] is not None else 0.0
        except Exception as e:
            print(f"Error fetching total profit: {e}")
            return 0.0

    def get_open_positions_cost(self):
        """현재 보유 중인 포지션의 매수 원금 합계를 계산하여 반환"""
        try:
            df = self.get_all_trades()
            if df.empty:
                return 0.0
            
            holdings = {}
            # 시간 순으로 정렬하여 거래 이력을 추적
            df_sorted = df.copy()
            df_sorted['timestamp'] = pd.to_datetime(df_sorted['timestamp'])
            df_sorted = df_sorted.sort_values('timestamp')
            
            for _, row in df_sorted.iterrows():
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
                        
            total_open_cost = sum(h['total_cost'] for h in holdings.values())
            return total_open_cost
        except Exception as e:
            print(f"Error calculating open positions cost: {e}")
            return 0.0

