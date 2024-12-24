import os
import hashlib
from ecdsa import SigningKey, SECP256k1

def generate_bitcoin_address():
    # Generate a random private key
    private_key = os.urandom(32)
    private_key_hex = private_key.hex()

    # Generate the public key
    sk = SigningKey.from_string(private_key, curve=SECP256k1)
    public_key = sk.verifying_key
    public_key_hex = "04" + public_key.to_string().hex()  # Uncompressed format

    # Compute the Bitcoin address
    sha256_hash = hashlib.sha256(bytes.fromhex(public_key_hex)).digest()
    ripemd160_hash = hashlib.new('ripemd160', sha256_hash).digest()
    bitcoin_address = "1" + ripemd160_hash.hex()  # Simplified; typically a Base58Check encoding is used

    return private_key_hex, public_key_hex, bitcoin_address

# Generate Bob's Bitcoin address
bob_private_key, bob_public_key, bob_bitcoin_address = generate_bitcoin_address()

print("Bob's Private Key:", bob_private_key)
print("Bob's Public Key:", bob_public_key)
print("Bob's Bitcoin Address:", bob_bitcoin_address)