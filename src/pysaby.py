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
        self.db_file: str = 'saby_manager.db'
        self._init_db()
    
    def __str__(self):
        text = f'SABY manager login: {self.login}'
        if ["X-SBISSessionID"]:
            text += f', authorised already'
        else:
            text += f', need to authorise'

    def __repr__(self):
        return f'SABYManager(login={self.login}, password=..., charset={self.charset}, headers={self.headers})'

    def _init_db(self) -> None:
        """
        Инициализирует SQLite-базу и создаёт таблицу для хранения токенов.

        Таблица имеет следующие поля:
            - id: PRIMARY KEY
            - login: логин пользователя (NOT NULL)
            - token: строка с токеном

        :raises sqlite3.Error: В случае ошибок работы с базой данных.
        """
        with sqlite3.connect(self.db_file) as conn:
            with conn:
                cursor =  conn.cursor()
                cursor.execute(
                    f'CREATE TABLE IF NOT EXISTS {self.db_table_name} ('
                    'id INTEGER PRIMARY KEY, '
                    'login TEXT NOT NULL, '
                    'token TEXT)'
                )
                cursor.close()

    def _save_auth_state(self, token: str) -> None:
        """
        Сохраняет токен авторизации для данного логина в базе данных.
        Предыдущий токен для этого логина удаляется.

        :param token: Токен авторизации.
        :type token: str
        :raises sqlite3.Error: В случае ошибок работы с базой данных.
        """
        with sqlite3.connect(self.db_file) as conn:
            with conn:
                cursor = conn.cursor()
                cursor.execute(f"DELETE FROM {self.db_table_name} WHERE login='{self.login}'")
                cursor.execute(f"INSERT INTO {self.db_table_name} (login, token) VALUES ('{self.login}', '{token}')")
                cursor.close()

    def _load_auth_state(self) -> Optional[str]:
        """
        Загружает токен авторизации из базы данных для данного логина.

        :return: Токен, если найден, иначе None.
        :rtype: Optional[str]
        """
        with sqlite3.connect(self.db_file) as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"SELECT token FROM {self.db_table_name} WHERE login = '{self.login}' LIMIT 1"
            )
            row = cursor.fetchone()
            cursor.close()
        return row[0] if row else None

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
        resp_json = json.loads(resp_text)
        logging.debug(f"{self.auth_method_name}: {resp_json}")

        token = resp_json.get("result")
        if token:
            self._save_auth_state(token)
            return token
        else:
            return self._handle_auth_error(resp_json, url)

    def _handle_auth_error(self, resp_json: str, url: str) -> Optional[str]:
        """
        Обрабатывает ошибки аутентификации, включая проверку необходимости SMS подтверждения.

        :param resp_json: Текст ответа сервера.
        :type resp_json: str
        :param url: URL запроса аутентификации.
        :type url: str
        :return: Токен, если аутентификация завершилась успешно, иначе None.
        :rtype: Optional[str]
        """
        error_msg = resp_json.get("error", "Unknown error")
        logging.warning(f"Authorization error: {error_msg}")

        error_data = error_msg.get("data", {})
        error_id = error_data.get("classid")

        # Проверка, требует ли ошибка аутентификацию через SMS
        if error_id == "{00000000-0000-0000-0000-1fa000001002}":
            return self._handle_sms_authentication(error_data, url)

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

        self.headers["X-SBISSessionID"] = session_info["ИдентификаторСессии"]

        # Отправка кода аутентификации
        payload = {
            "jsonrpc": "2.0",
            "method": "СБИС.ОтправитьКодАутентификации",
            "params": {"Идентификатор": session_info["Идентификатор"]},
            "id": 0
        }
        self._send_json_request(url, payload, self.headers)

        while True: # Пока пользователь не введёт правильный код, программа будет посылать запросы на SMS
            auth_code = input(
                "На номер " + str(session_info['Телефон']) + " отправлен код подтверждения входа.\n"
                "Нажмите Ctrl+D, чтобы выйти из программы.\n\nВведите код сюда и нажмите Enter: "
            )
            # Подтверждение входа
            payload = {
                "jsonrpc": "2.0",
                "method": "СБИС.ПодтвердитьВход",
                "params": {"Идентификатор": session_info["Идентификатор"], "Код": auth_code},
                "id": 0
            }
            status_code, resp_text = self._send_json_request(url, payload, self.headers)
            response = json.loads(resp_text)

            token = response.get("result")
            if token:
                self._save_auth_state(token)
                return token
            
            else:
                error_msg = response.get("error", response)
                logging.warning(f"Авторизация не удалась: {error_msg}. Новая попытка...")

    def _get_sid(self) -> Optional[str]:
        """
        Возвращает сохранённый токен авторизации или инициирует аутентификацию, если токен не найден.

        :return: Токен авторизации.
        :rtype: Optional[str]
        """
        return self._load_auth_state() or self._auth()

    def send_query(self, method, params):
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
        resp_json = json.loads(resp_text)
        logging.debug(f"URL: {url}\nЗаголовок: {self.headers}\nПараметры: {params}\nОтвет: {resp_json}\n")

        error_text = resp_json.get("error")
        if error_text:
            logging.critical(f"Ошибка: {error_text}")
            return error_text

        match status_code:
            case 200:
                return resp_json.get("result")
            case 401:
                logging.info("Попытка обновить токен...")
                self.headers["X-SBISSessionID"] = self._auth() or ""
                status_code, resp_text = self._send_json_request(url, payload, self.headers)
                if status_code == 200:
                    return json.loads(resp_text).get("result")
                else:
                    raise 
            case 404:
                raise AttributeError(f"Ошибка в названии метода '{method}', либо к методу подобраны"
                                        f"неверные параметры. Данные об ошибке: {resp_json['error']}")
            case 500:
                raise AttributeError(f"{method}: {resp_json['error']}")
            case _:
                logging.error(f"Код ошибки {status_code}: {resp_text}")
                return None

        return resp_json