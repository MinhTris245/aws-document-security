import json
import os
import uuid
from datetime import datetime, timezone
from urllib.parse import quote

import boto3
from botocore.exceptions import ClientError


dynamodb = boto3.resource("dynamodb")
sns = boto3.client("sns")
ec2 = boto3.client("ec2")

INCIDENTS_TABLE = os.getenv("INCIDENTS_TABLE", "SecurityIncidents")
SNS_TOPIC_ARN = os.environ["SNS_TOPIC_ARN"]
QUARANTINE_SG_ID = os.getenv("QUARANTINE_SG_ID", "")
ALLOWED_INSTANCE_IDS = {
    value.strip()
    for value in os.getenv("ALLOWED_INSTANCE_IDS", "").split(",")
    if value.strip()
}
PROTECTED_INSTANCE_IDS = {
    value.strip()
    for value in os.getenv("PROTECTED_INSTANCE_IDS", "").split(",")
    if value.strip()
}
TAG_MIN_SEVERITY = float(os.getenv("TAG_MIN_SEVERITY", "7"))
INCIDENT_PORTAL_URL = os.getenv("INCIDENT_PORTAL_URL", "").rstrip("/")


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def severity_label(score):
    score = float(score or 0)
    if score >= 9.0:
        return "CRITICAL"
    if score >= 7.0:
        return "HIGH"
    if score >= 4.0:
        return "MEDIUM"
    return "LOW"


def get_instance_id(detail):
    return (
        detail.get("resource", {})
        .get("instanceDetails", {})
        .get("instanceId")
    )


def get_resource_id(detail):
    instance_id = get_instance_id(detail)
    if instance_id:
        return instance_id

    resource = detail.get("resource", {})
    buckets = resource.get("s3BucketDetails", [])
    if buckets:
        return buckets[0].get("name", "S3 resource")
    return resource.get("resourceType", "Unknown resource")


def is_allowed_instance(instance_id):
    return bool(
        instance_id
        and instance_id in ALLOWED_INSTANCE_IDS
        and instance_id not in PROTECTED_INSTANCE_IDS
    )


def ensure_not_protected_instance(instance_id):
    if instance_id in PROTECTED_INSTANCE_IDS:
        raise ValueError("Instance is protected and cannot be modified by automated response")


def incident_table():
    return dynamodb.Table(INCIDENTS_TABLE)


def update_incident(incident_id, values):
    names = {}
    attributes = {}
    assignments = []
    for index, (key, value) in enumerate(values.items()):
        name_key = f"#n{index}"
        value_key = f":v{index}"
        names[name_key] = key
        attributes[value_key] = value
        assignments.append(f"{name_key} = {value_key}")

    incident_table().update_item(
        Key={"incident_id": incident_id},
        UpdateExpression="SET " + ", ".join(assignments),
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=attributes,
    )


def publish(subject, message):
    sns.publish(
        TopicArn=SNS_TOPIC_ARN,
        Subject=subject[:100],
        Message=message,
    )


def get_instance_network(instance_id):
    response = ec2.describe_instances(InstanceIds=[instance_id])
    reservations = response.get("Reservations", [])
    if not reservations or not reservations[0].get("Instances"):
        raise ValueError(f"Instance not found: {instance_id}")

    instance = reservations[0]["Instances"][0]
    interfaces = instance.get("NetworkInterfaces", [])
    if not interfaces:
        raise ValueError(f"Instance has no network interface: {instance_id}")

    primary = next(
        (
            interface
            for interface in interfaces
            if interface.get("Attachment", {}).get("DeviceIndex") == 0
        ),
        interfaces[0],
    )
    return {
        "vpc_id": instance["VpcId"],
        "network_interface_id": primary["NetworkInterfaceId"],
        "security_group_ids": [group["GroupId"] for group in primary["Groups"]],
    }


def verify_quarantine_group(vpc_id):
    if not QUARANTINE_SG_ID:
        raise ValueError("QUARANTINE_SG_ID is not configured")

    response = ec2.describe_security_groups(GroupIds=[QUARANTINE_SG_ID])
    security_group = response["SecurityGroups"][0]
    if security_group["VpcId"] != vpc_id:
        raise ValueError("Quarantine Security Group is in a different VPC")


def tag_suspected_instance(instance_id, finding_id, severity):
    ec2.create_tags(
        Resources=[instance_id],
        Tags=[
            {"Key": "SecurityStatus", "Value": "Suspected"},
            {"Key": "GuardDutyFindingId", "Value": finding_id[:256]},
            {"Key": "GuardDutySeverity", "Value": severity},
        ],
    )


def process_guardduty_finding(event):
    detail = event.get("detail", {})
    finding_id = detail.get("id") or str(uuid.uuid4())
    finding_type = detail.get("type", "Unknown")
    severity_score = float(detail.get("severity", 0) or 0)
    severity = severity_label(severity_score)
    region = detail.get("region") or os.getenv("AWS_REGION", "ap-southeast-1")
    account_id = detail.get("accountId", "unknown")
    resource_id = get_resource_id(detail)
    instance_id = get_instance_id(detail)
    timestamp = detail.get("updatedAt") or detail.get("createdAt") or now_iso()
    raw_detail = json.dumps(detail, ensure_ascii=False, default=str)

    item = {
        "incident_id": finding_id,
        "timestamp": timestamp,
        "finding_type": finding_type,
        "severity": severity,
        "severity_score": str(severity_score),
        "region": region,
        "account_id": account_id,
        "resource_id": resource_id,
        "status": "OPEN",
        "response_action": "RECORDED_AND_ALERTED",
        "raw_detail": raw_detail[:300000],
    }

    tag_result = "NOT_APPLICABLE"
    if instance_id and severity_score >= TAG_MIN_SEVERITY:
        if is_allowed_instance(instance_id):
            try:
                tag_suspected_instance(instance_id, finding_id, severity)
                tag_result = "TAGGED_SUSPECTED"
                item["response_action"] = "TAGGED_AND_AWAITING_APPROVAL"
            except ClientError as exc:
                tag_result = f"TAG_FAILED:{exc.response['Error']['Code']}"
        else:
            tag_result = "SKIPPED_NOT_IN_ALLOWLIST"

    item["tag_result"] = tag_result
    incident_table().put_item(Item=item)

    approval_hint = ""
    if item["response_action"] == "TAGGED_AND_AWAITING_APPROVAL":
        approval_url = ""
        if INCIDENT_PORTAL_URL:
            approval_url = (
                f"\nReview and approve: {INCIDENT_PORTAL_URL}/incidents"
                f"?incident={quote(finding_id, safe='')}"
            )
        approval_hint = (
            "\nApproval required. Review the finding and approve quarantine "
            "only if isolation is justified."
            f"{approval_url}"
        )

    message = (
        "SECURITY ALERT\n\n"
        f"Type: {finding_type}\n"
        f"Severity: {severity} ({severity_score})\n"
        f"Resource: {resource_id}\n"
        f"Region: {region}\n"
        f"Account: {account_id}\n"
        f"Time: {timestamp}\n"
        f"Finding ID: {finding_id}\n"
        f"Response: {item['response_action']}\n"
        f"Tag result: {tag_result}"
        f"{approval_hint}"
    )
    publish(f"[SECURITY] {severity} - {finding_type}", message)

    return {
        "message": "Incident processed",
        "incident_id": finding_id,
        "instance_id": instance_id,
        "resource_id": resource_id,
        "severity": severity,
        "severity_score": severity_score,
        "requires_approval": (
            bool(instance_id)
            and severity_score >= TAG_MIN_SEVERITY
            and is_allowed_instance(instance_id)
        ),
        "response_action": item["response_action"],
        "tag_result": tag_result,
    }


def quarantine_approved(event):
    instance_id = event.get("instance_id", "")
    incident_id = event.get("incident_id", "")
    approved_by = event.get("approved_by", "")

    ensure_not_protected_instance(instance_id)
    if not is_allowed_instance(instance_id):
        raise ValueError("Instance is not in ALLOWED_INSTANCE_IDS")
    if not incident_id or not approved_by:
        raise ValueError("incident_id and approved_by are required")

    network = get_instance_network(instance_id)
    verify_quarantine_group(network["vpc_id"])
    original_groups = network["security_group_ids"]

    if original_groups == [QUARANTINE_SG_ID]:
        return {"message": "Instance is already quarantined", "instance_id": instance_id}

    ec2.modify_network_interface_attribute(
        NetworkInterfaceId=network["network_interface_id"],
        Groups=[QUARANTINE_SG_ID],
    )
    ec2.create_tags(
        Resources=[instance_id],
        Tags=[
            {"Key": "SecurityStatus", "Value": "Quarantined"},
            {"Key": "QuarantineIncidentId", "Value": incident_id[:256]},
        ],
    )
    update_incident(
        incident_id,
        {
            "status": "INVESTIGATING",
            "response_action": "QUARANTINED_AFTER_APPROVAL",
            "approved_by": approved_by,
            "approved_at": now_iso(),
            "instance_id": instance_id,
            "network_interface_id": network["network_interface_id"],
            "original_security_groups": original_groups,
            "quarantine_security_group": QUARANTINE_SG_ID,
        },
    )
    publish(
        "[SECURITY] EC2 quarantined after approval",
        f"Instance: {instance_id}\nIncident: {incident_id}\nApproved by: {approved_by}",
    )
    return {
        "message": "Instance quarantined",
        "instance_id": instance_id,
        "original_security_groups": original_groups,
    }


def restore_approved(event):
    instance_id = event.get("instance_id", "")
    incident_id = event.get("incident_id", "")
    approved_by = event.get("approved_by", "")
    ensure_not_protected_instance(instance_id)
    if not is_allowed_instance(instance_id):
        raise ValueError("Instance is not in ALLOWED_INSTANCE_IDS")
    if not incident_id or not approved_by:
        raise ValueError("incident_id and approved_by are required")

    item = incident_table().get_item(Key={"incident_id": incident_id}).get("Item", {})
    original_groups = item.get("original_security_groups", [])
    network_interface_id = item.get("network_interface_id")
    if not original_groups or not network_interface_id:
        raise ValueError("No saved Security Groups found for this incident")

    ec2.modify_network_interface_attribute(
        NetworkInterfaceId=network_interface_id,
        Groups=original_groups,
    )
    ec2.create_tags(
        Resources=[instance_id],
        Tags=[{"Key": "SecurityStatus", "Value": "Restored"}],
    )
    update_incident(
        incident_id,
        {
            "status": "RESOLVED",
            "response_action": "RESTORED_AFTER_APPROVAL",
            "restored_by": approved_by,
            "restored_at": now_iso(),
        },
    )
    publish(
        "[SECURITY] EC2 Security Groups restored",
        f"Instance: {instance_id}\nIncident: {incident_id}\nApproved by: {approved_by}",
    )
    return {"message": "Original Security Groups restored", "instance_id": instance_id}


def stop_approved(event):
    instance_id = event.get("instance_id", "")
    incident_id = event.get("incident_id", "")
    approved_by = event.get("approved_by", "")
    ensure_not_protected_instance(instance_id)
    if not is_allowed_instance(instance_id):
        raise ValueError("Instance is not in ALLOWED_INSTANCE_IDS")
    if not incident_id or not approved_by:
        raise ValueError("incident_id and approved_by are required")

    response = ec2.stop_instances(InstanceIds=[instance_id])
    current_state = response["StoppingInstances"][0]["CurrentState"]["Name"]
    ec2.create_tags(
        Resources=[instance_id],
        Tags=[
            {"Key": "SecurityStatus", "Value": "StoppedAfterApproval"},
            {"Key": "StopIncidentId", "Value": incident_id[:256]},
        ],
    )
    update_incident(
        incident_id,
        {
            "status": "INVESTIGATING",
            "response_action": "STOPPED_AFTER_APPROVAL",
            "stopped_by": approved_by,
            "stopped_at": now_iso(),
            "instance_id": instance_id,
            "instance_state": current_state,
        },
    )
    publish(
        "[SECURITY] EC2 stopped after approval",
        f"Instance: {instance_id}\nIncident: {incident_id}\nApproved by: {approved_by}",
    )
    return {
        "message": "EC2 stop requested",
        "instance_id": instance_id,
        "instance_state": current_state,
    }


def reject_approval(event):
    incident_id = event.get("incident_id", "")
    rejected_by = event.get("approved_by", "")
    if not incident_id or not rejected_by:
        raise ValueError("incident_id and approved_by are required")

    update_incident(
        incident_id,
        {
            "status": "OPEN",
            "response_action": "REJECTED_NO_AUTOMATED_ACTION",
            "rejected_by": rejected_by,
            "rejected_at": now_iso(),
        },
    )
    publish(
        "[SECURITY] Automated EC2 response rejected",
        f"Incident: {incident_id}\nRejected by: {rejected_by}",
    )
    return {
        "message": "Automated response rejected",
        "incident_id": incident_id,
    }


def lambda_handler(event, context):
    try:
        action = event.get("action", "PROCESS_FINDING")
        if action == "QUARANTINE_APPROVED":
            result = quarantine_approved(event)
        elif action == "RESTORE_APPROVED":
            result = restore_approved(event)
        elif action == "STOP_APPROVED":
            result = stop_approved(event)
        elif action == "REJECT_APPROVAL":
            result = reject_approval(event)
        elif event.get("source") == "aws.guardduty" or event.get("detail"):
            result = process_guardduty_finding(event)
        else:
            raise ValueError("Unsupported event")

        return {"statusCode": 200, "body": json.dumps(result)}
    except Exception as exc:
        print(json.dumps({"error": str(exc), "event": event}, default=str))
        raise
