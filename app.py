from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from flask_mysqldb import MySQL
import MySQLdb
import config
import json
from flask import request, jsonify


app = Flask(__name__)
app.config['SESSION_COOKIE_NAME'] = 'edufeed_session'
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = False
app.config['SESSION_PERMANENT'] = False
app.secret_key = config.SECRET_KEY

from datetime import timedelta
app.permanent_session_lifetime = timedelta(minutes=15)  # Auto-logout after 15 minutes

# MySQL Configuration
app.config['MYSQL_HOST'] = config.MYSQL_HOST
app.config['MYSQL_USER'] = config.MYSQL_USER
app.config['MYSQL_PASSWORD'] = config.MYSQL_PASSWORD
app.config['MYSQL_DB'] = config.MYSQL_DB
app.config['MYSQL_CURSORCLASS'] = config.MYSQL_CURSORCLASS

mysql = MySQL(app)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        print("📩 Form Data:", request.form.to_dict())
        print("✅ Form submitted!")

        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role')
        department_name = request.form.get('department_name')
        year = request.form.get('year')
        college_name = request.form.get('college_name')

        print(f"🔍 name={name}, email={email}, role={role}, dept_name={department_name}, year={year}, college={college_name}")

        # Now fetch department_id from name
        cur = mysql.connection.cursor()
        cur.execute("SELECT id FROM departments WHERE name = %s", (department_name,))
        dept = cur.fetchone()
        print("🧭 Department fetched:", dept)

        if not dept:
            flash("⚠ Department not found in database.", "danger")
            cur.close()
            return render_template('register.html')

        department_id = dept['id']

        # Check for existing user
        cur.execute("SELECT * FROM users WHERE email = %s", (email,))
        if cur.fetchone():
            flash("❗ Email already exists.", "danger")
            cur.close()
            return render_template('register.html')

        hashed_password = generate_password_hash(password)

        cur.execute("""
            INSERT INTO users (name, email, password, role, department_id, year, college_name)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (name, email, hashed_password, role, department_id, year, college_name))
        mysql.connection.commit()
        cur.close()

        flash("✅ Registered successfully. Please log in.", "success")
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')

        cur = mysql.connection.cursor()
        cur.execute("SELECT id, name, email, password, role, department_id, year FROM users WHERE email=%s", (email,))
        user = cur.fetchone()
        cur.close()

        # Generic error so attackers can't tell what failed
        invalid_msg = 'Invalid email or password.'
        
        '''if not user or user['status'] != 'active':
            flash(invalid_msg, 'danger')
            return render_template('login.html')'''

        if not check_password_hash(user['password'], password):
            flash(invalid_msg, 'danger')
            return render_template('login.html')
        
        print("User fetched from DB:", user)

        session.clear()
        session.permanent = True  # Enable session timeout tracking
        session['loggedin'] = True
        session['id'] = user['id']
        session['name'] = user['name']
        session['role'] = user['role']
        session['department_id'] = user.get('department_id')
        session['year'] = user.get('year') if user['role'] == 'student' else None
        session['college_name'] = user.get('college_name')


        print("✅ Session after login:", dict(session))
        print("👤 User from DB:", user)

        # route by role from DB only
        if user['role'] == 'admin':
            flash('Welcome back, ' + user['name'], 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Welcome back, ' + user['name'], 'success')
            return redirect(url_for('dashboard'))


    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'loggedin' not in session:
        flash('Please log in first! OR Your session has expired; Please log in again!', 'warning')
        return redirect(url_for('login'))

    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT d.name AS department_name, f.year
        FROM feedback f
        JOIN departments d ON f.department_id = d.id
        WHERE f.user_id = %s
    """, (session['id'],))
    submitted_feedback = cur.fetchall()
    cur.close()

    # Convert to a set for easy checking in template
    submitted_set = {(row['department_name'], row['year']) for row in submitted_feedback}
    
    if request.method == 'POST':
        department_name = request.form.get('department_name')
        year = request.form.get('year')

        # Check if feedback already exists
        for item in submitted_feedback:
            if item['department_name'] == department_name and item['year'] == year:
                flash(f"You have already submitted feedback for {department_name} - {year}.", "info")
                return redirect(url_for('dashboard'))

        cur = mysql.connection.cursor()
        cur.execute("SELECT id FROM departments WHERE name = %s", (department_name,))
        department = cur.fetchone()
        cur.close()

        if not department:
            flash("Selected department not found in database.", "danger")
            return redirect(url_for('dashboard'))

        session['department_id'] = department['id']
        session['year'] = year

        return redirect(url_for('syllabus'))

    return render_template('dashboard.html', name=session.get('name'), submitted_feedback=submitted_feedback)


@app.route('/syllabus')
def syllabus():
    if 'loggedin' not in session:
        flash('Please log in to view the syllabus.', 'warning')
        return redirect(url_for('login'))

    department_id = session.get('department_id')
    year = session.get('year')

    if not department_id or not year:
        flash("Department or year not selected properly.", "danger")
        return redirect(url_for('dashboard'))

    year_mapping = {
        "First Year (FY)": "First Year",
        "Second Year (SY)": "Second Year",
        "Third Year (TY)": "Third Year"
    }

    year_display = year
    year = year_mapping.get(year, year)

    cur = mysql.connection.cursor()

    # Get department name
    cur.execute("SELECT name FROM departments WHERE id = %s", (department_id,))
    dept_row = cur.fetchone()
    department_name = dept_row['name'] if dept_row else 'Unknown Department'

    # Fetch subjects and topics
    cur.execute("""
        SELECT s.name AS subject, t.name AS topic
        FROM subjects s
        JOIN topics t ON s.id = t.subject_id
        WHERE s.department_id = %s AND s.year = %s
        ORDER BY s.name, t.name
    """, (department_id, year))

    data = cur.fetchall()
    cur.close()

    # Group topics under subjects
    syllabus_data = {}
    for row in data:
        subject = row['subject']
        topic = row['topic']
        syllabus_data.setdefault(subject, []).append(topic)

    # ✅ Print debug only after syllabus_data is formed
    print("📌 department_id:", department_id)
    print("📌 year:", year)
    print("📌 syllabus_data:", syllabus_data)

    return render_template(
        'syllabus.html',
        syllabus_data=syllabus_data,
        department=department_name,
        year=year_display
    )

# Feedback Page (normalized with feedback + feedback_answers)
@app.route('/feedback', methods=['GET', 'POST'])
def feedback():
    if 'loggedin' not in session:
        flash('Please log in first! OR Your session has expired; log in again!', 'warning')
        return redirect(url_for('login'))

    # Prevent double submissions (keeps your existing UX)
    if session.get('feedback_submitted'):
        flash("You've already submitted feedback.", 'info')
        return redirect(url_for('dashboard'))

    # use dict cursor for easier field access
    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    # department name: preferred from session if present, otherwise fetch from DB
    department_id = session.get('department_id')
    department_name = None
    if department_id:
        cur.execute("SELECT name FROM departments WHERE id = %s", (department_id,))
        dept_row = cur.fetchone()
        if dept_row:
            department_name = dept_row.get('name') if isinstance(dept_row, dict) else dept_row[0]
    if not department_name:
        department_name = session.get('department_name') or 'Unknown Department'

    role = session.get('role') or 'student'

    # fetch dynamic questions for logged-in role, ordered by id (exactly what admin saved)
    cur.execute("SELECT id, question_text FROM questions WHERE role = %s ORDER BY id", (role,))
    questions = cur.fetchall()
    total_questions = len(questions)

    if request.method == 'POST':
        # --- Ensure feedback table exists (metadata only) ---
        cur.execute("""
            CREATE TABLE IF NOT EXISTS feedback (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                department_id INT,
                year VARCHAR(50),
                submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        mysql.connection.commit()

        # --- Ensure answers table exists (normalized) ---
        cur.execute("""
            CREATE TABLE IF NOT EXISTS feedback_answers (
                id INT AUTO_INCREMENT PRIMARY KEY,
                feedback_id INT NOT NULL,
                question_id INT NOT NULL,
                answer VARCHAR(100),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (feedback_id) REFERENCES feedback(id) ON DELETE CASCADE,
                FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE
            )
        """)
        mysql.connection.commit()

        # Step 1 → insert into feedback metadata
        cur.execute(
            "INSERT INTO feedback (user_id, department_id, year) VALUES (%s, %s, %s)",
            (
                session.get('id'),
                department_id,
                session.get('year') if session.get('role') == 'student' else None
            )
        )
        feedback_id = cur.lastrowid

        # Step 2 → insert answers linked to feedback_id
        for idx, q in enumerate(questions, start=1):
            ans = request.form.get(f"q{idx}")
            if ans:
                cur.execute(
                    "INSERT INTO feedback_answers (feedback_id, question_id, answer) VALUES (%s, %s, %s)",
                    (feedback_id, q['id'], ans)
                )

        mysql.connection.commit()
        cur.close()

        # mark as submitted so user cannot submit twice
        session['feedback_submitted'] = True
        flash("✅ Feedback submitted successfully!", "success")

        return redirect(url_for('confirmation'))

    # GET -> render the page with department, year, role and dynamic questions
    cur.close()
    return render_template(
        'feedback.html',
        department=department_name,
        year=session.get('year'),
        role=role,
        questions=questions
    )

@app.route('/confirmation')
def confirmation():
    if 'loggedin' not in session:
        flash('Please log in first! OR Your session has expired; log in again!', 'warning')
        return redirect(url_for('login'))
    cur = mysql.connection.cursor()
    department_id = session.get('department_id')
    # Get department name
    cur.execute("SELECT name FROM departments WHERE id = %s", (department_id,))
    dept_row = cur.fetchone()
    department_name = dept_row['name'] if dept_row else 'Unknown Department'
    
    return render_template('confirmation.html',
        name=session.get('name'),
        department=department_name,
        year=session.get('year'),
        role=session.get('role')
        )



from functools import wraps
from flask import session, redirect, url_for, flash, render_template

def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get('loggedin'):
            flash('Please log in first.', 'warning')
            return redirect(url_for('login'))
        if session.get('role') != 'admin':
            flash('Unauthorized access.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return wrapper

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    if 'loggedin' not in session or session.get('role') != 'admin':
        flash("Unauthorized access.", "danger")
        return redirect(url_for('login'))

    cur = mysql.connection.cursor()

    # Fetch Quick Stats
    cur.execute("SELECT COUNT(*) AS total FROM users")
    total_users = cur.fetchone()['total']

    cur.execute("SELECT COUNT(*) AS total FROM departments")
    total_departments = cur.fetchone()['total']

    cur.execute("SELECT COUNT(*) AS total FROM subjects")
    total_subjects = cur.fetchone()['total']

    cur.execute("SELECT COUNT(*) AS total FROM feedback")
    total_feedbacks = cur.fetchone()['total']

    cur.close()

    return render_template(
        'admin_dashboard.html',
        name=session.get('name'),
        total_users=total_users,
        total_departments=total_departments,
        total_subjects=total_subjects,
        total_feedbacks=total_feedbacks
    )

@app.route('/admin/departments')
@admin_required
def admin_manage_departments():
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM departments ORDER BY name ASC")
    departments = cur.fetchall()
    cur.close()
    return render_template('manage_departments.html', departments=departments)


# Add Department
@app.route('/add_department', methods=['POST'])
@admin_required
def add_department():
    dept_name = request.form.get('department_name', '').strip()
    if dept_name:
        cur = mysql.connection.cursor()
        cur.execute("INSERT INTO departments (name) VALUES (%s)", (dept_name,))
        mysql.connection.commit()
        cur.close()
        flash("✅ Department added successfully", "success")
    else:
        flash("⚠️ Please enter a department name.", "warning")
    return redirect(url_for('admin_manage_departments'))


# Edit department (single)
@app.route('/edit_department/<int:dept_id>', methods=['POST'])
@admin_required
def edit_department(dept_id):
    new_name = request.form.get('new_name', '').strip()
    if new_name:
        cur = mysql.connection.cursor()
        cur.execute("UPDATE departments SET name=%s WHERE id=%s", (new_name, dept_id))
        mysql.connection.commit()
        cur.close()
        flash("✏ Department updated successfully", "success")
    else:
        flash("⚠️ Department name cannot be empty.", "warning")
    return redirect(url_for('admin_manage_departments'))


# Delete multiple departments (app-level cascade)
@app.route('/delete_departments', methods=['POST'])
@admin_required
def delete_departments():
    selected = request.form.getlist('selected_departments')
    if not selected:
        flash("⚠️ No departments selected.", "warning")
        return redirect(url_for('admin_manage_departments'))

    cur = mysql.connection.cursor()
    # delete related rows first (subjects, user links) to avoid FK errors
    for dept_id in selected:
        cur.execute("DELETE FROM subjects WHERE department_id=%s", (dept_id,))
        cur.execute("DELETE FROM users WHERE department_id=%s", (dept_id,))
        cur.execute("DELETE FROM departments WHERE id=%s", (dept_id,))
    mysql.connection.commit()
    cur.close()

    flash("🗑 Selected department(s) deleted.", "success")
    return redirect(url_for('admin_manage_departments'))


@app.route('/admin/syllabus')
@admin_required
def admin_manage_syllabus():
    cur = mysql.connection.cursor()

    # fetch all years (just distinct from subjects table or predefined list)
    years = ["First Year", "Second Year", "Third Year"]

    # fetch departments
    cur.execute("SELECT id, name FROM departments ORDER BY name")
    departments = cur.fetchall()

    # fetch subjects
    cur.execute("""
        SELECT s.id, s.name, s.year, d.name AS department
        FROM subjects s
        JOIN departments d ON s.department_id = d.id
        ORDER BY s.year, d.name, s.name
    """)
    subjects = cur.fetchall()

    # fetch topics
    cur.execute("""
        SELECT t.id, t.name, s.name AS subject
        FROM topics t
        JOIN subjects s ON t.subject_id = s.id
        ORDER BY s.name, t.name
    """)
    topics = cur.fetchall()

    cur.close()
    return render_template(
        'manage_syllabus.html',
        years=years,
        departments=departments,
        subjects=subjects,
        topics=topics
    )


# Add Subject
@app.route('/admin/syllabus/subject/add', methods=['POST'])
@admin_required
def add_subject():
    name = request.form['name']
    year = request.form['year']
    department_id = request.form['department_id']
    cur = mysql.connection.cursor()
    cur.execute("INSERT INTO subjects (name, year, department_id) VALUES (%s, %s, %s)",
                (name, year, department_id))
    mysql.connection.commit()
    cur.close()
    flash("✅ Subject added.", "success")
    return redirect(url_for('admin_manage_syllabus'))


# Add Topic
@app.route('/admin/syllabus/topic/add', methods=['POST'])
@admin_required
def add_topic():
    name = request.form['name']
    subject_id = request.form['subject_id']
    cur = mysql.connection.cursor()
    cur.execute("INSERT INTO topics (name, subject_id) VALUES (%s, %s)", (name, subject_id))
    mysql.connection.commit()
    cur.close()
    flash("✅ Topic added.", "success")
    return redirect(url_for('admin_manage_syllabus'))


# Delete Subjects
@app.route('/admin/syllabus/subject/delete', methods=['POST'])
@admin_required
def delete_subjects():
    ids = request.form.getlist("selected_subjects")
    if ids:
        cur = mysql.connection.cursor()
        cur.execute("DELETE FROM topics WHERE subject_id IN %s", (tuple(ids),))
        cur.execute("DELETE FROM subjects WHERE id IN %s", (tuple(ids),))
        mysql.connection.commit()
        cur.close()
        flash("🗑 Subjects deleted.", "success")
    return redirect(url_for('admin_manage_syllabus'))


# Delete Topics
@app.route('/admin/syllabus/topic/delete', methods=['POST'])
@admin_required
def delete_topics():
    ids = request.form.getlist("selected_topics")
    if ids:
        cur = mysql.connection.cursor()
        cur.execute("DELETE FROM topics WHERE id IN %s", (tuple(ids),))
        mysql.connection.commit()
        cur.close()
        flash("🗑 Topics deleted.", "success")
    return redirect(url_for('admin_manage_syllabus'))


# Manage Users
@app.route('/manage_users')
@admin_required
def manage_users():
    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    # fetch users with department join
    cur.execute("""
        SELECT u.id, u.name, u.email, u.role, u.year, u.college_name, d.name AS department_name
        FROM users u
        LEFT JOIN departments d ON u.department_id = d.id
    """)
    rows = cur.fetchall()

    users = []
    for row in rows:
        users.append({
            "id": row["id"],
            "name": row["name"],
            "email": row["email"],
            "role": row["role"],
            "year": row["year"],
            "college_name": row["college_name"],
            "department_name": row["department_name"]
        })
    cur.close()

    # fetch departments list for dropdown
    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cur.execute("SELECT id, name FROM departments ORDER BY name")
    departments = cur.fetchall()
    cur.close()

    return render_template("manage_users.html", users=users, departments=departments)



# Add User
from werkzeug.security import generate_password_hash

@app.route('/add_user', methods=['POST'])
def add_user():
    name = request.form['name']
    email = request.form['email']
    password = request.form['password']
    role = request.form['role']
    department = request.form.get('department', '')
    year = request.form.get('year', '')
    college = request.form.get('college', '')

    hashed_password = generate_password_hash(password)

    cur = mysql.connection.cursor()

    department_id = None
    if role == "student" or role == "internal":
        if department:
            cur.execute("SELECT id FROM departments WHERE name=%s", (department,))
            dept_row = cur.fetchone()
            if dept_row:
                department_id = dept_row['id']
    elif role == "external":
        # externals may or may not have department → store NULL if not provided
        if department:
            cur.execute("SELECT id FROM departments WHERE name=%s", (department,))
            dept_row = cur.fetchone()
            if dept_row:
                department_id = dept_row['id']

    cur.execute("""
        INSERT INTO users (name, email, password, role, department_id, year, college_name)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (name, email, hashed_password, role, department_id, year, college))
    
    mysql.connection.commit()
    cur.close()
    flash("✅ User added successfully.", "success")
    return redirect(url_for('manage_users'))

# Update User
@app.route('/update_user/<int:user_id>', methods=['POST'])
def update_user(user_id):
    data = request.get_json()  # because fetch() sends JSON
    name = data.get('name')
    email = data.get('email')
    role = data.get('role')
    department_id = data.get('department_id') or None
    year = data.get('year') or None
    college_name = data.get('college_name') or None

    cur = mysql.connection.cursor()
    cur.execute("""
        UPDATE users
        SET name=%s, email=%s, role=%s, department_id=%s, year=%s, college_name=%s
        WHERE id=%s
    """, (name, email, role, department_id, year, college_name, user_id))
    mysql.connection.commit()
    cur.close()

    return {"success": True}


# Delete Users (multiple)
@app.route('/delete_user', methods=['POST'])
@admin_required
def delete_user():
    selected_ids = request.form.getlist('selected_users')
    if selected_ids:
        cur = mysql.connection.cursor()
        for uid in selected_ids:
            # skip deleting admins
            cur.execute("SELECT role FROM users WHERE id=%s", (uid,))
            role = cur.fetchone()
            if role and role[0] == "admin":
                continue

            # delete dependent data first
            cur.execute("DELETE FROM feedback WHERE user_id=%s", (uid,))
            cur.execute("DELETE FROM users WHERE id=%s", (uid,))
        
        mysql.connection.commit()
        cur.close()
        flash("✅ Selected users deleted successfully.", "success")
    else:
        flash("⚠️ No users selected for deletion.", "warning")

    return redirect(url_for('manage_users'))

# Manage Questions Page
@app.route('/admin/questions')
@admin_required
def admin_manage_questions():
    cur = mysql.connection.cursor()

    # Fetch questions grouped by role
    cur.execute("SELECT id, role, question_text FROM questions ORDER BY role, id")
    rows = cur.fetchall()
    cur.close()

    # Group questions by role
    questions = {"student": [], "internal": [], "external": []}
    for row in rows:
        questions[row['role']].append(row)

    return render_template('manage_questions.html', questions=questions)


# Add Question
@app.route('/admin/questions/add', methods=['POST'])
@admin_required
def add_question():
    role = request.form['role']
    text = request.form['text']
    cur = mysql.connection.cursor()
    cur.execute("INSERT INTO questions (role, question_text) VALUES (%s, %s)", (role, text))
    mysql.connection.commit()
    cur.close()
    flash("✅ Question added.", "success")
    return redirect(url_for('admin_manage_questions'))


# Edit Question
@app.route('/admin/questions/edit/<int:qid>', methods=['POST'])
@admin_required
def edit_question(qid):
    new_text = request.form['new_text']
    cur = mysql.connection.cursor()
    cur.execute("UPDATE questions SET question_text=%s WHERE id=%s", (new_text, qid))
    mysql.connection.commit()
    cur.close()
    flash("✏️ Question updated.", "success")
    return redirect(url_for('admin_manage_questions'))


# Delete Questions
@app.route('/admin/questions/delete', methods=['POST'])
@admin_required
def delete_questions():
    ids = request.form.getlist("selected_questions")
    if not ids:
        flash("⚠ No questions selected.", "warning")
        return redirect(url_for('admin_manage_questions'))

    # ensure all ids are integers (basic sanity)
    try:
        ids = [int(i) for i in ids]
    except ValueError:
        flash("⚠ Invalid selection.", "danger")
        return redirect(url_for('admin_manage_questions'))

    cur = mysql.connection.cursor()

    # Build placeholders safely and execute
    placeholders = ",".join(["%s"] * len(ids))
    query = f"DELETE FROM questions WHERE id IN ({placeholders})"
    cur.execute(query, tuple(ids))
    mysql.connection.commit()
    cur.close()

    flash(f"🗑 Deleted {len(ids)} question(s).", "success")
    return redirect(url_for('admin_manage_questions'))


import MySQLdb
from flask import request, jsonify, render_template
# make sure admin_required decorator is in scope
'''
# Render the reports page (initial page)
@app.route('/admin/reports')
@admin_required
def admin_feedback_reports():
    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    # Basic KPIs (initial display)
    cur.execute("SELECT COUNT(DISTINCT id) AS total_feedbacks FROM feedback")
    total_feedbacks = cur.fetchone()['total_feedbacks'] or 0

    # questions count (distinct question ids in feedback_answers)
    cur.execute("SELECT COUNT(DISTINCT question_id) AS q_count FROM feedback_answers")
    questions_count = cur.fetchone()['q_count'] or 0

    # departments count (distinct used in feedback)
    cur.execute("SELECT COUNT(DISTINCT department_id) AS dept_count FROM feedback WHERE department_id IS NOT NULL")
    departments_count = cur.fetchone()['dept_count'] or 0

    # lists for filter dropdowns
    cur.execute("SELECT id, name FROM departments ORDER BY name")
    departments = cur.fetchall()

    cur.execute("SELECT id, question_text FROM questions ORDER BY id")
    questions = cur.fetchall()

    cur.close()
    return render_template(
        'feedback_reports.html',
        total_feedbacks=total_feedbacks,
        questions_count=questions_count,
        departments_count=departments_count,
        departments=departments,
        questions=questions
    )


# Data API for reports (used by frontend to power charts/tables)
@app.route('/admin/reports/data')
@admin_required
def admin_feedback_reports_data():
    # Accept role, department_id, year from query params
    role = request.args.get('role') or None
    department_id = request.args.get('department_id') or None
    year = request.args.get('year') or None

    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    # Build WHERE clauses joining feedback -> users
    where_clauses = []
    params = []

    if role:
        where_clauses.append("u.role = %s")
        params.append(role)
    if department_id:
        where_clauses.append("f.department_id = %s")
        params.append(department_id)
    if year:
        where_clauses.append("f.year = %s")
        params.append(year)

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    # KPI: total distinct feedback submissions (filtered)
    cur.execute(f"""
        SELECT COUNT(DISTINCT f.id) AS total_responses
        FROM feedback f
        JOIN users u ON f.user_id = u.id
        {where_sql}
    """, tuple(params))
    total_responses = cur.fetchone()['total_responses'] or 0

    # Collect all answers for avg rating calculation (map text -> numeric)
    cur.execute(f"""
        SELECT fa.answer
        FROM feedback_answers fa
        JOIN feedback f ON fa.feedback_id = f.id
        JOIN users u ON f.user_id = u.id
        {where_sql}
    """, tuple(params))
    all_answers_rows = cur.fetchall()
    rating_map = {"Very Good": 5, "Good": 4, "Neutral": 3, "Bad": 2, "Very Bad": 1}
    numeric_vals = [rating_map[r['answer']] for r in all_answers_rows if r['answer'] in rating_map]
    avg_rating = round(sum(numeric_vals)/len(numeric_vals), 2) if numeric_vals else 0.0

    # Role distribution (apply department/year filters but group by role)
    role_where = []
    role_params = []
    if department_id:
        role_where.append("f.department_id = %s"); role_params.append(department_id)
    if year:
        role_where.append("f.year = %s"); role_params.append(year)
    role_where_sql = ("WHERE " + " AND ".join(role_where)) if role_where else ""
    cur.execute(f"""
        SELECT u.role, COUNT(DISTINCT f.id) AS cnt
        FROM feedback f
        JOIN users u ON f.user_id = u.id
        {role_where_sql}
        GROUP BY u.role
    """, tuple(role_params))
    role_distribution = cur.fetchall()  # list of dicts

    # Heatmap data: departments x years
    years = ['First Year', 'Second Year', 'Third Year']
    cur.execute("SELECT id, name FROM departments ORDER BY name")
    depts = cur.fetchall()
    dept_labels = [d['name'] for d in depts]
    heatmap_matrix = []
    for d in depts:
        row = []
        for y in years:
            cur.execute("""
                SELECT AVG(
                  CASE fa.answer
                    WHEN 'Very Good' THEN 5
                    WHEN 'Good' THEN 4
                    WHEN 'Neutral' THEN 3
                    WHEN 'Bad' THEN 2
                    WHEN 'Very Bad' THEN 1
                  END
                ) AS avg_rating
                FROM feedback_answers fa
                JOIN feedback f ON fa.feedback_id = f.id
                WHERE f.department_id = %s AND f.year = %s
            """, (d['id'], y))
            r = cur.fetchone()
            avg_val = r['avg_rating'] if r and r['avg_rating'] is not None else None
            row.append(round(avg_val,2) if avg_val is not None else None)
        heatmap_matrix.append(row)

    # Avg rating per department (bar)
    cur.execute(f"""
        SELECT d.name AS department,
               AVG(CASE fa.answer
                    WHEN 'Very Good' THEN 5
                    WHEN 'Good' THEN 4
                    WHEN 'Neutral' THEN 3
                    WHEN 'Bad' THEN 2
                    WHEN 'Very Bad' THEN 1
               END) AS avg_rating
        FROM feedback_answers fa
        JOIN feedback f ON fa.feedback_id = f.id
        JOIN departments d ON f.department_id = d.id
        JOIN users u ON f.user_id = u.id
        {where_sql}
        GROUP BY d.id
        ORDER BY avg_rating DESC
    """, tuple(params))
    dept_avg_ratings = cur.fetchall()  # list of {department, avg_rating}

    # Top 5 low scoring questions (apply filters)
    cur.execute(f"""
        SELECT q.question_text,
               AVG(CASE fa.answer
                    WHEN 'Very Good' THEN 5
                    WHEN 'Good' THEN 4
                    WHEN 'Neutral' THEN 3
                    WHEN 'Bad' THEN 2
                    WHEN 'Very Bad' THEN 1
               END) AS avg_rating,
               COUNT(*) AS responses
        FROM feedback_answers fa
        JOIN feedback f ON fa.feedback_id = f.id
        JOIN questions q ON fa.question_id = q.id
        JOIN users u ON f.user_id = u.id
        {where_sql}
        GROUP BY q.id
        ORDER BY avg_rating ASC
        LIMIT 5
    """, tuple(params))
    low_scoring_questions = cur.fetchall()

    # Filtered: avg rating per question (for detailed chart/table)
    cur.execute(f"""
        SELECT q.id, q.question_text,
               AVG(CASE fa.answer
                    WHEN 'Very Good' THEN 5
                    WHEN 'Good' THEN 4
                    WHEN 'Neutral' THEN 3
                    WHEN 'Bad' THEN 2
                    WHEN 'Very Bad' THEN 1
               END) AS avg_rating,
               COUNT(*) AS responses
        FROM feedback_answers fa
        JOIN feedback f ON fa.feedback_id = f.id
        JOIN questions q ON fa.question_id = q.id
        JOIN users u ON f.user_id = u.id
        {where_sql}
        GROUP BY q.id
        ORDER BY q.id
    """, tuple(params))
    filtered_questions_stats = cur.fetchall()

    # Sentiment: average sentiment scoring (coarse mapping)
    cur.execute(f"""
        SELECT fa.answer
        FROM feedback_answers fa
        JOIN feedback f ON fa.feedback_id = f.id
        JOIN users u ON f.user_id = u.id
        {where_sql}
    """, tuple(params))
    rows_sent = cur.fetchall()
    sentiment_map = {'Very Good': 2, 'Good': 1, 'Neutral': 0, 'Bad': -1, 'Very Bad': -2}
    scores = [sentiment_map[r['answer']] for r in rows_sent if r['answer'] in sentiment_map]
    sentiment_avg = round(sum(scores)/len(scores), 3) if scores else 0.0
    if sentiment_avg >= 0.75:
        sentiment_label = "Very Positive"
    elif sentiment_avg >= 0.25:
        sentiment_label = "Positive"
    elif sentiment_avg > -0.25:
        sentiment_label = "Neutral"
    elif sentiment_avg > -0.75:
        sentiment_label = "Negative"
    else:
        sentiment_label = "Very Negative"

    cur.close()

    payload = {
        "kpis": {
            "total_responses": total_responses,
            "avg_rating": avg_rating,
            "departments_count": len(dept_labels),
            "questions_count": len(filtered_questions_stats)
        },
        "role_distribution": role_distribution,
        "heatmap": {
            "years": years,
            "departments": dept_labels,
            "matrix": heatmap_matrix
        },
        "dept_avg_ratings": dept_avg_ratings,
        "low_scoring_questions": low_scoring_questions,
        "filtered_questions_stats": filtered_questions_stats,
        "sentiment": {
            "avg_score": sentiment_avg,
            "label": sentiment_label
        }
    }

    return jsonify(payload)
'''
@app.route('/admin/reports')
@admin_required
def admin_feedback_reports():
    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    # --- KPI Metrics ---
    cur.execute("SELECT COUNT(DISTINCT id) AS total_responses FROM feedback")
    total_responses = cur.fetchone()['total_responses']

    cur.execute("""
        SELECT AVG(
            CASE answer
                WHEN 'Very Bad' THEN 1
                WHEN 'Bad' THEN 2
                WHEN 'Neutral' THEN 3
                WHEN 'Good' THEN 4
                WHEN 'Very Good' THEN 5
            END
        ) AS avg_rating
        FROM feedback_answers
    """)
    avg_rating = round(cur.fetchone()['avg_rating'] or 0, 2)

    # department count
    cur.execute("SELECT COUNT(*) AS dept_count FROM departments")
    departments_count = cur.fetchone()['dept_count']

    # also fetch list of departments for charts/dropdowns
    cur.execute("SELECT id, name FROM departments ORDER BY name")
    departments = cur.fetchall()

    # total questions
    cur.execute("SELECT COUNT(*) AS q_count FROM questions")
    questions_count = cur.fetchone()['q_count']

    # --- Avg rating per department ---
    cur.execute("""
        SELECT d.name AS department,
               AVG(
                   CASE fa.answer
                       WHEN 'Very Bad' THEN 1
                       WHEN 'Bad' THEN 2
                       WHEN 'Neutral' THEN 3
                       WHEN 'Good' THEN 4
                       WHEN 'Very Good' THEN 5
                   END
               ) AS avg_rating
        FROM feedback_answers fa
        JOIN feedback f ON fa.feedback_id = f.id
        JOIN departments d ON f.department_id = d.id
        GROUP BY d.name
    """)
    dept_ratings = cur.fetchall()

    # --- Top 5 low-scoring questions ---
    cur.execute("""
        SELECT q.question_text,
               ROUND(AVG(
                   CASE fa.answer
                       WHEN 'Very Bad' THEN 1
                       WHEN 'Bad' THEN 2
                       WHEN 'Neutral' THEN 3
                       WHEN 'Good' THEN 4
                       WHEN 'Very Good' THEN 5
                   END
               ),2) AS avg_rating
        FROM feedback_answers fa
        JOIN questions q ON fa.question_id = q.id
        GROUP BY q.id, q.question_text
        ORDER BY avg_rating ASC
        LIMIT 5
    """)
    low_scoring_questions = cur.fetchall()

    # --- Heatmap Data (Department vs Year avg rating) ---
    cur.execute("""
        SELECT d.name AS department, f.year,
               ROUND(AVG(
                   CASE fa.answer
                       WHEN 'Very Bad' THEN 1
                       WHEN 'Bad' THEN 2
                       WHEN 'Neutral' THEN 3
                       WHEN 'Good' THEN 4
                       WHEN 'Very Good' THEN 5
                   END
               ),2) AS avg_rating
        FROM feedback_answers fa
        JOIN feedback f ON fa.feedback_id = f.id
        JOIN departments d ON f.department_id = d.id
        GROUP BY d.name, f.year
    """)
    heatmap_data = cur.fetchall()

    # --- Role Distribution ---
    cur.execute("""
        SELECT u.role, COUNT(*) AS cnt
        FROM feedback f
        JOIN users u ON f.user_id = u.id
        GROUP BY u.role
    """)
    role_distribution = cur.fetchall()

    # --- Filtered Questions Stats (default: all data) ---
    cur.execute("""
        SELECT q.question_text,
               ROUND(AVG(
                   CASE fa.answer
                       WHEN 'Very Bad' THEN 1
                       WHEN 'Bad' THEN 2
                       WHEN 'Neutral' THEN 3
                       WHEN 'Good' THEN 4
                       WHEN 'Very Good' THEN 5
                   END
               ),2) AS avg_rating,
               COUNT(fa.id) AS responses
        FROM feedback_answers fa
        JOIN questions q ON fa.question_id = q.id
        JOIN feedback f ON fa.feedback_id = f.id
        GROUP BY q.id, q.question_text
        ORDER BY q.id
    """)
    filtered_questions_stats = cur.fetchall()

    # --- Feedback Sentiment ---
    cur.execute("""
        SELECT AVG(
            CASE answer
                WHEN 'Very Bad' THEN 1
                WHEN 'Bad' THEN 2
                WHEN 'Neutral' THEN 3
                WHEN 'Good' THEN 4
                WHEN 'Very Good' THEN 5
            END
        ) AS avg_sentiment
        FROM feedback_answers
    """)
    sentiment_avg = cur.fetchone()['avg_sentiment'] or 0

    if sentiment_avg >= 3.5:
        sentiment_label = "😊 Positive"
        sentiment_color = "text-success"
    elif sentiment_avg >= 2.5:
        sentiment_label = "😐 Neutral"
        sentiment_color = "text-warning"
    else:
        sentiment_label = "☹️ Negative"
        sentiment_color = "text-danger"

    cur.close()

    return render_template(
        "feedback_reports.html",
        total_responses=total_responses,
        avg_rating=avg_rating,
        departments_count=departments_count,
        departments=departments,
        questions_count=questions_count,
        dept_ratings=dept_ratings,
        low_scoring_questions=low_scoring_questions,
        heatmap_data=heatmap_data,
        role_distribution=role_distribution,
        filtered_questions_stats=filtered_questions_stats,
        sentiment_label=sentiment_label,
        sentiment_color=sentiment_color
    )

@app.route('/admin/reports/filter', methods=['POST'])
@admin_required
def filter_feedback_reports():
    data = request.json
    role = data.get("role")
    department = data.get("department")
    year = data.get("year")

    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    query = """
        SELECT q.question_text,
               ROUND(AVG(
                   CASE fa.answer
                       WHEN 'Very Bad' THEN 1
                       WHEN 'Bad' THEN 2
                       WHEN 'Neutral' THEN 3
                       WHEN 'Good' THEN 4
                       WHEN 'Very Good' THEN 5
                   END
               ),2) AS avg_rating,
               COUNT(fa.id) AS responses
        FROM feedback_answers fa
        JOIN feedback f ON fa.feedback_id = f.id
        JOIN questions q ON fa.question_id = q.id
        JOIN users u ON f.user_id = u.id
        JOIN departments d ON f.department_id = d.id
        WHERE 1=1
    """
    filters = []
    values = []

    if role and role != "All Roles":
        filters.append("u.role = %s")
        values.append(role)

    if department and department != "All Departments":
        filters.append("d.name = %s")
        values.append(department)

    if year and year != "All Years":
        filters.append("f.year = %s")
        values.append(year)

    if filters:
        query += " AND " + " AND ".join(filters)

    query += " GROUP BY q.id, q.question_text ORDER BY q.id"

    cur.execute(query, tuple(values))
    results = cur.fetchall()
    cur.close()

    return jsonify(results)

import csv
from io import StringIO, BytesIO
from flask import Response
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet

@app.route("/admin/reports/export/all/csv")
@admin_required
def export_all_feedback_csv():
    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cur.execute("""
        SELECT u.name, u.role, d.name AS department, f.year, fa.question_id, q.question_text, fa.answer, f.submitted_at
        FROM feedback_answers fa
        JOIN feedback f ON fa.feedback_id = f.id
        JOIN users u ON f.user_id = u.id
        JOIN departments d ON f.department_id = d.id
        JOIN questions q ON fa.question_id = q.id
        ORDER BY f.submitted_at DESC
    """)
    rows = cur.fetchall()
    cur.close()

    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(["User", "Role", "Department", "Year", "Question", "Answer", "Submitted At"])
    for r in rows:
        cw.writerow([r["name"], r["role"], r["department"], r["year"], r["question_text"], r["answer"], r["submitted_at"]])

    output = Response(si.getvalue(), mimetype="text/csv")
    output.headers["Content-Disposition"] = "attachment; filename=feedback_report.csv"
    return output


@app.route("/admin/reports/export/all/pdf")
@admin_required
def export_all_feedback_pdf():
    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cur.execute("""
        SELECT u.name, u.role, d.name AS department, f.year, fa.question_id, q.question_text, fa.answer, f.submitted_at
        FROM feedback_answers fa
        JOIN feedback f ON fa.feedback_id = f.id
        JOIN users u ON f.user_id = u.id
        JOIN departments d ON f.department_id = d.id
        JOIN questions q ON fa.question_id = q.id
        ORDER BY f.submitted_at DESC
    """)
    rows = cur.fetchall()
    cur.close()

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer)
    elements = []
    styles = getSampleStyleSheet()

    data = [["User", "Role", "Department", "Year", "Question", "Answer", "Submitted At"]]
    for r in rows:
        data.append([
            r["name"], r["role"], r["department"], r["year"],
            r["question_text"], r["answer"], str(r["submitted_at"])
        ])

    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#9E77ED")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("GRID", (0,0), (-1,-1), 0.5, colors.grey),
        ("ALIGN", (0,0), (-1,-1), "CENTER"),
        ("FONTSIZE", (0,0), (-1,-1), 8),
    ]))
    elements.append(Paragraph("Feedback Report", styles["Title"]))
    elements.append(table)
    doc.build(elements)

    buffer.seek(0)
    return Response(buffer, mimetype="application/pdf",
                    headers={"Content-Disposition": "attachment;filename=feedback_report.pdf"})

# View Feedback
@app.route('/admin/feedback')
@admin_required
def admin_view_feedback():
    import MySQLdb
    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    cur.execute("""
        SELECT f.id AS feedback_id, f.submitted_at, f.year,
               u.name AS user_name, u.role, d.name AS department,
               q.question_text, a.answer
        FROM feedback f
        JOIN users u ON f.user_id = u.id
        LEFT JOIN departments d ON f.department_id = d.id
        JOIN feedback_answers a ON f.id = a.feedback_id
        JOIN questions q ON a.question_id = q.id
        ORDER BY f.submitted_at DESC, f.id, q.id
    """)
    rows = cur.fetchall()
    cur.close()

    # Group answers by feedback_id
    feedback_dict = {}
    for row in rows:
        fid = row['feedback_id']
        if fid not in feedback_dict:
            feedback_dict[fid] = {
                "user_name": row['user_name'],
                "role": row['role'],
                "department": row['department'],
                "year": row['year'],
                "submitted_at": row['submitted_at'],
                "answers": []
            }
        feedback_dict[fid]["answers"].append(
            f"{row['question_text']} → {row['answer']}"
        )

    return render_template("view_feedback.html", feedbacks=feedback_dict.values())

import csv
from io import StringIO, BytesIO
from flask import Response
from reportlab.platypus import SimpleDocTemplate, Paragraph
from reportlab.lib.styles import getSampleStyleSheet

# Export CSV
@app.route('/admin/feedback/export/csv')
@admin_required
def export_feedback_csv():
    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cur.execute("""
        SELECT u.name, u.role, d.name AS department, u.year, f.submitted_at
        FROM feedback f
        JOIN users u ON f.user_id = u.id
        LEFT JOIN departments d ON u.department_id = d.id
        ORDER BY f.submitted_at DESC
    """)
    rows = cur.fetchall()
    cur.close()

    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(["Name", "Role", "Department", "Year", "Submitted At"])
    for r in rows:
        cw.writerow([r["name"], r["role"], r["department"], r["year"], r["submitted_at"]])
    output = si.getvalue().encode("utf-8")

    return Response(output, mimetype="text/csv",
                    headers={"Content-Disposition": "attachment;filename=feedback.csv"})

# Export PDF
@app.route('/admin/feedback/export/pdf')
@admin_required
def export_feedback_pdf():
    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cur.execute("""
        SELECT u.name, u.role, d.name AS department, u.year, f.submitted_at
        FROM feedback f
        JOIN users u ON f.user_id = u.id
        LEFT JOIN departments d ON u.department_id = d.id
        ORDER BY f.submitted_at DESC
    """)
    rows = cur.fetchall()
    cur.close()

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer)
    styles = getSampleStyleSheet()
    content = []

    for r in rows:
        line = f"{r['name']} ({r['role']}) - {r['department'] or '-'} - {r['year'] or '-'} - {r['submitted_at']}"
        content.append(Paragraph(line, styles["Normal"]))

    doc.build(content)
    buffer.seek(0)

    return Response(buffer, mimetype="application/pdf",
                    headers={"Content-Disposition": "attachment;filename=feedback.pdf"})


@app.route('/')
def home():
    return '✅ Flask is running! Go to /login or /register to start.'

if __name__ == '__main__':
    app.run(debug=True)
