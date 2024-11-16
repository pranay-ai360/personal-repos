from flask import Flask
import pandas as pd
from datetime import datetime

app = Flask(__name__)

@app.route('/refresh', methods=['GET'])
def refresh_data():
    # Define file names
    transactions_file = 'transactions_1707992286338.csv'
    sm_transfers_file = 'sm_transfers.csv'

    # Load and filter the transactions file
    transactions_df = pd.read_csv(transactions_file)
    transactions_df = transactions_df[transactions_df['Created By'].isin(['', 'API_Initiator_SM PayMaya Philippines'])]
    transactions_df = transactions_df[['Fireblocks TxId', 'Status', 'Created By']]

    # Load the sm_transfers file
    sm_transfers_df = pd.read_csv(sm_transfers_file)
    sm_transfers_df = sm_transfers_df[['transfer_id', 'remote_txid', 'status']]

    # Merge both dataframes on the condition Fireblocks TxId = remote_txid
    merged_df = pd.merge(transactions_df, sm_transfers_df, left_on='Fireblocks TxId', right_on='remote_txid', how='outer', indicator=True)

    # Separate matched and unmatched records
    matched_df = merged_df[merged_df['_merge'] == 'both']
    unmatched_df = merged_df[merged_df['_merge'] != 'both']

    # Drop the merge indicator column
    matched_df.drop('_merge', axis=1, inplace=True)
    unmatched_df.drop('_merge', axis=1, inplace=True)

    # Generate filenames based on the current datetime
    datetime_str = datetime.now().strftime('%Y%m%d%H%M%S')
    all_results_filename = f'all_result_{datetime_str}.csv'
    unmatched_results_filename = f'unmatched_result_{datetime_str}.csv'

    # Write matched and unmatched records to files
    matched_df.to_csv(all_results_filename, index=False)
    unmatched_df.to_csv(unmatched_results_filename, index=False)

    return f"Processed data. Matched records saved to {all_results_filename} and unmatched records to {unmatched_results_filename}."

if __name__ == '__main__':
    app.run(debug=True)
