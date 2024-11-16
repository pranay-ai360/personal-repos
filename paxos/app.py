from flask import Flask, redirect, url_for, session, jsonify, request
from authlib.integrations.flask_client import OAuth
from dotenv import load_dotenv
import os
import requests

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY')  # Replace with your Flask secret key

# Initialize OAuth
oauth = OAuth(app)

# Set up Paxos configuration
paxos = oauth.register(
    name='paxos',
    client_id=os.getenv('PAXOS_CLIENT_ID'),  # Replace with your Paxos Client ID
    client_secret=os.getenv('PAXOS_CLIENT_SECRET'),  # Replace with your Paxos Client Secret
    access_token_url='https://oauth.sandbox.paxos.com/oauth2/token',
    authorize_url=None,
    api_base_url=None,
    client_kwargs={'scope': 'scope1 scope2'},  # Replace with your required scopes
)

@app.route('/')
def home():
    return 'Welcome to the Flask Paxos example! <a href="/login">Authenticate with Paxos</a>'

@app.route('/login')
def login():
    # Use client credentials grant type
    token_url = 'https://oauth.sandbox.paxos.com/oauth2/token'
    payload = {
        'grant_type': 'client_credentials',
        'client_id': os.getenv('PAXOS_CLIENT_ID'),
        'client_secret': os.getenv('PAXOS_CLIENT_SECRET'),
        'scope': 'funding:read_profile'  # List multiple scopes here
    }
    response = requests.post(token_url, data=payload)
    
    if response.status_code == 200:
        session['token'] = response.json()
        return redirect('/list_profiles')
    else:
        return f'Error: {response.status_code} - {response.text}', response.status_code

@app.route('/list_profiles')
def list_profiles():
    token = session.get('token')
    if token:
        headers = {
            'Authorization': f'Bearer {token["access_token"]}',
            'Accept': 'application/json'
        }
        response = requests.get('https://api.sandbox.paxos.com/v2/profiles', headers=headers)
        
        if response.status_code == 200:
            profiles = response.json()
            # Include the token in the response
            return jsonify({
                'token': token,
                'profiles': profiles
            })
        else:
            return f'Error: {response.status_code} - {response.text}', response.status_code
    else:
        return 'No token found in session', 401
    
    return redirect('/')

@app.route('/createSandboxDeposit', methods=['POST'])
def create_sandbox_deposit():
    token = session.get('token')
    if token:
        # Get the data from the JSON request body
        data = request.json
        profile_id = data.get('profile_id')
        asset = data.get('asset')
        amount = data.get('amount')
        crypto_network = data.get('crypto_network')
        
        # Check for missing fields
        if not profile_id or not asset or not amount or not crypto_network:
            return 'Missing required fields: profile_id, asset, amount, or crypto_network', 400

        # Define the API endpoint with the profile_id
        deposit_url = f'https://api.sandbox.paxos.com/v2/sandbox/profiles/{profile_id}/deposit'

        # Prepare the payload and headers
        payload = {
            'asset': asset,
            'amount': amount,
            'crypto_network': crypto_network
        }
        headers = {
            'Authorization': f'Bearer {token["access_token"]}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }

        # Make the POST request to create the deposit
        response = requests.post(deposit_url, json=payload, headers=headers)
        
        # Handle the response from Paxos API
        if response.status_code == 200:
            result = response.json()
            return jsonify(result)
        else:
            return f'Error: {response.status_code} - {response.text}', response.status_code
    else:
        return 'No token found in session', 401


@app.route('/logout')
def logout():
    session.pop('token', None)
    return redirect('/')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000, debug=True)