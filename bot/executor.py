import logging
import os
import json
import time
import base64
import uuid
import aiohttp
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend

log = logging.getLogger('executor')


def sign_request(method, path, private_key_str):
    timestamp = str(int(time.time() * 1000))
    path_to_sign = path.split('?')[0]
    message = timestamp + method.upper() + path_to_sign
    private_key_bytes = private_key_str.strip().replace('\\n', '\n').encode()
    if not private_key_bytes.startswith(b'-----'):
        private_key_bytes = b'-----BEGIN RSA PRIVATE KEY-----\n' + private_key_bytes + b'\n-----END RSA PRIVATE KEY-----'
    try:
        private_key = serialization.load_pem_private_key(private_key_bytes, password=None, backend=default_backend())
        signature = private_key.sign(message.encode(), padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=hashes.SHA256.digest_size), hashes.SHA256())
        sig_b64 = base64.b64encode(signature).decode()
        return {
            'KALSHI-ACCESS-KEY': os.getenv('KALSHI_API_KEY'),
            'KALSHI-ACCESS-SIGNATURE': sig_b64,
            'KALSHI-ACCESS-TIMESTAMP': timestamp,
            'Content-Type': 'application/json',
        }
    except Exception as e:
        log.error(f"Signing failed: {e}")
        return {'Content-Type': 'application/json'}


class TradeExecutor:
    def __init_
