import csv
import json  # for parsing JSON file content
import mysql.connector
import os
from datetime import datetime
from flask import Flask, request, jsonify
from flask import render_template  # the ui
from io import StringIO

app = Flask(__name__)


# Connection function
def get_db_connection():
    return mysql.connector.connect(
        host=os.environ.get("MYSQL_HOST", "db"),
        user=os.environ.get("MYSQL_USER", "root"),
        password=os.environ.get("MYSQL_PASSWORD", "root"),
        database=os.environ.get("MYSQL_DATABASE", "weight")
    )


@app.route("/", methods=["GET"])
def home():
    return "Weight service is running", 200


@app.route("/health", methods=["GET"])
def health_check():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1;")
        cursor.fetchone()
        cursor.close()
        conn.close()
        return "OK", 200
    except Exception as e:
        print("Health check failed:", e)
        return "Failure", 500


# ----POST weight endpoint----

# Helper function to find the last session for a truck
def find_last_session(cursor, truck):
    cursor.execute("""
        SELECT id, direction FROM transactions
        WHERE truck = %s 
        ORDER BY datetime DESC LIMIT 1
    """, (truck,))
    return cursor.fetchone()


# Helper function to find the last "in" session for a truck
def find_last_in_session(cursor, truck):
    cursor.execute("""
        SELECT id, bruto, containers FROM transactions
        WHERE truck = %s AND direction = 'in' AND truckTara IS NULL
        ORDER BY datetime DESC LIMIT 1
    """, (truck,))
    return cursor.fetchone()


# Helper function to calculate neto weight for an "out" session
def calculate_neto(cursor, in_session, truck_tara):
    total_container_tara = 0
    unknown_containers = []

    # For each container, find its tare weight in the containers_registered table
    for container_id in in_session["containers"].split(","):
        if container_id:
            cursor.execute("""
                SELECT weight FROM containers_registered
                WHERE container_id=%s
                """, (container_id,))
            row = cursor.fetchone()

            if row and row["weight"] is not None:  # If the container exists and has a weight, add it to the total
                total_container_tara += row["weight"]
            else:  # If it doesn't exist or has no weight, add to unknown_containers
                unknown_containers.append(container_id)

    # If even one container’s weight is missing, we cannot calculate neto correctly
    if unknown_containers:
        return None
    else:
        return in_session["bruto"] - truck_tara - total_container_tara


@app.route("/weight", methods=["POST"])
def record_weight():
    conn = None
    cursor = None
    try:
        data = request.get_json(force=True)  # Reads the incoming JSON payload from the client request body

        # Extract and validate fields
        direction = data.get("direction")  # must be "in", "out", or "none"
        truck = data.get("truck", "na")  # truck license or "na" if not relevant
        containers = data.get("containers",
                              [])  # list of container IDs, or an empty list if the client didnt send a containers field
        weight = data.get("weight")  # bruto weight of the truck/containers
        unit = data.get("unit", "kg")  # "kg" or "lbs", defaults to "kg"
        force = data.get("force", False)  # if True, used for overwriting previous records
        produce = data.get("produce", "na")  # produce type, defaults to "na"

        # Validate required fields
        if direction not in ["in", "out", "none"]:
            return jsonify({"error": "Direction must be in, out, or none"}), 400
        if weight is None:
            return jsonify({"error": "Weight is required"}), 400

        # Convert containers to a list if it's a string
        if isinstance(containers, str):
            containers = [c.strip() for c in containers.split(",") if c.strip()]
        containers_str = ",".join(containers)

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        truck_tara = None
        neto = None
        last = find_last_session(cursor, truck)

        if direction == "in":
            if last and last["direction"] == "in" and not force:
                return jsonify({"error": "Cannot do 'in' after 'in' without force=True"}), 400
            if last and last["direction"] == "in" and force:
                # If force is True, delete the last "in" record
                cursor.execute("DELETE FROM transactions WHERE id = %s", (last["id"],))

        elif direction == "out":
            # Find the last "in" session for this truck
            in_session = find_last_in_session(cursor, truck)
            if not in_session:
                return jsonify({"error": "No matching 'in' session found for this truck"}), 400

            truck_tara = weight
            neto = calculate_neto(cursor, in_session, truck_tara)

            # Update the "in" session with truckTara and neto
            cursor.execute("""
                UPDATE transactions
                SET truckTara=%s, neto=%s
                WHERE id=%s               
            """, (truck_tara, neto, in_session["id"]))

        elif direction == "none":
            if last and last["direction"] == "in":
                return jsonify({"error": "'none' cannot follow 'in'"}), 400

        # Insert the new transaction record
        cursor.execute("""
            INSERT INTO transactions (datetime, direction, truck, containers, bruto, truckTara, neto, produce)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)             
        """, (timestamp, direction, truck, containers_str, weight, truck_tara, neto, produce))
        conn.commit()

        # Get the ID of the newly inserted record
        session_id = cursor.lastrowid

        # response for all directions
        response = {
            "id": session_id,
            "truck": truck,
            "bruto": weight
        }

        # if out also include truckTara and neto
        if direction == "out":
            response["truckTara"] = truck_tara
            response["neto"] = neto if neto is not None else "na"

        return jsonify(response), 201

    except Exception as e:
        if conn:
            conn.rollback()  # Rollback any changes if an error occurs
        return jsonify({"error": str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


# ----POST weight endpoint end----


@app.route("/weight", methods=["GET"])
def get_weight():
    # Get query parameters
    t1 = request.args.get("from")
    t2 = request.args.get("to")
    filters = request.args.get("filter", "in,out,none").split(",")

    # If the user didn’t send from, set it to today at midnight
    if not t1:
        t1 = datetime.now().strftime("%Y%m%d") + "000000"
    # If the user didn’t send to, set it to now
    if not t2:
        t2 = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        placeholders = ",".join(["%s"] * len(filters))
        query = f"""
            SELECT id, direction, bruto, neto, produce, containers
            FROM transactions
            WHERE datetime >= %s AND datetime <= %s
            AND direction IN ({placeholders})
            """

        params = [t1, t2] + filters
        cursor.execute(query, params)
        rows = cursor.fetchall()

        if not rows:
            return jsonify({"error": "No records found for given criteria"}), 404

        for row in rows:
            # Convert containers from comma-separated string to list
            row["containers"] = row["containers"].split(",") if row["containers"] else []
            # If neto is NULL in DB, return "na"
            row["neto"] = row["neto"] if row["neto"] is not None else "na"

        return jsonify(rows), 200

    except Exception as e:
        print("Error fetching weights:", e)
        return jsonify({"error": "Database query failed"}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@app.route("/session/<int:session_id>", methods=["GET"])
def get_session(session_id):
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Fetch the session details
        cursor.execute("""
            SELECT id, direction, truck, bruto, truckTara, neto 
            FROM transactions 
            WHERE id = %s
        """, (session_id,))

        # Fetch the first result (and only one)
        row = cursor.fetchone()
        if not row:
            return jsonify({"error": f"No records found for session {session_id}"}), 404

        # Always return truckTara and neto
        session_data = {
            "id": row["id"],
            "truck": row["truck"],
            "bruto": row["bruto"]
        }

        # Include truckTara and neto only for "out"
        if row["direction"] == "out":
            session_data["truckTara"] = row["truckTara"]
            session_data["neto"] = row["neto"] if row["neto"] is not None else "na"

        return jsonify(session_data), 200

    except Exception as e:
        print("Error fetching session:", e)
        return jsonify({"error": "Database query failed"}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@app.route("/item/<string:item_id>", methods=["GET"])
def get_item(item_id):
    t1 = request.args.get("from")
    t2 = request.args.get("to")

    # If the user didn’t send from, set it to today at midnight
    if not t1:
        first_of_month = datetime.now().replace(day=1, hour=0, minute=0, second=0)
        t1 = first_of_month.strftime("%Y-%m-%d %H:%M:%S")

    # If the user didn’t send to, set it to now
    if not t2:
        t2 = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
                       SELECT id, truck, truckTara, containers
                       FROM transactions
                       WHERE datetime >= %s AND datetime <= %s
                       AND (truck = %s OR FIND_IN_SET(%s, containers))
                       """, (t1, t2, item_id, item_id))
        rows = cursor.fetchall()

        # No results found
        if not rows:
            return jsonify({"error": f"No records found for item {item_id}"}), 404

        # Lists of all transaction IDs (sessions) that involve this item.
        sessions = [row["id"] for row in rows]

        tara = "na"

        # If the item is a truck
        trucks = [r for r in rows if r["truck"] == item_id]
        if trucks:
            # Last known truck tara
            for row in reversed(trucks):
                if row["truckTara"] is not None:
                    tara = row["truckTara"]
                    break

        # If the item is a container
        else:
            cursor.execute("""
                        SELECT weight FROM containers_registered WHERE container_ID = %s  
                        """, (item_id,))
            container_row = cursor.fetchone()
            if container_row and container_row["weight"] is not None:
                tara = container_row["weight"]

        return jsonify({
            "id": item_id,
            "tara": tara,
            "sessions": sessions
        }), 200

    except Exception as e:
        print("Error fetching item:", e)
        return jsonify({"error": "Database query failed"}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


# helper function for Post /batch-weight
"""
    Processes CSV content line-by-line, extracts container_id, weight, and unit,
    and inserts or updates them in the containers_registered table.
"""


def process_csv(content, conn):
    cursor = None
    try:
        cursor = conn.cursor()
        reader = csv.reader(StringIO(content.strip()))

        for row in reader:
            if len(row) != 2:
                continue  # skip invalid lines

            cid, value_unit = row
            cid = cid.strip()
            value_unit = value_unit.strip().lower()

            if value_unit.endswith('kg'):
                unit = 'kg'
                value = value_unit[:-2]
            elif value_unit.endswith('lbs'):
                unit = 'lbs'
                value = value_unit[:-3]
            else:
                raise ValueError(f"Missing or unsupported unit in line: {','.join(row)}")

            cursor.execute("""
                INSERT INTO containers_registered (container_id, weight, unit)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE 
                    weight = VALUES(weight),
                    unit = VALUES(unit)
            """, (cid, int(float(value)), unit))
    finally:
        if cursor:
            cursor.close()


# helper function for Post /batch-weight
"""
    Processes a JSON list of container objects and stores them in the database.
    Each object should contain: id, weight, and unit.
"""


def process_json(content, conn):
    cursor = None
    try:
        cursor = conn.cursor()
        data = json.loads(content)

        for entry in data:
            cid = entry.get("id")
            weight = entry.get("weight")
            unit = entry.get("unit")

            if not cid or weight is None or not unit:
                raise ValueError(f"Missing fields in entry: {entry}")

            cursor.execute("""
                INSERT INTO containers_registered (container_id, weight, unit)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE 
                    weight = VALUES(weight),
                    unit = VALUES(unit)
            """, (cid.strip(), int(float(weight)), unit.lower()))
    finally:
        if cursor:
            cursor.close()


"""
    Uploads a .csv or .json file to register multiple containers in the database.
"""


@app.route('/batch-weight', methods=['POST'])
def batch_weight():
    file = request.files.get('file')  # get uploaded file from form-data
    if not file:
        return jsonify({"error": "No file uploaded"}), 400
    conn = None
    try:
        content = file.read().decode("utf-8")  # decode file content
        conn = get_db_connection()  # connect to the database

        # Process based on file extension
        if file.filename.endswith('.csv'):
            process_csv(content, conn)
        elif file.filename.endswith('.json'):
            process_json(content, conn)
        else:
            return jsonify({"error": "Unsupported file format. Use .csv or .json"}), 400

        conn.commit()  # save all changes to DB
        return jsonify({"message": "Containers saved successfully"}), 201

    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        return jsonify({"error": f"Failed to process file: {str(e)}"}), 400
    finally:
        if conn:
            conn.close()


@app.route('/unknown', methods=['GET'])
def get_unknown():
    """
    Returns a list of all recorded containers that have unknown weight
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Get all registered container IDs
        cursor.execute("SELECT container_id FROM containers_registered")
        registered = set(row[0] for row in cursor.fetchall())

        # Get all container lists from transactions table
        cursor.execute("SELECT containers FROM transactions")
        all_containers = set()

        for (container_str,) in cursor.fetchall():
            if container_str:
                containers = [cid.strip() for cid in container_str.split(',')]
                all_containers.update(containers)

        # Find unregistered containers
        unknown_containers = all_containers - registered

        return jsonify(sorted(unknown_containers)), 200

    except Exception as e:
        print("Exception in /unknown:", e)
        return jsonify({"error": str(e)}), 500

    finally:
        cursor.close()
        conn.close()


# UI route to serve the frontend
@app.route("/weight-system")
def ui():
    return render_template("index.html")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
