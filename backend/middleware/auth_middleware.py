import os
from functools import wraps

import jwt
from flask import jsonify, request

from services.cognito_service import decode_cognito_token, identity_from_claims


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        auth_header = request.headers.get('Authorization')

        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]

        if not token:
            return jsonify({'error': 'Token is missing'}), 401

        try:
            if os.getenv('AUTH_PROVIDER', 'demo').lower() == 'cognito':
                payload = decode_cognito_token(token)
                identity = identity_from_claims(payload)
                request.current_user = identity['username']
                request.current_role = identity['role']
            else:
                payload = jwt.decode(token, os.getenv('JWT_SECRET_KEY'), algorithms=['HS256'])
                request.current_user = payload['username']
                request.current_role = payload.get('role', 'user')
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token has expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Token is invalid'}), 401
        except RuntimeError as exc:
            return jsonify({'error': str(exc)}), 500

        return f(*args, **kwargs)

    return decorated


def require_role(*roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if getattr(request, 'current_role', None) not in roles:
                return jsonify({'error': 'Permission denied'}), 403
            return f(*args, **kwargs)

        return decorated

    return decorator
