from flask import Flask
app = Flask(__name__)

provider_id = {}
id = 1

@app.get("/")
def root():
    return {"message": "Billing service running"}

@app.route('/health', methods=['GET'])
def health():
    try:
        # Simulate DB check
        _ = {"db": "connected"}  # or list(providers.keys())
        return "OK", 200
    except:
        return "Failure", 500
    
@app.route("/<provider>", methods=["POST"])
def new_provider(provider):
    if provider == "health":
        return {"error": "Invalid provider name"}, 400
    global id
    if provider not in provider_id:
        provider_id[provider] = id
        id += 1
    else:
        return {"error": "Provider already exists"}, 400
    return { "id": provider_id[provider] , "name": provider }, 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)
