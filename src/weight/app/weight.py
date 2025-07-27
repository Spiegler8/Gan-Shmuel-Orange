
import os
from flask import Flask,request,jsonify
from datetime import datetime 
import mysql.connector

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
        query = """
            SELECT id, direction, bruto,neto, produce, containers
            FROM weights
            WHERE timestamp >= %s AND timestamp <= %s
            AND direction IN (%s)
            """ % ({placeholders})

        params = [t1,t2] + filters
        cursor.execute(query, params)
        rows = cursor.fetchall()

        for row in rows:
            row["containers"] = row["containers"].split(",") if row["containers"] else []

        cursor.close()
        conn.close()

        return jsonify(rows), 200
    
    except Exception as e:
        print("Error fetching weights:", e)
        return "Failure", 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
