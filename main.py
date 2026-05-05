from flask import Flask, jsonify
import os

app = Flask(__name__)

@app.route("/")
def home():
    return "Server is working"

@app.route("/healthz")
def health():
    return jsonify({"ok": True})

@app.route("/get")
def get_data():
    return jsonify([
        ["Answer 1 - Page 1"],
        ["Answer 2 - Page 1", "Answer 2 - Page 2"]
    ])

if name == "__main__":
    port = int(os.environ.get("PORT", 3000))
    app.run(host="0.0.0.0", port=port)
