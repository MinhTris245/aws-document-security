import os

import boto3


def get_s3_client():
    return boto3.client(
        's3',
        region_name=os.getenv('AWS_REGION'),
    )


def upload_file(file_obj, filename):
    s3 = get_s3_client()
    bucket = os.getenv('S3_BUCKET_NAME')

    s3.upload_fileobj(file_obj, bucket, filename)
    return filename


def generate_download_url(
    filename,
    expiry=3600,
    version_id=None,
):
    s3 = get_s3_client()
    bucket = os.getenv('S3_BUCKET_NAME')

    params = {
        'Bucket': bucket,
        'Key': filename,
    }

    if version_id:
        params['VersionId'] = version_id

    return s3.generate_presigned_url(
        'get_object',
        Params=params,
        ExpiresIn=expiry,
    )


def list_file_versions(filename):
    s3 = get_s3_client()
    bucket = os.getenv('S3_BUCKET_NAME')
    paginator = s3.get_paginator('list_object_versions')

    versions = []

    for page in paginator.paginate(
        Bucket=bucket,
        Prefix=filename,
    ):
        for item in page.get('Versions', []):
            # Prefix có thể khớp key khác, nên kiểm tra chính xác.
            if item['Key'] != filename:
                continue

            versions.append({
                'version_id': item['VersionId'],
                'is_latest': item['IsLatest'],
                'last_modified': (
                    item['LastModified'].isoformat()
                ),
                'size': item['Size'],
                'etag': item['ETag'].strip('"'),
                'storage_class': item.get(
                    'StorageClass',
                    'STANDARD',
                ),
                'is_delete_marker': False,
            })

        for item in page.get('DeleteMarkers', []):
            if item['Key'] != filename:
                continue

            versions.append({
                'version_id': item['VersionId'],
                'is_latest': item['IsLatest'],
                'last_modified': (
                    item['LastModified'].isoformat()
                ),
                'size': 0,
                'etag': None,
                'storage_class': None,
                'is_delete_marker': True,
            })

    versions.sort(
        key=lambda version: version['last_modified'],
        reverse=True,
    )

    return versions


def delete_file(filename):
    s3 = get_s3_client()
    bucket = os.getenv('S3_BUCKET_NAME')
    s3.delete_object(Bucket=bucket, Key=filename)