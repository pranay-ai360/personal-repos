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
notifications_dir = '_notificationsstillowe'
os.makedirs(notifications_dir, exist_ok=True)

# List to hold notification data for Excel
notifications_list = []

# Iterate over the user DataFrame to process each user
for _, user_row in user_df.iterrows():
    first_name = user_row['first_name']
    mobile_nr = user_row['mobile_nr']
    emailaddress = user_row['email']
    
    # Fetch price and sell_rate from usdc_df for the corresponding user
    user_usdc_data = usdc_df[usdc_df['mobile_nr'] == mobile_nr]
    if not user_usdc_data.empty:
        price = user_usdc_data['buy_asset_amount'].iloc[0]
        sell_rate = user_usdc_data['sell_rate'].iloc[0]
    else:
        price = 0
        sell_rate = 0

    # Fetch credit transactions for the mobile number
    credit_transactions = credit_df[credit_df['Mobile_Number'] == mobile_nr]
    if not credit_transactions.empty:
        for _, credit_row in credit_transactions.iterrows():
            creditedback = float(credit_row['creditedback'])
            revised_demandLetter = float(credit_row['revised_demandLetter'])
            amountOwedStart = float(credit_row['RevisedExposure'])
            
            if revised_demandLetter > 0:
                # Prepare message header
                message = (f"Hi {first_name} (Mobile Number: {mobile_nr}),\n\n"
                           "Greetings from Maya!\n\n"
                           "As a follow-up to our previous communication, we want to update you on the status of your recent USDC transactions. "
                           "As part of our ongoing review, we have made adjustments to your account to reflect the correct transaction rates. "
                           "While the adjusted amount has been credited to your Maya Wallet, there remains an outstanding balance.\n\n"
                           "In our earlier message, the discrepancy in pricing was identified as a temporary and limited issue, "
                           "and our adjustments were made to ensure fairness for our customers. "
                           "As part of this process, the full outstanding amount has been adjusted from your account to reflect these corrections.\n\n"
                           f"Your full outstanding amount is {amountOwedStart:.2f} PHP.\n\n")

                # Fetch USDC transactions for the mobile number
                usdc_transactions = usdc_df[usdc_df['mobile_nr'] == mobile_nr]
                index = 0  

                for _, usdc_row in usdc_transactions.iterrows():
                    index += 1

                    transaction_id = usdc_row['trade_id']
                    date = usdc_row['CREATEDAT_PHT']
                    quantity = float(usdc_row['buy_asset_amount'])
                    sell_asset_amount = float(usdc_row['sell_asset_amount'])
                    incorrect_rate = float(usdc_row['price'])
                    buy_asset_amount = float(usdc_row['buy_asset_amount'])
                    User_should_have_paid_in_php = float(usdc_row['User_should_have_paid_in_php'])
                    message += (f"Transaction = {index}\n"
                                f"Transaction ID - {transaction_id}\n"
                                f"Date of the Transaction - {date}\n"
                                f"Volume of USDC - {quantity:.6f}\n"
                                f"Rate Previously applied - {incorrect_rate:.2f} PHP\n"
                                f"The Rate applied - {sell_rate:.2f} PHP\n"
                                f"You paid - {buy_asset_amount:.2f} PHP\n"
                                f"You are supposed to pay - {User_should_have_paid_in_php:.2f} PHP\n\n")

                # Fetch wallet transactions for the mobile number
                wallet_transactions = wallet_df[wallet_df['mobile_nr'] == mobile_nr]
                if not wallet_transactions.empty:
                    message += "Please see the balance adjustments performed in your account:\n\n"
                    
                    for _, wallet_row in wallet_transactions.iterrows():
                        amount_debited = float(wallet_row['Amount_Debited'])
                        message += f"Wallet Balance Adjustment: {amount_debited:.2f} PHP\n\n"

                # Fetch bank transactions for the mobile number
                bank_transactions = bank_df[bank_df['MobileNR'] == mobile_nr]
                if not bank_transactions.empty:
                    for _, bank_row in bank_transactions.iterrows():
                        actual_debit = float(bank_row['Actual_Debit'])
                        account = bank_row['AccountNumber']
                        message += f"Account Number: {account}, Bank Account Balance Adjustment: {actual_debit:.2f} PHP\n\n"

                # Fetch crypto transactions for the mobile number
                crypto_transactions = crypto_df[crypto_df['mobile_nr'] == mobile_nr]
                if not crypto_transactions.empty:
                    for _, crypto_row in crypto_transactions.iterrows():
                        currency_id = crypto_row['currency_id']
                        amount = float(crypto_row['amount'])
                        value = float(crypto_row['value'])
                        message += f"Currency: {currency_id}, Balance Adjustment: {amount:.6f}, Value: {value:.6f} PHP\n"

                # Handle creditedback and revised_demandLetter messages
                if creditedback > 0:
                    message += (f"We have also credited your account for any funds that we debited in excess:\n"
                                f"Credit Adjustment: {creditedback:.2f} PHP\n")
                if revised_demandLetter > 0:
                    message += f"Following this adjustment, there remains an outstanding balance of {revised_demandLetter:.2f} PHP that needs to be settled.\n\n"

                # Add closing text
                message += ("We kindly request that you remit the amount to the following account:\n\n"
                            "Maya Bank Savings Account\n"
                            "Account Name: Maya Philippines Inc.\n"
                            "Account Number: 707229159199\n\n"
                            "Once the payment is completed, please send a copy of the proof of deposit to cryptocollections@maya.ph. \n\n"
                            "To resolve this matter promptly, we request that the payment be made within 7 calendar days from the date of this email.\n\n"
                            "Should you have any questions or need further assistance, don’t hesitate to reach out to us. "
                            "We are committed to working with you to find the best resolution.\n\n"
                            "Thank you for your understanding and cooperation.\n\n"
                            "Sincerely,\n"
                            "Maya Philippines Inc.\n")

                # Save the message to a text file in the _notifications folder
                text_file_name = os.path.join(notifications_dir, f'notification_{mobile_nr}.txt')
                with open(text_file_name, 'w') as text_file:
                    text_file.write(message)

                # Append notification data to the list for Excel export
                notifications_list.append({
                    'First Name': first_name,
                    'Mobile Number': mobile_nr,
                    'Email Address': emailaddress,
                    'Outstanding Amount': amountOwedStart,
                    'Message': message  # Save only the first 50 characters of the message
                })

# Create a DataFrame from the notifications list
notifications_df = pd.DataFrame(notifications_list)

# Save the notifications to an Excel file
output_file_path = os.path.join(notifications_dir, 'notifications_summary_stillowe.xlsx')
notifications_df.to_excel(output_file_path, index=False)

print("Notification text files have been created successfully and summary Excel file has been generated.")