import json
import mysql.connector
import os
import os
# Import the Flask app from the correct path
import sys
import unittest
from datetime import datetime
from io import StringIO, BytesIO
from unittest.mock import patch, MagicMock

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'app'))

# Mock the database connection before importing the app
with patch.dict(os.environ, {
    'MYSQL_HOST': 'test_host',
    'MYSQL_USER': 'test_user',
    'MYSQL_PASSWORD': 'test_password',
    'MYSQL_DATABASE': 'test_database'
}):
    from weight import app, process_csv, process_json, get_db_connection


class WeightServiceTests(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures before each test method."""
        self.app = app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

        # Mock database connection
        self.mock_conn = MagicMock()
        self.mock_cursor = MagicMock()
        self.mock_conn.cursor.return_value = self.mock_cursor

    # ------------------------- BASIC ENDPOINTS -------------------------

    def test_home_endpoint(self):
        """Test the home endpoint returns correct response."""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.decode(), 'Weight service is running')

    @patch("weight.get_db_connection")
    def test_health_ok(self, mdb):
        mdb.return_value = self.mock_conn
        self.mock_cursor.fetchone.return_value = (1,)
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data.decode(), "OK")

    @patch("weight.get_db_connection")
    def test_health_fail(self, mdb):
        mdb.side_effect = mysql.connector.Error("fail")
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 500)

    # ------------------------- POST /weight -------------------------

    @patch("weight.get_db_connection")
    def test_post_weight_in_success(self, mdb):
        mdb.return_value = self.mock_conn
        self.mock_cursor.lastrowid = 10
        data = {"direction": "in", "truck": "T1", "weight": 5000, "containers": ["C1"]}
        r = self.client.post("/weight", data=json.dumps(data),
                             content_type="application/json")
        self.assertEqual(r.status_code, 201)
        j = json.loads(r.data)
        self.assertEqual(j["id"], 10)
        self.assertEqual(j["truck"], "T1")
        self.assertEqual(j["bruto"], 5000)

    @patch("weight.get_db_connection")
    def test_post_weight_force_in_delete(self, mdb):
        mdb.return_value = self.mock_conn
        # simulate last session is "in"
        self.mock_cursor.fetchone.return_value = {"id": 1, "direction": "in"}
        self.mock_cursor.lastrowid = 11
        data = {"direction": "in", "truck": "T1", "weight": 100, "force": True}
        r = self.client.post("/weight", data=json.dumps(data),
                             content_type="application/json")
        self.assertEqual(r.status_code, 201)

    @patch("weight.get_db_connection")
    def test_post_weight_in_after_in_without_force(self, mdb):
        mdb.return_value = self.mock_conn
        self.mock_cursor.fetchone.return_value = {"id": 1, "direction": "in"}
        data = {"direction": "in", "truck": "T1", "weight": 100}
        r = self.client.post("/weight", data=json.dumps(data),
                             content_type="application/json")
        self.assertEqual(r.status_code, 400)

    @patch("weight.get_db_connection")
    def test_post_weight_none_direction(self, mdb):
        mdb.return_value = self.mock_conn
        self.mock_cursor.lastrowid = 50
        data = {"direction": "none", "truck": "NA", "weight": 123}
        r = self.client.post("/weight", data=json.dumps(data),
                             content_type="application/json")
        self.assertEqual(r.status_code, 201)

    @patch("weight.get_db_connection")
    def test_post_weight_out_with_matching_in(self, mdb):
        mdb.return_value = self.mock_conn
        # Provide enough return values for each fetchone call
        self.mock_cursor.fetchone.side_effect = [
            {"id": 99, "direction": "in"},  # find_last_session
            {"id": 1, "bruto": 5000, "containers": "C1,C2"},  # find_last_in_session
            {"weight": 100}, {"weight": 200}  # container weights
        ]
        self.mock_cursor.lastrowid = 20
        data = {"direction": "out", "truck": "T1", "weight": 1000}
        r = self.client.post("/weight", data=json.dumps(data),
                             content_type="application/json")
        self.assertEqual(r.status_code, 201)
        j = json.loads(r.data)
        self.assertEqual(j["truckTara"], 1000)
        self.assertTrue("neto" in j)

    @patch("weight.get_db_connection")
    def test_post_weight_out_without_matching_in(self, mdb):
        mdb.return_value = self.mock_conn
        self.mock_cursor.fetchone.return_value = None
        data = {"direction": "out", "truck": "T1", "weight": 1000}
        r = self.client.post("/weight", data=json.dumps(data),
                             content_type="application/json")
        self.assertEqual(r.status_code, 400)

    @patch("weight.get_db_connection")
    def test_post_weight_missing_weight(self, mdb):
        mdb.return_value = self.mock_conn
        data = {"direction": "in", "truck": "T1"}
        r = self.client.post("/weight", data=json.dumps(data),
                             content_type="application/json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("Weight is required", r.data.decode())

    @patch("weight.get_db_connection")
    def test_post_weight_invalid_direction(self, mdb):
        mdb.return_value = self.mock_conn
        data = {"direction": "bad", "truck": "T1", "weight": 1}
        r = self.client.post("/weight", data=json.dumps(data),
                             content_type="application/json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("Direction must be", r.data.decode())

    @patch("weight.get_db_connection")
    def test_post_weight_db_error(self, mdb):
        mdb.return_value = self.mock_conn
        self.mock_cursor.execute.side_effect = mysql.connector.Error("error")
        data = {"direction": "in", "truck": "T1", "weight": 1}
        r = self.client.post("/weight", data=json.dumps(data),
                             content_type="application/json")
        self.assertEqual(r.status_code, 500)

    # ------------------------- GET /weight -------------------------

    @patch("weight.get_db_connection")
    def test_get_weight_success(self, mdb):
        mdb.return_value = self.mock_conn
        self.mock_cursor.fetchall.return_value = [{
            "id": 1, "direction": "in", "bruto": 100,
            "neto": None, "produce": "apples", "containers": "C1,C2"
        }]
        r = self.client.get("/weight")
        self.assertEqual(r.status_code, 200)
        j = json.loads(r.data)
        self.assertEqual(j[0]["containers"], ["C1", "C2"])
        self.assertEqual(j[0]["neto"], "na")

    @patch("weight.get_db_connection")
    def test_get_weight_no_records(self, mdb):
        mdb.return_value = self.mock_conn
        self.mock_cursor.fetchall.return_value = []
        r = self.client.get("/weight?from=20230101&to=20230101")
        self.assertEqual(r.status_code, 404)

    # ------------------------- GET /session -------------------------

    @patch("weight.get_db_connection")
    def test_get_session_out(self, mdb):
        mdb.return_value = self.mock_conn
        self.mock_cursor.fetchone.return_value = {
            "id": 1, "direction": "out", "truck": "T1",
            "bruto": 200, "truckTara": 100, "neto": 100
        }
        r = self.client.get("/session/1")
        self.assertEqual(r.status_code, 200)
        j = json.loads(r.data)
        self.assertIn("truckTara", j)

    @patch("weight.get_db_connection")
    def test_get_session_in(self, mdb):
        mdb.return_value = self.mock_conn
        self.mock_cursor.fetchone.return_value = {
            "id": 1, "direction": "in", "truck": "T1",
            "bruto": 200, "truckTara": None, "neto": None
        }
        r = self.client.get("/session/1")
        self.assertEqual(r.status_code, 200)
        j = json.loads(r.data)
        self.assertNotIn("truckTara", j)

    @patch("weight.get_db_connection")
    def test_get_session_not_found(self, mdb):
        mdb.return_value = self.mock_conn
        self.mock_cursor.fetchone.return_value = None
        r = self.client.get("/session/99")
        self.assertEqual(r.status_code, 200)
        self.assertIn("not found", r.data.decode())

    # ------------------------- GET /item -------------------------

    @patch("weight.get_db_connection")
    def test_get_item_truck(self, mdb):
        mdb.return_value = self.mock_conn
        self.mock_cursor.fetchall.return_value = [
            {"id": 1, "truck": "T1", "truckTara": 10, "containers": "C1"},
            {"id": 2, "truck": "T1", "truckTara": 20, "containers": "C2"},
        ]
        r = self.client.get("/item/T1")
        self.assertEqual(r.status_code, 200)
        j = json.loads(r.data)
        self.assertEqual(j["tara"], 20)

    @patch("weight.get_db_connection")
    def test_get_item_container(self, mdb):
        mdb.return_value = self.mock_conn
        self.mock_cursor.fetchall.return_value = [
            {"id": 1, "truck": "X", "truckTara": None, "containers": "C1,C2"}
        ]
        self.mock_cursor.fetchone.return_value = {"weight": 50}
        r = self.client.get("/item/C1")
        self.assertEqual(r.status_code, 200)
        j = json.loads(r.data)
        self.assertEqual(j["tara"], 50)

    @patch("weight.get_db_connection")
    def test_get_item_not_found(self, mdb):
        mdb.return_value = self.mock_conn
        self.mock_cursor.fetchall.return_value = []
        r = self.client.get("/item/NA")
        self.assertEqual(r.status_code, 404)

    # ------------------------- CSV/JSON PROCESSING -------------------------

    def test_process_csv_valid(self):
        csv = "C1,100kg\nC2,200lbs"
        mc = MagicMock()
        mcu = MagicMock()
        mc.cursor.return_value = mcu
        process_csv(csv, mc)
        self.assertEqual(mcu.execute.call_count, 2)

    def test_process_csv_invalid_unit(self):
        csv = "C1,100grams"
        mc = MagicMock()
        with self.assertRaises(ValueError):
            process_csv(csv, mc)

    def test_process_json_valid(self):
        js = json.dumps([{"id": "C1", "weight": 10, "unit": "kg"}])
        mc = MagicMock()
        mcu = MagicMock()
        mc.cursor.return_value = mcu
        process_json(js, mc)
        self.assertEqual(mcu.execute.call_count, 1)

    def test_process_json_invalid(self):
        with self.assertRaises(json.JSONDecodeError):
            process_json("not json", MagicMock())

    def test_process_json_missing_fields(self):
        bad = json.dumps([{"id": "C1"}])
        with self.assertRaises(ValueError):
            process_json(bad, MagicMock())

    # ------------------------- /batch-weight -------------------------

    @patch("weight.get_db_connection")
    def test_batch_csv_success(self, mdb):
        mdb.return_value = self.mock_conn
        f = BytesIO(b"C1,100kg\n")
        r = self.client.post("/batch-weight",
                             data={"file": (f, "c.csv")},
                             content_type="multipart/form-data")
        self.assertEqual(r.status_code, 201)

    @patch("weight.get_db_connection")
    def test_batch_json_success(self, mdb):
        mdb.return_value = self.mock_conn
        f = BytesIO(json.dumps([{"id": "C1", "weight": 10, "unit": "kg"}]).encode())
        r = self.client.post("/batch-weight",
                             data={"file": (f, "c.json")},
                             content_type="multipart/form-data")
        self.assertEqual(r.status_code, 201)

    def test_batch_no_file(self):
        r = self.client.post("/batch-weight", data={},
                             content_type="multipart/form-data")
        self.assertEqual(r.status_code, 400)

    @patch("weight.get_db_connection")
    def test_batch_invalid_format(self, mdb):
        mdb.return_value = self.mock_conn
        f = BytesIO(b"abc")
        r = self.client.post("/batch-weight",
                             data={"file": (f, "f.txt")},
                             content_type="multipart/form-data")
        self.assertEqual(r.status_code, 400)

    @patch("weight.get_db_connection")
    def test_batch_processing_error(self, mdb):
        mdb.return_value = self.mock_conn
        f = BytesIO(b"C1,100grams")
        r = self.client.post("/batch-weight",
                             data={"file": (f, "bad.csv")},
                             content_type="multipart/form-data")
        self.assertEqual(r.status_code, 400)

    def test_get_db_connection_with_defaults(self):
        """Test database connection function uses default values when env vars not set."""
        # Remove environment variables
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
            # Restore original environment
            for var, value in original_env.items():
                os.environ[var] = value

    @patch('weight.get_db_connection')
    def test_get_weight_cursor_cleanup(self, mock_get_db):
        """Test cursor cleanup in get_weight endpoint."""
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
        # Verify cursor and connection cleanup
        mock_cursor.close.assert_called_once()
        mock_conn.close.assert_called_once()

    @patch('weight.get_db_connection')
    def test_get_weight_cursor_none_cleanup(self, mock_get_db):
        """Test cursor cleanup when cursor is None."""
        mock_conn = MagicMock()
        mock_get_db.return_value = mock_conn
        mock_conn.cursor.return_value = None

        response = self.client.get('/weight')

        self.assertEqual(response.status_code, 500)
        # Should not fail even if cursor is None
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
        # Verify cleanup
        mock_cursor.close.assert_called_once()
        mock_conn.close.assert_called_once()

    @patch('weight.get_db_connection')
    def test_get_item_cursor_cleanup(self, mock_get_db):
        """Test cursor and connection cleanup in get_item endpoint."""
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
        # Verify cleanup
        mock_cursor.close.assert_called_once()
        mock_conn.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
