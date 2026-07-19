import base64
import hashlib
import hmac
import os

import boto3
from botocore.exceptions import ClientError


class CognitoConfigError(RuntimeError):
    pass


class CognitoAuthError(RuntimeError):
    pass


def _required_env(name):
    value = os.getenv(name)
    if not value:
        raise CognitoConfigError(f'{name} is not configured')
    return value


def _client():
    return boto3.client('cognito-idp', region_name=_required_env('AWS_REGION'))


def _secret_hash(username, client_id):
    client_secret = os.getenv('COGNITO_CLIENT_SECRET')
    if not client_secret:
        return None

    digest = hmac.new(
        client_secret.encode('utf-8'),
        msg=f'{username}{client_id}'.encode('utf-8'),
        digestmod=hashlib.sha256,
    ).digest()
    return base64.b64encode(digest).decode()


def _role_from_claims(claims):
    configured_admin_group = os.getenv('COGNITO_ADMIN_GROUP', 'admin').lower()
    groups = [group.lower() for group in claims.get('cognito:groups', [])]
    if configured_admin_group in groups:
        return 'admin'
    return claims.get('custom:role') or claims.get('role') or 'user'


def login_with_cognito(username, password):
    client_id = _required_env('COGNITO_CLIENT_ID')
    auth_parameters = {
        'USERNAME': username,
        'PASSWORD': password,
    }

    secret_hash = _secret_hash(username, client_id)
    if secret_hash:
        auth_parameters['SECRET_HASH'] = secret_hash

    try:
        response = _client().initiate_auth(
            ClientId=client_id,
            AuthFlow=os.getenv('COGNITO_AUTH_FLOW', 'USER_PASSWORD_AUTH'),
            AuthParameters=auth_parameters,
        )
    except ClientError as exc:
        code = exc.response.get('Error', {}).get('Code', '')
        if code in {
            'NotAuthorizedException',
            'UserNotFoundException',
            'PasswordResetRequiredException',
            'UserNotConfirmedException',
        }:
            raise CognitoAuthError('Username or password is incorrect') from exc
        raise

    challenge_name = response.get('ChallengeName')
    if challenge_name:
        raise CognitoAuthError(f'Cognito challenge is required: {challenge_name}')

    auth_result = response.get('AuthenticationResult') or {}
    access_token = auth_result.get('AccessToken')
    id_token = auth_result.get('IdToken')
    if not access_token:
        raise CognitoAuthError('Cognito did not return an access token')

    claims = decode_cognito_token(access_token, expected_token_use='access')
    username_claim = claims.get('username') or claims.get('cognito:username') or username

    return {
        'token': access_token,
        'id_token': id_token,
        'username': username_claim,
        'role': _role_from_claims(claims),
        'expires_in': auth_result.get('ExpiresIn'),
        'token_type': auth_result.get('TokenType', 'Bearer'),
    }


def decode_cognito_token(token, expected_token_use=None):
    import jwt
    from jwt import PyJWKClient

    user_pool_id = _required_env('COGNITO_USER_POOL_ID')
    client_id = _required_env('COGNITO_CLIENT_ID')
    region = _required_env('AWS_REGION')
    issuer = f'https://cognito-idp.{region}.amazonaws.com/{user_pool_id}'
    jwks_url = f'{issuer}/.well-known/jwks.json'

    signing_key = PyJWKClient(jwks_url).get_signing_key_from_jwt(token)
    claims = jwt.decode(
        token,
        signing_key.key,
        algorithms=['RS256'],
        issuer=issuer,
        options={'verify_aud': False},
    )

    token_use = claims.get('token_use')
    expected_use = expected_token_use or os.getenv('COGNITO_TOKEN_USE', 'access')
    if token_use != expected_use:
        raise jwt.InvalidTokenError(f'Expected {expected_use} token, got {token_use}')

    if token_use == 'id' and claims.get('aud') != client_id:
        raise jwt.InvalidTokenError('Token audience does not match Cognito app client')
    if token_use == 'access' and claims.get('client_id') != client_id:
        raise jwt.InvalidTokenError('Token client_id does not match Cognito app client')

    return claims


def identity_from_claims(claims):
    return {
        'username': claims.get('username') or claims.get('cognito:username') or claims.get('sub'),
        'role': _role_from_claims(claims),
    }
