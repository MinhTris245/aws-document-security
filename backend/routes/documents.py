import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from botocore.exceptions import BotoCoreError, ClientError
from flask import Blueprint, jsonify, request
from werkzeug.utils import secure_filename

from middleware.auth_middleware import require_auth, require_role
from services.dynamodb_service import (
    get_document,
    list_documents,
    list_version_audit,
    save_document_metadata,
    save_version_audit,
    update_document,
)
from services.s3_service import (
    delete_file,
    delete_file_version,
    generate_download_url,
    list_file_versions,
    restore_file_version,
    upload_file,
)

documents_bp = Blueprint('documents', __name__)

ALLOWED_EXTENSIONS = {
    '.pdf',
    '.doc',
    '.docx',
    '.xls',
    '.xlsx',
    '.png',
    '.jpg',
    '.jpeg',
    '.txt',
}
MAX_FILE_SIZE = 20 * 1024 * 1024
QUARANTINE_PREFIX = os.getenv('S3_QUARANTINE_PREFIX', 'quarantine').strip('/')


def validate_uploaded_file(file):
    if not file or file.filename == '':
        return None, None, 'Filename is invalid'

    original_name = secure_filename(file.filename)
    extension = Path(original_name).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        return None, None, 'File type is not allowed'

    file.seek(0, 2)
    size = file.tell()
    file.seek(0)

    if size > MAX_FILE_SIZE:
        return None, None, 'File is larger than 20 MB'

    return original_name, size, None


@documents_bp.route('/documents', methods=['GET'])
@require_auth
def get_documents():
    try:
        status = request.args.get('status', 'active')
        return jsonify(list_documents(status=status))
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except (BotoCoreError, ClientError) as exc:
        return jsonify({
            'error': 'Cannot load documents',
            'detail': str(exc),
        }), 502


@documents_bp.route('/documents/upload', methods=['POST'])
@require_auth
def upload_document():
    if 'file' not in request.files:
        return jsonify({'error': 'No file was uploaded'}), 400

    file = request.files['file']
    original_name, size, validation_error = (
        validate_uploaded_file(file)
    )

    if validation_error:
        return jsonify({'error': validation_error}), 400

    extension = Path(original_name).suffix.lower()
    doc_id = str(uuid.uuid4())
    filename = f'{QUARANTINE_PREFIX}/{doc_id}_{original_name}'

    try:
        upload_file(file, filename)

        save_document_metadata(
            doc_id=doc_id,
            filename=filename,
            original_name=original_name,
            uploader=request.current_user,
            size=size,
            file_type=extension.lstrip('.'),
        )
        versions = list_file_versions(filename)
        latest = next(
            (item for item in versions if item['is_latest']),
            None,
        )
        save_version_audit(
            doc_id,
            'DOCUMENT_CREATED',
            request.current_user,
            s3_key=filename,
            s3_version_id=(latest or {}).get('version_id'),
            original_name=original_name,
            size=size,
            scan_status='PENDING_SCAN',
        )
    except (BotoCoreError, ClientError) as exc:
        return jsonify({
            'error': 'Cannot upload document to AWS',
            'detail': str(exc),
        }), 502

    return jsonify({
        'message': 'Upload successful',
        'document_id': doc_id,
    }), 201


@documents_bp.route(
    '/documents/<doc_id>/versions',
    methods=['GET'],
)
@require_auth
def get_document_versions(doc_id):
    try:
        doc = get_document(doc_id)

        if not doc:
            return jsonify({
                'error': 'Document not found',
            }), 404

        versions = list_file_versions(doc['filename'])

        return jsonify({
            'document_id': doc_id,
            'original_name': doc.get('original_name'),
            'filename': doc['filename'],
            'versions': versions,
        })
    except (BotoCoreError, ClientError) as exc:
        return jsonify({
            'error': 'Cannot load document versions',
            'detail': str(exc),
        }), 502


@documents_bp.route(
    '/documents/<doc_id>/versions',
    methods=['POST'],
)
@require_auth
def upload_document_version(doc_id):
    if 'file' not in request.files:
        return jsonify({
            'error': 'No file was uploaded',
        }), 400

    file = request.files['file']
    original_name, size, validation_error = (
        validate_uploaded_file(file)
    )

    if validation_error:
        return jsonify({'error': validation_error}), 400

    try:
        doc = get_document(doc_id)

        if not doc:
            return jsonify({
                'error': 'Document not found',
            }), 404

        new_extension = Path(original_name).suffix.lower()
        current_extension = (
            f".{doc.get('file_type', '')}".lower()
        )

        if new_extension != current_extension:
            return jsonify({
                'error': (
                    'New version must have the same file type'
                ),
            }), 400

        # Quan trọng: dùng lại S3 key của tài liệu hiện tại.
        staging_key = (
            f'{QUARANTINE_PREFIX}/'
            f'{doc_id}_{uuid.uuid4()}_{original_name}'
        )
        upload_file(file, staging_key)

        versions = list_file_versions(staging_key)
        latest_version = next(
            (
                version
                for version in versions
                if version['is_latest']
                and not version['is_delete_marker']
            ),
            None,
        )

        update_document(doc_id, {
            'pending_version_status': 'PENDING_SCAN',
            'pending_version_key': staging_key,
            'pending_version_size': size,
            'status': 'ACTIVE',
        })
        save_version_audit(
            doc_id,
            'VERSION_UPLOAD_REQUESTED',
            request.current_user,
            s3_key=staging_key,
            s3_version_id=(latest_version or {}).get('version_id'),
            size=size,
            scan_status='PENDING_SCAN',
        )

        return jsonify({
            'message': 'New document version uploaded',
            'document_id': doc_id,
            'version_id': (
                latest_version['version_id']
                if latest_version
                else None
            ),
            'size': size,
        }), 201
    except (BotoCoreError, ClientError) as exc:
        return jsonify({
            'error': 'Cannot upload document version',
            'detail': str(exc),
        }), 502

    return jsonify({
        'message': 'Upload successful',
        'document_id': doc_id,
        'scan_status': 'PENDING_SCAN',
        'download_allowed': False,
    }), 201

@documents_bp.route(
    '/documents/<doc_id>/versions/download',
    methods=['GET'],
)
@require_auth
def download_document_version(doc_id):
    version_id = request.args.get('version_id')

    if not version_id:
        return jsonify({
            'error': 'Version ID is required',
        }), 400

    try:
        doc = get_document(doc_id)

        if not doc:
            return jsonify({
                'error': 'Document not found',
            }), 404

        versions = list_file_versions(doc['filename'])
        selected_version = next(
            (
                version
                for version in versions
                if version['version_id'] == version_id
                and not version['is_delete_marker']
            ),
            None,
        )

        if not selected_version:
            return jsonify({
                'error': 'Document version not found',
            }), 404

        scan_status = str(doc.get('scan_status', 'UNSCANNED')).upper()
        if scan_status != 'CLEAN':
            return jsonify({
                'error': 'Version download is locked until malware scan is clean',
                'scan_status': scan_status,
                'download_allowed': False,
            }), 423

        url = generate_download_url(
            doc['filename'],
            version_id=version_id,
        )

        return jsonify({
            'download_url': url,
            'version_id': version_id,
        })
    except (BotoCoreError, ClientError) as exc:
        return jsonify({
            'error': 'Cannot create version download URL',
            'detail': str(exc),
        }), 502


@documents_bp.route(
    '/documents/download/<doc_id>',
    methods=['GET'],
)
@require_auth
def download_document(doc_id):
    try:
        doc = get_document(doc_id)

        if not doc:
            return jsonify({
                'error': 'Document not found',
            }), 404

        scan_status = str(doc.get('scan_status', 'UNSCANNED')).upper()
        if scan_status != 'CLEAN':
            return jsonify({
                'error': 'Document download is locked until the malware scan confirms it is clean',
                'scan_status': scan_status,
                'download_allowed': False,
            }), 423

        url = generate_download_url(doc['filename'])

        return jsonify({'download_url': url})
    except (BotoCoreError, ClientError) as exc:
        return jsonify({
            'error': 'Cannot create download URL',
            'detail': str(exc),
        }), 502


@documents_bp.route(
    '/documents/<doc_id>',
    methods=['DELETE'],
)
@require_auth
@require_role('admin')
def remove_document(doc_id):
    try:
        doc = get_document(doc_id)

        if not doc:
            return jsonify({
                'error': 'Document not found',
            }), 404

        if str(doc.get('status', 'ACTIVE')).upper() == 'DELETED':
            return jsonify({
                'error': 'Document is already deleted',
            }), 409

        save_version_audit(
            doc_id,
            'DOCUMENT_SOFT_DELETE_REQUESTED',
            request.current_user,
            s3_key=doc['filename'],
        )
        response = delete_file(doc['filename'])
        marker_version_id = response.get('VersionId')
        deleted_at = datetime.now(timezone.utc).isoformat()
        update_document(doc_id, {
            'status': 'DELETED',
            'deleted_at': deleted_at,
            'deleted_by': request.current_user,
            'delete_marker_version_id': marker_version_id,
            'download_allowed': False,
        })
        save_version_audit(
            doc_id,
            'DOCUMENT_SOFT_DELETED',
            request.current_user,
            s3_key=doc['filename'],
            s3_version_id=marker_version_id,
        )

        return jsonify({
            'message': 'Document moved to recycle bin',
            'delete_marker_version_id': marker_version_id,
        })
    except (BotoCoreError, ClientError) as exc:
        return jsonify({
            'error': 'Cannot delete document from AWS',
            'detail': str(exc),
        }), 502


@documents_bp.route('/documents/<doc_id>/recover', methods=['POST'])
@require_auth
@require_role('admin')
def recover_document(doc_id):
    try:
        doc = get_document(doc_id)
        if not doc:
            return jsonify({'error': 'Document not found'}), 404
        if str(doc.get('status', 'ACTIVE')).upper() != 'DELETED':
            return jsonify({'error': 'Document is not deleted'}), 409

        versions = list_file_versions(doc['filename'])
        marker = next(
            (
                item for item in versions
                if item['is_delete_marker'] and item['is_latest']
            ),
            None,
        )
        if not marker:
            return jsonify({'error': 'Active delete marker not found'}), 409

        save_version_audit(
            doc_id,
            'DOCUMENT_RECOVERY_REQUESTED',
            request.current_user,
            s3_key=doc['filename'],
            s3_version_id=marker['version_id'],
        )
        delete_file_version(doc['filename'], marker['version_id'])
        recovered_at = datetime.now(timezone.utc).isoformat()
        update_document(doc_id, {
            'status': 'ACTIVE',
            'recovered_at': recovered_at,
            'recovered_by': request.current_user,
            'delete_marker_version_id': '',
        })
        save_version_audit(
            doc_id,
            'DOCUMENT_RECOVERED',
            request.current_user,
            s3_key=doc['filename'],
            s3_version_id=marker['version_id'],
        )
        return jsonify({'message': 'Document recovered'})
    except (BotoCoreError, ClientError) as exc:
        return jsonify({
            'error': 'Cannot recover document',
            'detail': str(exc),
        }), 502


@documents_bp.route(
    '/documents/<doc_id>/versions/restore',
    methods=['POST'],
)
@require_auth
@require_role('admin')
def restore_document_version(doc_id):
    data = request.get_json(silent=True) or {}
    version_id = data.get('version_id', '').strip()
    if not version_id:
        return jsonify({'error': 'Version ID is required'}), 400
    try:
        doc = get_document(doc_id)
        if not doc:
            return jsonify({'error': 'Document not found'}), 404
        versions = list_file_versions(doc['filename'])
        selected = next(
            (
                item for item in versions
                if item['version_id'] == version_id
                and not item['is_delete_marker']
            ),
            None,
        )
        if not selected:
            return jsonify({'error': 'Document version not found'}), 404

        new_version_id = restore_file_version(doc['filename'], version_id)
        update_document(doc_id, {
            'status': 'ACTIVE',
            'size': selected['size'],
            'scan_status': 'UNSCANNED',
            'download_allowed': False,
            'restored_at': datetime.now(timezone.utc).isoformat(),
            'restored_by': request.current_user,
        })
        save_version_audit(
            doc_id,
            'VERSION_RESTORED',
            request.current_user,
            s3_key=doc['filename'],
            source_version_id=version_id,
            s3_version_id=new_version_id,
            scan_status='UNSCANNED',
        )
        return jsonify({
            'message': 'Version restored as latest',
            'source_version_id': version_id,
            'new_version_id': new_version_id,
            'scan_status': 'UNSCANNED',
        })
    except (BotoCoreError, ClientError) as exc:
        return jsonify({
            'error': 'Cannot restore document version',
            'detail': str(exc),
        }), 502


@documents_bp.route(
    '/documents/<doc_id>/versions/permanent-delete',
    methods=['DELETE'],
)
@require_auth
@require_role('admin')
def permanently_delete_document_version(doc_id):
    data = request.get_json(silent=True) or {}
    version_id = data.get('version_id', '').strip()
    if not version_id:
        return jsonify({'error': 'Version ID is required'}), 400
    if data.get('confirmation') != 'PERMANENTLY DELETE':
        return jsonify({
            'error': 'Permanent delete confirmation is required',
        }), 400

    try:
        doc = get_document(doc_id)
        if not doc:
            return jsonify({'error': 'Document not found'}), 404
        versions = list_file_versions(doc['filename'])
        selected = next(
            (item for item in versions if item['version_id'] == version_id),
            None,
        )
        if not selected:
            return jsonify({'error': 'Document version not found'}), 404

        save_version_audit(
            doc_id,
            'VERSION_PERMANENT_DELETE_REQUESTED',
            request.current_user,
            s3_key=doc['filename'],
            s3_version_id=version_id,
            is_delete_marker=selected['is_delete_marker'],
            reason=data.get('reason', '').strip(),
        )
        response = delete_file_version(doc['filename'], version_id)
        remaining = list_file_versions(doc['filename'])

        if selected['is_delete_marker'] and selected['is_latest']:
            update_document(doc_id, {
                'status': 'ACTIVE',
                'delete_marker_version_id': '',
                'recovered_at': datetime.now(timezone.utc).isoformat(),
                'recovered_by': request.current_user,
            })
        elif not any(not item['is_delete_marker'] for item in remaining):
            update_document(doc_id, {
                'status': 'DELETED',
                'download_allowed': False,
            })
        elif selected['is_latest']:
            update_document(doc_id, {
                'scan_status': 'UNSCANNED',
                'download_allowed': False,
            })

        save_version_audit(
            doc_id,
            'VERSION_PERMANENTLY_DELETED',
            request.current_user,
            s3_key=doc['filename'],
            s3_version_id=version_id,
            is_delete_marker=response.get('DeleteMarker', False),
            reason=data.get('reason', '').strip(),
        )
        return jsonify({'message': 'Version permanently deleted'})
    except (BotoCoreError, ClientError) as exc:
        return jsonify({
            'error': 'Cannot permanently delete version',
            'detail': str(exc),
        }), 502


@documents_bp.route('/documents/<doc_id>/audit', methods=['GET'])
@require_auth
def get_document_audit(doc_id):
    try:
        if not get_document(doc_id):
            return jsonify({'error': 'Document not found'}), 404
        return jsonify(list_version_audit(doc_id))
    except (BotoCoreError, ClientError) as exc:
        return jsonify({
            'error': 'Cannot load document audit',
            'detail': str(exc),
        }), 502
