from flask import Flask
from datetime import datetime 
import sqlite3 

app = Flask(__name__)


# opens a connection to the database
def get_db_connection():
    conn = sqlite3.connect('weight.db')
    conn.row_factory = sqlite3.Row # allows to access columns by name instead of index
    return conn

# health check
@app.route("/health", methods=["GET"])
def health_check():
    try:
        conn = get_db_connection() # connects to the database
        conn.excute("SELECT 1;") # runs a query to check if the database is reachable
        return "OK", 200
    except :
        return "Failure", 500
    
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
