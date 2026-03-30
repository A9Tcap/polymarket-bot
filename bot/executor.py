import logging
import os
import json
import time
import base64
import uuid
import aiohttp
from typing import Dict
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend

log = logging.getLogger('executor')


def sign_request(method, path, private_key_str):
    timestamp = str(int(time.time() * 1000))
    path_to_sign = path.split('?')[0]
    message = timestamp + method.upper() + path_to_sign
    try:
        private_key_bytes = private_key_str.strip().encode()
        if not private_key_bytes.startswith(b'-----'):
            private_key_bytes = b'-----BEGIN RSA PRIVATE KEY-----\n' + private_key_bytes + b'\n-----END RSA PRIVATE KEY-----'
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
    def __init__(self, config):
        self.dry_run = config.get('dry_run', True)
        self.private_key = os.getenv('KALSHI_PRIVATE_KEY', '')
        self.session = None
        if not self.dry_run:
            log.warning("LIVE TRADING MODE ENABLED")

    async def _get_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def execute(self, trade):
        market = trade['market']
        direction = trade['direction']
        size = trade['position_size_usdc']
        question = market['question'][:60]

        if self.dry_run:
            log.info(f"[DRY RUN] Would execute: {direction} ${size:.2f} on '{question}'")
            return {'status': 'dry_run', 'direction': direction, 'size': size, 'market
