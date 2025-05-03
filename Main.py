import firebase_admin
import base64
import os
import pyodbc
import logging
from pathlib import Path
from firebase_admin import credentials, auth, firestore
from flask import Flask, request, jsonify
from datetime import datetime
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)

# pyinstaller --onefile Server.py

cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

load_dotenv()

db_host = os.getenv("DB_HOST")
db_name = os.getenv("DN_NAME")
db_username = os.getenv("DB_USERNAME")
db_password = os.getenv("DB_PASSWORD")
connection = pyodbc.connect(f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={db_host};DATABASE={db_name};UID={db_username};PWD={db_password}")
cursor = connection.cursor()

app = Flask(__name__)

@app.route("/")
def home():
    return "Hello, This is the Flask App in IIS Server."

#-----------------------
# verify route 
#-----------------------
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
        print(e)
        return jsonify({"error": str(e)}), 401

#-----------------------
# history route 
#-----------------------
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

@app.route('/history', methods=['GET'])
def loadhistory():
    pass

#-----------------------
# slips route 
#-----------------------
@app.route('/slips', methods=['POST'])
def loadslips():
    try:
        data = request.json
        file_path = data.get('path')
        if not file_path:
            return jsonify({"error": "Missing 'path' field in JSON"}), 400

        file = Path(file_path)
        if file.is_file():

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

#-----------------------
# users route 
#-----------------------
@app.route('/users', methods=['POST'])
def registerUser():
    try:
        data = request.json

        _name = data.get('name')
        _email = data.get('email')
        _password = data.get('password')
        _user = data.get('createduser')

        if not _email:
            return jsonify({
                "error": "ไม่พบอีเมล (Missing 'email')",
                "details": "กรุณาระบุฟิลด์ 'email' เพื่อดำเนินการลงทะเบียน (Please provide the 'email' field to register)"
            }), 400

        if not _password:
            return jsonify({
                "error": "ไม่พบรหัสผ่าน (Missing 'password')",
                "details": "กรุณาระบุฟิลด์ 'password' เพื่อดำเนินการลงทะเบียน (Please provide the 'password' field to register)"
            }), 400

        firebase_auth = auth.create_user(email=_email, password=_password)

        sql = """INSERT INTO users (uid, name, createdby, updateby) VALUES (?, ?, ?, ?)"""

        with connection.cursor() as cursor:
            cursor.execute(sql, (firebase_auth.uid, _name, _user, _user))
            connection.commit()

        return jsonify({
            "success": True,
            "message": f"ลงทะเบียนผู้ใช้เรียบร้อย (User registered successfully)"
        }), 200

    except auth.EmailAlreadyExistsError:
        return jsonify({
            "success": False,
            "error": "อีเมลนี้ถูกใช้งานแล้ว (Email already exists)",
            "details": "ไม่สามารถใช้ที่อยู่อีเมลนี้ในการลงทะเบียนได้ (This email address is already in use)"
        }), 400

    except Exception as e:
        logging.error(f"Error in /users [POST]: {str(e)}")
        return jsonify({
            "success": False,
            "error": "เกิดข้อผิดพลาดภายในระบบ (Internal Server Error)",
            "details": f"{str(e)}"
        }), 500

@app.route('/users', methods=['GET'])
def loadUsers():
    search = request.args.get('search')
    searchby = request.args.get('searchby')
    try:
        with connection.cursor() as cursor:
            if searchby is not None and search:
                if searchby == 'uid':
                    sql = """SELECT 
                                users.id,
                                users.uid,
                                users.name,
                                credits.credit,
                                user_created_credit.name as credit_created_by,
                                user_update_credit.name as credit_update_by,
                                users.enable,
                                users.blacklist,
                                user_created.name as user_created_by,
                                user_update.name as user_update_by,
                                users.syscreate,
                                users.sysupdate
                            FROM
                                users
                                LEFT JOIN credits ON credits.userid = users.id
                                LEFT JOIN users AS user_created_credit ON user_created_credit.id = credits.createdby
                                LEFT JOIN users AS user_update_credit ON user_update_credit.id = credits.updateby
                                LEFT JOIN users AS user_created ON user_created.id = users.createdby
                                LEFT JOIN users AS user_update ON user_update.id = users.updateby
                            WHERE users.uid LIKE ?"""
                elif searchby == 'name':
                    sql = """SELECT 
                                users.id,
                                users.uid,
                                users.name,
                                credits.credit,
                                user_created_credit.name as credit_created_by,
                                user_update_credit.name as credit_update_by,
                                users.enable,
                                users.blacklist,
                                user_created.name as user_created_by,
                                user_update.name as user_update_by,
                                users.syscreate,
                                users.sysupdate
                            FROM
                                users
                                LEFT JOIN credits ON credits.userid = users.id
                                LEFT JOIN users AS user_created_credit ON user_created_credit.id = credits.createdby
                                LEFT JOIN users AS user_update_credit ON user_update_credit.id = credits.updateby
                                LEFT JOIN users AS user_created ON user_created.id = users.createdby
                                LEFT JOIN users AS user_update ON user_update.id = users.updateby
                            WHERE users.name LIKE ?"""
                else:
                    return jsonify({
                        "error": f"Invalid value for 'searchby': '{searchby}'. Expected 'uid' or 'name'."
                    }), 400

                cursor.execute(sql, (f'%{search}%',))
            else:
                sql = """SELECT 
                            users.id,
                            users.uid,
                            users.name,
                            credits.credit,
                            user_created_credit.name as credit_created_by,
                            user_update_credit.name as credit_update_by,
                            users.enable,
                            users.blacklist,
                            user_created.name as user_created_by,
                            user_update.name as user_update_by,
                            users.syscreate,
                            users.sysupdate
                        FROM
                            users
                            LEFT JOIN credits ON credits.userid = users.id
                            LEFT JOIN users AS user_created_credit ON user_created_credit.id = credits.createdby
                            LEFT JOIN users AS user_update_credit ON user_update_credit.id = credits.updateby
                            LEFT JOIN users AS user_created ON user_created.id = users.createdby
                            LEFT JOIN users AS user_update ON user_update.id = users.updateby"""
                cursor.execute(sql)

            columns = [column[0] for column in cursor.description]
            result = [dict(zip(columns, row)) for row in cursor.fetchall()]
            return jsonify(result), 200
    except Exception as e:
        return jsonify({
            "error": "An unexpected error occurred while loading users.",
            "details": str(e)
        }), 500

@app.route('/users', methods=['PATCH'])
def updateUser():
    try:
        data = request.json
        if not data:
            return jsonify({
                "error": "ไม่พบข้อมูลที่ส่งเข้ามา (Missing JSON body)",
                "details": "กรุณาส่งข้อมูล JSON ที่ต้องการอัปเดต"
            }), 400

        _id = data.get('id')
        _updateby = data.get('updateby')

        if not _id:
            return jsonify({
                "error": "ไม่พบ ID ผู้ใช้งาน (Missing 'id')",
                "details": "ต้องระบุฟิลด์ 'id' เพื่อระบุผู้ใช้ที่ต้องการอัปเดต"
            }), 400

        if not _updateby:
            return jsonify({
                "error": "ไม่พบข้อมูลผู้ทำรายการ (Missing 'updateby')",
                "details": "ต้องระบุฟิลด์ 'updateby' เพื่อบันทึกว่าใครเป็นผู้แก้ไข"
            }), 400

        fields = []
        values = []

        if 'name' in data:
            fields.append("name = ?")
            values.append(data['name'])

        if 'enable' in data:
            fields.append("enable = ?")
            values.append(data['enable'])

        if 'blacklist' in data:
            fields.append("blacklist = ?")
            values.append(data['blacklist'])

        if not fields:
            return jsonify({
                "error": "ไม่มีข้อมูลที่สามารถอัปเดตได้",
                "details": "กรุณาระบุอย่างน้อยหนึ่งฟิลด์จาก: 'name', 'enable', 'blacklist'"
            }), 400

        fields.append("updateby = ?")
        values.append(_updateby)

        fields.append("sysupdate = GETDATE()")

        sql = f"UPDATE users SET {', '.join(fields)} WHERE id = ?"
        values.append(_id)

        with connection.cursor() as cursor:
            cursor.execute(sql, tuple(values))
            connection.commit()

        return jsonify({"message": "อัปเดตข้อมูลผู้ใช้เรียบร้อยแล้ว"}), 200

    except Exception as e:
        return jsonify({
            "error": "เกิดข้อผิดพลาดภายในเซิร์ฟเวอร์",
            "details": str(e)
        }), 500

#-----------------------
# credit route 
#-----------------------
@app.route('/credit', methods=['PUT'])
def updateCredit():
    try:
        data = request.json
        if not data:
            return jsonify({
                "error": "Missing JSON body. / ไม่พบข้อมูล JSON",
                "details": "Expected JSON body in request but got none. / โปรดระบุข้อมูลในรูปแบบ JSON มาด้วย"
            }), 400

        _userid = data.get('userid')
        _updateby = data.get('updateby')

        if not _userid:
            return jsonify({
                "error": "Missing field: 'userid' / ไม่พบฟิลด์ 'userid'",
                "details": "The 'userid' field is required to identify the credit record. / ต้องระบุ 'userid' เพื่อระบุรายการเครดิตที่ต้องการแก้ไข"
            }), 400

        if not _updateby:
            return jsonify({
                "error": "Missing field: 'updateby' / ไม่พบฟิลด์ 'updateby'",
                "details": "The 'updateby' field is required to track who updated the record. / ต้องระบุ 'updateby' เพื่อบันทึกว่าใครเป็นผู้ทำรายการแก้ไข"
            }), 400

        fields = []
        values = []

        if 'credit' in data:
            fields.append("credit = ?")
            values.append(data['credit'])

        if not fields:
            return jsonify({
                "error": "No update fields provided. / ไม่มีฟิลด์ข้อมูลสำหรับอัปเดต",
                "details": "At least the 'credit' field must be included to perform an update. / ต้องมีอย่างน้อยฟิลด์ 'credit' เพื่อดำเนินการอัปเดต"
            }), 400

        fields.append("updateby = ?")
        values.append(_updateby)
        fields.append("sysupdate = GETDATE()")

        sql = f"UPDATE credits SET {', '.join(fields)} WHERE userid = ?"
        values.append(_userid)

        with connection.cursor() as cursor:
            cursor.execute(sql, tuple(values))
            connection.commit()

        return jsonify({
            "message": "Credit updated successfully. / อัปเดตข้อมูลเครดิตเรียบร้อยแล้ว"
        }), 200

    except Exception as e:
        return jsonify({
            "error": "An unexpected error occurred while updating credit. / เกิดข้อผิดพลาดขณะอัปเดตข้อมูลเครดิต",
            "details": str(e)
        }), 500


# ฟังก์ชันสำหรับตัดส่วน "data:image/png;base64,"
def clean_base64_data(img_base64: str) -> str:
    if img_base64.startswith("data:image/png;base64,"):
        return img_base64.split("data:image/png;base64,")[1]
    return img_base64
    
def clean_base64_data(img_base64):
    if ',' in img_base64:
        return img_base64.split(',')[1]
    return img_base64

# flask run --reload


