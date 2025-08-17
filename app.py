import logging
from flask import Flask, render_template, request, redirect, url_for, flash
import os
import sqlite3
from contextlib import closing
from werkzeug.exceptions import HTTPException

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'dev-secret-key-123')

# Configure logging
logging.basicConfig(
    level=os.environ.get('LOG_LEVEL', 'DEBUG').upper(),
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('task_tracker.log')
    ]
)

DATABASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tasks.db')

def get_db_connection():
    """Get a database connection with proper error handling"""
    try:
        conn = sqlite3.connect(DATABASE)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn
    except sqlite3.Error as e:
        logging.error(f"Database connection error: {str(e)}")
        raise RuntimeError("Database connection failed") from e

def init_db():
    """Initialize the database with proper error handling"""
    try:
        with closing(get_db_connection()) as conn:
            # Drop existing table if it has wrong schema
            conn.execute('DROP TABLE IF EXISTS tasks')
            
            # Create new table with correct schema
            conn.execute('''
                CREATE TABLE tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    description TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()
        logging.info("Database initialized successfully")
    except sqlite3.Error as e:
        logging.error(f"Database initialization error: {str(e)}")
        raise RuntimeError("Database initialization failed") from e

@app.before_first_request
def initialize_app():
    """Initialize application before first request"""
    try:
        init_db()
    except Exception as e:
        logging.critical(f"Failed to initialize database: {str(e)}")
        raise

@app.route('/')
def index():
    """Show all tasks"""
    try:
        with closing(get_db_connection()) as conn:
            # First check if created_at column exists
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(tasks)")
            columns = [column[1] for column in cursor.fetchall()]
            
            if 'created_at' not in columns:
                # Fallback to simple select if column doesn't exist
                tasks = conn.execute('SELECT id, description FROM tasks').fetchall()
            else:
                tasks = conn.execute('SELECT * FROM tasks ORDER BY created_at DESC').fetchall()
                
        return render_template('index.html', tasks=tasks)
    except Exception as e:
        logging.error(f"Error fetching tasks: {str(e)}")
        flash('Failed to load tasks. Please try again.', 'error')
        return render_template('index.html', tasks=[])

@app.route('/add', methods=['POST'])
def add_task():
    """Add a new task"""
    task = request.form.get('task', '').strip()
    if not task:
        flash('Task cannot be empty!', 'error')
        return redirect(url_for('index'))

    try:
        with closing(get_db_connection()) as conn:
            conn.execute('INSERT INTO tasks (description) VALUES (?)', (task,))
            conn.commit()
        flash('Task added successfully!', 'success')
        logging.info(f"Added task: {task}")
    except Exception as e:
        logging.error(f"Error adding task: {str(e)}")
        flash('Failed to add task. Please try again.', 'error')
    
    return redirect(url_for('index'))

@app.route('/delete/<int:task_id>')
def delete_task(task_id):
    """Delete a task"""
    try:
        with closing(get_db_connection()) as conn:
            cursor = conn.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
            conn.commit()
            if cursor.rowcount == 0:
                flash('Task not found!', 'error')
            else:
                flash('Task deleted successfully!', 'success')
                logging.info(f"Deleted task ID: {task_id}")
    except Exception as e:
        logging.error(f"Error deleting task: {str(e)}")
        flash('Failed to delete task. Please try again.', 'error')
    
    return redirect(url_for('index'))

@app.route('/edit/<int:task_id>', methods=['GET', 'POST'])
def edit_task(task_id):
    """Edit an existing task"""
    try:
        with closing(get_db_connection()) as conn:
            if request.method == 'POST':
                new_task = request.form.get('task', '').strip()
                if not new_task:
                    flash('Task cannot be empty!', 'error')
                else:
                    cursor = conn.execute(
                        'UPDATE tasks SET description = ? WHERE id = ?',
                        (new_task, task_id)
                    )
                    conn.commit()
                    if cursor.rowcount == 0:
                        flash('Task not found!', 'error')
                    else:
                        flash('Task updated successfully!', 'success')
                        return redirect(url_for('index'))

            task = conn.execute(
                'SELECT * FROM tasks WHERE id = ?', 
                (task_id,)
            ).fetchone()
            
            if not task:
                flash('Task not found!', 'error')
                return redirect(url_for('index'))

            return render_template('edit.html', task=task)
    except Exception as e:
        logging.error(f"Error editing task: {str(e)}")
        flash('Failed to edit task. Please try again.', 'error')
        return redirect(url_for('index'))

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    logging.error(f"Internal Server Error: {str(e)}")
    return render_template('500.html'), 500

if __name__ == '__main__':
    try:
        initialize_app()
        app.run(host='0.0.0.0', port=5000, debug=True)
    except Exception as e:
        logging.critical(f"Application failed to start: {str(e)}")
