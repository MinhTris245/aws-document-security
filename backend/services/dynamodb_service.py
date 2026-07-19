import os
from datetime import datetime
from decimal import Decimal

import boto3


def _json_safe(value):
    if isinstance(value, Decimal):
        return int(value) if value % 1 == 0 else float(value)
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    return value


def get_table(table_name):
    dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION'))
    return dynamodb.Table(table_name)


def save_document_metadata(doc_id, filename, original_name, uploader, size, file_type):
    table = get_table(os.getenv('DYNAMODB_DOCUMENTS_TABLE'))
    table.put_item(Item={
        'document_id': doc_id,
        'filename': filename,
        'original_name': original_name,
        'uploader': uploader,
        'size': size,
        'file_type': file_type,
        'uploaded_at': datetime.utcnow().isoformat(),
        'scan_status': 'PENDING_SCAN',
        'download_allowed': False,
    })


def list_documents():
    table = get_table(os.getenv('DYNAMODB_DOCUMENTS_TABLE'))
    response = table.scan()
    items = [_json_safe(item) for item in response.get('Items', [])]
    items.sort(key=lambda x: x.get('uploaded_at', ''), reverse=True)
    return items


def get_document(doc_id):
    table = get_table(os.getenv('DYNAMODB_DOCUMENTS_TABLE'))
    response = table.get_item(Key={'document_id': doc_id})
    item = response.get('Item')
    return _json_safe(item) if item else None


def delete_document(doc_id):
    table = get_table(os.getenv('DYNAMODB_DOCUMENTS_TABLE'))
    table.delete_item(Key={'document_id': doc_id})
