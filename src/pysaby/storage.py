import sqlite3
import logging
from typing import Optional


class SQLiteTokenStorage:
    """Реализация хранилища токенов на SQLite."""
    
    def __init__(self, db_file: str, table_name: str = 'auth_state'):
        self.db_file = db_file
        self.table_name = table_name
        self._init_db()
    
    def _init_db(self) -> None:
        """Инициализирует SQLite БД и создает таблицу для хранения токенов."""
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f'''CREATE TABLE IF NOT EXISTS {self.table_name} (
                    id INTEGER PRIMARY KEY,
                    login TEXT NOT NULL,
                    token TEXT
                    )'''
                )
                conn.commit()
        except sqlite3.Error as e:
            logging.error(f"Не удалось создать базу данных: {e}")
            raise
    
    def save_token(self, login: str, token: str) -> None:
        """Сохраняет токен для указанного логина."""
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                cursor.execute(f"DELETE FROM {self.table_name} WHERE login = ?", (login,))
                cursor.execute(f"INSERT INTO {self.table_name} (login, token) VALUES (?, ?)", 
                               (login, token))
                conn.commit()
        except sqlite3.Error as e:
            logging.error(f"Не удалось сохранить токен для логина {login}: {e}")
            raise
    
    def load_token(self, login: str) -> Optional[str]:
        """Загружает токен для указанного логина."""
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                cursor.execute(f"SELECT token FROM {self.table_name} WHERE login = ? LIMIT 1", 
                               (login,))
                row = cursor.fetchone()
                return row[0] if row else None
        except sqlite3.Error as e:
            logging.error(f"Не удалось загрузить токен для логина {login}: {e}")
            return None
            