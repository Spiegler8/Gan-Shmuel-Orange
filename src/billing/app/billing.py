from flask import Flask
app = Flask(__name__)


@app.route('/health', methods=['GET'])
def health():
    try:
        # Simulate DB check
        _ = {"db": "connected"}  # or list(providers.keys())
        return "OK", 200
    except:
        return "Failure", 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)
