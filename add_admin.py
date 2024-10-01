import sqlite3
import hashlib

def hash_password(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def add_admin(username, password):
    conn = sqlite3.connect('project_management.db')
    c = conn.cursor()

    # Create users table if it doesn't exist
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY, username TEXT UNIQUE, password TEXT, is_admin INTEGER)''')

    # Check if the username already exists
    c.execute('SELECT * FROM users WHERE username=?', (username,))
    if c.fetchone():
        print(f"User '{username}' already exists.")
        conn.close()
        return

    # Insert new admin user
    try:
        c.execute('INSERT INTO users (username, password, is_admin) VALUES (?, ?, ?)',
                  (username, hash_password(password), 1))
        conn.commit()
        print(f"Admin user '{username}' created successfully.")
    except sqlite3.Error as e:
        print(f"An error occurred: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    admin_username = "admin"
    admin_password = "admin"
    add_admin(admin_username, admin_password)