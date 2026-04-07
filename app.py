# app.py
import sqlite3
import json
import urllib.request
import os
from flask import Flask, request, jsonify, send_from_directory

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
    print("--- Received request for /api/upload ---")
    try:
        print(f"Request Headers: {request.headers}")
        print(f"Request Form Data: {request.form}")
        print(f"Request Files: {request.files}")

        if 'file' not in request.files:
            print("Error: 'file' not in request.files")
            return jsonify({"error": "No file part in the request"}), 400
        
        uploaded_file = request.files["file"]
        hospital_name = request.form.get("hospitalName")
        report_date = request.form.get("reportDate")

        if not uploaded_file or uploaded_file.filename == '':
            print("Error: No selected file or empty filename")
            return jsonify({"error": "No selected file"}), 400

        if not all([hospital_name, report_date]):
            print(f"Error: Missing form data. hospitalName: {hospital_name}, reportDate: {report_date}")
            return jsonify({"error": "Missing form data (hospitalName or reportDate)"}), 400

        print(f"Processing upload for {hospital_name} on {report_date} with file {uploaded_file.filename}")
        raw_bytes = uploaded_file.read()
        file_content = None
        try:
            file_content = raw_bytes.decode('utf-8')
            print("File decoded successfully as UTF-8.")
        except UnicodeDecodeError:
            print("UTF-8 decoding failed. Trying GBK...")
            try:
                file_content = raw_bytes.decode('gbk')
                print("File decoded successfully as GBK.")
            except UnicodeDecodeError:
                print("GBK decoding also failed. Returning error.")
                return jsonify({"error": "Unsupported file encoding. Please save the file as UTF-8 or GBK and re-upload."}), 400

        if file_content is None:
            print("Error: File content is None after decoding attempts.")
            return jsonify({"error": "An unexpected error occurred during file decoding."}), 500

        data_to_store = {"file_content": file_content}

        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO financial_reports (hospital_name, report_date, data_json) VALUES (?, ?, ?)",
                (hospital_name, report_date, json.dumps(data_to_store))
            )
        print("Data successfully saved to database.")
        return jsonify({"message": f"Successfully uploaded and saved data for {hospital_name} for date {report_date}."})

    except Exception as e:
        print(f"!!! An exception occurred in handle_upload_request: {str(e)}")
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
