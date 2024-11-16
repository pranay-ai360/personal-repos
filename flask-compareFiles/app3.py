from flask import Flask, jsonify
import pandas as pd

app = Flask(__name__)

@app.route('/sm-headings')
def column_headings():
    # Read the CSV file
    df = pd.read_csv('sm_transfers.csv')
    

    # Get the column headings
    columns = df.columns.tolist()

    # Return the column headings as a JSON response
    return jsonify(columns)

if __name__ == '__main__':
    app.run(debug=True)
