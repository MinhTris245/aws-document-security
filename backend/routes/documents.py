import os
import uuid
from pathlib import Path

from botocore.exceptions import BotoCoreError, ClientError
from flask import Blueprint, jsonify, request
from werkzeug.utils import secure_filename

from middleware.auth_middleware import require_auth, require_role
from services.dynamodb_service import delete_document, get_document, list_documents, save_document_metadata
from services.s3_service import delete_file, generate_download_url, upload_file

documents_bp = Blueprint('documents', __name__)

ALLOWED_EXTENSIONS = {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.png', '.jpg', '.jpeg', '.txt'}
MAX_FILE_SIZE = 20 * 1024 * 1024
QUARANTINE_PREFIX = os.getenv('S3_QUARANTINE_PREFIX', 'quarantine').strip('/')


@documents_bp.route('/documents', methods=['GET'])
@require_auth
def get_documents():
    try:
        return jsonify(list_documents())
    except (BotoCoreError, ClientError) as exc:
        return jsonify({'error': 'Cannot load documents', 'detail': str(exc)}), 502


@documents_bp.route('/documents/upload', methods=['POST'])
@require_auth
def upload_document():
    if 'file' not in request.files:
        return jsonify({'error': 'No file was uploaded'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Filename is invalid'}), 400

    original_name = secure_filename(file.filename)
    extension = Path(original_name).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        return jsonify({'error': 'File type is not allowed'}), 400

    file.seek(0, 2)
    size = file.tell()
    file.seek(0)
    if size > MAX_FILE_SIZE:
        return jsonify({'error': 'File is larger than 20 MB'}), 400

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
    except (BotoCoreError, ClientError) as exc:
        return jsonify({'error': 'Cannot upload document to AWS', 'detail': str(exc)}), 502

    return jsonify({
        'message': 'Upload successful',
        'document_id': doc_id,
        'scan_status': 'PENDING_SCAN',
        'download_allowed': False,
    }), 201


@documents_bp.route('/documents/download/<doc_id>', methods=['GET'])
@require_auth
def download_document(doc_id):
    try:
        doc = get_document(doc_id)
        if not doc:
            return jsonify({'error': 'Document not found'}), 404

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
        return jsonify({'error': 'Cannot create download URL', 'detail': str(exc)}), 502


@documents_bp.route('/documents/<doc_id>', methods=['DELETE'])
@require_auth
@require_role('admin')
def remove_document(doc_id):
    try:
        doc = get_document(doc_id)
        if not doc:
            return jsonify({'error': 'Document not found'}), 404

        delete_file(doc['filename'])
        delete_document(doc_id)
        return jsonify({'message': 'Delete successful'})
    except (BotoCoreError, ClientError) as exc:
        return jsonify({'error': 'Cannot delete document from AWS', 'detail': str(exc)}), 502
