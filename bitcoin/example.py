import os
import hashlib
from ecdsa import SigningKey, VerifyingKey, SECP256k1, BadSignatureError

# Provided keys and address
private_key_hex = "8f2a559490b100d0aa6e4c8bb9d3bb1d3a5d65745d1353e4d72dfb3c7c13eb74"
public_key_hex = "04bfcabdcabd0a8391e9056e4cd8e9d1c6c42c37a7740da0b5f1b935534fb89f5f9e0b4e51a3013f42191db6e0c244112e4bb1c146a9032b95cb6cb6ad8968eb71"
alice_address = "1ec13ff50868c3ecf5a04a7cb105104dc0da2c"

def hash_transaction(inputs, outputs):
    """
    Hashes the transaction inputs and outputs.
    """
    tx_data = str(inputs) + str(outputs)
    return hashlib.sha256(hashlib.sha256(tx_data.encode()).digest()).digest()

def validate_transaction(inputs, outputs, signature, public_key_hex):
    """
    Validates a Bitcoin transaction.
    """
    # Recreate the transaction hash
    tx_hash = hash_transaction(inputs, outputs)
    
    # Convert the public key to VerifyingKey format
    public_key = VerifyingKey.from_string(bytes.fromhex(public_key_hex), curve=SECP256k1)
    
    try:
        # Verify the signature
        public_key.verify(signature, tx_hash)
        print("Transaction is valid.")
        return True
    except BadSignatureError:
        print("Transaction validation failed: Invalid signature.")
        return False

# Simulated inputs and outputs for Alice's transaction
inputs = [
    {
        "txid": "e3a1d8f033a9873e5b0a09d2a3a69f4dcaae14b122a9a6c9f7c2b9c99120a9c3",
        "vout": 0
    }
]
outputs = [
    {
        "value": 0.1,
        "address": "1445f9154ef7a084316d39353f0a7cb8534446b87"
    },
    {
        "value": 0.0499,
        "address": alice_address
    }
]

# Simulated signature (signed with Alice's private key)
private_key = bytes.fromhex(private_key_hex)
sk = SigningKey.from_string(private_key, curve=SECP256k1)
tx_hash = hash_transaction(inputs, outputs)
signature = sk.sign(tx_hash)

# Validate the transaction
is_valid = validate_transaction(inputs, outputs, signature, public_key_hex)
print("Validation result:", is_valid)