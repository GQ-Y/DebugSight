from flask import Flask, request, jsonify
import json
import logging
from threading import Event
from werkzeug.serving import make_server

app = Flask(__name__)
server = None

@app.route('/receive_data', methods=['POST'])
def receive_data():
    data = request.json
    logging.info(f"Received JSON data: {json.dumps(data, ensure_ascii=False)}")
    return jsonify({"status": "success", "message": "Data received and logged"}), 200

def run_flask_app(stop_event):
    global server
    server = make_server('0.0.0.0', 5001, app)
    server.serve_forever()

def stop_flask_app():
    global server
    if server:
        server.shutdown()