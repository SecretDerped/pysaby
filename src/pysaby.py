import os
import sqlite3
import json
import urllib.request
import urllib.error
import logging
from typing import Any, Dict, Optional, Tuple

MAX_JSON_SIZE: int = 100 * 1024 * 1024  # 100 MB


class SABYManager:
    """
    Менеджер для работы с API SABY. Инициализирует
    подключение к сервису от имени введённого аккаунта.

    Документация API:
       https://saby.ru/help/integration/api/all_methods/auth_one

    :param login: Логин пользователя.
    :type login: str
    :param password: Пароль пользователя.
    :type password: str
    """
    def __init__(self, login: str, password: str) -> None:
        self.login: str = login
        self.password: str = password
        self.auth_method_name: str = 'СБИС.Аутентифицировать'
        self.auth_params: Dict[str, str] = {"Логин": self.login, "Пароль": self.password}
        
        self.charset: str = 'utf-8'
        self.base_url: str = 'https://online.sbis.ru'
        self.headers: Dict[str, str] = {
            'Host': 'online.sbis.ru',
            'Content-Type': f'application/json-rpc; charset={self.charset}',
            'Accept': 'application/json-rpc'
        }

        self.db_table_name: str = 'auth_state'
        # База будет храниться в папке с библиотекой
        self.db_file: str = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'saby_manager.db')
        self._init_db()
    
    def __str__(self) -> str:
        if self.headers.get("X-SBISSessionID"):
            status = 'Авторизован.'
        else:
            status = 'Нет доступа. Нужна авторизация.'
        return f'SABY manager login: {self.login}, {status}'

    def __repr__(self) -> str:
         return f'SABYManager(login={self.login}, password=***, charset={self.charset}, headers={self.headers})'

    def _init_db(self) -> None:
        """
        Инициализирует SQLite-базу и создаёт таблицу для хранения токенов.

        Таблица имеет следующие поля:
            - id: PRIMARY KEY
            - login: логин пользователя (NOT NULL)
            - token: строка с токеном

        :raises sqlite3.Error: В случае ошибок работы с базой данных.
        """
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f'''CREATE TABLE IF NOT EXISTS {self.db_table_name} (
                        id INTEGER PRIMARY KEY,
                        login TEXT NOT NULL,
                        token TEXT
                    )'''
                )
                conn.commit()
                cursor.close()
        except sqlite3.Error as e:
            logging.error(f"Не удалось создать базу: {e}")
            raise

    def _save_auth_state(self, token: str) -> None:
        """
        Сохраняет токен авторизации для данного логина в базе данных.
        Предыдущий токен для этого логина удаляется.

        :param token: Токен авторизации.
        :type token: str
        :raises sqlite3.Error: В случае ошибок работы с базой данных.
        """
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                # Поля с данными пользователя выводим отдельно во избежание SQL-иньекций
                cursor.execute(f"DELETE FROM {self.db_table_name} WHERE login = ?", (self.login,))
                cursor.execute(f"INSERT INTO {self.db_table_name} (login, token) VALUES (?, ?)", (self.login, token))
                conn.commit()
                cursor.close()
        except sqlite3.Error as e:
            logging.error(f"Ошибка при сохранении токена авторизации в базу данных: {e}")
            raise

    def _load_auth_state(self) -> Optional[str]:
        """
        Загружает токен авторизации из базы данных для данного логина.

        :return: Токен, если найден, иначе None.
        :rtype: Optional[str]
        """
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                cursor.execute(f"SELECT token FROM {self.db_table_name} WHERE login = ? LIMIT 1", (self.login,))
                row = cursor.fetchone()
                cursor.close()
                return row[0] if row else None
        except sqlite3.Error as e:
            logging.error(f"Ошибка при загрузке токена авторизации из базы данных: {e}")
            return None

    def _send_json_request(self,
                           url: str,
                           payload: Dict[str, Any],
                           headers: Dict[str, str]) -> Tuple[int, str]:
        """
        Преобразует данные в JSON, проверяет их размер и отправляет HTTP POST-запрос.

        :param url: URL для отправки запроса.
        :type url: str
        :param payload: Данные запроса.
        :type payload: Dict[str, Any]
        :param headers: Заголовки HTTP-запроса.
        :type headers: Dict[str, str]
        :return: Кортеж из кода ответа и текста ответа.
        :rtype: Tuple[int, str]
        :raises ValueError: Если размер JSON превышает MAX_JSON_SIZE.
        :raises urllib.error.URLError: В случае сетевых ошибок.
        """
        json_data = json.dumps(payload)
        encoded_json = json_data.encode(self.charset)
        if len(encoded_json) > MAX_JSON_SIZE:
            raise ValueError("Размер JSON запроса превышает 100 MB. Сделайте запрос легче и попробуйте снова.")
        
        req = urllib.request.Request(url, data=encoded_json, headers=headers)
        try:
            with urllib.request.urlopen(req) as response:
                status_code = response.getcode()
                resp_text = response.read().decode(self.charset)
        except urllib.error.HTTPError as e:
            status_code = e.code
            resp_text = e.read().decode(self.charset)
        except urllib.error.URLError as e:
            logging.error(f"Ошибка запроса: {e}")
            raise
        return status_code, resp_text

    def _auth(self) -> Optional[str]:
        """
        Аутентифицирует пользователя, получает токен, сохраняет его в базе и возвращает.

        :return: Токен авторизации или None, если аутентификация не удалась.
        :rtype: Optional[str]
        """
        payload = {
            "jsonrpc": "2.0",
            "method": self.auth_method_name,
            "params": self.auth_params,
            "protocol": 2,
            "id": 0
        }

        url = f"{self.base_url}/auth/service/"
        status_code, resp_text = self._send_json_request(url, payload, self.headers)
        logging.debug(f"{self.auth_method_name}: {resp_text=}")

        try:
            response_data = json.loads(resp_text)
            token = response_data["result"]
            self._save_auth_state(token)
            return token
        except KeyError:
            # Если в ответе нет ключа "result", то ловим
            return self._handle_auth_error(resp_text, url)
        except json.JSONDecodeError as e:
            logging.error(f"Ошибка декодирования JSON ответа: {e}")
            raise

    def _handle_auth_error(self, resp_text: str, url: str) -> Optional[str]:
        """
        Обрабатывает ошибки аутентификации, включая проверку необходимости SMS подтверждения.

        :param resp_text: Текст ответа сервера.
        :type resp_text: str
        :param url: URL запроса аутентификации.
        :type url: str
        :return: Токен, если аутентификация завершилась успешно, иначе None.
        :rtype: Optional[str]
        """
        try:
            response_data = json.loads(resp_text)
        except json.JSONDecodeError as e:
            logging.error(f"Ошибка декодирования JSON ответа ошибки при авторизации: {e}")
            raise

        error = response_data.get("error", {})
        if isinstance(error, dict):
            error_data = error.get("data", {})
            error_id = error_data.get("classid")
            logging.warning(f"Authorization error: {error}")
            # Проверяем, нужна ли авторизация по номеру
            if error_id == "{00000000-0000-0000-0000-1fa000001002}":
                return self._handle_sms_authentication(error_data, url)
        else:
            logging.warning(f"Неизвестная ошибка: {error}")
        return None

    def _handle_sms_authentication(self, error_data: Dict[str, Any], url: str) -> Optional[str]:
        """
        Обрабатывает аутентификацию через SMS-код.

        :param error_data: Данные об ошибке аутентификации.
        :type error_data: Dict[str, Any]
        :param url: URL запроса аутентификации.
        :type url: str
        :return: Токен, если SMS-аутентификация прошла успешно, иначе None.
        :rtype: Optional[str]
        """
        session_info = error_data.get("addinfo")
        if not session_info:
            logging.error("Данные для процедуры авторизации по SMS отсутствуют.")
            return None

        session_id = session_info.get("ИдентификаторСессии")
        if not session_id:
            logging.error("Идентификатор сессии не был получен.")
            return None

        self.headers["X-SBISSessionID"] = session_id

        # Отправка кода аутентификации
        payload = {
            "jsonrpc": "2.0",
            "method": "СБИС.ОтправитьКодАутентификации",
            "params": {"Идентификатор": session_info.get("Идентификатор")},
            "id": 0
        }
        self._send_json_request(url, payload, self.headers)

        while True:   # Пока пользователь не введёт правильный код, программа будет посылать запросы на SMS
            try:
                auth_code = input(
                    "На номер " + str(session_info.get('Телефон')) + " отправлен код подтверждения входа.\n"
                    "Нажмите Ctrl+D, чтобы выйти из программы.\n\nВведите код сюда и нажмите Enter: "
                )
            except EOFError:
                logging.info("Пользователь вышел из программы.")
                return None

            # Подтверждение входа
            payload = {
                "jsonrpc": "2.0",
                "method": "СБИС.ПодтвердитьВход",
                "params": {"Идентификатор": session_info.get("Идентификатор"), "Код": auth_code},
                "id": 0
            }
            status_code, resp_text = self._send_json_request(url, payload, self.headers)
            try:
                response_data = json.loads(resp_text)
            except json.JSONDecodeError as e:
                logging.error(f"Ошибка декодирования JSON в процессе авторизации по номеру: {e}")
                continue

            if token := response.get("result"):
                self._save_auth_state(token)
                return token
            if error_msg := response.get("error"):
                logging.warning(f"Авторизация не удалась: {error_msg}. Новая попытка...")

    def _get_sid(self) -> Optional[str]:
        """
        Возвращает сохранённый токен авторизации или инициирует аутентификацию, если токен не найден.

        :return: Токен авторизации.
        :rtype: Optional[str]
        """
        token = self._load_auth_state()
        return token if token else self._auth()

    def send_query(self, method: str, params: Dict[str, Any]) -> Any:
        """
        Выполняет основной запрос к SABY API.

        Если сервер возвращает ошибку авторизации (код 401), пытается обновить токен и повторяет запрос.

        :param method: Имя метода API.
        :type method: str
        :param params: Параметры запроса.
        :type params: Dict[str, Any]
        :return: Результат запроса или информацию об ошибке.
        :rtype: Any
        :raises Exception: Если не удалось получить токен авторизации.
        """
        token = self._get_sid()
        if token is None:
            raise Exception("Не удалось получить токен.")
        self.headers['X-SBISSessionID'] = token

        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "protocol": 2,
            "id": 0
        }
        url = f"{self.base_url}/service/"
        status_code, resp_text = self._send_json_request(url, payload, self.headers)
        logging.info(f"Метод: {method}. Код ответа: {status_code}")
        logging.debug(f"URL: {url}\nЗаголовок: {self.headers}\nПараметры: {params}\nОтвет: {resp_text}\n")

        try:
            response_data = json.loads(resp_text)
        except json.JSONDecodeError as e:
            logging.error(f"Ошибка декодирования JSON ответа на запрос {method}: {e}")
            return None

        match status_code:
            case 200:
                return response_data.get("result")
            case 401:
                logging.info("Попытка обновить токен...")
                new_token = self._auth()
                if new_token:
                    self.headers["X-SBISSessionID"] = new_token
                    status_code, resp_text = self._send_json_request(url, payload, self.headers)
                    try:
                        response_data = json.loads(resp_text)
                    except json.JSONDecodeError as e:
                        logging.error(f"Ошибка декодирования JSON после обновления токена для метода {method}: {e}")
                        return None
                    return response_data.get("result")
                else:
                    raise Exception("Не удалось получить токен.")
            case 404:
                error_detail = response_data.get("error")
                raise AttributeError(
                    f"Метод '{method}' не найден, либо параметры не подходят. Данные об ошибке: {error_detail}"
                )
            case 500:
                error_detail = response_data.get("error")
                raise AttributeError(f"Ошибка сервера при запросе {method}: {error_detail}")
            case _:
                logging.error(f"Неожиданный код ошибки - {status_code}: {resp_text}")
                return None
