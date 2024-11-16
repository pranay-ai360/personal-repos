from flask import Flask
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)

# Update the username, password, host, port, and database name according to your MariaDB configuration
# Note the change to mysql+pymysql in the URI below
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+mysqldb://crypto_analytics_viewer:krffZ3C8VW9ADr7xd9FTosFhxLFPz7y37gXRnLONO2dxLwZ5@13.215.135.190:20003/paymaya_api'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

@app.route('/')
def index():
    try:
        # Attempt to query the database to ensure connection is established
        db.engine.execute('SELECT 1')
        return 'Connection established'
    except Exception as e:
        # If an error occurs, return the error message
        return f'Error establishing connection: {e}'

if __name__ == '__main__':
    app.run(debug=True)
