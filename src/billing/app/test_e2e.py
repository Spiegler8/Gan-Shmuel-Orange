import uuid
import pytest
import os
import pandas as pd
import requests
import mysql.connector

BASE_URL = "http://localhost:8000"

# Utility to generate a short ID within DB length limits
def short_id(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:6]}"

def fetch_provider_id_from_db(provider_name):
    conn = mysql.connector.connect(
        host="localhost",  # Or your DB container name if using Docker
        user="root",
        password="rootpass",
        database="billdb"
    )
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM Provider WHERE name = %s", (provider_name,))
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    if result:
        return result[0]
    return None

@pytest.fixture(scope="module")
def provider_id():
    provider_name = "E2E Provider"
    res = requests.post(f"{BASE_URL}/provider", json={"name": provider_name})
    print("Sent JSON:", {"name": provider_name})

    if res.status_code == 200:
        data = res.json()
        return data["id"]
    elif res.status_code == 400:
        print("Provider already exists")
        return fetch_provider_id_from_db(provider_name)
    else:
        raise Exception(f"Unexpected status: {res.status_code} - {res.text}")
        

def test_create_truck_with_valid_provider(provider_id):
    truck_id = short_id("T1")
    res = requests.post(f"{BASE_URL}/truck", json={"id": truck_id, "provider": provider_id})
    print("Status Code:", res.status_code)
    print("Response Text:", res.text)
    assert res.status_code == 201

def test_create_second_truck(provider_id):
    truck_id = short_id("T2")
    res = requests.post(f"{BASE_URL}/truck", json={"id": truck_id, "provider": provider_id})
    assert res.status_code == 201

def test_create_duplicate_truck_id(provider_id):
    truck_id = short_id("T3")
    res1 = requests.post(f"{BASE_URL}/truck", json={"id": truck_id, "provider": provider_id})
    assert res1.status_code == 201

    res2 = requests.post(f"{BASE_URL}/truck", json={"id": truck_id, "provider": provider_id})
    assert res2.status_code in [400, 409], f"Unexpected status code on duplicate: {res2.status_code}"



def test_upload_rates_mixed_insert_and_update():
 
    # Use relative path (must match your Docker volume mount, e.g., ./in:/in)
    os.makedirs("in", exist_ok=True)
    test_file_path = "in/test_rates.xlsx"  # changed from absolute to relative
    suffix = uuid.uuid4().hex[:6]
    # Mix of existing and new product/scope combinations
    test_data = pd.DataFrame([
        {"Product": f"NewProduct1_{suffix}", "Rate": 123, "Scope": "ALL"},
        {"Product": f"Mandarin_{suffix}", "Rate": 130, "Scope": "NEW"},
        {"Product": "InsertOnlyProduct1", "Rate": 200, "Scope": "E2E"},
        {"Product": "InsertOnlyProduct2", "Rate": 210, "Scope": "TEST"},
        {"Product": "TotallyNew1", "Rate": 200, "Scope": "E2E"},
        {"Product": "TotallyNew2", "Rate": 210, "Scope": "TEST"},  # <--- missing comma was here
        {"Product": "Navel", "Rate": 100, "Scope": "ALL"},         # Should trigger UPDATE
        {"Product": "Blood", "Rate": 112, "Scope": "ALL"},         # Same rate → no change
        {"Product": "Tangerine", "Rate": 92, "Scope": "ALL"},      # Same → no change
        {"Product": "Clementine", "Rate": 115, "Scope": "ALL"},    # Should trigger UPDATE
        {"Product": "Grapefruit", "Rate": 99, "Scope": "ALL"},     # Should trigger UPDATE
        {"Product": "Shamuti", "Rate": 84, "Scope": "ALL"},        # Same → no change
        {"Product": "NewProduct1", "Rate": 123, "Scope": "ALL"},   # Should INSERT
        {"Product": "Mandarin", "Rate": 130, "Scope": "NEW"},      # Should INSERT
    ])
    test_data.to_excel(test_file_path, index=False)

    res = requests.post("http://localhost:8000/rates")
    print("Status Code:", res.status_code)
    print("Response JSON:", res.json())

    # Clean up test file after the test
    os.remove(test_file_path)

    assert res.status_code == 200
    json_data = res.json()

    # Check the keys and reasonable values
    assert "inserted" in json_data
    assert "updated" in json_data
    assert json_data["inserted"] >= 1
    assert json_data["updated"] >= 1


def test_get_rates_file():
    url = "http://localhost:8000/rates"

    response = requests.get(url)

    # Check status code
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    # Check content type
    assert response.headers["Content-Type"] == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    ), f"Unexpected Content-Type: {response.headers['Content-Type']}"

    # Check content disposition (download name)
    content_disposition = response.headers.get("Content-Disposition", "")
    assert "attachment" in content_disposition
    assert "rates_file.xlsx" in content_disposition

    # Optional: Check content is non-empty
    assert len(response.content) > 0, "Excel file content is empty"

    # Optional: Save locally to inspect manually (during dev/debug)
    with open("test_downloaded_rates.xlsx", "wb") as f:
        f.write(response.content)

    print("✔ /rates file download successful")


# ======= Future tests =======

# def test_get_bill_empty():
#     res = requests.get(f"{BASE_URL}/bill")
#     assert res.status_code == 200
# ==============================


# --- Additional error tests ---

def test_create_provider_missing_name():
    res = requests.post(f"{BASE_URL}/provider", json={})
    assert res.status_code == 400
    assert "error" in res.json()

def test_create_provider_invalid_name():
    res = requests.post(f"{BASE_URL}/provider", json={"name": ""})
    assert res.status_code == 400
    assert "error" in res.json()

def test_create_truck_missing_id(provider_id):
    res = requests.post(f"{BASE_URL}/truck", json={"provider": provider_id})
    assert res.status_code == 400
    assert "error" in res.json()

def test_create_truck_missing_provider():
    truck_id = short_id("T4")
    res = requests.post(f"{BASE_URL}/truck", json={"id": truck_id})
    assert res.status_code == 400
    assert "error" in res.json()

def test_create_truck_nonexistent_provider():
    truck_id = short_id("T5")
    res = requests.post(f"{BASE_URL}/truck", json={"id": truck_id, "provider": 999999})
    assert res.status_code == 404
    assert "error" in res.json()

def test_create_truck_id_too_long(provider_id):
    long_id = "T" * 300  # exceeds typical DB column length limits
    res = requests.post(f"{BASE_URL}/truck", json={"id": long_id, "provider": provider_id})
    assert res.status_code == 500 or res.status_code == 400
    assert "error" in res.json()  
