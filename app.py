import csv
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from functools import wraps
from flask import Flask, request, jsonify, render_template, Response, session, redirect, url_for
from flask_cors import CORS
import json
import sqlite3
import os
import io

app = Flask(__name__)
app.secret_key = 'super-secret-key-change-this-later'
CORS(app)

DB_PATH = 'linkedin_data.db'

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Existing data table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS linkedin_data (
            url TEXT PRIMARY KEY,
            type TEXT,
            first_name TEXT,
            last_name TEXT,
            job_title TEXT,
            company_name TEXT,
            location TEXT,
            industry TEXT,
            domain TEXT,
            employee_size TEXT,
            headquarters TEXT,
            timestamp TEXT,
            full_data TEXT
        )
    ''')
    
    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            password TEXT,
            role TEXT DEFAULT 'user',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Activity Logs table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS activity_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            email TEXT,
            action TEXT,
            details TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    ''')
    
    # Create default admin if not exists
    admin_email = 'admin@abs.com'
    cursor.execute("SELECT * FROM users WHERE email = ?", (admin_email,))
    if not cursor.fetchone():
        hashed_password = generate_password_hash('admin@abs.com')
        cursor.execute("INSERT INTO users (email, password, role) VALUES (?, ?, ?)", 
                       (admin_email, hashed_password, 'admin'))
    
    conn.commit()
    conn.close()

init_db()

# --- Auth Decorators ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'role' not in session or session['role'] != 'admin':
            return jsonify({"status": "error", "message": "Admin access required"}), 403
        return f(*args, **kwargs)
    return decorated_function

def log_activity(action, details=""):
    try:
        user_id = session.get('user_id')
        email = session.get('email', 'Guest')
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO activity_logs (user_id, email, action, details) VALUES (?, ?, ?, ?)", 
                       (user_id, email, action, details))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Log Error: {e}")

# --- Page Routes ---
@app.route('/login')
def login_page():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/')
@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')

@app.route('/admin')
@login_required
def admin_dashboard_page():
    if session.get('role') != 'admin':
        return redirect(url_for('dashboard'))
    return render_template('admin.html')

# --- Auth APIs ---
@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
    user = cursor.fetchone()
    conn.close()
    
    if user and check_password_hash(user['password'], password):
        session['user_id'] = user['id']
        session['email'] = user['email']
        session['role'] = user['role']
        log_activity("Login")
        return jsonify({"status": "success", "role": user['role']})
    
    return jsonify({"status": "error", "message": "Invalid email or password"}), 401

@app.route('/logout')
def logout():
    log_activity("Logout")
    session.clear()
    return redirect(url_for('login_page'))

# --- Admin APIs ---
@app.route('/api/admin/users', methods=['GET', 'POST'])
@admin_required
def manage_users():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    if request.method == 'POST':
        data = request.json
        email = data.get('email')
        password = data.get('password')
        role = data.get('role', 'user')
        
        try:
            hashed = generate_password_hash(password)
            cursor.execute("INSERT INTO users (email, password, role) VALUES (?, ?, ?)", (email, hashed, role))
            conn.commit()
            log_activity("User Created", f"Created account for {email}")
            return jsonify({"status": "success"})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 400
    
    cursor.execute("SELECT id, email, role, created_at FROM users")
    users = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({"status": "success", "users": users})

@app.route('/api/admin/users/<int:user_id>', methods=['DELETE'])
@admin_required
def delete_user(user_id):
    if user_id == session.get('user_id'):
        return jsonify({"status": "error", "message": "Cannot delete yourself"}), 400
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    log_activity("User Deleted", f"Deleted user ID {user_id}")
    return jsonify({"status": "success"})

@app.route('/api/admin/logs')
@admin_required
def get_logs():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM activity_logs ORDER BY timestamp DESC LIMIT 500")
    logs = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({"status": "success", "logs": logs})

@app.route('/export')
@login_required
def export_csv():
    try:
        # log export activity
        details = f"Filters: {request.args.to_dict()}"
        log_activity("Download CSV", details)
        
        # ... rest of export_csv logic ...
        # Get filter parameters
        f_type = request.args.get('type')
        f_titles = request.args.get('title', '').split(',') if request.args.get('title') else []
        f_company = request.args.get('company')
        f_locations = request.args.get('location', '').split(',') if request.args.get('location') else []
        f_industries = request.args.get('industry', '').split(',') if request.args.get('industry') else []
        f_domains = request.args.get('domain', '').split(',') if request.args.get('domain') else []
        f_sizes = request.args.get('size', '').split(',') if request.args.get('size') else []
        f_start_date = request.args.get('start_date')
        f_end_date = request.args.get('end_date')

        query = "SELECT type, first_name, last_name, job_title, company_name, location, industry, domain, employee_size, headquarters, url, timestamp FROM linkedin_data WHERE 1=1"
        params = []

        if f_type and f_type != 'All':
            query += " AND type = ?"
            params.append(f_type)
        
        if f_titles:
            placeholders = ','.join(['?'] * len(f_titles))
            query += f" AND job_title IN ({placeholders})"
            params.extend(f_titles)
            
        if f_company:
            query += " AND company_name LIKE ?"
            params.append(f"%{f_company}%")
            
        if f_locations:
            placeholders = ','.join(['?'] * len(f_locations))
            query += f" AND (location IN ({placeholders}) OR headquarters IN ({placeholders}))"
            params.extend(f_locations * 2)
            
        if f_industries:
            placeholders = ','.join(['?'] * len(f_industries))
            query += f" AND industry IN ({placeholders})"
            params.extend(f_industries)

        if f_sizes:
            placeholders = ','.join(['?'] * len(f_sizes))
            query += f" AND employee_size IN ({placeholders})"
            params.extend(f_sizes)

        if f_start_date:
            query += " AND DATE(timestamp) >= DATE(?)"
            params.append(f_start_date)
        if f_end_date:
            query += " AND DATE(timestamp) <= DATE(?)"
            params.append(f_end_date)

        query += " ORDER BY timestamp DESC"

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        output = io.StringIO()
        writer = csv.writer(output)
        
        # Header
        writer.writerow(['Type', 'First Name', 'Last Name', 'Job Title', 'Company Name', 'Location', 'Industry', 'Domain', 'Employee Size', 'Headquarters', 'LinkedIn URL', 'Extraction Date'])
        
        # Data
        for row in rows:
            writer.writerow(row)

        output.seek(0)
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-disposition": "attachment; filename=linkedin_extractions_filtered.csv"}
        )
    except Exception as e:
        return f"Error: {e}", 500

@app.route('/api/all', methods=['GET'])
def get_all_data():
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM linkedin_data ORDER BY timestamp DESC')
        rows = cursor.fetchall()
        conn.close()

        data_list = []
        for row in rows:
            data_list.append({
                "url": row['url'],
                "type": row['type'],
                "timestamp": row['timestamp'],
                "data": json.loads(row['full_data'])
            })

        return jsonify({"status": "success", "data": data_list}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/collect', methods=['POST'])
def collect_data():
    try:
        data = request.json
        if not data:
            return jsonify({"status": "error", "message": "No data received"}), 400

        url = data.get('url')
        if not url:
            return jsonify({"status": "error", "message": "URL is missing"}), 400

        # Filter specific fields as requested
        if data.get('email') == "Check Contact Info Section (Usually hidden)":
            data.pop('email', None)
        if data.get('aboutSummary') == "N/A":
            data.pop('aboutSummary', None)

        data_type = "Prospect" if "firstName" in data else "Company"
        
        # Log to server console with rich aesthetics
        border = "═" * 60
        print(f"\n{border}")
        print(f" 🚀 RECEIVED {data_type.upper()} UPDATE ")
        print(f" URL: {url}")
        print(f" Time: {data.get('timestamp', 'N/A')}")
        print("-" * 60)
        
        if data_type == "Prospect":
            print(f" 👤 Name:     {data.get('firstName')} {data.get('lastName')}")
            print(f" 💼 Title:    {data.get('jobTitle')}")
            print(f" 🏢 Company:  {data.get('companyName')}")
            print(f" 📍 Location: {data.get('location')}")
        else:
            print(f" 🏢 Company:  {data.get('companyName')}")
            print(f" 🌐 Domain:   {data.get('domain')}")
            print(f" 🏭 Industry: {data.get('industry')}")
            print(f" 👥 Size:     {data.get('employeeSize')}")
            print(f" 🗺️  HQ:       {data.get('headquarters')}")
        
        print(f"{border}\n")
        
        # Store in DB (Upsert - always updates existing records)
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO linkedin_data (
                url, type, first_name, last_name, job_title, company_name, 
                location, industry, domain, employee_size, headquarters, 
                timestamp, full_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                type=excluded.type,
                first_name=excluded.first_name,
                last_name=excluded.last_name,
                job_title=excluded.job_title,
                company_name=excluded.company_name,
                location=excluded.location,
                industry=excluded.industry,
                domain=excluded.domain,
                employee_size=excluded.employee_size,
                headquarters=excluded.headquarters,
                timestamp=excluded.timestamp,
                full_data=excluded.full_data
        ''', (
            url, 
            data_type,
            data.get('firstName'),
            data.get('lastName'),
            data.get('jobTitle'),
            data.get('companyName'),
            data.get('location'),
            data.get('industry'),
            data.get('domain'),
            data.get('employeeSize'),
            data.get('headquarters'),
            data.get('timestamp'),
            json.dumps(data)
        ))
        conn.commit()
        conn.close()

        return jsonify({"status": "success", "message": f"{data_type} stored successfully"}), 200
    except Exception as e:
        print(f"Error in /collect: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/find', methods=['GET'])
def find_data():
    url = request.args.get('url')
    if not url:
        return jsonify({"status": "error", "message": "URL parameter required"}), 400

    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT full_data FROM linkedin_data WHERE url = ?', (url,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return jsonify({"status": "found", "data": json.loads(row['full_data'])}), 200
        else:
            return jsonify({"status": "not_found", "message": "No data found for this URL"}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    print("LinkedIn Data Collector Backend running on http://192.168.100.135:3000")
    app.run(host='0.0.0.0', port=3000, debug=True)
