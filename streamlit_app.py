import streamlit as st
import sqlite3
import hashlib
import streamlit_quill
import sys
from datetime import datetime
from streamlit_quill import st_quill
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Set page config at the very beginning
st.set_page_config(layout="wide",page_icon="assets/artwork.png",page_title="DIGIT ERP - PM TOOL")

# Custom HTML/CSS for the banner
# custom_html = """
# <div class="banner">
#     <img src="./assets/artwork.png" alt="DIGIT ERP">
# </div>
# <style>
#     .banner {
#         width: 160%;
#         height: 200px;
#         overflow: hidden;
#     }
#     .banner img {
#         width: 100%;
#         object-fit: cover;
#     }
# </style>
# """
# # Display the custom HTML
# st.components.v1.html(custom_html)

# Database connection
@st.cache_resource
def init_connection():
    return sqlite3.connect('project_management.db', check_same_thread=False)

conn = init_connection()

# Function to get a new cursor
def get_cursor():
    return conn.cursor()

# Function to add columns if they don't exist
def add_column_if_not_exists(table, column, type):
    c = get_cursor()
    c.execute(f"PRAGMA table_info({table})")
    columns = [col[1] for col in c.fetchall()]
    if column not in columns:
        c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {type}")
        conn.commit()

# Create tables and add necessary columns
def init_db():
    c = get_cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY, username TEXT UNIQUE, password TEXT, is_admin INTEGER)''')
    add_column_if_not_exists('users', 'email', 'TEXT')
    add_column_if_not_exists('users', 'phone_number', 'TEXT')

    c.execute('''CREATE TABLE IF NOT EXISTS projects
                 (id INTEGER PRIMARY KEY, name TEXT, description TEXT)''')

    c.execute('''CREATE TABLE IF NOT EXISTS tasks
                 (id INTEGER PRIMARY KEY, project_id INTEGER, name TEXT, description TEXT, 
                  assigned_to INTEGER, status TEXT, 
                  FOREIGN KEY (project_id) REFERENCES projects(id),
                  FOREIGN KEY (assigned_to) REFERENCES users(id))''')

    c.execute('''CREATE TABLE IF NOT EXISTS comments
                 (id INTEGER PRIMARY KEY, task_id INTEGER, user_id INTEGER, content TEXT, created_at TIMESTAMP,
                  FOREIGN KEY (task_id) REFERENCES tasks(id),
                  FOREIGN KEY (user_id) REFERENCES users(id))''')

    c.execute('''CREATE TABLE IF NOT EXISTS notifications
                 (id INTEGER PRIMARY KEY, user_id INTEGER, message TEXT, created_at TIMESTAMP,
                  FOREIGN KEY (user_id) REFERENCES users(id))''')

    c.execute('''CREATE TABLE IF NOT EXISTS notification_settings
                 (id INTEGER PRIMARY KEY, email INTEGER, in_app INTEGER, sms INTEGER)''')

    conn.commit()

# Initialize the database
init_db()

# Email configuration
EMAIL_HOST = 'smtp.gmail.com'  # Replace with your SMTP server
EMAIL_PORT = 587  # Replace with your SMTP port
EMAIL_HOST_USER = 'your_email@gmail.com'  # Replace with your email
EMAIL_HOST_PASSWORD = 'your_email_password'  # Replace with your email password

# Helper functions
def hash_password(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_user(username, password):
    c = get_cursor()
    c.execute('SELECT id, username, password, is_admin, email FROM users WHERE username=? AND password=?', (username, hash_password(password)))
    return c.fetchone()

def is_admin(user_id):
    c = get_cursor()
    c.execute('SELECT is_admin FROM users WHERE id=?', (user_id,))
    return c.fetchone()[0] == 1

def create_user(username, password, email, is_admin=0):
    c = get_cursor()
    try:
        c.execute('INSERT INTO users (username, password, is_admin, email) VALUES (?, ?, ?, ?)',
                  (username, hash_password(password), is_admin, email))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False

def get_projects():
    c = get_cursor()
    c.execute('SELECT * FROM projects')
    return c.fetchall()

def create_project(name, description):
    c = get_cursor()
    c.execute('INSERT INTO projects (name, description) VALUES (?, ?)', (name, description))
    conn.commit()

def get_tasks(project_id, user_id):
    c = get_cursor()
    if is_admin(user_id):
        c.execute('SELECT * FROM tasks WHERE project_id=?', (project_id,))
    else:
        c.execute('SELECT * FROM tasks WHERE project_id=? AND assigned_to=?', (project_id, user_id))
    return c.fetchall()

def create_task(project_id, name, description, assigned_to, notify_email, notify_in_app, notify_sms):
    c = get_cursor()
    c.execute('INSERT INTO tasks (project_id, name, description, assigned_to, status) VALUES (?, ?, ?, ?, ?)',
              (project_id, name, description, assigned_to, 'New'))
    conn.commit()
    
    # Send notifications based on selected options
    c.execute('SELECT email, phone_number FROM users WHERE id=?', (assigned_to,))
    result = c.fetchone()
    user_email = result[0] if result else None
    user_phone = result[1] if result and len(result) > 1 else None
    
    notification_message = f"New task assigned: {name}"
    
    if notify_email and user_email:
        send_email_notification(user_email, "New Task Assigned", notification_message)
    
    if notify_in_app:
        send_in_app_notification(assigned_to, notification_message)
    
    if notify_sms and user_phone:
        send_sms_notification(user_phone, notification_message)

def update_task_status(task_id, status, user_id):
    c = get_cursor()
    c.execute('UPDATE tasks SET status=? WHERE id=?', (status, task_id))
    conn.commit()
    
    # Notify admin
    c.execute('SELECT name FROM tasks WHERE id=?', (task_id,))
    task_name = c.fetchone()[0]
    c.execute('SELECT username FROM users WHERE id=?', (user_id,))
    username = c.fetchone()[0]
    notify_admin(f"Task '{task_name}' status updated to {status} by {username}")

def update_task_description(task_id, description):
    c = get_cursor()
    c.execute('UPDATE tasks SET description=? WHERE id=?', (description, task_id))
    conn.commit()

def delete_task(task_id):
    c = get_cursor()
    c.execute('DELETE FROM tasks WHERE id=?', (task_id,))
    c.execute('DELETE FROM comments WHERE task_id=?', (task_id,))
    conn.commit()

def get_users():
    c = get_cursor()
    c.execute('SELECT id, username FROM users WHERE is_admin=0')
    return c.fetchall()

def calculate_project_progress(project_id):
    c = get_cursor()
    c.execute('SELECT COUNT(*) FROM tasks WHERE project_id=?', (project_id,))
    total_tasks = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM tasks WHERE project_id=? AND status IN ("Completed", "Closed")', (project_id,))
    completed_tasks = c.fetchone()[0]
    return completed_tasks / total_tasks if total_tasks > 0 else 0

def add_comment(task_id, user_id, content):
    c = get_cursor()
    c.execute('INSERT INTO comments (task_id, user_id, content, created_at) VALUES (?, ?, ?, ?)',
              (task_id, user_id, content, datetime.now()))
    conn.commit()

    # Notify admin
    c.execute('SELECT name FROM tasks WHERE id=?', (task_id,))
    task_name = c.fetchone()[0]
    c.execute('SELECT username FROM users WHERE id=?', (user_id,))
    username = c.fetchone()[0]
    notify_admin(f"New comment on task '{task_name}' by {username}")

def get_comments(task_id):
    c = get_cursor()
    c.execute('''SELECT comments.content, comments.created_at, users.username 
                 FROM comments 
                 JOIN users ON comments.user_id = users.id 
                 WHERE comments.task_id=? 
                 ORDER BY comments.created_at DESC''', (task_id,))
    return c.fetchall()

def send_email_notification(to_email, subject, body):
    msg = MIMEMultipart()
    msg['From'] = EMAIL_HOST_USER
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    try:
        server = smtplib.SMTP(EMAIL_HOST, EMAIL_PORT)
        server.starttls()
        server.login(EMAIL_HOST_USER, EMAIL_HOST_PASSWORD)
        text = msg.as_string()
        server.sendmail(EMAIL_HOST_USER, to_email, text)
        server.quit()
        return True
    except Exception as e:
        st.error(f"Failed to send email: {str(e)}")
        return False

def send_in_app_notification(user_id, message):
    c = get_cursor()
    c.execute('INSERT INTO notifications (user_id, message, created_at) VALUES (?, ?, ?)',
              (user_id, message, datetime.now()))
    conn.commit()

def send_sms_notification(phone_number, message):
    # This is a placeholder for SMS sending logic
    print(f"SMS notification sent to {phone_number}: {message}")

def get_notifications(user_id):
    c = get_cursor()
    c.execute('SELECT message, created_at FROM notifications WHERE user_id=? ORDER BY created_at DESC', (user_id,))
    return c.fetchall()

def notify_admin(message):
    c = get_cursor()
    c.execute('SELECT id FROM users WHERE is_admin=1')
    admin_ids = [row[0] for row in c.fetchall()]
    for admin_id in admin_ids:
        send_in_app_notification(admin_id, message)

def get_notification_settings():
    c = get_cursor()
    c.execute('SELECT * FROM notification_settings LIMIT 1')
    settings = c.fetchone()
    if settings is None:
        c.execute('INSERT INTO notification_settings (email, in_app, sms) VALUES (?, ?, ?)', (1, 1, 0))
        conn.commit()
        return {'email': True, 'in_app': True, 'sms': False}
    return {'email': bool(settings[1]), 'in_app': bool(settings[2]), 'sms': bool(settings[3])}

def update_notification_settings(email, in_app, sms):
    c = get_cursor()
    c.execute('UPDATE notification_settings SET email=?, in_app=?, sms=?', (int(email), int(in_app), int(sms)))
    conn.commit()

# Function to display tasks
def display_tasks(project_id, user_id, user_is_admin):
    st.subheader('Tasks')
    
    # Filters
    status_filter = st.multiselect('Filter by Status', ['New', 'Opened', 'In-Progress', 'Completed', 'Re-Opened', 'Closed'], key='status_filter')
    assignee_filter = st.multiselect('Filter by Assignee', [user[1] for user in get_users()], key='assignee_filter')

    tasks = get_tasks(project_id, user_id)
    filtered_tasks = [task for task in tasks if 
                      (not status_filter or task[5] in status_filter) and
                      (not assignee_filter or task[4] in [user[0] for user in get_users() if user[1] in assignee_filter])]

    for index, task in enumerate(filtered_tasks):
        task_id, _, task_name, task_description, assigned_to, status = task
        with st.expander(f'{task_name} (Status: {status})'):
            st.write(f'**Assigned to:** {assigned_to}')
            
            st.write('**Description:**')
            st.write(task_description)
            
            st.write('**Comments:**')
            comments = get_comments(task_id)
            for comment in comments:
                st.text(f"{comment[2]} ({comment[1]}): {comment[0]}")
            
            if status != 'Closed' or user_is_admin:
                new_comment = st.text_area('Add a comment', key=f'comment_input_{task_id}')
                if st.button('Post Comment', key=f'post_comment_{task_id}'):
                    add_comment(task_id, user_id, new_comment)
                    st.success('Comment added successfully')
                    st.rerun()
            
            if user_is_admin:
                new_status = st.selectbox('Update Status', 
                                          ['New', 'Opened', 'In-Progress', 'Completed', 'Re-Opened', 'Closed'],
                                          index=['New', 'Opened', 'In-Progress', 'Completed', 'Re-Opened', 'Closed'].index(status),
                                          key=f'status_select_{task_id}')
                if new_status != status:
                    if new_status in ['Completed', 'Closed'] and not comments:
                        st.error('Please add a comment before marking the task as Completed or Closed.')
                    elif st.button('Update Status', key=f'update_status_{task_id}'):
                        update_task_status(task_id, new_status, user_id)
                        st.success('Status updated successfully')                        
                        st.rerun()
            elif user_id == assigned_to and status != 'Closed':
                new_status = st.selectbox('Update Status', 
                                          ['New', 'Opened', 'In-Progress', 'Completed', 'Re-Opened'],
                                          index=['New', 'Opened', 'In-Progress', 'Completed', 'Re-Opened'].index(status),
                                          key=f'status_select_{task_id}')
                if new_status != status:
                    if new_status == 'Completed' and not comments:
                        st.error('Please add a comment before marking the task as Completed.')
                    elif st.button('Update Status', key=f'update_status_{task_id}'):
                        update_task_status(task_id, new_status, user_id)
                        st.success('Status updated successfully')
                        st.rerun()
            else:
                st.write(f'**Current Status:** {status}')
            
            if user_is_admin:
                if st.button('Delete Task', key=f'delete_task_{task_id}'):
                    delete_task(task_id)
                    st.success('Task deleted successfully')
                    st.rerun()

# Streamlit UI
# st.image("assets/artwork.png", width=150)
st.header('DIGIT ERP - Project Management Tool')

# Initialize session state
if 'user' not in st.session_state:
    st.session_state.user = None
if 'view' not in st.session_state:
    st.session_state.view = None

# Sidebar for login and logout
sidebar = st.sidebar

# Login/Logout
if st.session_state.user is None:
    sidebar.header("Login")
    username = sidebar.text_input('Username')
    password = sidebar.text_input('Password', type='password')
    if sidebar.button('Login'):
        user = check_user(username, password)
        if user:
            st.session_state.user = {
                'id': user[0],
                'username': user[1],
                'is_admin': user[3],
                'email': user[4]
            }
            st.success('Logged in successfully')
            st.rerun()
        else:
            st.error('Invalid username or password')
else:
    if sidebar.button('Logout'):
        st.session_state.user = None
        st.session_state.view = None
        st.rerun()

# Main application
if st.session_state.user:
    user_id = st.session_state.user['id']
    username = st.session_state.user['username']
    user_is_admin = st.session_state.user['is_admin']
    user_email = st.session_state.user['email']
    
    sidebar.write(f'Welcome, {username}!')

    # Get current notification settings
    notification_settings = get_notification_settings()

    # Admin-only section
    if user_is_admin:
        admin_action = sidebar.selectbox(
            "Admin Actions",
            ["None", "Manage Projects", "Create User", "Notification Settings"],
            key="admin_action"
        )
        if admin_action != "None":
            st.session_state.view = "admin"
        
    # Project selection (for all users)
    sidebar.header('Projects')
    projects = get_projects()
    project_names = [p[1] for p in projects]
    project_names.insert(0, "Select a project")
    selected_project_name = sidebar.selectbox('Select a project', project_names, key='project_select')
    
    if selected_project_name != "Select a project":
        st.session_state.view = "project"

    # Main content area
    if st.session_state.view == "admin":
        if admin_action == "Manage Projects":
            tab1, tab2 = st.tabs(["Create Project", "Existing Projects"])
            
            with tab1:
                st.subheader("Create New Project")
                new_project_name = st.text_input("Project Name")
                new_project_description = st.text_area("Project Description")
                if st.button("Create Project"):
                    if new_project_name and new_project_description:
                        create_project(new_project_name, new_project_description)
                        st.success(f"Project '{new_project_name}' created successfully!")
                        st.rerun()
                    else:
                        st.error("Project name and description are required.")
            
            with tab2:
                st.subheader("Existing Projects")
                projects = get_projects()
                for project in projects:
                    st.write(f"- {project[1]}")

        elif admin_action == "Create User":
            st.subheader("Create New User")
            new_username = st.text_input('New Username')
            new_password = st.text_input('New Password', type='password')
            new_email = st.text_input('Email')
            if st.button('Create User'):
                if create_user(new_username, new_password, new_email):
                    st.success('User created successfully')
                else:
                    st.error('Username already exists')

        elif admin_action == "Notification Settings":
            st.subheader('Notification Settings')
            email = st.checkbox('Email Notifications', value=notification_settings['email'], key='email_notif')
            in_app = st.checkbox('In-App Notifications', value=notification_settings['in_app'], key='in_app_notif')
            sms = st.checkbox('SMS Notifications', value=notification_settings['sms'], key='sms_notif')
            if st.button('Save Settings', key='save_notif_settings'):
                update_notification_settings(email, in_app, sms)
                st.success('Notification settings updated successfully')
                st.rerun()

    elif st.session_state.view == "project":
        if selected_project_name != "Select a project":
            try:
                selected_project = next(p for p in projects if p[1] == selected_project_name)
                project_id, project_name, project_description = selected_project
                
                st.header(project_name)
                st.write(project_description)
                progress = calculate_project_progress(project_id)
                st.progress(progress)   
                st.write(f'Progress: {progress:.0%}')

                if user_is_admin:
                    # Admin view
                    view_option = st.radio('View', ['Side by Side', 'Tabbed'], key='view_option')

                    if view_option == 'Side by Side':
                        left_column, right_column = st.columns(2)
                        
                        # Create task
                        with left_column:
                            st.subheader('Create Task')
                            task_name = st.text_input('Task Name', key='task_name_input')
                            use_rich_text = st.checkbox('Use Rich Text Editor for Description', key='use_rich_text_checkbox')
                            if use_rich_text:
                                task_description = st_quill(placeholder="Enter task description...", key="task_description_quill")
                            else:
                                task_description = st.text_area('Task Description', key='task_description_textarea')
                            
                            users = get_users()
                            selected_user = st.selectbox('Assign To', users, format_func=lambda x: x[1], key='assign_to_select')
                            
                            st.subheader("Notification Options")
                            notify_email = st.checkbox("Send Email Notification", key="notify_email_checkbox", disabled=not notification_settings['email'])
                            notify_in_app = st.checkbox("Send In-App Notification", key="notify_in_app_checkbox", disabled=not notification_settings['in_app'])
                            notify_sms = st.checkbox("Send SMS Notification", key="notify_sms_checkbox", disabled=not notification_settings['sms'])
                            
                            if st.button('Create Task', key='create_task_button'):
                                if task_name and task_description:
                                    create_task(project_id, task_name, task_description, selected_user[0], notify_email, notify_in_app, notify_sms)
                                    st.success('Task created successfully')
                                    st.rerun()
                                else:
                                    st.error('Task name and description are required. Please fill in both fields.')

                        # Task list
                        with right_column:
                            display_tasks(project_id, user_id, user_is_admin)
                    else:
                        tab1, tab2 = st.tabs(["Create Task", "View Tasks"])
                        
                        # Create task
                        with tab1:
                            st.subheader('Create Task')
                            task_name = st.text_input('Task Name', key='task_name_input_tab')
                            use_rich_text = st.checkbox('Use Rich Text Editor for Description', key='use_rich_text_checkbox_tab')
                            if use_rich_text:
                                task_description = st_quill(placeholder="Enter task description...", key="task_description_quill_tab")
                            else:
                                task_description = st.text_area('Task Description', key='task_description_textarea_tab')
                            
                            users = get_users()
                            selected_user = st.selectbox('Assign To', users, format_func=lambda x: x[1], key='assign_to_select_tab')
                            
                            st.subheader("Notification Options")
                            notify_email = st.checkbox("Send Email Notification", key="notify_email_checkbox_tab", disabled=not notification_settings['email'])
                            notify_in_app = st.checkbox("Send In-App Notification", key="notify_in_app_checkbox_tab", disabled=not notification_settings['in_app'])
                            notify_sms = st.checkbox("Send SMS Notification", key="notify_sms_checkbox_tab", disabled=not notification_settings['sms'])
                            
                            if st.button('Create Task', key='create_task_button_tab'):
                                if task_name and task_description:
                                    create_task(project_id, task_name, task_description, selected_user[0], notify_email, notify_in_app, notify_sms)
                                    st.success('Task created successfully')
                                    st.rerun()
                                else:
                                    st.error('Task name and description are required. Please fill in both fields.')

                        # Task list
                        with tab2:
                            display_tasks(project_id, user_id, user_is_admin)
                else:
                    # Non-admin view
                    display_tasks(project_id, user_id, user_is_admin)
            except StopIteration:
                st.warning("The selected project could not be found. It may have been deleted.")
        else:
            st.info("Please select a project from the sidebar to view details.")
    else:
        st.info("Please select a project from the sidebar or an admin action to view details.")

    # Notifications
    sidebar.header('Notifications')
    notifications = get_notifications(user_id)
    for i, (message, created_at) in enumerate(notifications):
        sidebar.write(f'[{created_at}] {message}')

else:
    st.write("Please log in to access the application.")

# Create initial admin user if not exists
c = get_cursor()
c.execute('SELECT * FROM users WHERE is_admin=1')
if not c.fetchone():
    create_user('admin', 'admin123', 'admin@example.com', is_admin=1)
    st.info('Initial admin user created. Username: admin, Password: admin123, Email: admin@example.com')