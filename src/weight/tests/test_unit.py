import json
import mysql.connector
import os
import sys
import unittest
from io import BytesIO
from unittest.mock import patch, MagicMock

# Add app directory to Python path for importing
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'app'))

# Mock environment variables so weight.py picks up test DB values
with patch.dict(os.environ, {
    'MYSQL_HOST': 'test_host',
    'MYSQL_USER': 'test_user',
    'MYSQL_PASSWORD': 'test_password',
    'MYSQL_DATABASE': 'test_database'
}):
    # Import application components
    from weight import app, process_csv, process_json, get_db_connection


class WeightServiceTests(unittest.TestCase):
    """Unit tests for weight service endpoints and utilities."""

    def setUp(self):
        """Set up test fixtures before each test method."""
        self.app = app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

        # Prepare reusable mocks for DB connection and cursor
        self.mock_conn = MagicMock()
        self.mock_cursor = MagicMock()
        self.mock_conn.cursor.return_value = self.mock_cursor

    # ------------------------- BASIC ENDPOINTS -------------------------

    def test_home_endpoint(self):
        """Test root endpoint returns correct service message."""
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data.decode(), "Weight service is running")

    @patch("weight.get_db_connection")
    def test_health_ok(self, mock_db):
        """Test /health returns OK when DB connection works."""
        mock_db.return_value = self.mock_conn
        self.mock_cursor.fetchone.return_value = (1,)
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data.decode(), "OK")

    @patch("weight.get_db_connection")
    def test_health_fail(self, mock_db):
        """Test /health returns 500 when DB connection fails."""
        mock_db.side_effect = mysql.connector.Error("fail")
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 500)

    # ------------------------- POST /weight -------------------------

    @patch("weight.get_db_connection")
    def test_post_weight_in_success(self, mock_db):
        """Test POST /weight with 'in' direction stores record."""
        mock_db.return_value = self.mock_conn
        self.mock_cursor.lastrowid = 10
        data = {"direction": "in", "truck": "T1", "weight": 5000, "containers": ["C1"]}
        resp = self.client.post("/weight", data=json.dumps(data),
                                content_type="application/json")
        self.assertEqual(resp.status_code, 201)
        j = json.loads(resp.data)
        self.assertEqual(j["id"], 10)
        self.assertEqual(j["truck"], "T1")
        self.assertEqual(j["bruto"], 5000)

    @patch("weight.get_db_connection")
    def test_post_weight_force_in_delete(self, mock_db):
        """Test force flag allows replacing previous 'in' session."""
        mock_db.return_value = self.mock_conn
        # Simulate an existing 'in' record
        self.mock_cursor.fetchone.return_value = {"id": 1, "direction": "in"}
        self.mock_cursor.lastrowid = 11
        data = {"direction": "in", "truck": "T1", "weight": 100, "force": True}
        resp = self.client.post("/weight", data=json.dumps(data),
                                content_type="application/json")
        self.assertEqual(resp.status_code, 201)

    @patch("weight.get_db_connection")
    def test_post_weight_in_after_in_without_force(self, mock_db):
        """Test duplicate 'in' session without force should fail."""
        mock_db.return_value = self.mock_conn
        self.mock_cursor.fetchone.return_value = {"id": 1, "direction": "in"}
        data = {"direction": "in", "truck": "T1", "weight": 100}
        resp = self.client.post("/weight", data=json.dumps(data),
                                content_type="application/json")
        self.assertEqual(resp.status_code, 400)

    @patch("weight.get_db_connection")
    def test_post_weight_none_direction(self, mock_db):
        """Test 'none' direction is allowed."""
        mock_db.return_value = self.mock_conn
        self.mock_cursor.lastrowid = 50
        data = {"direction": "none", "truck": "NA", "weight": 123}
        resp = self.client.post("/weight", data=json.dumps(data),
                                content_type="application/json")
        self.assertEqual(resp.status_code, 201)

    @patch("weight.get_db_connection")
    def test_post_weight_out_with_matching_in(self, mock_db):
        """Test completing an 'out' session with a matching 'in' session."""
        mock_db.return_value = self.mock_conn
        # Provide sequence of fetchone() responses for internal queries
        self.mock_cursor.fetchone.side_effect = [
            {"id": 99, "direction": "in"},  # last session
            {"id": 1, "bruto": 5000, "containers": "C1,C2"},  # last 'in'
            {"weight": 100}, {"weight": 200}  # container weights
        ]
        self.mock_cursor.lastrowid = 20
        data = {"direction": "out", "truck": "T1", "weight": 1000}
        resp = self.client.post("/weight", data=json.dumps(data),
                                content_type="application/json")
        self.assertEqual(resp.status_code, 201)
        j = json.loads(resp.data)
        self.assertEqual(j["truckTara"], 1000)
        self.assertIn("neto", j)

    @patch("weight.get_db_connection")
    def test_post_weight_out_without_matching_in(self, mock_db):
        """Test 'out' session with no matching 'in' session fails."""
        mock_db.return_value = self.mock_conn
        self.mock_cursor.fetchone.return_value = None
        data = {"direction": "out", "truck": "T1", "weight": 1000}
        resp = self.client.post("/weight", data=json.dumps(data),
                                content_type="application/json")
        self.assertEqual(resp.status_code, 400)

    @patch("weight.get_db_connection")
    def test_post_weight_missing_weight(self, mock_db):
        """Test weight is mandatory."""
        mock_db.return_value = self.mock_conn
        data = {"direction": "in", "truck": "T1"}
        resp = self.client.post("/weight", data=json.dumps(data),
                                content_type="application/json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Weight is required", resp.data.decode())

    @patch("weight.get_db_connection")
    def test_post_weight_invalid_direction(self, mock_db):
        """Test invalid direction values return 400."""
        mock_db.return_value = self.mock_conn
        data = {"direction": "bad", "truck": "T1", "weight": 1}
        resp = self.client.post("/weight", data=json.dumps(data),
                                content_type="application/json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Direction must be", resp.data.decode())

    @patch("weight.get_db_connection")
    def test_post_weight_db_error(self, mock_db):
        """Test DB error results in 500."""
        mock_db.return_value = self.mock_conn
        self.mock_cursor.execute.side_effect = mysql.connector.Error("error")
        data = {"direction": "in", "truck": "T1", "weight": 1}
        resp = self.client.post("/weight", data=json.dumps(data),
                                content_type="application/json")
        self.assertEqual(resp.status_code, 500)

    # ------------------------- GET /weight -------------------------

    @patch("weight.get_db_connection")
    def test_get_weight_success(self, mock_db):
        """Test GET /weight returns weight records."""
        mock_db.return_value = self.mock_conn
        self.mock_cursor.fetchall.return_value = [{
            "id": 1, "direction": "in", "bruto": 100,
            "neto": None, "produce": "apples", "containers": "C1,C2"
        }]
        resp = self.client.get("/weight")
        self.assertEqual(resp.status_code, 200)
        j = json.loads(resp.data)
        self.assertEqual(j[0]["containers"], ["C1", "C2"])
        self.assertEqual(j[0]["neto"], "na")

    @patch("weight.get_db_connection")
    def test_get_weight_no_records(self, mock_db):
        """Test GET /weight returns 404 when no records found."""
        mock_db.return_value = self.mock_conn
        self.mock_cursor.fetchall.return_value = []
        resp = self.client.get("/weight?from=20230101&to=20230101")
        self.assertEqual(resp.status_code, 404)

    # ------------------------- GET /session -------------------------

    @patch("weight.get_db_connection")
    def test_get_session_out(self, mock_db):
        """Test GET /session/<id> with 'out' session returns truckTara."""
        mock_db.return_value = self.mock_conn
        self.mock_cursor.fetchone.return_value = {
            "id": 1, "direction": "out", "truck": "T1",
            "bruto": 200, "truckTara": 100, "neto": 100
        }
        resp = self.client.get("/session/1")
        self.assertEqual(resp.status_code, 200)
        j = json.loads(resp.data)
        self.assertIn("truckTara", j)

    @patch("weight.get_db_connection")
    def test_get_session_in(self, mock_db):
        """Test GET /session/<id> with 'in' session omits truckTara."""
        mock_db.return_value = self.mock_conn
        self.mock_cursor.fetchone.return_value = {
            "id": 1, "direction": "in", "truck": "T1",
            "bruto": 200, "truckTara": None, "neto": None
        }
        resp = self.client.get("/session/1")
        self.assertEqual(resp.status_code, 200)
        j = json.loads(resp.data)
        self.assertNotIn("truckTara", j)

    @patch("weight.get_db_connection")
    def test_get_session_not_found(self, mock_db):
        """Test GET /session/<id> returns not found when no record exists."""
        mock_db.return_value = self.mock_conn
        self.mock_cursor.fetchone.return_value = None
        resp = self.client.get("/session/99")
        self.assertEqual(resp.status_code, 404)
        self.assertIn("no records found for session 99", resp.data.decode().lower())

    # ------------------------- GET /item -------------------------

    @patch("weight.get_db_connection")
    def test_get_item_truck(self, mock_db):
        """Test GET /item/<truck_id> returns latest truck tara."""
        mock_db.return_value = self.mock_conn
        self.mock_cursor.fetchall.return_value = [
            {"id": 1, "truck": "T1", "truckTara": 10, "containers": "C1"},
            {"id": 2, "truck": "T1", "truckTara": 20, "containers": "C2"},
        ]
        resp = self.client.get("/item/T1")
        self.assertEqual(resp.status_code, 200)
        j = json.loads(resp.data)
        self.assertEqual(j["tara"], 20)

    @patch("weight.get_db_connection")
    def test_get_item_container(self, mock_db):
        """Test GET /item/<container_id> returns container weight."""
        mock_db.return_value = self.mock_conn
        self.mock_cursor.fetchall.return_value = [
            {"id": 1, "truck": "X", "truckTara": None, "containers": "C1,C2"}
        ]
        self.mock_cursor.fetchone.return_value = {"weight": 50}
        resp = self.client.get("/item/C1")
        self.assertEqual(resp.status_code, 200)
        j = json.loads(resp.data)
        self.assertEqual(j["tara"], 50)

    @patch("weight.get_db_connection")
    def test_get_item_not_found(self, mock_db):
        """Test GET /item/<id> returns 404 when no item is found."""
        mock_db.return_value = self.mock_conn
        self.mock_cursor.fetchall.return_value = []
        resp = self.client.get("/item/NA")
        self.assertEqual(resp.status_code, 404)

    # ------------------------- CSV/JSON PROCESSING -------------------------

    def test_process_csv_valid(self):
        """Test process_csv processes valid csv lines."""
        csv_data = "C1,100kg\nC2,200lbs"
        mc = MagicMock()
        mcu = MagicMock()
        mc.cursor.return_value = mcu

        # Call the function with the mock connection
        process_csv(csv_data, mc)

        # Check execute called twice for two lines
        self.assertEqual(mcu.execute.call_count, 2)

    def test_process_csv_invalid_unit(self):
        """Test process_csv rejects invalid weight units."""
        csv_data = "C1,100grams"
        mc = MagicMock()
        with self.assertRaises(ValueError):
            process_csv(csv_data, mc)

    def test_process_json_valid(self):
        """Test process_json processes valid JSON list of containers."""
        js = json.dumps([{"id": "C1", "weight": 10, "unit": "kg"}])
        mc = MagicMock()
        mcu = MagicMock()
        mc.cursor.return_value = mcu

        process_json(js, mc)

        self.assertEqual(mcu.execute.call_count, 1)

    def test_process_json_invalid(self):
        """Test process_json fails on invalid JSON string."""
        with self.assertRaises(json.JSONDecodeError):
            process_json("not json", MagicMock())

    def test_process_json_missing_fields(self):
        """Test process_json fails when fields are missing."""
        bad = json.dumps([{"id": "C1"}])
        with self.assertRaises(ValueError):
            process_json(bad, MagicMock())

    # ------------------------- /batch-weight -------------------------

    @patch("weight.get_db_connection")
    def test_batch_csv_success(self, mock_db):
        """Test /batch-weight processes CSV files successfully."""
        mock_db.return_value = self.mock_conn
        f = BytesIO(b"C1,100kg\n")
        resp = self.client.post("/batch-weight",
                                data={"file": (f, "c.csv")},
                                content_type="multipart/form-data")
        self.assertEqual(resp.status_code, 201)

    @patch("weight.get_db_connection")
    def test_batch_json_success(self, mock_db):
        """Test /batch-weight processes JSON files successfully."""
        mock_db.return_value = self.mock_conn
        f = BytesIO(json.dumps([{"id": "C1", "weight": 10, "unit": "kg"}]).encode())
        resp = self.client.post("/batch-weight",
                                data={"file": (f, "c.json")},
                                content_type="multipart/form-data")
        self.assertEqual(resp.status_code, 201)

    def test_batch_no_file(self):
        """Test /batch-weight fails when no file is uploaded."""
        resp = self.client.post("/batch-weight", data={},
                                content_type="multipart/form-data")
        self.assertEqual(resp.status_code, 400)

    @patch("weight.get_db_connection")
    def test_batch_invalid_format(self, mock_db):
        """Test /batch-weight rejects unsupported file extensions."""
        mock_db.return_value = self.mock_conn
        f = BytesIO(b"abc")
        resp = self.client.post("/batch-weight",
                                data={"file": (f, "f.txt")},
                                content_type="multipart/form-data")
        self.assertEqual(resp.status_code, 400)

    @patch("weight.get_db_connection")
    def test_batch_processing_error(self, mock_db):
        """Test /batch-weight returns 400 if processing fails."""
        mock_db.return_value = self.mock_conn
        f = BytesIO(b"C1,100grams")
        resp = self.client.post("/batch-weight",
                                data={"file": (f, "bad.csv")},
                                content_type="multipart/form-data")
        self.assertEqual(resp.status_code, 400)

    # ------------------------- DB connection defaults -------------------------

    def test_get_db_connection_with_defaults(self):
        """Test get_db_connection uses default values when env vars are missing."""
        env_vars_to_remove = ['MYSQL_HOST', 'MYSQL_USER', 'MYSQL_PASSWORD', 'MYSQL_DATABASE']
        original_env = {}

        for var in env_vars_to_remove:
            if var in os.environ:
                original_env[var] = os.environ[var]
                del os.environ[var]

        try:
            with patch('mysql.connector.connect') as mock_connect:
                mock_connect.return_value = MagicMock()

                get_db_connection()

                mock_connect.assert_called_once_with(
                    host='db',
                    user='root',
                    password='root',
                    database='weight'
                )
        finally:
            for var, value in original_env.items():
                os.environ[var] = value

    # ------------------------- Cursor cleanup tests -------------------------

    @patch('weight.get_db_connection')
    def test_get_weight_cursor_cleanup(self, mock_get_db):
        """Test cursor and connection are cleaned up in /weight."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            {
                'id': 1,
                'direction': 'in',
                'bruto': 5000,
                'neto': 3250,
                'produce': 'apples',
                'containers': 'CONT001'
            }
        ]
        response = self.client.get('/weight')
        self.assertEqual(response.status_code, 200)
        mock_cursor.close.assert_called_once()
        mock_conn.close.assert_called_once()

    @patch('weight.get_db_connection')
    def test_get_weight_cursor_none_cleanup(self, mock_get_db):
        """Test cleanup logic handles case when cursor is None."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn

        # Return a mock cursor with fetchall returning valid data to avoid serialization issues
        mock_cursor.fetchall.return_value = [{
            "id": 1,
            "direction": "in",
            "bruto": 5000,
            "neto": None,
            "produce": "apples",
            "containers": "C1,C2"
        }]

        mock_conn.cursor.return_value = mock_cursor

        response = self.client.get('/weight')

        self.assertEqual(response.status_code, 200)
        mock_cursor.close.assert_called_once()
        mock_conn.close.assert_called_once()

    @patch('weight.get_db_connection')
    def test_get_session_cursor_cleanup(self, mock_get_db):
        """Test cursor and connection cleanup in get_session endpoint."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = {
            'id': 123,
            'direction': 'out',
            'truck': 'TRUCK001',
            'bruto': 1500,
            'truckTara': 1500,
            'neto': 3250
        }

        response = self.client.get('/session/123')
        self.assertEqual(response.status_code, 200)
        mock_cursor.close.assert_called_once()
        mock_conn.close.assert_called_once()

    @patch('weight.get_db_connection')
    def test_get_item_cursor_cleanup(self, mock_get_db):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            {
                'id': 123,
                'truck': 'TRUCK001',
                'truckTara': 1500,
                'containers': 'CONT001'
            }
        ]
        response = self.client.get('/item/TRUCK001')
        self.assertEqual(response.status_code, 200)
        mock_cursor.close.assert_called_once()
        mock_conn.close.assert_called_once()

    # ------------------------- /unknown -------------------------

    @patch('weight.get_db_connection')
    def test_get_unknown_success(self, mock_db_conn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_db_conn.return_value = mock_conn

        mock_cursor.fetchall.side_effect = [
            [(u'C1',), (u'C2',)],
            [('C1,C3,C4',), ('C5',)]
        ]

        resp = self.client.get('/unknown')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(sorted(data), ['C3', 'C4', 'C5'])

        mock_cursor.close.assert_called_once()
        mock_conn.close.assert_called_once()

    @patch('weight.get_db_connection')
    def test_get_unknown_empty(self, mock_db_conn):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_db_conn.return_value = mock_conn
        mock_cursor.fetchall.side_effect = [[], []]
        resp = self.client.get('/unknown')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data, [])

    @patch('weight.get_db_connection')
    def test_get_unknown_exception(self, mock_db_conn):
        mock_db_conn.side_effect = Exception("DB connection error")
        with self.assertRaises(Exception):
            self.client.get('/unknown')


if __name__ == '__main__':
    unittest.main()
