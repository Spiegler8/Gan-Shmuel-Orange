import requests
import time
import os

BASE_URL = os.getenv("BASE_URL", "http://localhost:5000")

def wait_for_service():
    for _ in range(30):
        try:
            r = requests.get(f"{BASE_URL}/health")
            if r.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(2)
    raise RuntimeError("Service not ready")

def test_00_service_up():
    wait_for_service()
    r = requests.get(f"{BASE_URL}/")
    assert r.status_code == 200
    assert "Weight service" in r.text


def test_01_post_in_and_out_weight():
    # 1. IN transaction
    payload_in = {
        "direction": "in",
        "truck": "TRUCK123",
        "containers": ["C1", "C2"],
        "weight": 10000,
        "unit": "kg"
    }
    r = requests.post(f"{BASE_URL}/weight", json=payload_in)
    assert r.status_code == 201
    in_id = r.json()["id"]

    # 2. Attempt duplicate in without force (should fail)
    r2 = requests.post(f"{BASE_URL}/weight", json=payload_in)
    assert r2.status_code == 400

    # 3. Duplicate in with force
    payload_in["force"] = True
    r3 = requests.post(f"{BASE_URL}/weight", json=payload_in)
    assert r3.status_code == 201

    # 4. OUT transaction (truckTara=6000)
    payload_out = {
        "direction": "out",
        "truck": "TRUCK123",
        "containers": ["C1", "C2"],
        "weight": 6000,
    }
    r4 = requests.post(f"{BASE_URL}/weight", json=payload_out)
    assert r4.status_code == 201
    out_json = r4.json()
    assert "truckTara" in out_json
    assert "neto" in out_json


def test_02_get_weight_list():
    r = requests.get(f"{BASE_URL}/weight")
    assert r.status_code in (200, 404)


def test_03_get_session_by_id():
    # Take the latest session ID from /weight
    r = requests.get(f"{BASE_URL}/weight")
    if r.status_code == 200:
        session_id = r.json()[0]["id"]
        r2 = requests.get(f"{BASE_URL}/session/{session_id}")
        assert r2.status_code == 200


def test_04_item_endpoint():
    r = requests.get(f"{BASE_URL}/item/TRUCK123")
    assert r.status_code in (200, 404)


def test_05_batch_weight_csv(tmp_path):
    csv_file = tmp_path / "containers.csv"
    csv_file.write_text("C1,100kg\nC2,120kg\n")
    with open(csv_file, "rb") as f:
        r = requests.post(f"{BASE_URL}/batch-weight", files={"file": f})
    assert r.status_code == 201


def test_06_unknown():
    r = requests.get(f"{BASE_URL}/unknown")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
