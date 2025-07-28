
import os
from flask import Flask,request,jsonify
from datetime import datetime 
import mysql.connector
import json     # for parsing JSON file content

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

    
@app.route("/weight", methods=["POST"])
def record_weight():
    conn = None
    try:
        # Get database connection
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get JSON data from request
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['direction', 'truck', 'containers', 'bruto']
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"Missing required field: {field}"}), 400
        
        direction = data['direction']
        truck = data['truck']
        containers = data['containers']  # Should be a list of container IDs
        bruto = data['bruto']
        produce = data.get('produce', '')
        
        # Validate direction
        if direction not in ['in', 'out']:
            return jsonify({"error": "Direction must be 'in' or 'out'"}), 400
        
        # Convert containers list to comma-separated string for storage
        containers_str = ','.join(containers) if isinstance(containers, list) else str(containers)
        
        # Calculate neto and truckTara based on direction
        neto = None
        truck_tara = None
        current_time = datetime.now().isoformat()  # SQLite compatible timestamp
        
        if direction == 'in':
            # First weighing (with containers) - store all available data
            # We save everything we know right now, but can't calculate neto yet
            pass  # Just continue to the insertion at the end
            
        elif direction == 'out':
            # Second weighing (without containers) - this gives us truck tara
            truck_tara = bruto
            
            # Find the corresponding 'in' transaction for this truck
            cursor.execute("""
                SELECT id, bruto, containers FROM transactions 
                WHERE truck = ? AND direction = 'in' AND truckTara IS NULL 
                ORDER BY datetime DESC LIMIT 1
            """, (truck,))
            
            in_transaction = cursor.fetchone()
            
            if in_transaction:
                in_id = in_transaction['id']
                gross_weight = in_transaction['bruto']
                in_containers = in_transaction['containers']
                
                # Calculate total container tara weight
                container_ids = in_containers.split(',') if in_containers else []
                total_container_tara = 0
                unknown_containers = []
                
                
            for container_id in container_ids:
                # Check if container_id is not empty/whitespace
                if container_id.strip():  
                    # Look up this specific container's weight in the database
                    cursor.execute("""
                        SELECT weight FROM containers_registered 
                        WHERE container_id = ?
                    """, (container_id.strip(),))
                    
                    # Get the result (returns None if no matching container found)
                    container_weight = cursor.fetchone()
                    
                    # Check if we found the container AND it has a weight value
                    if container_weight and container_weight['weight'] is not None:
                        total_container_tara += container_weight['weight']
                    else:
                        # Container either doesn't exist OR exists but has NULL weight
                        unknown_containers.append(container_id.strip())


                # Calculate neto (fruit weight)
                if not unknown_containers:
                    neto = gross_weight - truck_tara - total_container_tara
                else:
                    neto = None  # Can't calculate if containers are unknown
                
                # Update the 'in' transaction with truck tara and neto
                cursor.execute("""
                    UPDATE transactions 
                    SET truckTara = ?, neto = ? 
                    WHERE id = ?
                """, (truck_tara, neto, in_id))
        
        # Insert new transaction record
        cursor.execute("""
            INSERT INTO transactions 
            (datetime, direction, truck, containers, bruto, truckTara, neto, produce) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (current_time, direction, truck, containers_str, bruto, truck_tara, neto, produce))
        
        conn.commit()
        transaction_id = cursor.lastrowid
        
        # Prepare response
        response_data = {
            "session_id": transaction_id,
            "direction": direction,
            "truck": truck,
            "containers": containers,
            "bruto": bruto,
            "datetime": current_time
        }
        
        if truck_tara is not None:
            response_data["truckTara"] = truck_tara
        
        if neto is not None:
            response_data["neto"] = neto
        elif direction == 'out' and neto is None:
            response_data["neto"] = "na"  # Some containers unknown
        
        return jsonify(response_data), 201
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            conn.close()

    

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
        t2 = datetime.now().strftime("%Y%m%d%H%M%S")

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
        
        params = [t1,t2] + filters
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
            return jsonify({"error": f"Session with id {session_id} not found"})
        
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




# helper function for Post /batch-weight
"""
    Processes CSV content line-by-line, extracts container_id, weight, and unit,
    and inserts or updates them in the containers_registered table.
"""
def process_csv(content, conn):
    cursor = conn.cursor()
    for line in content.strip().split('\n'):
        parts = line.strip().split(',')
        if len(parts) != 2:
            continue  # skip invalid lines

        cid, value_unit = parts
        cid = cid.strip()
        value_unit = value_unit.strip().lower()

        # Determine the unit and extract the numeric value
        if value_unit.endswith('kg'):
            unit = 'kg'
            value = value_unit[:-2]
        elif value_unit.endswith('lbs'):
            unit = 'lbs'
            value = value_unit[:-3]
        else:
            raise ValueError(f"Missing or unsupported unit in line: {line}")

        # Insert or update the record in the table
        cursor.execute("""
            INSERT OR REPLACE INTO containers_registered (container_id, weight, unit)
            VALUES (?, ?, ?)
        """, (cid, int(float(value)), unit))

# helper function for Post /batch-weight
"""
    Processes a JSON list of container objects and stores them in the database.
    Each object should contain: id, weight, and unit.
"""
def process_json(content, conn):
    cursor = conn.cursor()
    data = json.loads(content)

    for entry in data:
        cid = entry.get("id")
        weight = entry.get("weight")
        unit = entry.get("unit")

        if not cid or weight is None or not unit:
            raise ValueError(f"Missing fields in entry: {entry}")

        cursor.execute("""
            INSERT OR REPLACE INTO containers_registered (container_id, weight, unit)
            VALUES (?, ?, ?)
        """, (cid.strip(), int(float(weight)), unit.lower()))
   
"""
    Uploads a .csv or .json file to register multiple containers in the database.
"""   
@app.route('/batch-weight', methods=['POST'])
def batch_weight():
    file = request.files.get('file')  # get uploaded file from form-data
    if not file:
        return jsonify({"error": "No file uploaded"}), 400

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
        print("ValueError:", ve) #debug
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        print("Exception:", e) #debug
        return jsonify({"error": f"Failed to process file: {str(e)}"}), 400



if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
