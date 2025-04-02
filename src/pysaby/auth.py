import json
import logging
from typing import Any, Dict, Optional

from pysaby.interfaces import TokenStorage, HttpClient, AuthCodeProvider

class ConsoleAuthCodeProvider:
    """Реализация кода авторизации, использующая ввод с консоли."""
    
    def get_auth_code(self, phone_number: str) -> Optional[str]:
        """Получает код авторизации от пользователя через консольный ввод."""
        try:
            auth_code = input(
                f"Код авторизации отправлен на номер {phone_number}.\n"
                "Нажмите Ctrl+D, чтобы выйти из программы.\n\nВведите код и нажмите Enter: "
            )
            return auth_code
        except EOFError:
            logging.info("Отмена авторизации...")
            return None

class SABYAuthenticator:
    """Обработчик процессов аутентификации в СБИС."""
    
    def __init__(self, login: str, password: str, http_client: HttpClient, 
                 token_storage: TokenStorage, auth_code_provider: AuthCodeProvider,
                 base_url: str = 'https://online.sbis.ru', charset: str = 'utf-8'):
        self.login = login
        self.password = password
        self.auth_method_name = 'СБИС.Аутентифицировать'
        self.auth_params = {"Логин": login, "Пароль": password}
        self.base_url = base_url
        self.charset = charset
        self.headers = {
            'Host': 'online.sbis.ru',
            'Content-Type': f'application/json-rpc; charset={charset}',
            'Accept': 'application/json-rpc'
        }
        self.http_client = http_client
        self.token_storage = token_storage
        self.auth_code_provider = auth_code_provider
    
    def get_token(self) -> Optional[str]:
        """Получить токен аутентификации."""
        token = self.token_storage.load_token(self.login)
        return token if token else self._authenticate()
    
    def _authenticate(self) -> Optional[str]:
        """Аутентифицировать пользователя и получить токен."""
        payload = {
            "jsonrpc": "2.0",
            "method": self.auth_method_name,
            "params": self.auth_params,
            "protocol": 2,
            "id": 0
        }
        
        url = f"{self.base_url}/auth/service/"
        status_code, resp_text = self.http_client.send_request(url, payload, self.headers)
        resp_json = json.loads(resp_text)
        logging.debug(f"{self.auth_method_name}: {resp_json}")
        
        token = resp_json.get("result")
        if token:
            self.token_storage.save_token(self.login, token)
            return token
        else:
            return self._handle_auth_error(resp_json, url)
    
    def _handle_auth_error(self, resp_json: Dict[str, Any], url: str) -> Optional[str]:
        """Обработать ошибки аутентификации."""
        error_msg = resp_json.get("error", "Неизвестная ошибка")
        logging.warning(f"Ошибка авторизации: {error_msg}")
        
        error_data = error_msg.get("data", {})
        error_id = error_data.get("classid")
        
        # Check if error requires SMS authentication
        if error_id == "{00000000-0000-0000-0000-1fa000001002}":
            return self._handle_sms_authentication(error_data, url)
        
        return None
    
    def _handle_sms_authentication(self, error_data: Dict[str, Any], url: str) -> Optional[str]:
        """Обработчик процесса аутентификации по SMS."""
        session_info = error_data.get("addinfo")
        if not session_info:
            logging.error("Данные для процедуры аутентификации по SMS отсутствуют.")
            return None
        
        session_id = session_info.get("ИдентификаторСессии")
        if not session_id:
            logging.error("Идентификатор сессии не получен.")
            return None
        
        headers = self.headers.copy()  # На всякий случай копируем заголовки
        headers["X-SBISSessionID"] = session_id
        
        payload = {
            "jsonrpc": "2.0",
            "method": "СБИС.ОтправитьКодАутентификации",
            "params": {"Идентификатор": session_info.get("Идентификатор")},
            "id": 0
        }
        self.http_client.send_request(url, payload, headers)
        
        while True:
            auth_code = self.auth_code_provider.get_auth_code(session_info.get('Телефон'))
            if auth_code is None:
                return None
            
            # Confirm login
            payload = {
                "jsonrpc": "2.0",
                "method": "СБИС.ПодтвердитьВход",
                "params": {"Идентификатор": session_info.get("Идентификатор"), "Код": auth_code},
                "id": 0
            }
            status_code, resp_text = self.http_client.send_request(url, payload, headers)
            response = json.loads(resp_text)
            
            token = response.get("result")
            if token:
                self.token_storage.save_token(self.login, token)
                return token
            else:
                error_msg = response.get("error", response)
                logging.warning(f"Authorization failed: {error_msg}. New attempt...")
