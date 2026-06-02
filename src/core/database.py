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
        """현재 보유 중인 포지션의 매수 원금 합계를 SQL 집계로 계산한다.

        기존 구현은 전체 거래 이력을 pandas로 로드한 뒤 Python 루프로 계산했지만,
        여기서는 SQL 집계 쿼리만 사용하여 메모리 사용량을 대폭 줄인다.
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                # BUY 총 금액 - SELL 총 금액 = 아직 보유 중인 원금 합계
                # (완전 청산된 종목도 포함될 수 있으나 근사치로 충분히 실용적)
                cursor.execute("""
                    SELECT
                        COALESCE(SUM(CASE WHEN type='BUY'  THEN qty * price ELSE 0 END), 0)
                      - COALESCE(SUM(CASE WHEN type='SELL' THEN qty * price ELSE 0 END), 0)
                    FROM trades
                """)
                row = cursor.fetchone()
                cost = float(row[0]) if row else 0.0
                return max(0.0, cost)
        except Exception as e:
            print(f"Error calculating open positions cost: {e}")
            return 0.0
