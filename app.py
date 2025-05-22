from flask import Flask, render_template, request, redirect, url_for, session, abort, Response, send_from_directory, jsonify
import yaml
import sqlite3
import os
import csv
import io
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
import random
import re

app = Flask(__name__, static_url_path='/static')
app.secret_key = 'your_secret_key_here'  # Change this in production

# Load config
with open('config.yaml') as f:
    config = yaml.safe_load(f)
DASHBOARD_PASSWORD = config['dashboard']['password']
RESERVATION_TIMEOUT_MINUTES = config['study']['reservation_timeout_minutes']

# Mobile device detection regex
MOBILE_AGENT_RE = re.compile(r".*(iphone|mobile|androidtouch)", re.IGNORECASE)

def is_mobile_device(user_agent):
    return bool(MOBILE_AGENT_RE.match(user_agent))

# Database setup
def init_db():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row  # This will make rows accessible by column name
    c = conn.cursor()
    
    # Create tables if they don't exist
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (username TEXT PRIMARY KEY,
                  email TEXT NOT NULL UNIQUE,
                  created_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS images
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  gt_path TEXT NOT NULL,
                  sr_path TEXT NOT NULL,
                  answered_count INTEGER DEFAULT 0)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS responses
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT NOT NULL,
                  image_id INTEGER NOT NULL,
                  answer TEXT NOT NULL,
                  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                  FOREIGN KEY(image_id) REFERENCES images(id))''')
    
    # Create scores table
    c.execute('''CREATE TABLE IF NOT EXISTS user_scores
                 (username TEXT PRIMARY KEY,
                  score INTEGER DEFAULT 0,
                  last_updated DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    
    # Populate images table if empty
    c.execute('SELECT COUNT(*) FROM images')
    if c.fetchone()[0] == 0:
        gt_dir = 'static/GT'
        sr_dir = 'static/SR'
        
        if os.path.exists(gt_dir) and os.path.exists(sr_dir):
            # Create dictionaries mapping base filenames (without extensions) to full paths
            gt_files = {}
            sr_files = {}
            
            # Process GT files
            for f in os.listdir(gt_dir):
                if os.path.isfile(os.path.join(gt_dir, f)):
                    # Get filename without extension
                    base_name = os.path.splitext(f)[0]
                    # Store relative path from static directory
                    gt_files[base_name] = os.path.join('static', 'GT', f)
            
            # Process SR files
            for f in os.listdir(sr_dir):
                if os.path.isfile(os.path.join(sr_dir, f)):
                    # Get filename without extension
                    base_name = os.path.splitext(f)[0]
                    # Store relative path from static directory
                    sr_files[base_name] = os.path.join('static', 'SR', f)
            
            # Find common base filenames
            common_base_names = set(gt_files.keys()) & set(sr_files.keys())
            
            for base_name in common_base_names:
                gt_path = gt_files[base_name]
                sr_path = sr_files[base_name]
                try:
                    c.execute('INSERT INTO images (gt_path, sr_path) VALUES (?, ?)', (gt_path, sr_path))
                except sqlite3.Error as e:
                    print(f"Error inserting image pair {base_name}: {e}")
    
    conn.commit()
    conn.close()

# Function to clean up expired reservations
def cleanup_expired_reservations():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    # Calculate the expiration time
    expiration_time = datetime.now() - timedelta(minutes=RESERVATION_TIMEOUT_MINUTES)
    expiration_str = expiration_time.strftime('%Y-%m-%d %H:%M:%S')
    
    # Find expired reservations
    c.execute('''SELECT image_id FROM responses 
                 WHERE answer = 'RESERVED' AND timestamp < ?''', 
              (expiration_str,))
    expired_reservations = c.fetchall()
    
    # Clean up each expired reservation
    for (image_id,) in expired_reservations:
        # Delete the expired reservation
        c.execute('''DELETE FROM responses 
                     WHERE answer = 'RESERVED' AND image_id = ? AND timestamp < ?''', 
                  (image_id, expiration_str))
    
    conn.commit()
    conn.close()
    
    return len(expired_reservations)

# Initialize database
init_db()

# Add a route to serve images from icon_memes_normalized
@app.route('/icon_memes_normalized/<path:filename>')
def serve_icon(filename):
    return send_from_directory('icon_memes_normalized', filename)

# Add a route to serve images
@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory('static', filename)

@app.route('/', methods=['GET', 'POST'])
def index():
    # Get database connection
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    
    # Get statistics
    total_responses = conn.execute('SELECT COUNT(*) FROM responses WHERE answer != "RESERVED"').fetchone()[0]
    total_images = conn.execute('SELECT COUNT(*) FROM images').fetchone()[0]
    max_responses_per_pair = config['study']['max_responses_per_pair']
    total_possible_responses = total_images * max_responses_per_pair
    completion_percent = (total_responses / total_possible_responses * 100) if total_possible_responses > 0 else 0
    
    # Get top users
    top_users = conn.execute('''
        SELECT u.username, s.score, s.last_updated, u.email
        FROM user_scores s
        JOIN users u ON s.username = u.username
        ORDER BY s.score DESC 
        LIMIT 10
    ''').fetchall()
    
    # Load config file to get latest prices
    with open('config.yaml') as f:
        current_config = yaml.safe_load(f)
    prices = current_config.get('prices', [])
    
    conn.close()

    # Handle POST request (login attempt)
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        
        if not username or not email:
            return render_template('index.html', 
                                 error="Please provide both username and email",
                                 total_responses=total_responses,
                                 total_possible_responses=total_possible_responses,
                                 completion_percent=completion_percent,
                                 top_users=top_users,
                                 prices=prices)
        
        conn = sqlite3.connect('database.db')
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        # Check if username exists
        c.execute('SELECT email FROM users WHERE username = ?', (username,))
        existing_user = c.fetchone()
        
        if existing_user:
            if existing_user['email'] != email:
                return render_template('index.html', 
                                     error="Username already taken or wrong email",
                                     total_responses=total_responses,
                                     total_possible_responses=total_possible_responses,
                                     completion_percent=completion_percent,
                                     top_users=top_users,
                                     prices=prices)
        else:
            # Create new user
            try:
                c.execute('INSERT INTO users (username, email) VALUES (?, ?)', (username, email))
                conn.commit()
            except sqlite3.IntegrityError:
                return render_template('index.html', 
                                     error="Username or email already exists",
                                     total_responses=total_responses,
                                     total_possible_responses=total_possible_responses,
                                     completion_percent=completion_percent,
                                     top_users=top_users,
                                     prices=prices)
        
        # Set session
        session['username'] = username
        conn.close()
        return redirect(url_for('compare'))
    
    # Handle GET request
    # If user is logged in, show the login page with a "Continue as [username]" option
    if 'username' in session:
        return render_template('index.html', 
                             logged_in=True, 
                             current_username=session['username'],
                             total_responses=total_responses,
                             total_possible_responses=total_possible_responses,
                             completion_percent=completion_percent,
                             top_users=top_users,
                             prices=prices)
    
    return render_template('index.html',
                         total_responses=total_responses,
                         total_possible_responses=total_possible_responses,
                         completion_percent=completion_percent,
                         top_users=top_users,
                         prices=prices)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    print("\n=== Dashboard Route Accessed ===")
    if request.method == 'POST':
        password = request.form.get('password', '')
        print(f"Dashboard login attempt with password: {password}")
        if password == DASHBOARD_PASSWORD:
            session['dashboard_authenticated'] = True
            return redirect(url_for('dashboard'))
        else:
            return render_template('dashboard_login.html', error="Incorrect password")
    
    if not session.get('dashboard_authenticated'):
        print("User not authenticated for dashboard")
        return render_template('dashboard_login.html')
    
    print("User authenticated, fetching dashboard data")
    # Clean up expired reservations before showing dashboard
    expired_count = cleanup_expired_reservations()
    print(f"Cleaned up {expired_count} expired reservations")
    
    # Load config file to get latest prices
    with open('config.yaml') as f:
        current_config = yaml.safe_load(f)
    prices = current_config.get('prices', [])
    print(f"Loaded {len(prices)} prices from config")
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    try:
        # Get response statistics
        c.execute('SELECT COUNT(*) FROM responses WHERE answer != "RESERVED"')
        total_responses = c.fetchone()[0]
        print(f"Total responses: {total_responses}")
        
        c.execute('SELECT COUNT(DISTINCT username) FROM responses WHERE answer != "RESERVED"')
        unique_users = c.fetchone()[0]
        print(f"Unique users: {unique_users}")
        
        c.execute('SELECT COUNT(*) FROM images WHERE answered_count = ?', 
                  (config['study']['max_responses_per_pair'],))
        completed_pairs = c.fetchone()[0]
        print(f"Completed pairs: {completed_pairs}")
        
        c.execute('SELECT COUNT(*) FROM images')
        total_pairs = c.fetchone()[0]
        print(f"Total pairs: {total_pairs}")
        
        # Calculate total possible responses
        total_possible_responses = total_pairs * config['study']['max_responses_per_pair']
        
        completion_percent = (total_responses/total_possible_responses)*100 if total_possible_responses > 0 else 0
        print(f"Completion percent: {completion_percent}")
        
        # Get recent responses with scores
        c.execute('''SELECT r.username, i.gt_path, r.answer, r.timestamp, COALESCE(s.score, 0) as user_score
                     FROM responses r 
                     JOIN images i ON r.image_id = i.id
                     LEFT JOIN user_scores s ON r.username = s.username
                     WHERE r.answer != "RESERVED"
                     ORDER BY r.timestamp DESC LIMIT 10''')
        recent_responses = c.fetchall()
        print(f"Recent responses count: {len(recent_responses)}")
        if recent_responses:
            print("Sample response:", recent_responses[0])
        
        # Get top users by score with email information
        c.execute('''SELECT u.username, s.score, s.last_updated, u.email
                     FROM user_scores s
                     JOIN users u ON s.username = u.username
                     ORDER BY s.score DESC 
                     LIMIT 10''')
        top_users = c.fetchall()
        
        # Get active reservations with proper time elapsed calculation
        c.execute('''SELECT r.username, i.gt_path, r.timestamp
                    FROM responses r JOIN images i ON r.image_id = i.id
                    WHERE r.answer = "RESERVED"
                    ORDER BY r.timestamp ASC''')
        active_reservations = c.fetchall()
        
        # Calculate time elapsed for each reservation
        current_time = datetime.now()
        active_reservations_with_time = []
        for reservation in active_reservations:
            try:
                reservation_time = datetime.strptime(reservation[2], '%Y-%m-%d %H:%M:%S')
            except ValueError:
                reservation_time = datetime.strptime(reservation[2], '%Y-%m-%d %H:%M:%S.%f')
            
            time_elapsed = (current_time - reservation_time).total_seconds() / 60
            active_reservations_with_time.append((reservation[0], reservation[1], reservation[2], round(time_elapsed, 1)))
        
        print(f"Active reservations count: {len(active_reservations_with_time)}")
        
        return render_template('dashboard.html',
                             total_responses=total_responses,
                             unique_users=unique_users,
                             completed_pairs=completed_pairs,
                             total_pairs=total_pairs,
                             total_possible_responses=total_possible_responses,
                             recent_responses=recent_responses,
                             completion_percent=completion_percent,
                             active_reservations=active_reservations_with_time,
                             expired_count=expired_count,
                             top_users=top_users,
                             prices=prices)
    except sqlite3.Error as e:
        print(f"Database error in dashboard route: {e}")
        return "Database error occurred", 500
    finally:
        conn.close()

@app.route('/dashboard/logout')
def dashboard_logout():
    session.pop('dashboard_authenticated', None)
    return redirect(url_for('dashboard'))

@app.route('/download_csv')
def download_csv():
    # Check if user is authenticated for dashboard
    if not session.get('dashboard_authenticated'):
        abort(403)  # Forbidden
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    # Get all responses with image details, excluding reservations
    c.execute('''SELECT r.username, i.gt_path, i.sr_path, r.answer, r.timestamp 
                 FROM responses r 
                 JOIN images i ON r.image_id = i.id
                 WHERE r.answer != "RESERVED"
                 ORDER BY r.timestamp DESC''')
    all_responses = c.fetchall()
    
    conn.close()
    
    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow(['User Code', 'Ground Truth Image', 'Super Resolution Image', 'Answer', 'Timestamp'])
    
    # Write data rows
    for response in all_responses:
        # Extract filenames from paths
        gt_filename = response[1].split('/')[-1]
        sr_filename = response[2].split('/')[-1]
        writer.writerow([response[0], gt_filename, sr_filename, response[3], response[4]])
    
    # Prepare response
    output.seek(0)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename=study_results_{timestamp}.csv"}
    )

@app.route('/compare')
def compare():
    if 'username' not in session:
        return redirect(url_for('index'))
    
    # Clean up any expired reservations first
    cleanup_expired_reservations()
    
    # Load config file to get latest prices
    with open('config.yaml') as f:
        current_config = yaml.safe_load(f)
    prices = current_config.get('prices', [])
    
    conn = sqlite3.connect('database.db')
    # Enable immediate transaction mode to prevent other transactions from modifying data
    conn.isolation_level = 'IMMEDIATE'
    c = conn.cursor()
    
    try:
        # Get user's annotation count
        c.execute('''SELECT COUNT(*) FROM responses 
                     WHERE username = ? AND answer != 'RESERVED' ''', 
                  (session['username'],))
        annotation_count = c.fetchone()[0]
        session['annotation_count'] = annotation_count
        
        # Get completion statistics
        c.execute('SELECT COUNT(*) FROM images WHERE answered_count = ?', 
                  (config['study']['max_responses_per_pair'],))
        completed_pairs = c.fetchone()[0]
        
        c.execute('SELECT COUNT(*) FROM images')
        total_pairs = c.fetchone()[0]
        
        # Calculate total possible responses
        total_possible_responses = total_pairs * config['study']['max_responses_per_pair']
        
        # Get total actual responses
        c.execute('SELECT COUNT(*) FROM responses WHERE answer != "RESERVED"')
        total_responses = c.fetchone()[0]
        
        completion_percent = (total_responses/total_possible_responses)*100 if total_possible_responses > 0 else 0
        
        # Get top users
        c.execute('''SELECT u.username, s.score, s.last_updated, u.email
                     FROM user_scores s
                     JOIN users u ON s.username = u.username
                     ORDER BY s.score DESC 
                     LIMIT 10''')
        top_users = c.fetchall()
        
        # Begin transaction
        c.execute('BEGIN TRANSACTION')
        
        # Check if user has any existing reservation
        c.execute('''SELECT i.id, i.gt_path, i.sr_path, r.timestamp
                     FROM responses r
                     JOIN images i ON r.image_id = i.id
                     WHERE r.username = ? AND r.answer = 'RESERVED'
                     LIMIT 1''', (session['username'],))
        
        existing_reservation = c.fetchone()
        
        if existing_reservation:
            image_id, gt_path, sr_path, timestamp_str = existing_reservation
            
            # Check if reservation is expired
            try:
                reservation_time = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                # Handle SQLite's datetime format
                reservation_time = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S.%f')
                
            expiration_time = reservation_time + timedelta(minutes=RESERVATION_TIMEOUT_MINUTES)
            current_time = datetime.now()
            
            if current_time > expiration_time:
                # Reservation expired - clean it up
                c.execute('''DELETE FROM responses 
                             WHERE username = ? AND image_id = ? AND answer = 'RESERVED' ''', 
                          (session['username'], image_id))
                
                # Continue to find a new image
            else:
                # Return the existing reservation
                conn.commit()
                conn.close()
                
                # Store reservation info in session
                session['reserved_image_id'] = image_id
                
                # Calculate remaining time in seconds
                remaining_seconds = int((expiration_time - current_time).total_seconds())
                
                # Check if the request is from a mobile device
                if is_mobile_device(request.user_agent.string):
                    return render_template('mobile_compare.html', 
                                         gt_path=gt_path, 
                                         sr_path=sr_path,
                                         image_id=image_id,
                                         timeout_seconds=remaining_seconds,
                                         top_users=top_users,
                                         prices=prices,
                                         completed_pairs=completed_pairs,
                                         total_pairs=total_pairs,
                                         total_responses=total_responses,
                                         total_possible_responses=total_possible_responses,
                                         completion_percent=completion_percent,
                                         annotation_count=annotation_count,
                                         config=config)
                
                return render_template('compare.html', 
                                     gt_path=gt_path, 
                                     sr_path=sr_path,
                                     image_id=image_id,
                                     timeout_seconds=remaining_seconds,
                                     top_users=top_users,
                                     prices=prices,
                                     completed_pairs=completed_pairs,
                                     total_pairs=total_pairs,
                                     total_responses=total_responses,
                                     total_possible_responses=total_possible_responses,
                                     completion_percent=completion_percent,
                                     annotation_count=annotation_count,
                                     config=config)
        
        # Find an image pair that needs answers and lock the row for update
        c.execute('''SELECT i.id, i.gt_path, i.sr_path, i.answered_count 
                     FROM images i
                     WHERE i.answered_count < ?
                     AND NOT EXISTS (
                         SELECT 1 FROM responses r 
                         WHERE r.image_id = i.id AND r.username = ?
                     )
                     ORDER BY RANDOM()
                     LIMIT 1''', (config['study']['max_responses_per_pair'], session['username']))
        
        image_data = c.fetchone()
        
        if not image_data:
            # All images have been answered by this user or all pairs are complete
            conn.commit()
            conn.close()
            return render_template('complete.html')
        
        image_id, gt_path, sr_path, current_count = image_data
        
        # Double-check the count is still below maximum before proceeding
        if current_count >= config['study']['max_responses_per_pair']:
            conn.commit()
            conn.close()
            # Try again by redirecting back to compare
            return redirect(url_for('compare'))
        
        try:
            # Create a temporary reservation record with current timestamp
            current_timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            c.execute('''INSERT INTO responses (username, image_id, answer, timestamp)
                         VALUES (?, ?, 'RESERVED', ?)''', 
                      (session['username'], image_id, current_timestamp))
            
            # Commit transaction to release locks but keep the reservation
            conn.commit()
            conn.close()
            
            # Store reservation info in session
            session['reserved_image_id'] = image_id
            
            # Set timeout to 5 minutes (300 seconds)
            timeout_seconds = RESERVATION_TIMEOUT_MINUTES * 60
            
            # Check if the request is from a mobile device
            if is_mobile_device(request.user_agent.string):
                return render_template('mobile_compare.html', 
                                     gt_path=gt_path, 
                                     sr_path=sr_path,
                                     image_id=image_id,
                                     timeout_seconds=timeout_seconds,
                                     top_users=top_users,
                                     prices=prices,
                                     completed_pairs=completed_pairs,
                                     total_pairs=total_pairs,
                                     total_responses=total_responses,
                                     total_possible_responses=total_possible_responses,
                                     completion_percent=completion_percent,
                                     annotation_count=annotation_count,
                                     config=config)
            
            return render_template('compare.html', 
                                 gt_path=gt_path, 
                                 sr_path=sr_path,
                                 image_id=image_id,
                                 timeout_seconds=timeout_seconds,
                                 top_users=top_users,
                                 prices=prices,
                                 completed_pairs=completed_pairs,
                                 total_pairs=total_pairs,
                                 total_responses=total_responses,
                                 total_possible_responses=total_possible_responses,
                                 completion_percent=completion_percent,
                                 annotation_count=annotation_count,
                                 config=config)
            
        except sqlite3.Error as e:
            conn.rollback()
            conn.close()
            print(f"Database error in compare route: {e}")
            return redirect(url_for('compare'))
    
    except Exception as e:
        # If any error occurs, rollback the transaction
        conn.rollback()
        conn.close()
        print(f"Error in compare route: {e}")
        return redirect(url_for('compare'))

@app.route('/gamble', methods=['POST'])
def gamble():
    print("\n=== Gamble Route Accessed ===")
    if 'username' not in session:
        print("No username in session")
        return jsonify({'success': False, 'error': 'Not logged in'}), 401
    
    data = request.get_json()
    prize = data.get('prize')
    print(f"Received prize data: {prize}")
    
    if not prize:
        print("Invalid prize data")
        return jsonify({'success': False, 'error': 'Invalid prize data'}), 400
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    try:
        # Begin transaction
        c.execute('BEGIN TRANSACTION')
        
        # Get current score
        c.execute('SELECT score FROM user_scores WHERE username = ?', (session['username'],))
        result = c.fetchone()
        print(f"Current score from database: {result}")
        
        if not result:
            # Create new score entry if doesn't exist
            c.execute('INSERT INTO user_scores (username, score) VALUES (?, 0)', (session['username'],))
            current_score = 0
            print("Created new score entry")
        else:
            current_score = result[0]
        
        # Apply prize effect
        new_score = current_score
        if 'points' in prize:
            new_score += prize['points']
            print(f"Adding {prize['points']} points. New score: {new_score}")
        elif 'multiplier' in prize:
            # Store multiplier in session for next response
            session['score_multiplier'] = prize['multiplier']
            print(f"Stored multiplier: {prize['multiplier']}")
        
        # Update score if it changed
        if new_score != current_score:
            c.execute('''UPDATE user_scores 
                         SET score = ?, last_updated = CURRENT_TIMESTAMP 
                         WHERE username = ?''', 
                      (new_score, session['username']))
            print(f"Updated score in database to: {new_score}")
        
        # Update session score
        session['user_score'] = new_score
        print(f"Updated session score to: {new_score}")
        
        conn.commit()
        print("Transaction committed")
        
        response_data = {
            'success': True,
            'new_score': new_score,
            'prize': prize
        }
        print(f"Sending response: {response_data}")
        return jsonify(response_data)
        
    except sqlite3.Error as e:
        conn.rollback()
        print(f"Database error in gamble route: {e}")
        return jsonify({'success': False, 'error': 'Database error'}), 500
    finally:
        conn.close()

@app.route('/submit', methods=['POST'])
def submit():
    print("\n=== Submit Route Accessed ===")
    if 'username' not in session:
        print("No username in session")
        return redirect(url_for('index'))
    
    answer = request.form.get('answer')
    image_id = request.form.get('image_id')
    
    print(f"Received submission - User: {session['username']}, Answer: {answer}, Image ID: {image_id}")
    
    if not answer or not image_id:
        print("Missing answer or image_id")
        return redirect(url_for('compare'))
    
    # Verify this is the reserved image
    if session.get('reserved_image_id') != int(image_id):
        print(f"Image ID mismatch - Session: {session.get('reserved_image_id')}, Submitted: {image_id}")
        return redirect(url_for('compare'))
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    try:
        # Begin transaction
        c.execute('BEGIN TRANSACTION')
        
        # Check if reservation exists
        c.execute('''SELECT timestamp FROM responses 
                     WHERE username = ? AND image_id = ? AND answer = 'RESERVED' ''', 
                  (session['username'], image_id))
        
        result = c.fetchone()
        if not result:
            print("No reservation found")
            conn.rollback()
            conn.close()
            session.pop('reserved_image_id', None)
            return redirect(url_for('compare'))
            
        timestamp_str = result[0]
        try:
            reservation_time = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            # Handle SQLite's datetime format
            reservation_time = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S.%f')
            
        expiration_time = reservation_time + timedelta(minutes=RESERVATION_TIMEOUT_MINUTES)
        current_time = datetime.now()
        
        print(f"Reservation time: {reservation_time}")
        print(f"Expiration time: {expiration_time}")
        print(f"Current time: {current_time}")
        
        if current_time > expiration_time:
            # Reservation expired - clean it up and redirect
            c.execute('''DELETE FROM responses 
                         WHERE username = ? AND image_id = ? AND answer = 'RESERVED' ''', 
                      (session['username'], image_id))
            
            conn.commit()
            conn.close()
            session.pop('reserved_image_id', None)
            print("Reservation expired")
            return redirect(url_for('compare'))
        
        # Delete the reservation
        c.execute('''DELETE FROM responses 
                     WHERE username = ? AND image_id = ? AND answer = 'RESERVED' ''', 
                  (session['username'], image_id))
        
        # Insert the actual answer with current timestamp
        current_timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        c.execute('''INSERT INTO responses (username, image_id, answer, timestamp)
                     VALUES (?, ?, ?, ?)''', 
                  (session['username'], image_id, answer, current_timestamp))
        
        # Update the image's answered count
        c.execute('''UPDATE images 
                     SET answered_count = answered_count + 1
                     WHERE id = ?''', (image_id,))
        
        # Calculate points with multiplier if active
        points = 1
        if session.get('score_multiplier'):
            points *= session['score_multiplier']
            session.pop('score_multiplier')  # Remove multiplier after use
        
        # Update user's score
        c.execute('''INSERT INTO user_scores (username, score, last_updated)
                     VALUES (?, ?, ?)
                     ON CONFLICT(username) DO UPDATE SET 
                     score = score + ?,
                     last_updated = ?''', 
                  (session['username'], points, current_timestamp, points, current_timestamp))
        
        print(f"Successfully recorded answer: {answer} for image {image_id}")
        
        # Verify the insertion
        c.execute('''SELECT * FROM responses 
                     WHERE username = ? AND image_id = ? AND answer = ?''',
                  (session['username'], image_id, answer))
        verification = c.fetchone()
        print(f"Verification of saved response: {verification}")
        
        # Get updated score
        c.execute('SELECT score FROM user_scores WHERE username = ?', (session['username'],))
        score_result = c.fetchone()
        if score_result:
            session['user_score'] = score_result[0]
        
        conn.commit()
        
    except sqlite3.Error as e:
        conn.rollback()
        print(f"Database error in submit route: {e}")
    finally:
        conn.close()
    
    # Clear reservation from session
    session.pop('reserved_image_id', None)
    return redirect(url_for('compare'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)