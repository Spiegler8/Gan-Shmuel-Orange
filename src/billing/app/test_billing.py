import pytest
from billing import app
from unittest.mock import patch, MagicMock, Mock
import json
import pandas as pd

@pytest.fixture
def client():
    app.testing = True
    with app.test_client() as client:
        yield client

# ------------------------ PROVIDER TESTS ------------------------

def test_new_provider_success(client):
    with patch("billing.mysql.connector.connect") as mock_connect:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None
        mock_cursor.lastrowid = 1234

        response = client.post("/provider", json={"name": "test-provider"})

        assert response.status_code == 200
        assert response.get_json() == {"id": 1234, "name": "test-provider"}

def test_new_provider_missing_name(client):
    response = client.post("/provider", json={})
    assert response.status_code == 400
    assert response.get_json()["error"] == "Missing provider name"

def test_new_provider_reserved_name(client):
    response = client.post("/provider", json={"name": "health"})
    assert response.status_code == 400
    assert response.get_json()["error"] == "Invalid provider name"

# ------------------------ TRUCK PUT TESTS ------------------------

def test_update_truck_success(client):
    with patch("billing.mysql.connector.connect") as mock_connect:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchone.side_effect = [(123,), (456,)]

        response = client.put("/truck/42", json={"id": 7})

        assert response.status_code == 200
        assert response.get_json() == {'message': 'Truck 42 updated successfully'}

def test_update_truck_not_found(client):
    with patch("billing.mysql.connector.connect") as mock_connect:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchone.side_effect = [None]

        response = client.put("/truck/99", json={"id": 1})
        assert response.status_code == 404
        assert response.get_json() == {'error': 'Truck not found'}

def test_update_truck_provider_not_found(client):
    with patch("billing.mysql.connector.connect") as mock_connect:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchone.side_effect = [(123,), None]

        response = client.put("/truck/55", json={"id": 999})
        assert response.status_code == 404
        assert response.get_json() == {'error': 'Provider not found'}

def test_update_truck_missing_data(client):
    response = client.put("/truck/1", json={})
    assert response.status_code == 400
    assert response.get_json() == {'error': 'Missing provider'}

# ------------------------ TRUCK GET TESTS ------------------------

@patch("billing.mysql.connector.connect")
@patch("requests.get")
def test_get_truck_details_success(mock_requests_get, mock_mysql_connect, client):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_mysql_connect.return_value = mock_conn
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.fetchone.return_value = {
        "id": "123-456",
        "provider_id": 10001
    }

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "tara": 1200,
        "sessions": [
            {"timestamp": "2024-07-01T10:00:00Z", "weight": 1500},
            {"timestamp": "2024-07-01T12:00:00Z", "weight": 1600}
        ]
    }
    mock_requests_get.return_value = mock_response

    response = client.get("/truck/123-456")
    assert response.status_code == 200
    data = response.get_json()
    assert data["tara"] == 1200
    assert len(data["sessions"]) == 2

@patch("billing.mysql.connector.connect")
def test_get_truck_not_found(mock_mysql_connect, client):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_mysql_connect.return_value = mock_conn
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.fetchone.return_value = None

    response = client.get("/truck/unknown-id")
    assert response.status_code == 404

@patch("billing.mysql.connector.connect")
@patch("requests.get")
def test_get_truck_weight_api_failure(mock_requests_get, mock_mysql_connect, client):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_mysql_connect.return_value = mock_conn
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.fetchone.return_value = {"id": "123-456", "provider_id": 10001}

    mock_response = Mock()
    mock_response.status_code = 500
    mock_requests_get.return_value = mock_response

    response = client.get("/truck/123-456")
    assert response.status_code == 500

# ------------------------ PROVIDER PUT TESTS ------------------------

@patch("billing.mysql.connector.connect")
def test_update_provider_success(mock_connect, client):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_connect.return_value = mock_conn
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.rowcount = 1

    response = client.put("/provider/42", json={"name": "Updated"})
    assert response.status_code == 200

@patch("billing.mysql.connector.connect")
def test_update_provider_not_found(mock_connect, client):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_connect.return_value = mock_conn
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.rowcount = 0

    response = client.put("/provider/99", json={"name": "Updated"})
    assert response.status_code == 404

def test_update_provider_missing_name(client):
    response = client.put("/provider/1", json={})
    assert response.status_code == 400

# ------------------------ POST /rates ------------------------

@patch("billing.glob.glob")
@patch("billing.pd.read_excel")
@patch("billing.mysql.connector.connect")
def test_upload_rates_success(mock_connect, mock_read_excel, mock_glob, client):
    mock_glob.return_value = ["/in/sample.xlsx"]
    mock_read_excel.return_value = pd.DataFrame([
        {"Product": "APPLE", "Rate": 100, "Scope": "ISRAEL"},
        {"Product": "BANANA", "Rate": 200, "Scope": "EXPORT"},
    ])
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_connect.return_value = mock_conn
    mock_conn.cursor.return_value = mock_cursor
    # Simulate SELECT returning existing rate for APPLE and nothing for BANANA
    # First call to fetchone → (50,) → triggers update
    # Second call to fetchone → None → triggers insert
    mock_cursor.fetchone.side_effect = [(50,), None]
    response = client.post("/rates")
    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data["updated"] == 1
    assert json_data["inserted"] == 1

# ------------------------ GET /rates ------------------------

@patch("billing.glob.glob")
@patch("billing.send_file")
def test_download_rates_success(mock_send_file, mock_glob, client):
    mock_glob.return_value = ["/in/rates.xlsx"]
    mock_send_file.return_value = "OK"

    response = client.get("/rates")
    assert response.status_code == 200

@patch("billing.glob.glob")
def test_download_rates_no_file(mock_glob, client):
    mock_glob.return_value = []
    response = client.get("/rates")
    assert response.status_code == 404

@patch("billing.glob.glob")
def test_download_rates_exception(mock_glob, client):
    mock_glob.side_effect = Exception("crash")
    response = client.get("/rates")
    assert response.status_code == 500



