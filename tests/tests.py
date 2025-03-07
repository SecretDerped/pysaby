import unittest
import os
import gc
import json
from unittest.mock import patch, MagicMock
from saby_module import SABYManager, MAX_JSON_SIZE

class TestSABYManager(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_db_file = "test_saby_manager.db"  # Для тестирования используем отдельную базу данных
        # Перед запуском тестов следим, чтобы база не осталась от прошлых тестов
        if os.path.exists(cls.test_db_file):
            os.remove(cls.test_db_file)

        cls.manager = SABYManager(login="test_user", password="test_pass")
        cls.manager.db_file = cls.test_db_file  # Назначим новую базу тестовому менеджеру
        cls.manager._init_db()

    @classmethod
    def tearDownClass(cls):
        # Удаляем тестовую базу данных после завершения всех тестов
        gc.collect()
        if os.path.exists(cls.test_db_file):
            os.remove(cls.test_db_file)

    def test_save_and_load_auth_state(self):
        token = "test_token"
        self.manager._save_auth_state(token)
        loaded_token = self.manager._load_auth_state()
        self.assertEqual(token, loaded_token)

    @patch('urllib.request.urlopen')
    def test_send_json_request_success(self, mock_urlopen):
        # Создаем фиктивный ответ
        fake_response = MagicMock()
        fake_response.getcode.return_value = 200
        fake_response.read.return_value = json.dumps({"result": "test_token"}).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = fake_response

        payload = {"jsonrpc": "2.0",
                   "method": "test_method",
                   "params": {}}
        status_code, resp_text = self.manager._send_json_request("http://fakeurl", payload, self.manager.headers)

        self.assertEqual(status_code, 200)
        self.assertIn("test_token", resp_text)

    def test_send_json_request_large_payload(self):
        # Формируем payload, превышающий лимит размера
        large_data = "a" * (MAX_JSON_SIZE + 1)
        payload = {"data": large_data}
        with self.assertRaises(ValueError):
            self.manager._send_json_request("http://fakeurl", payload, self.manager.headers)

    @patch('saby_module.SABYManager._send_json_request')
    def test_send_query_success(self, mock_send_json_request):
        # Эмулируем успешный ответ сервера
        token = "test_token"
        # Предварительно сохраняем токен, чтобы _get_sid не вызывал _auth
        self.manager._save_auth_state(token)
        # Эмулируем ответ запроса
        response_data = {"result": {"data": "value"}}
        mock_send_json_request.return_value = (200, json.dumps(response_data))
        result = self.manager.send_query("test.method", {"param": "value"})
        self.assertEqual(result, {"data": "value"})


if __name__ == "__main__":
    unittest.main()