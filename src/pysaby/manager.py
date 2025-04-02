import os
from typing import Any, Dict

from pysaby.storage import SQLiteTokenStorage
from pysaby.http import UrlLibHttpClient
from pysaby.auth import SABYAuthenticator, ConsoleAuthCodeProvider
from pysaby.api import SABYApiClient


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
        self.login = login
        self.charset = 'utf-8'
        self.base_url = 'https://online.sbis.ru'
        
        db_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'saby_manager.db')
        
        token_storage = SQLiteTokenStorage(db_file)
        http_client = UrlLibHttpClient(charset=self.charset)
        auth_code_provider = ConsoleAuthCodeProvider()
        
        self.authenticator = SABYAuthenticator(
            login=login,
            password=password,
            http_client=http_client,
            token_storage=token_storage,
            auth_code_provider=auth_code_provider,
            base_url=self.base_url,
            charset=self.charset
        )
        
        self.api_client = SABYApiClient(
            authenticator=self.authenticator,
            http_client=http_client,
            base_url=self.base_url
        )
    
    def __str__(self) -> str:
        token = self.authenticator.token_storage.load_token(self.login)
        status = 'Авторизован.' if token else 'Нет доступа. Нужна авторизация.'
        return f'SABY менеджер: {self.login}, {status}'
    
    def __repr__(self) -> str:
        return f'SABYManager(login={self.login}, password=***)'
    
    def send_query(self, method: str, params: Dict[str, Any]) -> Any:
        """
        Осуществляет запрос к API SABY.
        
        :param method: API метод.
        :type method: str
        :param params: Параметры запроса.
        :type params: Dict[str, Any]
        :return: Результат запроса или информация об ошибке.
        :rtype: Any
        :raises Exception: Если не удалось получить токен авторизации.
        """
        return self.api_client.send_query(method, params)
