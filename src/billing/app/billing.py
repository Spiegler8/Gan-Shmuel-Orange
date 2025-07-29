from flask import Flask, render_template, jsonify, request, send_file
from datetime import datetime
from collections import defaultdict
import mysql.connector
import requests
import pandas as pd
import glob
from mysql.connector import errorcode  
import os


app = Flask(__name__)


mysql_config = {
    'host': os.environ['DB_HOST'],
    'user': os.environ['DB_USER'],
    'password': os.environ['DB_PASSWORD'],
    'database': os.environ['DB_NAME']
}


@app.route("/")
def login():
    return render_template("index.html")


@app.route("/AdminHomePage")
def admin_home():
    return render_template("AdminHomePage.html")


@app.route("/ProviderHomePage")
def provider_home():
    return render_template("ProviderHomePage.html")


@app.route("/DeveloperHomePage")
def developer_home():
    return render_template("DeveloperHomePage.html")


@app.route("/")
def root():
    return "Billing service running", 200


@app.route("/health", methods=["GET"])
def health():
    conn = None
    cursor = None
    try:
        conn = mysql.connector.connect(**mysql_config)
        cursor = conn.cursor()
        cursor.execute("SELECT 1;")
        result = cursor.fetchone()
        if result and result[0] == 1:
            return "OK", 200
        else:
            return "Failure", 500
    except:
        return "Failure", 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.route("/provider", methods=["POST"])
def new_provider():
    data = request.get_json()
    if not data or "name" not in data:
        return jsonify({"error": "Missing provider name"}), 400
    provider = data["name"]
    if provider == "health" or not provider:
        return {"error": "Invalid provider name"}, 400

    conn = None
    cursor = None
    try:
        conn = mysql.connector.connect(**mysql_config)
        cursor = conn.cursor()

        # Check if provider already exists
        check_query = "SELECT id FROM Provider WHERE name = %s"
        cursor.execute(check_query, (provider,))
        result = cursor.fetchone()
        if result:
            return jsonify({"error": "Provider already exists"}), 400

        insert_query = "INSERT INTO Provider (name) VALUES (%s)"
        cursor.execute(insert_query, (provider,))
        conn.commit()

        return jsonify({"id": cursor.lastrowid, "name": provider}), 200

    except mysql.connector.Error as err:
        print("MySQL Error:", err)
        return jsonify({"error": str(err)}), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.route("/provider/<int:id>", methods=["PUT"])
def update_provider_name(id):
    data = request.get_json()
    if not data or "name" not in data:
        return jsonify({"error": "Missing provider name"}), 400

    new_name = data["name"]
    conn = None
    cursor = None
    try:
        conn = mysql.connector.connect(**mysql_config)
        cursor = conn.cursor()

        query = "UPDATE Provider SET name = %s WHERE id = %s"
        cursor.execute(query, (new_name, id))
        conn.commit()

        if cursor.rowcount == 0:
            return jsonify({"error": "Provider not found"}), 404

        return jsonify({"message": f"Provider {id} updated successfully"}), 200

    except mysql.connector.Error as err:
        print("MySQL Error:", err)
        return jsonify({"error": str(err)}), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.route("/rates", methods=["POST"])
def upload_rates():
    excel_files = glob.glob(
        "/in/*.xlsx"
    )  # direct path, no need to define UPLOAD_FOLDER

    if not excel_files:
        return jsonify({"message": "No Excel files found in /app/in"}), 400

    updated_rows = 0
    inserted_rows = 0
    conn = None
    cursor = None

    try:
        conn = mysql.connector.connect(**mysql_config)
        cursor = conn.cursor()

        for path in excel_files:
            df = pd.read_excel(path)

            for _, row in df.iterrows():
                product = str(row["Product"]).strip()
                rate = int(row["Rate"])
                scope = str(row["Scope"]).strip().upper()

                cursor.execute(
                    "SELECT rate FROM Rates WHERE product_id = %s AND UPPER(scope) = %s",
                    (product, scope),
                )
                result = cursor.fetchone()

                if result:
                    existing_rate = result[0]
                    if existing_rate != rate:
                        cursor.execute(
                            "UPDATE Rates SET rate = %s WHERE product_id = %s AND scope = %s",
                            (rate, product, scope),
                        )
                        updated_rows += 1
                else:
                    cursor.execute(
                        "INSERT INTO Rates (product_id, rate, scope) VALUES (%s, %s, %s)",
                        (product, rate, scope),
                    )
                    inserted_rows += 1

        conn.commit()
        return jsonify(
            {
                "message": "Rates processed from Excel files",
                "updated": updated_rows,
                "inserted": inserted_rows,
            }
        )

    except mysql.connector.Error as err:
        return jsonify({"error": str(err)}), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/rates', methods=['GET'])
def download_rates():
    try:
        files = glob.glob("/in/*.xlsx")        
        if not files:
            return jsonify({"error": "No Excel file found"}), 404
        
        file_path = files[0]
        return send_file(
            file_path,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name='rates_file.xlsx'
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500



@app.route("/truck", methods=["POST"])
def register_truck():
    data = request.get_json()

    if not data or "id" not in data or "provider" not in data:
        return jsonify({"error": "Missing truck id or provider"}), 400

    truck_id = data["id"]
    provider_id = data["provider"]

    conn = None
    cursor = None
    try:
        conn = mysql.connector.connect(**mysql_config)
        cursor = conn.cursor()

        # Check if provider exists
        cursor.execute("SELECT id FROM Provider WHERE id = %s", (provider_id,))
        if not cursor.fetchone():
            return jsonify({"error": "Provider not found"}), 404

        # Insert truck
        cursor.execute(
            "INSERT INTO Trucks (id, provider_id) VALUES (%s, %s)",
            (truck_id, provider_id),
        )
        conn.commit()
        return jsonify({"message": "Truck registered successfully"}), 201

    except mysql.connector.Error as err:
        if err.errno == errorcode.ER_DUP_ENTRY:
            return jsonify({'error': 'Truck ID already exists'}), 409
        return jsonify({'error': str(err)}), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.route("/truck/<int:id>", methods=["PUT"])
def update_truck(id):
    data = request.get_json()

    if not data:
        return jsonify({"error": "Missing provider"}), 400

    truck_id = data["id"]
    try:
        truck_id = int(truck_id)
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid truck id"}), 400

    conn = None
    cursor = None
    try:
        conn = mysql.connector.connect(**mysql_config)
        cursor = conn.cursor()

        # Check if truck exists
        cursor.execute("SELECT id FROM Trucks WHERE id = %s", (id,))
        if not cursor.fetchone():
            return jsonify({"error": "Truck not found"}), 404
        # Check if provider exists
        cursor.execute("SELECT id FROM Provider WHERE id = %s", (truck_id,))
        if not cursor.fetchone():
            return jsonify({"error": "Provider not found"}), 404
        # Update truck provider
        cursor.execute(
            "UPDATE Trucks SET provider_id = %s WHERE id = %s", (truck_id, id)
        )
        conn.commit()

        return jsonify({"message": f"Truck {id} updated successfully"}), 200

    except mysql.connector.Error as err:
        return jsonify({"error": str(err)}), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()



@app.route("/truck/<string:truck_id>", methods=["GET"])
def get_truck_details(truck_id):
    from_ts = request.args.get("from")
    to_ts = request.args.get("to")

    # Generate default timestamps if missing
    now = datetime.now()
    if not from_ts:
        from_ts = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).strftime("%Y%m%d%H%M%S")
    if not to_ts:
        to_ts = now.strftime("%Y%m%d%H%M%S")

    conn = None
    cursor = None

    try:
        conn = mysql.connector.connect(**mysql_config)
        cursor = conn.cursor(dictionary=True)

        # Check if the truck is registered
        cursor.execute("SELECT * FROM Trucks WHERE id = %s", (truck_id,))
        truck = cursor.fetchone()
        if not truck:
            return jsonify({"error": "Truck not found"}), 404

        # Fetch weight sessions from Weight system (external API)
        weight_url = f"http://weight:5000/item/{truck_id}"
        params = {
            "from": from_ts,
            "to": to_ts
        }

        weight_response = requests.get(weight_url, params=params)
        if weight_response.status_code != 200:
            return jsonify({"error": "Failed to fetch from weight system"}), 500

        weight_data = weight_response.json()

        return jsonify(
            {
                "id": truck_id,
                "tara": weight_data.get("tara", "na"),
                "sessions": weight_data.get("sessions", []),
            }
        )

    except mysql.connector.Error as err:
        print("DB Error:", err)
        return jsonify({"error": "Internal DB error"}), 500

    except Exception as e:
        print("Error:", e)
        return jsonify({"error": str(e)}), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/rates', methods=['GET'])
def download_rates():
    try:
        # Find the first .xlsx file in the /in directory
        files = glob.glob("/in/*.xlsx")
        if not files:
            return jsonify({"error": "No Excel file found"}), 404

        file_path = files[0]  # You can extend to support multiple later

        return send_file(
            file_path,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name='rates_file.xlsx'
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/bill/<provider_id>", methods=["GET"])
def get_bill(provider_id):
    from_str = request.args.get("from")
    to_str = request.args.get("to")

    if not from_str:
        from_str = datetime.now().strftime("%Y%m01000000")  # 1st of month
    if not to_str:
        to_str = datetime.now().strftime("%Y%m%d%H%M%S")

    # Validate date formats
    try:
        datetime.strptime(from_str, "%Y%m%d%H%M%S")
        datetime.strptime(to_str, "%Y%m%d%H%M%S")
    except ValueError:
        return jsonify({"error": "Invalid date format, use yyyymmddhhmmss"}), 400

    conn = cursor = None
    try:
        conn = mysql.connector.connect(**mysql_config)
        cursor = conn.cursor()

        # Get provider name
        cursor.execute("SELECT name FROM Provider WHERE id = %s", (provider_id,))
        provider_row = cursor.fetchone()
        if not provider_row:
            return jsonify({"error": "Provider not found"}), 404
        provider_name = provider_row[0]

        # Get all trucks of provider
        cursor.execute("SELECT id FROM Trucks WHERE provider_id = %s", (provider_id,))
        truck_rows = cursor.fetchall()
        if not truck_rows:
            return jsonify({"error": "No trucks registered for this provider"}), 404

        truck_ids = [row[0] for row in truck_rows]
        truck_count = len(truck_ids)

        # Collect all session IDs
        all_sessions = set()
        for truck_id in truck_ids:
            req = requests.get(
                f"http://localhost:5000/item/{truck_id}?from={from_str}&to={to_str}"
            )
            if req.status_code == 200:
                sessions = req.json().get("sessions", [])
                all_sessions.update(sessions)

        session_count = len(all_sessions)

        # Get all OUT sessions during time range
        req = requests.get(
            f"http://localhost:5000/weight?from={from_str}&to={to_str}&filter=out"
        )
        if req.status_code != 200:
            return jsonify({"error": "Failed to fetch weight data"}), 500

        out_sessions = req.json()

        # Filter relevant sessions (only those from provider's trucks)
        product_data = defaultdict(lambda: {"count": 0, "amount": 0})
        for session in out_sessions:
            if session["id"] not in all_sessions:
                continue
            neto = session.get("neto")
            product = session.get("product")
            if neto == "na" or not product:
                continue
            product_data[product]["count"] += 1
            product_data[product]["amount"] += neto

        # Fetch all rates
        cursor.execute("SELECT product, rate, scope FROM Rates")
        rate_rows = cursor.fetchall()
        rate_map = {}  # product -> rate
        for product, rate, scope in rate_rows:
            if product not in rate_map or scope == provider_id:
                rate_map[product] = rate

        # Prepare final product list
        products = []
        total_agorot = 0

        for product, data in product_data.items():
            rate = rate_map.get(product)
            if rate is None:
                continue  # Skip products with no rate
            pay = data["amount"] * rate
            total_agorot += pay
            products.append({
                "product": product,
                "count": str(data["count"]),
                "amount": data["amount"],
                "rate": rate,
                "pay": pay
            })

        return jsonify({
            "id": provider_id,
            "name": provider_name,
            "from": from_str,
            "to": to_str,
            "truckCount": truck_count,
            "sessionCount": session_count,
            "products": products,
            "total": total_agorot
        }), 200

    except mysql.connector.Error as err:
        return jsonify({"error": str(err)}), 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
