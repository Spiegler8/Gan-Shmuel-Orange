import os

import mysql.connector
from flask import Flask

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
    
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
