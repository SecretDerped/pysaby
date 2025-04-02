import json
import urllib.request
import urllib.error
import logging
from typing import Any, Dict, Tuple

MAX_JSON_SIZE: int = 100 * 1024 * 1024  # 100 MB


class UrlLibHttpClient:
    """Реализация HTTP клиента."""
    
    def __init__(self, charset: str = 'utf-8'):
        self.charset = charset
    
    def send_request(self, url: str, payload: Dict[str, Any], 
                     headers: Dict[str, str]) -> Tuple[int, str]:
        """Отправка HTTP запроса и возврат статус кода и текста ответа."""
        json_data = json.dumps(payload)
        encoded_json = json_data.encode(self.charset)
        
        if len(encoded_json) > MAX_JSON_SIZE:
            raise ValueError("Размер JSON запроса превышает 100 МБ. Сделайте запрос легче и попробуйте снова.")
        
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

