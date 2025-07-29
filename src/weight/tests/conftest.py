# tests/conftest.py
import os
import pytest
from unittest.mock import patch


@pytest.fixture(autouse=True)
def mock_environment():
    """Mock environment variables for all tests to avoid database connections."""
    with patch.dict(os.environ, {
        'MYSQL_HOST': 'test_host',
        'MYSQL_USER': 'test_user',
        'MYSQL_PASSWORD': 'test_password',
        'MYSQL_DATABASE': 'test_database'
    }):
        yield
