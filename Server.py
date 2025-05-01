import firebase_admin
from firebase_admin import credentials, auth, firestore
from flask import Flask, request, jsonify
from datetime import datetime
import base64
import os
import pyodbc
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)


# pyinstaller --onefile Server.py

# Initialize Firebase Admin SDK
cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

server = '192.168.10.162'
database = 'GLOBOT'
username = 'sa'
password = 'Admin@1234'
connection = pyodbc.connect(f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={server};DATABASE={database};UID={username};PWD={password}")
cursor = connection.cursor()

app = Flask(__name__)

# ฟังก์ชันสำหรับตัดส่วน "data:image/png;base64,"
def clean_base64_data(img_base64: str) -> str:
    if img_base64.startswith("data:image/png;base64,"):
        return img_base64.split("data:image/png;base64,")[1]
    return img_base64

@app.route("/")
def home():
    return "Hello, This is the Flask App in IIS Server."

@app.route('/verify', methods=['POST'])
def verify():
    data = request.json
    id_token = data.get('idToken')
    if not id_token:
        return jsonify({"error": "Missing ID Token"}), 400  
    try:
        decoded_token = auth.verify_id_token(id_token)
        user_id = decoded_token.get('uid')
        
        sql = '''SELECT 
                    users.id,
                    users.uid,
                    users.name,
                    users.enable,
                    users.blacklist,
                    rank.intlevel AS level,
                    credits.credit
                FROM users
                    LEFT JOIN rank ON rank.id = users.rank
                    LEFT JOIN credits ON credits.userid = users.id
                WHERE users.uid = ?'''   
                
        cursor.execute(sql, user_id)           
        columns = [column[0] for column in cursor.description]  
        result = [dict(zip(columns, row)) for row in cursor.fetchall()] 
        id = result[0]['id']
        uid = result[0]['uid']
        name = result[0]['name']
        enable = result[0]['enable']
        blacklist = result[0]['blacklist']
        level = result[0]['level']
        credit = int(result[0]['credit'])

        if enable:
            if not blacklist:
                return jsonify({"message": "Token is valid", "id": id, "uid": uid, "name": name, "level": level, "credit": credit, "verify": True}), 200
            else:
                return jsonify({"message": "your account has been blacklisted.", "uid": uid, "verify": False}), 200
        else:
            return jsonify({"message": "Your account has not been activated.", "uid": uid, "verify": False}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 401

@app.route('/history', methods=['POST'])
def history():
    try:
        data = request.json
        id_token = data.get('idToken')
        img_base64 = data.get('img_base64')

        if not id_token or not img_base64:
            return jsonify({"error": "Missing required fields"}), 400

        # Verify token and retrieve user ID
        decoded_token = auth.verify_id_token(id_token)
        user_id = decoded_token.get('uid')

        # Create user-specific directory
        upload_folder = f'.\slips\{user_id}'
        os.makedirs(upload_folder, exist_ok=True)

        # Decode and save image
        img_data = base64.b64decode(clean_base64_data(img_base64))
        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S-%f')[:-3]
        file_path = os.path.join(upload_folder, f"{user_id}_{timestamp}.png")

        with open(file_path, 'wb') as f:
            f.write(img_data)

        # Fetch user ID from database
        sql_user = '''SELECT id FROM users WHERE uid = ?'''
        with connection.cursor() as cursor:
            cursor.execute(sql_user, (user_id,))
            user_row = cursor.fetchone()

        if not user_row:
            return jsonify({"error": "User not found"}), 404

        # Insert into history
        user_id_in_db = user_row[0]
        sql_insert = '''INSERT INTO glohistory (userid, image) VALUES (?, ?)'''
        with connection.cursor() as cursor:
            cursor.execute(sql_insert, (user_id_in_db, file_path))
            connection.commit()

        return jsonify({"success": True, "message": "Image saved"}), 200

    except Exception as e:
        logging.error(f"Error in /history: {str(e)}")
        return jsonify({"success": False, "message":"Exception","error": str(e)}), 500

@app.route('/loadslips', methods=['POST'])
def loadslips():
    try:
        data = request.json  # รับ JSON payload
        file_path = data.get('path')
        if not file_path:
            return jsonify({"error": "Missing 'path' field in JSON"}), 400

        # ตรวจสอบว่าไฟล์มีอยู่หรือไม่
        file = Path(file_path)
        if file.is_file():
            # อ่านไฟล์และแปลงเป็น Base64
            with open(file, "rb") as f:
                encoded_file = base64.b64encode(f.read()).decode('utf-8')
            return jsonify({
                "success": True,
                "message": "File exists",
                "file_path": file_path,
                "img_base64": encoded_file
            }), 200
        else:
            return jsonify({
                "success": False,
                "message": "File does not exist",
                "path": file_path
            }), 404

    except Exception as e:
        logging.error(f"Error in /loadslips: {str(e)}")
        return jsonify({"error": str(e)}), 500

    
def clean_base64_data(img_base64):
    if ',' in img_base64:
        return img_base64.split(',')[1]
    return img_base64

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

