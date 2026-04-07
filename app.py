# app.py
import sqlite3
import json
import urllib.request
from flask import Flask, request, jsonify, send_from_directory

import os

# --- Configuration ---
PORT = 8005
DB_NAME = "hospital_data.db"
# The API key is now read from an environment variable for security.
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_API_ENDPOINT = "https://api.openai.com/v1/chat/completions"
# ---------------------

app = Flask(__name__)

def initialize_database():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS financial_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hospital_name TEXT NOT NULL,
                report_date TEXT NOT NULL,
                data_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(hospital_name, report_date)
            )
        ''')
    print(f"Database '{DB_NAME}' initialized successfully.")

# --- API Routes ---

@app.route('/api/llm', methods=['POST'])
def handle_llm_request():
    try:
        client_data = request.get_json()
        if not client_data or 'promptContent' not in client_data:
            return jsonify({"error": "Invalid request, missing promptContent"}), 400

        openai_request_body = {
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": client_data["promptContent"]}],
            "temperature": 0.7,
            "max_tokens": 1500,
            "response_format": {"type": "json_object"}
        }

        req = urllib.request.Request(
            OPENAI_API_ENDPOINT,
            data=json.dumps(openai_request_body).encode('utf-8'),
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {OPENAI_API_KEY}'
            },
            method='POST'
        )

        with urllib.request.urlopen(req) as response:
            response_data = response.read()
            # Flask will handle content-type and status for jsonify
            return json.loads(response_data)

    except urllib.error.HTTPError as e:
        error_content = e.read().decode('utf-8')
        return jsonify({"error": f"OpenAI API Error: {e.code} - {error_content}"}), e.code
    except Exception as e:
        return jsonify({"error": f"Server error (LLM): {str(e)}"}), 500

@app.route('/api/upload', methods=['POST'])
def handle_upload_request():
    try:
        if 'file' not in request.files:
            return jsonify({"error": "No file part in the request"}), 400
        
        hospital_name = request.form.get("hospitalName")
        report_date = request.form.get("reportDate")
        uploaded_file = request.files["file"]

        if not all([hospital_name, report_date, uploaded_file.filename]):
            return jsonify({"error": "Missing form data (hospitalName, reportDate, or file)"}), 400

        file_content = uploaded_file.read().decode('utf-8')
        data_to_store = {"file_content": file_content}

        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO financial_reports (hospital_name, report_date, data_json) VALUES (?, ?, ?)",
                (hospital_name, report_date, json.dumps(data_to_store))
            )
        
        return jsonify({"message": f"Successfully uploaded and saved data for {hospital_name} for date {report_date}."})

    except Exception as e:
        return jsonify({"error": f"Server error (Upload): {str(e)}"}), 500

@app.route('/api/hospitals', methods=['GET'])
def handle_get_hospitals():
    try:
        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT hospital_name FROM financial_reports ORDER BY hospital_name")
            hospitals = [row[0] for row in cursor.fetchall()]
        return jsonify(hospitals)
    except Exception as e:
        return jsonify({"error": f"Failed to fetch hospitals: {str(e)}"}), 500

@app.route('/api/data', methods=['GET'])
def handle_get_data():
    try:
        hospital_name = request.args.get("hospitalName")
        start_date = request.args.get("startDate")
        end_date = request.args.get("endDate")

        if not all([hospital_name, start_date, end_date]):
            return jsonify({"error": "Missing query parameters"}), 400

        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT data_json FROM financial_reports WHERE hospital_name = ? AND report_date BETWEEN ? AND ? ORDER BY report_date DESC LIMIT 1",
                (hospital_name, start_date, end_date)
            )
            row = cursor.fetchone()

        if not row:
            return jsonify({"error": f"No data found for {hospital_name} in the specified date range."}), 404
        
        # The data is stored as a JSON string, so parse and return it
        return json.loads(row[0])

    except Exception as e:
        return jsonify({"error": f"Failed to fetch data: {str(e)}"}), 500

# --- Static File Serving ---

@app.route('/')
def serve_index():
    return send_from_directory('.', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('.', path)

# --- Main Execution ---

if __name__ == '__main__':
    initialize_database()
    # The host must be set to '0.0.0.0' to be accessible from outside the container.
    # Debug mode is turned off for production.
    app.run(host='0.0.0.0', port=os.environ.get('PORT', PORT))
