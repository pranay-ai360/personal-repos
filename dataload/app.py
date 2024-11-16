from flask import Flask, request, render_template, redirect, url_for, flash
import pandas as pd
import os
import mysql.connector
from mysql.connector import Error

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Set a secret key for flash messages
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        file = request.files['file']
        if file and file.filename.endswith('.csv'):
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
            file.save(filepath)

            # Load CSV into a DataFrame
            df = pd.read_csv(filepath)

            # Get column names and data types
            columns_info = {col: str(df[col].dtype) for col in df.columns}
            return render_template('columns.html', columns=columns_info)

    return render_template('index.html')

@app.route('/process', methods=['POST'])
def process():
    # Get MySQL connection details from the form
    mysql_host = request.form.get('mysql_host')
    mysql_database = request.form.get('mysql_database')
    mysql_port = request.form.get('mysql_port')
    mysql_username = request.form.get('mysql_username')
    mysql_password = request.form.get('mysql_password')

    try:
        # Try to establish a connection
        connection = mysql.connector.connect(
            host=mysql_host,
            database=mysql_database,
            port=mysql_port,
            user=mysql_username,
            password=mysql_password
        )
        
        if connection.is_connected():
            flash("Connection successful!", "success")
            connection.close()
        else:
            flash("Connection failed!", "danger")
    except Error as e:
        flash(f"Error: {str(e)}", "danger")

    return redirect(url_for('index'))

@app.route('/columns', methods=['GET', 'POST'])
def columns():
    # Render a form for MySQL connection details
    return render_template('mysql_connection.html')

if __name__ == '__main__':
    app.run(debug=True)