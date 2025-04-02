from abc import abstractmethod
from typing import Any, Dict, Optional, Tuple, Protocol


class TokenStorage(Protocol):
    """Интерфейс для реализации хранения токенов."""
    
    def save_token(self, login: str, token: str) -> None:
        """Сохраняет токен для указанного логина."""
        pass
    
    def load_token(self, login: str) -> Optional[str]:
        """Загружает токен для указанного логина."""
        pass


class HttpClient(Protocol):
    """Интерфейс для HTTP клиента."""
    
    @abstractmethod
    def send_request(self, url: str, payload: Dict[str, Any], 
                     headers: Dict[str, str]) -> Tuple[int, str]:
        """Отправляет HTTP запрос и возвращает статус код и текст ответа."""
        pass


class AuthCodeProvider(Protocol):
    """Интерфейс для кода аутентификации."""
    
    def get_auth_code(self, phone_number: str) -> Optional[str]:
        """Получает код аутентификации от пользователя."""
        pass

