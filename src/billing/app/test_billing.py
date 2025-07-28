import pytest
from billing import app
from unittest.mock import patch, MagicMock, Mock

#----------------- testing POST /provider ----------------------
@pytest.fixture
def client():
    app.testing = True
    with app.test_client() as client:
        yield client

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
        mock_cursor.execute.assert_any_call("SELECT id FROM Provider WHERE name = %s", ("test-provider",))
        mock_cursor.execute.assert_any_call("INSERT INTO Provider (name) VALUES (%s)", ("test-provider",))

def test_new_provider_missing_name(client):
    response = client.post("/provider", json={})
    assert response.status_code == 400
    assert response.get_json()["error"] == "Missing provider name"

def test_new_provider_reserved_name(client):
    response = client.post("/provider", json={"name": "health"})
    assert response.status_code == 400
    assert response.get_json()["error"] == "Invalid provider name"


#------------------------------- testing PUT /truck   -------------------------------------------
def test_update_truck_success(client):
    with patch("billing.mysql.connector.connect") as mock_connect:
        # Setup mocks
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        # Simulate that both truck and provider exist
        mock_cursor.fetchone.side_effect = [(123,), (456,)]

        response = client.put("/truck/42", json={"id": 7})  # truck id in URL, provider id in body

        assert response.status_code == 200
        assert response.get_json() == {'message': 'Truck 42 updated successfully'}

        # Check SQL was called correctly
        mock_cursor.execute.assert_any_call("SELECT id FROM Trucks WHERE id = %s", (42,))
        mock_cursor.execute.assert_any_call("SELECT id FROM Provider WHERE id = %s", (7,))
        mock_cursor.execute.assert_any_call("UPDATE Trucks SET provider_id = %s WHERE id = %s", (7, 42))

def test_update_truck_not_found(client):
    with patch("billing.mysql.connector.connect") as mock_connect:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        # Truck not found
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

        # Truck found, provider not found
        mock_cursor.fetchone.side_effect = [(123,), None]

        response = client.put("/truck/55", json={"id": 999})
        assert response.status_code == 404
        assert response.get_json() == {'error': 'Provider not found'}

def test_update_truck_missing_data(client):
    response = client.put("/truck/1", json={})
    assert response.status_code == 400
    assert response.get_json() == {'error': 'Missing provider'}

#------------------------testing GET/ truck/id----------------------
import json

@patch('billing.mysql.connector.connect')
@patch('requests.get')
def test_get_truck_details_success(mock_requests_get, mock_mysql_connect, client):
    # Mock MySQL connection and cursor
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_mysql_connect.return_value = mock_conn
    mock_conn.cursor.return_value = mock_cursor

    # Return dict exactly like your real DB row for the truck
    mock_cursor.fetchone.return_value = {
        "id": "123-456",
        "provider_id": 10001
    }

    # Mock external API
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

    # Call route
    response = client.get("/truck/123-456")

    # Add debugging
    print(f"Response status: {response.status_code}")
    print(f"Response data: {response.data.decode()}")

    assert response.status_code == 200
    data = response.get_json()
    assert data["id"] == "123-456"
    assert data["tara"] == 1200
    assert len(data["sessions"]) == 2

@patch('billing.mysql.connector.connect')
def test_get_truck_not_found(mock_mysql_connect, client):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_mysql_connect.return_value = mock_conn
    mock_conn.cursor.return_value = mock_cursor
    
    # Simulate truck not found
    mock_cursor.fetchone.return_value = None
    
    response = client.get("/truck/nonexistent-id")
    
    assert response.status_code == 404
    assert response.get_json() == {"error": "Truck not found"}    


@patch('billing.mysql.connector.connect')
@patch('requests.get')
def test_get_truck_weight_api_failure(mock_requests_get, mock_mysql_connect, client):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_mysql_connect.return_value = mock_conn
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.fetchone.return_value = {"id": "123-456", "provider_id": 10001}

    # External API returns error
    mock_response = Mock()
    mock_response.status_code = 500
    mock_requests_get.return_value = mock_response

    response = client.get("/truck/123-456")
    assert response.status_code == 500
    assert response.get_json() == {"error": "Failed to fetch from weight system"}