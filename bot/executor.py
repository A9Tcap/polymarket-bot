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
    message = timestamp + method.upper() + path.split('?')[0]
    key_str = private_key_str.strip().replace('\\n', '\n')
    key_bytes = key_str.encode()
    try:
        private_key = serialization.load_pem_private_key(key_bytes, password=None, backend=default_backend())
        sig = private_key.sign(message.encode(), padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=hashes.SHA256.digest_size), hashes.SHA256())
        return {
            'KALSHI-ACCESS-KEY': os.getenv('KALSHI_API_KEY'),
            'KALSHI-ACCESS-SIGNATURE': base64.b64encode(sig).decode(),
            'KALSHI-ACCESS-TIMESTAMP': timestamp,
            'Content-Type': 'application/json',
        }
    except Exception as e:
        log.error(f"Signing failed: {e}")
        return {'Content-Type': 'application/json'}


class TradeExecutor:
