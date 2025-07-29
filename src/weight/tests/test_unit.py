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


class WeightServiceTestCase(unittest.TestCase):

    def setUp(self):
        """Set up test fixtures before each test method."""
        self.app = app
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

        # Mock database connection
        self.mock_conn = MagicMock()
        self.mock_cursor = MagicMock()
        self.mock_conn.cursor.return_value = self.mock_cursor

    def tearDown(self):
        """Clean up after each test method."""
        pass

    def test_home_endpoint(self):
        """Test the home endpoint returns correct response."""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.decode(), 'Weight service is running')

    @patch('weight.get_db_connection')
    def test_health_check_success(self, mock_get_db):
        """Test health check when database is available."""
        mock_get_db.return_value = self.mock_conn
        self.mock_cursor.execute.return_value = None
        self.mock_cursor.fetchone.return_value = (1,)

        response = self.client.get('/health')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.decode(), 'OK')

        # Verify database interaction
        self.mock_cursor.execute.assert_called_with("SELECT 1;")
        self.mock_cursor.close.assert_called_once()
        self.mock_conn.close.assert_called_once()

    @patch('weight.get_db_connection')
    def test_health_check_failure(self, mock_get_db):
        """Test health check when database is unavailable."""
        mock_get_db.side_effect = mysql.connector.Error("Connection failed")

        response = self.client.get('/health')
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.data.decode(), 'Failure')

    @patch('weight.get_db_connection')
    @patch('weight.datetime')
    def test_record_weight_in_direction_success(self, mock_datetime, mock_get_db):
        """Test recording weight with 'in' direction."""
        # Setup
        mock_datetime.now.return_value.isoformat.return_value = "2023-01-01T10:00:00"
        mock_get_db.return_value = self.mock_conn
        self.mock_cursor.lastrowid = 123

        data = {
            'direction': 'in',
            'truck': 'TRUCK001',
            'containers': ['CONT001', 'CONT002'],
            'bruto': 5000,
            'produce': 'apples'
        }

        response = self.client.post('/weight',
                                    data=json.dumps(data),
                                    content_type='application/json')

        self.assertEqual(response.status_code, 201)
        response_data = json.loads(response.data)

        # Verify response structure
        self.assertEqual(response_data['session_id'], 123)
        self.assertEqual(response_data['direction'], 'in')
        self.assertEqual(response_data['truck'], 'TRUCK001')
        self.assertEqual(response_data['containers'], ['CONT001', 'CONT002'])
        self.assertEqual(response_data['bruto'], 5000)

        # Verify database insert was called
        self.mock_cursor.execute.assert_called()
        self.mock_conn.commit.assert_called_once()

    @patch('weight.get_db_connection')
    @patch('weight.datetime')
    def test_record_weight_out_direction_with_matching_in(self, mock_datetime, mock_get_db):
        """Test recording weight with 'out' direction when matching 'in' record exists."""
        # Setup
        mock_datetime.now.return_value.isoformat.return_value = "2023-01-01T11:00:00"
        mock_get_db.return_value = self.mock_conn
        self.mock_cursor.lastrowid = 124

        # Mock the SELECT query to find matching 'in' transaction
        mock_in_transaction = {
            'id': 123,
            'bruto': 5000,
            'containers': 'CONT001,CONT002'
        }

        # Mock container weights lookup
        container_weights = [
            {'weight': 100},  # CONT001
            {'weight': 150}  # CONT002
        ]

        self.mock_cursor.fetchone.side_effect = [mock_in_transaction] + container_weights

        data = {
            'direction': 'out',
            'truck': 'TRUCK001',
            'containers': [],
            'bruto': 1500  # truck tara
        }

        response = self.client.post('/weight',
                                    data=json.dumps(data),
                                    content_type='application/json')

        self.assertEqual(response.status_code, 201)
        response_data = json.loads(response.data)

        # Verify response includes calculated values
        self.assertEqual(response_data['truckTara'], 1500)
        # neto should be 5000 - 1500 - 100 - 150 = 3250
        self.assertEqual(response_data['neto'], 3250)

    @patch('weight.get_db_connection')
    def test_record_weight_missing_required_fields(self, mock_get_db):
        """Test recording weight with missing required fields."""
        mock_get_db.return_value = self.mock_conn

        data = {
            'direction': 'in',
            'truck': 'TRUCK001'
            # Missing 'containers' and 'bruto'
        }

        response = self.client.post('/weight',
                                    data=json.dumps(data),
                                    content_type='application/json')

        self.assertEqual(response.status_code, 400)
        response_data = json.loads(response.data)
        self.assertIn('Missing required field', response_data['error'])

    @patch('weight.get_db_connection')
    def test_record_weight_invalid_direction(self, mock_get_db):
        """Test recording weight with invalid direction."""
        mock_get_db.return_value = self.mock_conn

        data = {
            'direction': 'invalid',
            'truck': 'TRUCK001',
            'containers': ['CONT001'],
            'bruto': 5000
        }

        response = self.client.post('/weight',
                                    data=json.dumps(data),
                                    content_type='application/json')

        self.assertEqual(response.status_code, 400)
        response_data = json.loads(response.data)
        self.assertEqual(response_data['error'], "Direction must be 'in' or 'out'")

    @patch('weight.get_db_connection')
    def test_record_weight_database_error(self, mock_get_db):
        """Test recording weight when database error occurs."""
        mock_get_db.return_value = self.mock_conn
        self.mock_cursor.execute.side_effect = mysql.connector.Error("Database error")

        data = {
            'direction': 'in',
            'truck': 'TRUCK001',
            'containers': ['CONT001'],
            'bruto': 5000
        }

        response = self.client.post('/weight',
                                    data=json.dumps(data),
                                    content_type='application/json')

        self.assertEqual(response.status_code, 500)
        response_data = json.loads(response.data)
        self.assertIn('error', response_data)

        # Verify rollback was called
        self.mock_conn.rollback.assert_called_once()

    @patch('weight.get_db_connection')
    @patch('weight.datetime')
    def test_get_weight_success(self, mock_datetime, mock_get_db):
        """Test getting weight records successfully."""
        # Setup
        mock_datetime.now.return_value.strftime.side_effect = lambda fmt: {
            "%Y%m%d": "20230101",
            "%Y%m%d%H%M%S": "20230101120000"
        }[fmt]

        mock_get_db.return_value = self.mock_conn
        self.mock_cursor.fetchall.return_value = [
            {
                'id': 1,
                'direction': 'in',
                'bruto': 5000,
                'neto': 3250,
                'produce': 'apples',
                'containers': 'CONT001,CONT002'
            }
        ]

        response = self.client.get('/weight')

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.data)

        self.assertEqual(len(response_data), 1)
        self.assertEqual(response_data[0]['containers'], ['CONT001', 'CONT002'])
        self.assertEqual(response_data[0]['neto'], 3250)

    @patch('weight.get_db_connection')
    def test_get_weight_no_records(self, mock_get_db):
        """Test getting weight records when no records found."""
        mock_get_db.return_value = self.mock_conn
        self.mock_cursor.fetchall.return_value = []

        response = self.client.get('/weight?from=20230101000000&to=20230101235959')

        self.assertEqual(response.status_code, 404)
        response_data = json.loads(response.data)
        self.assertEqual(response_data['error'], 'No records found for given criteria')

    @patch('weight.get_db_connection')
    def test_get_weight_with_null_neto(self, mock_get_db):
        """Test getting weight records with null neto values."""
        mock_get_db.return_value = self.mock_conn
        self.mock_cursor.fetchall.return_value = [
            {
                'id': 1,
                'direction': 'out',
                'bruto': 1500,
                'neto': None,  # NULL in database
                'produce': 'apples',
                'containers': ''
            }
        ]

        response = self.client.get('/weight')

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.data)
        self.assertEqual(response_data[0]['neto'], 'na')

    @patch('weight.get_db_connection')
    def test_get_session_success(self, mock_get_db):
        """Test getting session by ID successfully."""
        mock_get_db.return_value = self.mock_conn
        self.mock_cursor.fetchone.return_value = {
            'id': 123,
            'direction': 'out',
            'truck': 'TRUCK001',
            'bruto': 1500,
            'truckTara': 1500,
            'neto': 3250
        }

        response = self.client.get('/session/123')

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.data)

        self.assertEqual(response_data['id'], 123)
        self.assertEqual(response_data['truck'], 'TRUCK001')
        self.assertEqual(response_data['truckTara'], 1500)
        self.assertEqual(response_data['neto'], 3250)

    @patch('weight.get_db_connection')
    def test_get_session_not_found(self, mock_get_db):
        """Test getting session when session ID doesn't exist."""
        mock_get_db.return_value = self.mock_conn
        self.mock_cursor.fetchone.return_value = None

        response = self.client.get('/session/999')

        self.assertEqual(response.status_code, 200)  # Note: API returns 200 even for not found
        response_data = json.loads(response.data)
        self.assertIn('not found', response_data['error'])

    @patch('weight.get_db_connection')
    def test_get_session_in_direction(self, mock_get_db):
        """Test getting session with 'in' direction (should not include truckTara/neto)."""
        mock_get_db.return_value = self.mock_conn
        self.mock_cursor.fetchone.return_value = {
            'id': 123,
            'direction': 'in',
            'truck': 'TRUCK001',
            'bruto': 5000,
            'truckTara': None,
            'neto': None
        }

        response = self.client.get('/session/123')

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.data)

        self.assertEqual(response_data['id'], 123)
        self.assertEqual(response_data['truck'], 'TRUCK001')
        self.assertEqual(response_data['bruto'], 5000)
        self.assertNotIn('truckTara', response_data)
        self.assertNotIn('neto', response_data)

    @patch('weight.get_db_connection')
    @patch('weight.datetime')
    def test_get_item_truck_success(self, mock_datetime, mock_get_db):
        """Test getting item information for a truck."""
        # Setup datetime mocking
        mock_now = MagicMock()
        mock_now.replace.return_value.strftime.return_value = "20230101000000"
        mock_datetime.now.return_value = mock_now
        mock_datetime.now.return_value.strftime.return_value = "20230101120000"

        mock_get_db.return_value = self.mock_conn
        self.mock_cursor.fetchall.return_value = [
            {
                'id': 123,
                'truck': 'TRUCK001',
                'truckTara': 1500,
                'containers': 'CONT001'
            },
            {
                'id': 124,
                'truck': 'TRUCK001',
                'truckTara': 1600,
                'containers': 'CONT002'
            }
        ]

        response = self.client.get('/item/TRUCK001')

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.data)

        self.assertEqual(response_data['id'], 'TRUCK001')
        self.assertEqual(response_data['tara'], 1600)  # Last known tara
        self.assertEqual(response_data['sessions'], [123, 124])

    @patch('weight.get_db_connection')
    @patch('weight.datetime')
    def test_get_item_container_success(self, mock_datetime, mock_get_db):
        """Test getting item information for a container."""
        # Setup datetime mocking
        mock_now = MagicMock()
        mock_now.replace.return_value.strftime.return_value = "20230101000000"
        mock_datetime.now.return_value = mock_now
        mock_datetime.now.return_value.strftime.return_value = "20230101120000"

        mock_get_db.return_value = self.mock_conn

        # First query returns transactions involving the container
        # Second query returns container weight from registered containers
        self.mock_cursor.fetchall.return_value = [
            {
                'id': 123,
                'truck': 'TRUCK001',
                'truckTara': None,
                'containers': 'CONT001,CONT002'
            }
        ]
        self.mock_cursor.fetchone.return_value = {'weight': 150}

        response = self.client.get('/item/CONT001')

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.data)

        self.assertEqual(response_data['id'], 'CONT001')
        self.assertEqual(response_data['tara'], 150)
        self.assertEqual(response_data['sessions'], [123])

    @patch('weight.get_db_connection')
    @patch('weight.datetime')
    def test_get_item_not_found(self, mock_datetime, mock_get_db):
        """Test getting item that doesn't exist."""
        # Setup datetime mocking
        mock_now = MagicMock()
        mock_now.replace.return_value.strftime.return_value = "20230101000000"
        mock_datetime.now.return_value = mock_now
        mock_datetime.now.return_value.strftime.return_value = "20230101120000"

        mock_get_db.return_value = self.mock_conn
        self.mock_cursor.fetchall.return_value = []

        response = self.client.get('/item/NONEXISTENT')

        self.assertEqual(response.status_code, 404)
        response_data = json.loads(response.data)
        self.assertIn('No records found', response_data['error'])

    def test_process_csv_valid_data(self):
        """Test processing valid CSV data."""
        csv_content = "CONT001,100kg\nCONT002,150lbs"
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        process_csv(csv_content, mock_conn)

        # Verify execute was called twice (once for each container)
        self.assertEqual(mock_cursor.execute.call_count, 2)

    def test_process_csv_invalid_unit(self):
        """Test processing CSV with invalid unit."""
        csv_content = "CONT001,100grams"  # Invalid unit
        mock_conn = MagicMock()

        with self.assertRaises(ValueError) as context:
            process_csv(csv_content, mock_conn)

        self.assertIn("Missing or unsupported unit", str(context.exception))

    def test_process_csv_invalid_format(self):
        """Test processing CSV with invalid format (wrong number of columns)."""
        csv_content = "CONT001,100kg,extra_column"
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        # Should skip invalid lines without raising exception
        process_csv(csv_content, mock_conn)

        # Should not call execute for invalid lines
        mock_cursor.execute.assert_not_called()

    def test_process_json_valid_data(self):
        """Test processing valid JSON data."""
        json_content = json.dumps([
            {"id": "CONT001", "weight": 100, "unit": "kg"},
            {"id": "CONT002", "weight": 150, "unit": "lbs"}
        ])

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        process_json(json_content, mock_conn)

        # Verify execute was called twice
        self.assertEqual(mock_cursor.execute.call_count, 2)

    def test_process_json_missing_fields(self):
        """Test processing JSON with missing required fields."""
        json_content = json.dumps([
            {"id": "CONT001", "weight": 100}  # Missing unit
        ])

        mock_conn = MagicMock()

        with self.assertRaises(ValueError) as context:
            process_json(json_content, mock_conn)

        self.assertIn("Missing fields", str(context.exception))

    def test_process_json_invalid_json(self):
        """Test processing invalid JSON."""
        json_content = "invalid json content"
        mock_conn = MagicMock()

        with self.assertRaises(json.JSONDecodeError):
            process_json(json_content, mock_conn)

    @patch('weight.get_db_connection')
    def test_batch_weight_csv_success(self, mock_get_db):
        """Test batch weight upload with CSV file."""
        mock_get_db.return_value = self.mock_conn

        csv_data = "CONT001,100kg\nCONT002,150lbs"
        file_data = BytesIO(csv_data.encode())

        response = self.client.post('/batch-weight',
                                    data={'file': (file_data, 'containers.csv')},
                                    content_type='multipart/form-data')

        self.assertEqual(response.status_code, 201)
        response_data = json.loads(response.data)
        self.assertEqual(response_data['message'], 'Containers saved successfully')
        self.mock_conn.commit.assert_called_once()

    @patch('weight.get_db_connection')
    def test_batch_weight_json_success(self, mock_get_db):
        """Test batch weight upload with JSON file."""
        mock_get_db.return_value = self.mock_conn

        json_data = json.dumps([
            {"id": "CONT001", "weight": 100, "unit": "kg"},
            {"id": "CONT002", "weight": 150, "unit": "lbs"}
        ])
        file_data = BytesIO(json_data.encode())

        response = self.client.post('/batch-weight',
                                    data={'file': (file_data, 'containers.json')},
                                    content_type='multipart/form-data')

        self.assertEqual(response.status_code, 201)
        response_data = json.loads(response.data)
        self.assertEqual(response_data['message'], 'Containers saved successfully')
        self.mock_conn.commit.assert_called_once()

    def test_batch_weight_no_file(self):
        """Test batch weight upload without file."""
        response = self.client.post('/batch-weight',
                                    data={},
                                    content_type='multipart/form-data')

        self.assertEqual(response.status_code, 400)
        response_data = json.loads(response.data)
        self.assertEqual(response_data['error'], 'No file uploaded')

    @patch('weight.get_db_connection')
    def test_batch_weight_unsupported_format(self, mock_get_db):
        """Test batch weight upload with unsupported file format."""
        mock_get_db.return_value = self.mock_conn

        file_data = BytesIO(b"some text data")

        response = self.client.post('/batch-weight',
                                    data={'file': (file_data, 'data.txt')},
                                    content_type='multipart/form-data')

        self.assertEqual(response.status_code, 400)
        response_data = json.loads(response.data)
        self.assertEqual(response_data['error'], 'Unsupported file format. Use .csv or .json')

    @patch('weight.get_db_connection')
    def test_batch_weight_processing_error(self, mock_get_db):
        """Test batch weight upload with processing error."""
        mock_get_db.return_value = self.mock_conn

        # Invalid CSV data that will cause processing error
        csv_data = "CONT001,100grams"  # Invalid unit
        file_data = BytesIO(csv_data.encode())

        response = self.client.post('/batch-weight',
                                    data={'file': (file_data, 'containers.csv')},
                                    content_type='multipart/form-data')

        self.assertEqual(response.status_code, 400)
        response_data = json.loads(response.data)
        self.assertIn('Missing or unsupported unit', response_data['error'])

    @patch('weight.get_db_connection')
    def test_database_connection_cleanup_on_error(self, mock_get_db):
        """Test that database connections are properly closed on errors."""
        mock_get_db.return_value = self.mock_conn
        self.mock_cursor.execute.side_effect = Exception("Database error")

        data = {
            'direction': 'in',
            'truck': 'TRUCK001',
            'containers': ['CONT001'],
            'bruto': 5000
        }

        response = self.client.post('/weight',
                                    data=json.dumps(data),
                                    content_type='application/json')

        self.assertEqual(response.status_code, 500)
        # Verify connection cleanup
        self.mock_conn.rollback.assert_called_once()
        self.mock_conn.close.assert_called_once()

    @patch('weight.get_db_connection')
    @patch('weight.datetime')
    def test_containers_list_to_string_conversion(self, mock_datetime, mock_get_db):
        """Test that containers list is properly converted to string for storage."""
        mock_datetime.now.return_value.isoformat.return_value = "2023-01-01T10:00:00"
        mock_get_db.return_value = self.mock_conn
        self.mock_cursor.lastrowid = 123

        data = {
            'direction': 'in',
            'truck': 'TRUCK001',
            'containers': ['CONT001', 'CONT002', 'CONT003'],
            'bruto': 5000
        }

        response = self.client.post('/weight',
                                    data=json.dumps(data),
                                    content_type='application/json')

        # Verify that execute was called with comma-separated string
        calls = self.mock_cursor.execute.call_args_list
        insert_call = calls[-1]  # Last call should be the INSERT
        insert_args = insert_call[0][1]  # Arguments to the INSERT query
        containers_arg = insert_args[3]  # containers is 4th argument (index 3)

        self.assertEqual(containers_arg, 'CONT001,CONT002,CONT003')

        def test_get_db_connection_with_environment_variables(self):
            """Test database connection function uses environment variables."""
        with patch.dict(os.environ, {
            'MYSQL_HOST': 'custom_host',
            'MYSQL_USER': 'custom_user',
            'MYSQL_PASSWORD': 'custom_password',
            'MYSQL_DATABASE': 'custom_database'
        }):
            with patch('mysql.connector.connect') as mock_connect:
                mock_connect.return_value = MagicMock()

                get_db_connection()

                mock_connect.assert_called_once_with(
                    host='custom_host',
                    user='custom_user',
                    password='custom_password',
                    database='custom_database'
                )

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
    def test_record_weight_with_none_connection_during_rollback(self, mock_get_db):
        """Test rollback handling when connection is None."""
        # Simulate connection becoming None before rollback
        mock_conn = MagicMock()
        mock_get_db.return_value = mock_conn

        # Mock execute to raise an exception after setting conn to None
        def execute_side_effect(*args, **kwargs):
            nonlocal mock_conn
            mock_conn = None
            raise mysql.connector.Error("Database error")

        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.execute.side_effect = execute_side_effect

        data = {
            'direction': 'in',
            'truck': 'TRUCK001',
            'containers': ['CONT001'],
            'bruto': 5000
        }

        response = self.client.post('/weight',
                                    data=json.dumps(data),
                                    content_type='application/json')

        self.assertEqual(response.status_code, 500)

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
