import os

from botocore.exceptions import BotoCoreError, ClientError
from flask import Blueprint, jsonify

from services.dynamodb_service import get_table
from services.s3_service import get_s3_client

health_bp = Blueprint('health', __name__)


@health_bp.route('/health', methods=['GET'])
def health():
    checks = {
        'backend': {'ok': True},
        's3': {'ok': False},
        'documents_table': {'ok': False},
        'incidents_table': {'ok': False},
        'version_audit_table': {'ok': False},
    }

    try:
        get_s3_client().head_bucket(Bucket=os.getenv('S3_BUCKET_NAME'))
        checks['s3']['ok'] = True
    except (BotoCoreError, ClientError, TypeError) as exc:
        checks['s3']['error'] = str(exc)

    for key, env_name in (
        ('documents_table', 'DYNAMODB_DOCUMENTS_TABLE'),
        ('incidents_table', 'DYNAMODB_INCIDENTS_TABLE'),
        ('version_audit_table', 'DYNAMODB_VERSION_AUDIT_TABLE'),
    ):
        try:
            get_table(os.getenv(env_name)).load()
            checks[key]['ok'] = True
        except (BotoCoreError, ClientError, TypeError) as exc:
            checks[key]['error'] = str(exc)

    status = 'ok' if all(item['ok'] for item in checks.values()) else 'degraded'
    return jsonify({'status': status, 'checks': checks})
