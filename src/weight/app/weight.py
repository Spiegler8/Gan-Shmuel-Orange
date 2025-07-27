import os
import mysql.connector
from flask import Flask, request, jsonify
from datetime import datetime

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
