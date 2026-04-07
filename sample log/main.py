from flask import Flask, request, send_file
import datetime

app = Flask(__name__)

LOG_FILE = "sam3.log"

@app.route('/')
def index():
    return send_file("index.html")

@app.route('/log', methods=['POST'])
def log_data():
    data = request.json
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    log_entry = f"[{timestamp}] {data}\n"

    with open(LOG_FILE, "a") as f:
        f.write(log_entry)

    return {"status": "ok"}, 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)