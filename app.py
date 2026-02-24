# app.py — integrated and fixed version
import os, random, sqlite3
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, g, jsonify
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib

# ---------- Flask Setup ----------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__)
app.secret_key = "super_secret_key_99"   # change to a secure random key in production
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024  # 2MB limit

# ---------- Config (email) ----------
SMTP_EMAIL = "mathi663four@gmail.com"
SMTP_PASS = "pked pgkp lxef bixq"

# ---------- Database helpers ----------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES|sqlite3.PARSE_COLNAMES)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(error):
    db = g.pop("db", None)
    if db:
        db.close()

def init_db():
    db = get_db()
    # users
    db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            email TEXT,
            mobile TEXT UNIQUE,
            password TEXT,
            date_of_birth TEXT,
            profile_pic TEXT,
            role TEXT DEFAULT 'user'
        )
    """)
    # otp
    db.execute("""
        CREATE TABLE IF NOT EXISTS otp_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            email TEXT,
            mobile TEXT,
            otp TEXT,
            purpose TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # permissions requests
    db.execute("""
        CREATE TABLE IF NOT EXISTS permissions_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)
    # tasks (note moved_at column added)
    db.execute("""
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        title TEXT,
        description TEXT,
        status TEXT DEFAULT 'todo',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        assigned_time TIMESTAMP,
        completed_time TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
""")


    # board titles
    db.execute("""
        CREATE TABLE IF NOT EXISTS board_titles (
            status TEXT PRIMARY KEY,
            title TEXT
        )
    """)
    existing = db.execute("SELECT COUNT(*) AS c FROM board_titles").fetchone()["c"]
    if existing == 0:
        db.executemany("INSERT INTO board_titles (status, title) VALUES (?, ?)", [
            ('todo', 'To Do'),
            ('doing', 'Doing'),
            ('done', 'Done')
        ])
    db.commit()

def send_task_email(to_email, username, title, description):
    sender = "mathi663four@gmail.com" 
    sender_password = "pked pgkp lxef bixq"    

    subject = f"New Task Assigned: {title}"
    body = f"""
    Hello {username},

    A new task has been assigned to you.

    📝 Task: {title}
    📄 Description: {description}

    Please log in to your dashboard to view details.

    Regards,
    Task Management System
    """

    msg = MIMEMultipart()
    msg['From'] = sender
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender, sender_password)
            server.send_message(msg)
            print("✅ Task email sent to", to_email)
    except Exception as e:
        print("❌ Email sending failed:", e)



def send_role_change_email(to_email, username, new_role):
    sender = "mathi663four@gmail.com"
    password = "pked pgkp lxef bixq"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Your Role Has Been Updated"
    msg["From"] = sender
    msg["To"] = to_email

    html_content = f"""
    <html>
    <body style="font-family:Poppins,Arial,sans-serif;">
      <h2 style="color:#6c63ff;">Role Updated Notification</h2>
      <p>Hello <b>{username}</b>,</p>
      <p>Your account role has been updated by the admin.</p>
      <p><b>New Role:</b> {new_role.capitalize()}</p>
      <hr>
      <p style="color:#555;">If you believe this change was made in error, please contact support.</p>
    </body>
    </html>
    """

    msg.attach(MIMEText(html_content, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender, password)
            server.send_message(msg)
        print(f"✅ Role change email sent to {to_email}")
    except Exception as e:
        print("❌ Email error (role change):", e)


# ---------- Email helper ----------
def send_mail(to_email, subject, body_html):
    try:
        msg = MIMEText(body_html, "html")
        msg["Subject"] = subject
        msg["From"] = SMTP_EMAIL
        msg["To"] = to_email
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(SMTP_EMAIL, SMTP_PASS)
        server.sendmail(SMTP_EMAIL, to_email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"Email Error: {e}")
        return False

def generate_and_send_otp(username, email, mobile, purpose):
    otp = str(random.randint(100000, 999999))
    db = get_db()
    db.execute("DELETE FROM otp_data WHERE username=? AND purpose=?", (username, purpose))
    db.execute("INSERT INTO otp_data (username, email, mobile, otp, purpose) VALUES (?,?,?,?,?)",
               (username, email, mobile, otp, purpose))
    db.commit()
    body = f"<h2>Verification Code</h2><p>Your OTP for {purpose.replace('_',' ')} is: <b>{otp}</b></p>"
    send_mail(email, "Security Code", body)

def verify_otp(username, entered_otp, purpose):
    db = get_db()
    row = db.execute("SELECT * FROM otp_data WHERE username=? AND purpose=?", (username, purpose)).fetchone()
    return row and row["otp"] == entered_otp

# ---------- Auth decorators ----------
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'admin':
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.template_filter('to_datetime')
def to_datetime(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


# ---------- Helper functions ----------
def get_user_by_mobile(mobile):
    db = get_db()
    return db.execute("SELECT * FROM users WHERE mobile=?", (mobile,)).fetchone()

def get_user_by_username(username):
    db = get_db()
    return db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()

def get_user_tasks(user_id):
    db = get_db()
    return db.execute("SELECT * FROM tasks WHERE user_id=? ORDER BY created_at DESC", (user_id,)).fetchall()

def get_board_titles():
    db = get_db()
    rows = db.execute("SELECT status, title FROM board_titles").fetchall()
    return {row['status']: row['title'] for row in rows}

# ---------- Routes ----------
@app.route('/')
def index():
    return redirect(url_for('login'))

# ---------- Register ----------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        db = get_db()
        data = request.form
        if data.get('password') != data.get('confirm_password'):
            return render_template("register.html", message="❌ Passwords do not match", alert="error")
        hashed = generate_password_hash(data['password'])
        try:
            db.execute("INSERT INTO users (username, email, mobile, date_of_birth, password, profile_pic) VALUES (?,?,?,?,?,?)",
                       (data['username'], data['email'], data['mobile'], data['dob'], hashed, "default.png"))
            db.commit()
            return render_template("login.html", message="✅ Registered! Please Login", alert="success")
        except Exception as e:
            print("Register error:", e)
            return render_template("register.html", message="❌ Mobile or Email already exists", alert="error")
    return render_template("register.html")

# ---------- Login ----------
@app.route('/login', methods=['GET', 'POST'])
def login():
    message = None
    alert = None

    if request.method == 'POST':
        mobile = request.form['mobile']
        password = request.form['password']

        conn = sqlite3.connect('database.db')
        cur = conn.cursor()
        cur.execute("SELECT id, username, password, role FROM users WHERE mobile = ?", (mobile,))
        user = cur.fetchone()
        conn.close()

        if user:
            user_id, username, db_password, role = user
            if check_password_hash(db_password, password):
                session['user_id'] = user_id
                session['username'] = username
                session['role'] = role

                # ✅ Redirect based on role
                if role == 'admin':
                    return redirect(url_for('admin_dashboard'))
                else:
                    return redirect(url_for('dashboard'))
            else:
                message = "Incorrect password. Please try again."
                alert = "error"
        else:
            message = "No account found with this mobile number."
            alert = "error"

    return render_template('login.html', message=message, alert=alert)


# ---------- Dashboard ----------
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if session.get('role') != 'user':
        return redirect(url_for('admin_dashboard'))
    
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
    tasks = db.execute("SELECT * FROM tasks WHERE user_id=?", (user['id'],)).fetchall()
    age = "N/A"
    if user['date_of_birth']:
        try:
            dob = datetime.strptime(user['date_of_birth'], "%Y-%m-%d")
            today = datetime.today()
            age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        except:
            pass
    titles = get_board_titles()
    return render_template("dashboard.html", user=user, age=age, tasks=tasks, titles=titles)

# ---------- Edit Profile ----------
@app.route("/edit-profile", methods=["GET", "POST"])
@login_required
def edit_profile():
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
    if request.method == "POST":
        filename = user['profile_pic']
        if 'remove_pic' in request.form:
            filename = "default.png"
        elif 'profile_pic' in request.files:
            file = request.files['profile_pic']
            if file and file.filename != '':
                filename = secure_filename(f"{user['id']}_{file.filename}")
                file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
        db.execute("UPDATE users SET username=?, email=?, date_of_birth=?, profile_pic=? WHERE id=?",
                   (request.form['username'], request.form['email'], request.form['dob'], filename, user['id']))
        db.commit()
        session["user"] = request.form['username']
        return redirect(url_for("dashboard"))
    return render_template("editprofile.html", user=user)

# ---------- Forgot Password ----------
@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    db = get_db()
    step, message, alert = "send_mobile", None, "error"
    if request.method == "POST":
        if "send_otp" in request.form:
            user = db.execute("SELECT * FROM users WHERE mobile=?", (request.form['mobile'],)).fetchone()
            if user:
                session["reset_user"] = user["username"]
                generate_and_send_otp(user["username"], user["email"], user["mobile"], "forgot_password")
                step, alert = "verify_otp", "success"
                message = "✅ OTP sent to email!"
            else:
                message = "❌ Mobile not found"
        elif "verify_otp" in request.form:
            if verify_otp(session.get("reset_user"), request.form['otp'], "forgot_password"):
                step, alert = "new_password", "success"
            else:
                step, message = "verify_otp", "❌ Invalid OTP"
        elif "update_password" in request.form:
            hashed = generate_password_hash(request.form['new_password'])
            db.execute("UPDATE users SET password=? WHERE username=?", (hashed, session.get("reset_user")))
            db.commit()
            session.pop("reset_user", None)
            return render_template("login.html", message="✅ Password Reset Successful", alert="success")
    return render_template("forgotpassword.html", step=step, message=message, alert=alert)

# ---------- Change Password ----------
@app.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
    step = "send_otp"
    if request.method == "POST":
        if "send_otp" in request.form:
            generate_and_send_otp(user["username"], user["email"], user["mobile"], "change_password")
            step = "otp"
        elif "verify_otp" in request.form:
            if verify_otp(user["username"], request.form['otp'], "change_password"):
                step = "new_password"
            else:
                step = "otp"
        elif "update_password" in request.form:
            hashed = generate_password_hash(request.form['new_password'])
            db.execute("UPDATE users SET password=? WHERE username=?", (hashed, user["username"]))
            db.commit()
            return redirect(url_for("dashboard"))
    return render_template("changepassword.html", step=step)

# ---------- Request Permission ----------
@app.route("/request-permission")
@login_required
def request_permission():
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
    existing = db.execute("SELECT * FROM permissions_requests WHERE user_id=? AND status='pending'", (user['id'],)).fetchone()
    if not existing:
        db.execute("INSERT INTO permissions_requests (user_id, username) VALUES (?, ?)", (user['id'], user['username']))
        db.commit()
    return redirect(url_for("dashboard"))

# ---------- Update Task Status  ----------
@app.route('/update_task_status', methods=['POST'])
@login_required
def update_task_status():
    """Update a task's status when user moves it on their board."""
    data = request.get_json()
    task_id = data.get('id')
    new_status = (data.get('status') or '').strip().lower()

    db = get_db()
    print("🟣 Received task update:", task_id, new_status)

    if not task_id or not new_status:
        return jsonify({'success': False, 'error': 'Missing task ID or status'}), 400

    # ✅ Treat any "done/completed" as done
    done_aliases = ['done', 'completed', 'finished', 'complete']

    if new_status in done_aliases:
        db.execute("""
            UPDATE tasks
            SET status = ?, completed_time = datetime('now'), updated_at = datetime('now')
            WHERE id = ?
        """, ('done', task_id))
        print(f"✅ Task {task_id} marked as done at {datetime.now()}")
    elif new_status == 'todo':
        db.execute("""
            UPDATE tasks
            SET status = ?, assigned_time = datetime('now'), updated_at = datetime('now')
            WHERE id = ?
        """, (new_status, task_id))
        print(f"🔁 Task {task_id} moved back to To Do")
    else:
        db.execute("""
            UPDATE tasks
            SET status = ?, updated_at = datetime('now')
            WHERE id = ?
        """, (new_status, task_id))
        print(f"🟦 Task {task_id} moved to {new_status}")

    db.commit()

    # ✅ Get latest completed_time to send to frontend
    row = db.execute("SELECT completed_time FROM tasks WHERE id=?", (task_id,)).fetchone()
    completed_time = row['completed_time'] if row else None

    return jsonify({'success': True, 'status': new_status, 'completed_time': completed_time})

# ---------- Update Column Title (admin AJAX) ----------
@app.route('/update-column-title', methods=['POST'])
@admin_required
def update_column_title():
    if not request.is_json:
        return jsonify({'error': 'Invalid request format'}), 400

    data = request.get_json()
    status = data.get('status')
    new_title = data.get('new_title', '').strip()

    if not status or not new_title:
        return jsonify({'error': 'Missing required data'}), 400

    db = get_db()

    # Prevent duplicate column titles
    existing = db.execute("SELECT 1 FROM board_titles WHERE title = ?", (new_title,)).fetchone()
    if existing:
        return jsonify({'error': 'A column with this title already exists'}), 400

    # Update column title
    db.execute("UPDATE board_titles SET title = ? WHERE status = ?", (new_title, status))
    db.commit()

    print(f"✅ Column '{status}' renamed to '{new_title}'")  # for debugging
    return jsonify({'success': True, 'new_title': new_title})




# ---------- User Task Board ----------
@app.route("/user/tasks")
@login_required
def user_tasks():
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
    tasks = get_user_tasks(user['id'])
    titles = get_board_titles()  # exact same order from DB

    return render_template("user_taskboard.html", tasks=tasks, user=user, titles=titles)


# ---------- Admin Dashboard ----------
@app.route('/admin/dashboard')
def admin_dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if session.get('role') != 'admin':
        return redirect(url_for('dashboard'))

    db = get_db()
    users = db.execute("SELECT * FROM users").fetchall()
    requests = db.execute("SELECT * FROM permissions_requests WHERE status='pending'").fetchall()
    tasks = db.execute("SELECT * FROM tasks").fetchall()  # ✅ Fetch all tasks
    return render_template("admin.html", users=users, requests=requests, tasks=tasks)


# ---------- Admin Edit ----------
@app.route('/admin/edit/<int:user_id>', methods=['GET', 'POST'])
@login_required
def admin_edit(user_id):
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        return "User not found", 404

    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        mobile = request.form['mobile']
        dob = request.form['dob']
        new_role = request.form['role']
        profile_pic = user['profile_pic']

        # ✅ Handle Profile Picture Update or Removal
        if 'profile_pic' in request.files and request.files['profile_pic'].filename != '':
            pic_file = request.files['profile_pic']
            filename = secure_filename(pic_file.filename)
            pic_path = os.path.join('static/uploads', filename)
            pic_file.save(pic_path)
            profile_pic = filename
        elif 'remove_pic' in request.form:
            if user['profile_pic']:
                try:
                    os.remove(os.path.join('static/uploads', user['profile_pic']))
                except:
                    pass
            profile_pic = None

        # ✅ Update user data in DB
        db.execute("""
            UPDATE users 
            SET username=?, email=?, mobile=?, date_of_birth=?, role=?, profile_pic=?
            WHERE id=?
        """, (username, email, mobile, dob, new_role, profile_pic, user_id))
        db.commit()

        # ✅ Check if role changed
        if new_role != user['role']:
            send_role_change_email(email, username, new_role)

        # ✅ NEW: Mark permission request as reviewed
        db.execute("UPDATE permissions_requests SET status='reviewed' WHERE user_id=?", (user_id,))
        db.commit()
        # --------------------------------------------

        return redirect(url_for('admin_dashboard'))

    return render_template('adminedit.html', user=user)



# ---------- Admin Tasks Page ----------
@app.route('/admin/tasks')
def admin_tasks():

    db = get_db()
    users = db.execute("SELECT id, username, profile_pic FROM users").fetchall()
    tasks = db.execute("""
        SELECT tasks.*, users.username, users.profile_pic 
        FROM tasks 
        LEFT JOIN users ON tasks.user_id = users.id
        ORDER BY tasks.created_at DESC
    """).fetchall()
    titles = get_board_titles()
    return render_template("admintask.html", users=users, tasks=tasks, titles=titles)

# ---------- Add Task (admin) ----------
@app.route('/add_task', methods=['POST'])
@admin_required
def add_task():
    title = request.form.get('title')
    description = request.form.get('description')
    assignee_id = request.form.get('assignee')

    if not title or not assignee_id:
        return redirect(url_for('admin_tasks'))

    db = get_db()

    # ✅ get first (default) status dynamically from board_titles
    first_col = db.execute("SELECT status FROM board_titles ORDER BY ROWID ASC LIMIT 1").fetchone()
    status = first_col['status'] if first_col else 'todo'

    # ✅ insert new task with that status
    db.execute("""
        INSERT INTO tasks (title, description, status, user_id, created_at, assigned_time)
        VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))
    """, (title, description, status, assignee_id))
    db.commit()

    # ✅ send task email
    user = db.execute("SELECT email, username FROM users WHERE id = ?", (assignee_id,)).fetchone()
    if user and user['email']:
        try:
            send_task_email(user['email'], user['username'], title, description)
        except Exception as e:
            print("Email send error:", e)

    return redirect(url_for('admin_tasks'))

#----------complete task---------------
@app.route('/complete_task/<int:task_id>')
@admin_required
def complete_task(task_id):
    db = get_db()
    db.execute("""
        UPDATE tasks 
        SET status = 'done', completed_time = datetime('now') 
        WHERE id = ?
    """, (task_id,))
    db.commit()
    return redirect(url_for('admin_tasks'))


# ---------- Add Column ----------
@app.route('/add-column', methods=['POST'])
@admin_required
def add_column():
    data = request.get_json()
    status_key = data.get('status')
    title = data.get('title')

    if not status_key or not title:
        return jsonify({'error': 'Missing data'}), 400

    db = get_db()
    db.execute(
        "INSERT OR REPLACE INTO board_titles (status, title) VALUES (?, ?)",
        (status_key, title)
    )
    db.commit()

    return jsonify({'success': True})


@app.route('/delete_task/<int:task_id>')
@admin_required
def delete_task(task_id):
    db = get_db()
    db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    db.commit()
    return redirect(url_for('admin_tasks'))




@app.route('/delete-column', methods=['POST'])
@admin_required
def delete_column():
    if not request.is_json:
        return jsonify({'error': 'Invalid request format'}), 400

    data = request.get_json()
    status = data.get('status')

    if not status:
        return jsonify({'error': 'Missing column ID'}), 400

    db = get_db()

    # Check total columns
    total_cols = db.execute("SELECT COUNT(*) AS c FROM board_titles").fetchone()['c']
    used_tasks = db.execute("SELECT COUNT(*) AS c FROM tasks WHERE status = ?", (status,)).fetchone()['c']

    # Prevent unsafe delete
    if total_cols <= 1:
        return jsonify({'error': "❌ You can't delete the only remaining column."}), 400
    if used_tasks > 0:
        return jsonify({'error': f"❌ This column has {used_tasks} task(s). Please move or delete them first."}), 400

    db.execute("DELETE FROM board_titles WHERE status = ?", (status,))
    db.commit()

    print(f"🗑️ Column '{status}' deleted successfully")  # for debugging
    return jsonify({'success': True})


# ---------- Admin Delete ----------
@app.route("/admin/delete/<int:user_id>")
@admin_required
def admin_delete(user_id):
    db = get_db()
    db.execute("DELETE FROM users WHERE id=?", (user_id,))
    db.execute("DELETE FROM permissions_requests WHERE user_id=?", (user_id,))
    db.commit()
    return redirect(url_for('admin_tasks', deleted=1))


# ---------- Logout ----------
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))



# ---------- Main ----------
if __name__ == "__main__":
    with app.app_context():
        init_db()
    app.run(debug=True)
