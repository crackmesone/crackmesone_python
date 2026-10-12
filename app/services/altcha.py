"""First-party ALTCHA v2 proof-of-work verification, no cloud/API key.

Challenges are signed with per-form HMAC-derived secrets to prevent cross-form
reuse. MongoDB's unique ``_id`` index makes consumption atomic across Gunicorn
workers. Fail closed on invalid configuration, expiry or MongoDB failure.
"""

import base64
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import logging
import secrets

from altcha import create_challenge, verify_solution
from flask import current_app, jsonify
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.services.limiter import limit

logger = logging.getLogger(__name__)
SCOPES = ('Crackme', 'Writeup', 'Register', 'Comment')
_config = {}


def init_altcha(app, config):
    global _config
    _config = dict(config or {})
    app.config['ALTCHA_CONFIG'] = _config
    if _config.get('Enabled') is True:
        # Provision at startup, never on an individual HTTP submission.
        # An index/permission failure must prevent a protected deployment from
        # starting rather than silently weakening replay protection.
        app.config['MONGO_DB']['altcha_used'].create_index(
            'expires_at', expireAfterSeconds=0
        )


def read_config():
    return _config


def is_enabled(scope=None):
    if scope is not None and scope not in SCOPES:
        raise ValueError('Unknown ALTCHA scope: ' + str(scope))
    if _config.get('Enabled') is not True:
        return False
    return scope is None or _config.get('Protect', {}).get(scope, True) is True


def _secret(name, scope):
    """Derive a separate signing key for each form to prevent cross-scope use."""
    master = _config.get(name)
    if not isinstance(master, str) or len(master) < 32:
        raise ValueError('ALTCHA signing secrets must contain at least 32 characters')
    return hmac.new(master.encode('utf-8'), scope.encode('ascii'), hashlib.sha256).hexdigest()


def _parameters():
    cost = _config.get('Cost', 500)
    lower = _config.get('MinCounter', 250)
    upper = _config.get('MaxCounter', 750)
    ttl = _config.get('ExpiresMinutes', 20)
    # Reject insane workloads and badly configured expiry rather than hanging
    # visitors or creating challenges without a meaningful expiration.
    if not (type(cost) is int and 100 <= cost <= 10000
            and type(lower) is int and type(upper) is int
            and 1 <= lower < upper <= 20000
            and type(ttl) is int and 1 <= ttl <= 60):
        raise ValueError('Invalid ALTCHA work/expiry configuration')
    return cost, lower, upper, ttl


def register_altcha(app):
    """Attach the limit *after* init_limiter, regardless of import order."""
    app.add_url_rule('/altcha/challenge/<scope>', endpoint='altcha_challenge',
                     view_func=limit('30 per minute')(challenge), methods=['GET'])


def challenge(scope):
    if scope not in SCOPES or not is_enabled(scope):
        return jsonify({'error': 'Not found'}), 404
    try:
        cost, lower, upper, ttl = _parameters()
        challenge_data = create_challenge(
            algorithm='PBKDF2/SHA-256',
            cost=cost,
            counter=secrets.randbelow(upper - lower + 1) + lower,
            hmac_secret=_secret('HmacSecret', scope),
            hmac_key_secret=_secret('HmacKeySecret', scope),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=ttl),
        )
        response = jsonify(challenge_data.to_dict())
        response.headers['Cache-Control'] = 'no-store, max-age=0'
        return response
    except (ValueError, TypeError) as exc:
        logger.error('ALTCHA challenge configuration invalid: %s', exc)
        return jsonify({'error': 'CAPTCHA unavailable'}), 503


def _challenge_fingerprint(payload):
    """Identify the signed challenge, not the mutable PoW solution.

    A replay with changed JSON key order, whitespace, or solution metadata
    must retain the same signature. Only a *verified* signed challenge reaches
    this function, so using its signature as a stable identifier is safe.
    """
    raw = base64.b64decode(payload, validate=True)
    obj = json.loads(raw)
    if not isinstance(obj, dict):
        raise ValueError('Invalid ALTCHA JSON payload')
    # v2 payload carries its challenge signature; some library versions nest
    # the challenge data rather than putting the signature at the top level.
    signature = obj.get('signature')
    if signature is None and isinstance(obj.get('challenge'), dict):
        signature = obj['challenge'].get('signature')
    if not isinstance(signature, str) or len(signature) < 32 or len(signature) > 512:
        raise ValueError('ALTCHA payload missing challenge signature')
    return hashlib.sha256(signature.encode('utf-8')).hexdigest()


def verify(req, scope=None):
    if not is_enabled(scope):
        return True
    if scope is None:
        logger.error('ALTCHA scope is required for protected forms')
        return False
    payload = req.form.get('altcha', '')
    if not isinstance(payload, str) or not 1 <= len(payload) <= 8192:
        return False
    try:
        secret = _secret('HmacSecret', scope)
        key_secret = _secret('HmacKeySecret', scope)
        result = verify_solution(payload, secret, hmac_key_secret=key_secret)
        if result.verified is not True or result.expired:
            return False
        fingerprint = _challenge_fingerprint(payload)
        _, _, _, ttl = _parameters()
        # MongoDB _id is unique; this is an atomic single-use check shared
        # across all workers. No in-process sets or check-then-insert races.
        collection = current_app.config['MONGO_DB']['altcha_used']
        collection.insert_one({
            '_id': fingerprint,
            'expires_at': datetime.now(timezone.utc) + timedelta(minutes=ttl + 2),
        })
        return True
    except DuplicateKeyError:
        logger.info('ALTCHA replay blocked')
        return False
    except (ValueError, TypeError, KeyError, PyMongoError) as exc:
        logger.warning('ALTCHA verification failed: %s', exc)
        return False
    except Exception:
        logger.exception('ALTCHA verification unexpected error')
        return False
