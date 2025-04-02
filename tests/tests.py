import pytest
import os
from pysaby import SABYManager


@pytest.mark.skipif(
    "SABY_TEST_LOGIN" not in os.environ or "SABY_TEST_PASSWORD" not in os.environ,
    reason="SABY credentials not set in environment variables"
)
def test_real_api_authentication():
    """Тестирует аутентификацию с реальным API SABY."""
    login = os.environ.get("SABY_TEST_LOGIN")
    password = os.environ.get("SABY_TEST_PASSWORD")
    
    manager = SABYManager(login=login, password=password)
    
    result = manager.send_query("Контрагент.Список", {"Фильтр": {}})
    
    assert isinstance(result, dict)
    assert "error" not in result