import uuid
from pathlib import Path

from botocore.exceptions import BotoCoreError, ClientError
from flask import Blueprint, jsonify, request
from werkzeug.utils import secure_filename

from middleware.auth_middleware import require_auth, require_role
from services.dynamodb_service import (
    delete_document,
    get_document,
    list_documents,
    save_document_metadata,
)
from services.s3_service import (
    delete_file,
    generate_download_url,
    list_file_versions,
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
        return jsonify(list_documents())
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
    filename = f'{doc_id}_{original_name}'

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
        upload_file(file, doc['filename'])

        versions = list_file_versions(doc['filename'])
        latest_version = next(
            (
                version
                for version in versions
                if version['is_latest']
                and not version['is_delete_marker']
            ),
            None,
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

        delete_file(doc['filename'])
        delete_document(doc_id)

        return jsonify({
            'message': 'Delete successful',
        })
    except (BotoCoreError, ClientError) as exc:
        return jsonify({
            'error': 'Cannot delete document from AWS',
            'detail': str(exc),
        }), 502