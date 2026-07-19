import os
import uuid
from datetime import datetime, timezone
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
        'status': 'ACTIVE',
    })


def list_documents(status='active'):
    table = get_table(os.getenv('DYNAMODB_DOCUMENTS_TABLE'))
    items = []
    scan_args = {}
    while True:
        response = table.scan(**scan_args)
        items.extend(response.get('Items', []))
        last_key = response.get('LastEvaluatedKey')
        if not last_key:
            break
        scan_args['ExclusiveStartKey'] = last_key

    items = [_json_safe(item) for item in items]
    normalized_status = status.lower()
    if normalized_status == 'active':
        items = [
            item for item in items
            if str(item.get('status', 'ACTIVE')).upper() != 'DELETED'
        ]
    elif normalized_status == 'deleted':
        items = [
            item for item in items
            if str(item.get('status', 'ACTIVE')).upper() == 'DELETED'
        ]
    elif normalized_status != 'all':
        raise ValueError('Unsupported document status')

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


def update_document(doc_id, values):
    table = get_table(os.getenv('DYNAMODB_DOCUMENTS_TABLE'))
    names = {}
    attributes = {}
    assignments = []

    for index, (key, value) in enumerate(values.items()):
        name_token = f'#n{index}'
        value_token = f':v{index}'
        names[name_token] = key
        attributes[value_token] = value
        assignments.append(f'{name_token} = {value_token}')

    response = table.update_item(
        Key={'document_id': doc_id},
        UpdateExpression='SET ' + ', '.join(assignments),
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=attributes,
        ConditionExpression='attribute_exists(document_id)',
        ReturnValues='ALL_NEW',
    )
    return _json_safe(response.get('Attributes', {}))


def save_version_audit(doc_id, event_type, actor, **details):
    table_name = os.getenv(
        'DYNAMODB_VERSION_AUDIT_TABLE',
        'DocumentVersionAudit',
    )
    timestamp = datetime.now(timezone.utc).isoformat()
    event_id = f'{timestamp}#{uuid.uuid4()}'
    item = {
        'document_id': doc_id,
        'event_id': event_id,
        'event_type': event_type,
        'actor': actor,
        'created_at': timestamp,
        **{
            key: value
            for key, value in details.items()
            if value is not None
        },
    }
    get_table(table_name).put_item(
        Item=item,
        ConditionExpression=(
            'attribute_not_exists(document_id) '
            'AND attribute_not_exists(event_id)'
        ),
    )
    return _json_safe(item)


def list_version_audit(doc_id):
    table_name = os.getenv(
        'DYNAMODB_VERSION_AUDIT_TABLE',
        'DocumentVersionAudit',
    )
    response = get_table(table_name).query(
        KeyConditionExpression='document_id = :document_id',
        ExpressionAttributeValues={':document_id': doc_id},
        ScanIndexForward=False,
    )
    return [_json_safe(item) for item in response.get('Items', [])]
