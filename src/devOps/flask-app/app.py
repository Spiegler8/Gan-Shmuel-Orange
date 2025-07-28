from flask import Flask, request, send_from_directory, Response
import os
import mysql.connector
from datetime import datetime

app = Flask(__name__, static_folder='static')

CHAT_LOG_DIR = 'chatLogs'

def get_db_connection():
    return mysql.connector.connect(
        host=os.environ.get('MYSQL_HOST', 'localhost'),
        user=os.environ['MYSQL_USER'],
        password=os.environ['MYSQL_PASSWORD'],
        database=os.environ['MYSQL_DATABASE']
    )



@app.route('/', methods=['GET'])
def index():
    return send_from_directory('static', 'index.html')

@app.route('/<room>', methods=['GET'])
def room_index(room):
    return send_from_directory('static', 'index.html')

@app.route('/api/chat/<room>', methods=['GET'])
def get_chat(room):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT timestamp, username, message FROM messages WHERE room = %s ORDER BY timestamp ASC",
            (room,)
        )
        messages = cursor.fetchall()
        cursor.close()
        conn.close()

        # Format each message as requested: "[timestamp] username: message"
        lines = [f"[{ts}] {user}: {msg}" for ts, user, msg in messages]
        content = '\n'.join(lines)

        return Response(content, mimetype='text/plain'), 200
    except Exception as e:
        return f"Error reading messages: {e}", 500


@app.route('/api/chat/<room>', methods=['POST'])
def post_chat(room):
    username = request.form.get('username')
    message = request.form.get('msg')
    
    if not username or not message:
        return "Username and message are required!", 400

    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')  # for DATETIME column
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO messages (room, username, message, timestamp) VALUES (%s, %s, %s, %s)",
            (room, username, message, timestamp)
        )
        conn.commit()
        cursor.close()
        conn.close()
        return "Message received!", 200
    except Exception as e:
        return f"Error saving message: {e}", 500

if __name__ == '__main__':
    # Ensure the static directory exists
    if not os.path.exists('static'):
        os.makedirs('static')

    # Ensure the chat log directory exists
    if not os.path.exists(CHAT_LOG_DIR):
        os.makedirs(CHAT_LOG_DIR)
    
    # Run the Flask app
    app.run(host='0.0.0.0', port=5000)


