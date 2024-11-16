import pandas as pd
import os

# Load the updated XLSX file and its sheets
file_path = 'USDC_incorrect_price_clawback_usingSell_latest.xlsx'
usdc_df = pd.read_excel(file_path, sheet_name='full_transactionList')
clawback_file_path = 'ClawBackReport.xlsx'
wallet_df = pd.read_excel(clawback_file_path, sheet_name='Wallet_Clawback')
bank_df = pd.read_excel(clawback_file_path, sheet_name='Bank_ClawBack')
crypto_df = pd.read_excel(file_path, sheet_name='crypto_sell')
user_details = 'USDC_incorrect_price_clawback_latest.xlsx'
user_df = pd.read_excel(user_details, sheet_name='crypto_user_details')
credit_df = pd.read_excel(file_path, sheet_name='final_demandLetter')

# Create _notifications directory if it doesn't exist
notifications_dir = '_notifications'
os.makedirs(notifications_dir, exist_ok=True)

# Iterate over the user DataFrame to process each user
for _, user_row in user_df.iterrows():
    first_name = user_row['first_name']
    mobile_nr = user_row['mobile_nr']
    
    # Fetch price and sell_rate from usdc_df for the corresponding user
    user_usdc_data = usdc_df[usdc_df['mobile_nr'] == mobile_nr]
    if not user_usdc_data.empty:
        price = user_usdc_data['buy_asset_amount'].iloc[0]  # Assuming you want the first entry for the user
        sell_rate = user_usdc_data['sell_rate'].iloc[0]  # Assuming you want the first entry for the user
    else:
        price = 0  # Default value if no data found
        sell_rate = 0  # Default value if no data found

    # Fetch credit transactions for the mobile number
    credit_transactions = credit_df[credit_df['Mobile_Number'] == mobile_nr]
    if not credit_transactions.empty:
        # Check if any creditedback value is less than 0
        for _, credit_row in credit_transactions.iterrows(): 
            creditedback = float(credit_row['creditedback']) 
            revised_demandLetter  = float(credit_row['revised_demandLetter']) # Ensure this is float
            if  revised_demandLetter == 0:  # Only report if creditedback is less than 0
                # Prepare message header
                message = (f"Hi {first_name} (Mobile Number: {mobile_nr}),\n\n"
                           "Greetings from Maya!\n\n"
                           "We are writing to provide you with an important update regarding your recent USDC transaction. "
                           "We have successfully processed the necessary adjustments, and the correct amounts have now been credited to your Maya Wallet."
                           "You can view the details by checking your transaction history in the app.\n\n"
                           "To ensure transparency, the discrepancy in pricing that occurred was identified as a temporary technical issue. "
                           "Our adjustments were made to correct this error and ensure fairness to all our customers. "
                           "As part of this process, the full outstanding balance has been corrected in your account.\n\n"
                           "Please see the breakdown of your USDC transactions, including the buy, sell:\n\n")

                # Fetch USDC transactions for the mobile number
                usdc_transactions = usdc_df[usdc_df['mobile_nr'] == mobile_nr]
                index = 0  

                for _, usdc_row in usdc_transactions.iterrows():
                    index += 1  # Increment index for user-friendly numbering

                    transaction_id = usdc_row['trade_id']
                    date = usdc_row['CREATEDAT_PHT']
                    quantity = float(usdc_row['buy_asset_amount'])  # Ensure this is float
                    sell_asset_amount = float(usdc_row['sell_asset_amount'])  # Ensure this is float
                    incorrect_rate = float(usdc_row['price'])  # Ensure this is float
                    
                    message += (f"Transaction = {index}\n"
                                f"Transaction ID - {transaction_id}\n"
                                f"Date of the Transaction - {date}\n"
                                f"Volume of USDC - {quantity:.6f}\n"
                                f"Rate Previously applied - {incorrect_rate:.2f} PHP\n"
                                f"The Rate applied - {sell_rate:.2f} PHP\n\n")

                # Fetch wallet transactions for the mobile number
                wallet_transactions = wallet_df[wallet_df['mobile_nr'] == mobile_nr]
                if not wallet_transactions.empty:
                    message += "Please see the balance adjustments performed in your account:\n\n"
                    
                    for _, wallet_row in wallet_transactions.iterrows(): 
                        amount_debited = float(wallet_row['Amount_Debited'])  # Ensure this is float
                        message += f"Wallet Balance Adjustment: {amount_debited:.2f}\n\n"

                # Fetch bank transactions for the mobile number
                bank_transactions = bank_df[bank_df['MobileNR'] == mobile_nr]
                if not bank_transactions.empty:
                    
                    for _, bank_row in bank_transactions.iterrows(): 
                        actual_debit = float(bank_row['Actual_Debit'])  # Ensure this is float
                        account = bank_row['AccountNumber']
                        message += f"Account Number: {account}, Bank Account Balance Adjustment: {actual_debit:.2f}\n"

                # Fetch crypto transactions for the mobile number
                crypto_transactions = crypto_df[crypto_df['mobile_nr'] == mobile_nr]
                if not crypto_transactions.empty:
                    
                    for _, crypto_row in crypto_transactions.iterrows(): 
                        currency_id = crypto_row['currency_id']
                        amount = float(crypto_row['amount'])  # Ensure this is float
                        value = float(crypto_row['value'])
                        message += f"Currency: {currency_id}, Balance Adjustment: {amount:.6f}, Value: {value:.6f}\n"

                # Fetch credit transactions for the mobile number
                credit_transactions = credit_df[credit_df['Mobile_Number'] == mobile_nr]
                if not credit_transactions.empty:
                    for _, credit_row in credit_transactions.iterrows(): 
                        creditedback = float(credit_row['creditedback'])  # Ensure this is float
                        if creditedback > 0:  # Only report if creditedback is greater than 0
                            message += (f"We have also credited your account for any funds that we debited in excess:\n"
                                        f"Credit Adjustment: {round(creditedback, 2):.2f} PHP\n")  # Fixed to use round correctly

                # Add closing text
                message += ("\nWe apologize for any inconvenience this may have caused you and we appreciate your patience during this process.\n"
                            "Should you have any questions or need further assistance, don’t hesitate to reach out to us. "
                            "We are committed to working with you to find the best resolution.\n"
                            "Thank you for your understanding and cooperation.\n"
                            "Sincerely,\n"
                            "Maya Philippines Inc.\n"
                            "cryptocollections@maya.ph\n")

                # Save the message to a text file in the _notifications folder
                text_file_name = os.path.join(notifications_dir, f'notification_{mobile_nr}.txt')
                with open(text_file_name, 'w') as text_file:
                    text_file.write(message)

print("Notification text files have been created successfully.")