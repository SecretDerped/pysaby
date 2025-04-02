import json
import logging
from typing import Any, Dict

from pysaby.interfaces import HttpClient
from pysaby.auth import SABYAuthenticator


class SABYApiClient:
    """Клиент для работы с API SABY."""
    
    def __init__(self, authenticator: SABYAuthenticator, http_client: HttpClient, 
                 base_url: str = 'https://online.sbis.ru'):
        self.authenticator = authenticator
        self.http_client = http_client
        self.base_url = base_url
        self.headers = authenticator.headers.copy()
    
    def send_query(self, method: str, params: Dict[str, Any]) -> Any:
        """Посылает запрос к API SABY."""
        token = self.authenticator.get_token()
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
        status_code, resp_text = self.http_client.send_request(url, payload, self.headers)
        logging.info(f"Метод: {method}. Код ответа: {status_code}")
        
        resp_json = json.loads(resp_text)
        logging.debug(f"URL: {url}\nHeaders: {self.headers}\nParams: {params}\nResponse: {resp_json}\n")
        
        error_text = resp_json.get("error")
        if error_text:
            logging.critical(f"Ошибка: {error_text}")
            return error_text
        
        match status_code:
            case 200:
                return resp_json.get("result")
            case 401:
                logging.info("Попытка обновления токена...")
                token = self.authenticator._authenticate()
                if not token:
                    raise Exception("Не удалось обновить токен.")
                self.headers['X-SBISSessionID'] = token
                status_code, resp_text = self.http_client.send_request(url, payload, self.headers)
                if status_code == 200:
                    return json.loads(resp_text).get("result")
                else:
                    raise Exception(f"{method}: {resp_text}")
            case 404:
                raise AttributeError(f"Ошибка в названии метода '{method}', или некорректных параметрах. "
                                    f"Текст ошибки: {resp_json.get('error')}")
            case _:
                logging.error(f"Код ошибки {status_code}: {resp_text}")
                return None
        
        return resp_json
