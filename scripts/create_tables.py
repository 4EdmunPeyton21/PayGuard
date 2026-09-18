"""Creates PayGuard DynamoDB tables locally or in AWS."""
import os
import sys

# Ensure backend package is in pythonpath
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

import boto3
from app.config import settings
from botocore.exceptions import ClientError


def get_dynamodb_client():
    kwargs = {
        "region_name": settings.aws_region,
    }
    if settings.ddb_endpoint_url:
        kwargs["endpoint_url"] = settings.ddb_endpoint_url
        kwargs["aws_access_key_id"] = "dummy"
        kwargs["aws_secret_access_key"] = "dummy"
    return boto3.client("dynamodb", **kwargs)


def create_payguard_tables():
    client = get_dynamodb_client()
    table_name = settings.ddb_table

    print(f"Connecting to DynamoDB at {settings.ddb_endpoint_url or 'AWS default'}...")

    try:
        response = client.describe_table(TableName=table_name)
        print(f"Table '{table_name}' already exists (status: {response['Table']['TableStatus']}).")
        return
    except ClientError as e:
        if e.response["Error"]["Code"] != "ResourceNotFoundException":
            raise e

    print(f"Creating table '{table_name}'...")
    client.create_table(
        TableName=table_name,
        KeySchema=[
            {"AttributeName": "PK", "KeyType": "HASH"},
            {"AttributeName": "SK", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "PK", "AttributeType": "S"},
            {"AttributeName": "SK", "AttributeType": "S"},
            {"AttributeName": "GSI1PK", "AttributeType": "S"},
            {"AttributeName": "GSI1SK", "AttributeType": "S"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "GSI1",
                "KeySchema": [
                    {"AttributeName": "GSI1PK", "KeyType": "HASH"},
                    {"AttributeName": "GSI1SK", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
        BillingMode="PAY_PER_REQUEST",
    )

    # Wait for table to become active
    waiter = client.get_waiter("table_exists")
    waiter.wait(TableName=table_name)
    print(f"Table '{table_name}' created successfully.")

    # Enable TTL
    try:
        client.update_time_to_live(
            TableName=table_name,
            TimeToLiveSpecification={
                "Enabled": True,
                "AttributeName": "ttl",
            },
        )
        print("TTL enabled on attribute 'ttl'.")
    except Exception as exc:
        print(f"Notice: TTL update result: {exc}")


if __name__ == "__main__":
    create_payguard_tables()
