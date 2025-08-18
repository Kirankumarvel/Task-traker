import logging
from logging.handlers import RotatingFileHandler
from flask import Flask, render_template, request, redirect, url_for, flash
import os
import sqlite3
from contextlib import closing
from werkzeug.exceptions import HTTPException
from werkzeug.utils import escape
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

# Configuration
class Config:
    SECRET_KEY = os.environ.get('FLASK_SECRET_KEY', os.urandom(24).hex())
    DATABASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tasks.db')
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO').upper()
    MAX_LOG_BYTES = 1024 * 1024  # 1MB
    LOG_BACKUP_COUNT = 5
    FLASK_ENV = os.environ.get('FLASK_ENV', 'production')

# Custom Exceptions
class DatabaseError(Exception):
    """Base exception for database-related errors"""

class SchemaError(DatabaseError):
    """Exception for database schema issues"""

# Data Model
TASK_NOT_FOUND_MSG = 'Task not found!'

@dataclass
class Task:
    id: int
    description: str
    created_at: str
    is_completed: bool = False

# Application Factory
def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # Initialize logging
    configure_logging(app)
    
    # Initialize database
    with app.app_context():
        init_db(app)
    
    # Register error handlers
    register_error_handlers(app)
    
    # Register routes
    register_routes(app)
    
    return app

def configure_logging(app: Flask):
    """Configure application logging"""
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Console handler
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    
    # File handler with rotation
    file_handler = RotatingFileHandler(
        'task_tracker.log',
        maxBytes=app.config['MAX_LOG_BYTES'],
        backupCount=app.config['LOG_BACKUP_COUNT']
    )
    file_handler.setFormatter(formatter)
    
    # Set log level
    app.logger.setLevel(app.config['LOG_LEVEL'])
    
    # Remove default handlers
    for handler in app.logger.handlers[:]:
        app.logger.removeHandler(handler)
    
    # Add our handlers
    app.logger.addHandler(stream_handler)
    app.logger.addHandler(file_handler)

def get_db_connection(app: Flask) -> sqlite3.Connection:
    """Get a database connection with proper error handling"""
    try:
        conn = sqlite3.connect(app.config['DATABASE'])
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn
    except sqlite3.Error as e:
        app.logger.error(f"Database connection error: {str(e)}")
        raise DatabaseError("Database connection failed") from e

def init_db(app: Flask):
    """Initialize the database with proper schema"""
    try:
        with closing(get_db_connection(app)) as conn:
            # Check if table exists
            conn.execute('''
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    description TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_completed BOOLEAN DEFAULT FALSE
                )
            ''')
            
            # Create indexes
            conn.execute('CREATE INDEX IF NOT EXISTS idx_created_at ON tasks(created_at)')
            
            conn.commit()
        app.logger.info("Database initialized successfully")
    except sqlite3.Error as e:
        app.logger.error(f"Database initialization error: {str(e)}")
        raise SchemaError("Database initialization failed") from e

def register_error_handlers(app: Flask):
    """Register error handlers for the application"""
    
    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('404.html'), 404
    
    @app.errorhandler(500)
    def internal_server_error(e):
        app.logger.error(f"Internal Server Error: {str(e)}")
        return render_template('500.html'), 500
    
    @app.errorhandler(DatabaseError)
    def handle_database_error(e):
        app.logger.error(f"Database Error: {str(e)}")
        flash('A database error occurred. Please try again later.', 'error')
        return redirect(url_for('index'))

def register_routes(app: Flask):
    """Register all application routes"""
    
    @app.route('/')
    def index():
        """Show all tasks"""
        try:
            with closing(get_db_connection(app)) as conn:
                tasks = conn.execute(
                    'SELECT * FROM tasks ORDER BY created_at DESC'
                ).fetchall()
                
            return render_template('index.html', tasks=tasks)
        except Exception as e:
            app.logger.error(f"Error fetching tasks: {str(e)}")
            flash('Failed to load tasks. Please try again.', 'error')
            return render_template('index.html', tasks=[])

    @app.route('/add', methods=['POST'])
    def add_task():
        """Add a new task"""
        task = escape(request.form.get('task', '').strip())
        if not task:
            flash('Task cannot be empty!', 'error')
            return redirect(url_for('index'))

        try:
            with closing(get_db_connection(app)) as conn:
                conn.execute(
                    'INSERT INTO tasks (description) VALUES (?)',
                    (task,)
                )
                conn.commit()
            flash('Task added successfully!', 'success')
            app.logger.info(f"Added task: {task}")
        except Exception as e:
            app.logger.error(f"Error adding task: {str(e)}")
            flash('Failed to add task. Please try again.', 'error')
        
        return redirect(url_for('index'))

    @app.route('/delete/<int:task_id>')
    def delete_task(task_id):
        """Delete a task"""
        try:
            with closing(get_db_connection(app)) as conn:
                cursor = conn.execute(
                    'DELETE FROM tasks WHERE id = ?',
                    (task_id,)
                )
                    flash(TASK_NOT_FOUND_MSG, 'error')
                if cursor.rowcount == 0:
                    flash('Task not found!', 'error')
                else:
                    flash('Task deleted successfully!', 'success')
                    app.logger.info(f"Deleted task ID: {task_id}")
        except Exception as e:
            app.logger.error(f"Error deleting task: {str(e)}")
            flash('Failed to delete task. Please try again.', 'error')
        
        return redirect(url_for('index'))

    @app.route('/edit/<int:task_id>', methods=['GET', 'POST'])
    def edit_task(task_id):
        """Edit an existing task"""
        try:
            with closing(get_db_connection(app)) as conn:
                if request.method == 'POST':
                    new_task = escape(request.form.get('task', '').strip())
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
                if not task:
                    flash(TASK_NOT_FOUND_MSG, 'error')
                    return redirect(url_for('index'))
                    flash('Task not found!', 'error')
                    return redirect(url_for('index'))

                return render_template('edit.html', task=task)
        except Exception as e:
            app.logger.error(f"Error editing task: {str(e)}")
            flash('Failed to edit task. Please try again.', 'error')
            return redirect(url_for('index'))

    @app.route('/complete/<int:task_id>')
    def complete_task(task_id):
        """Mark a task as completed"""
        try:
            with closing(get_db_connection(app)) as conn:
                cursor = conn.execute(
                    'UPDATE tasks SET is_completed = TRUE WHERE id = ?',
                    (task_id,)
                )
                conn.commit()
                if cursor.rowcount == 0:
                    flash('Task not found!', 'error')
                else:
                    flash('Task marked as completed!', 'success')
        except Exception as e:
            app.logger.error(f"Error completing task: {str(e)}")
            flash('Failed to complete task. Please try again.', 'error')
        
        return redirect(url_for('index'))

# Application Entry Point
if __name__ == '__main__':
    app = create_app()
    
    # Run with production WSGI server if in production
    if app.config['FLASK_ENV'] == 'production':
        from waitress import serve
        serve(app, host='0.0.0.0', port=5000)
    else:
        app.run(host='0.0.0.0', port=5000, debug=True)
