"""PayGuard DynamoDB Single-Table Storage Layer.

Implements the single-table design from Architecture Section 4.5:
  PK: CASE#<id> | SK: META       -> case metadata, timestamps, risk level
  PK: CASE#<id> | SK: REPORT     -> full SafetyReport JSON
  PK: CASE#<id> | SK: EV#<id>    -> individual evidence items
  PK: CASE#<id> | SK: TRC#<seq>  -> ordered trace steps
  GSI1: GSI1PK = RISK#<level>, GSI1SK = <timestamp>
  ttl: Unix timestamp for automatic record expiration.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from app.config import settings
from app.schemas.case import NormalisedCase
from app.schemas.report import SafetyReport


def _float_to_decimal(obj: Any) -> Any:
    """Recursively convert float values to Decimal for DynamoDB."""
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: _float_to_decimal(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_float_to_decimal(v) for v in obj]
    return obj


def _decimal_to_float(obj: Any) -> Any:
    """Recursively convert Decimal values back to float/int."""
    if isinstance(obj, Decimal):
        return float(obj) if obj % 1 != 0 else int(obj)
    if isinstance(obj, dict):
        return {k: _decimal_to_float(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_decimal_to_float(v) for v in obj]
    return obj


def get_dynamodb_resource():
    kwargs: Dict[str, Any] = {
        "region_name": settings.aws_region,
    }
    if settings.ddb_endpoint_url:
        kwargs["endpoint_url"] = settings.ddb_endpoint_url
        kwargs["aws_access_key_id"] = "dummy"
        kwargs["aws_secret_access_key"] = "dummy"
    return boto3.resource("dynamodb", **kwargs)


def get_table():
    resource = get_dynamodb_resource()
    return resource.Table(settings.ddb_table)


def save_case_investigation(
    case_id: str,
    case: NormalisedCase,
    report: SafetyReport,
    trace: List[Any],
) -> None:
    """Persists case metadata, report, evidence, and trace steps into DynamoDB."""
    table = get_table()
    now_utc = datetime.now(timezone.utc)
    now_iso = now_utc.isoformat()
    now_ts = int(time.time())
    case_ttl = now_ts + (settings.case_ttl_days * 86400)

    # 1. Prepare items
    meta_item = {
        "PK": f"CASE#{case_id}",
        "SK": "META",
        "case_id": case_id,
        "created_at": now_iso,
        "status": "COMPLETED",
        "risk_level": report.risk_level,
        "risk_score": Decimal(str(report.risk_score)),
        "model": report.model,
        "tool_calls": report.tool_calls,
        "latency_ms": report.latency_ms,
        "GSI1PK": f"RISK#{report.risk_level}",
        "GSI1SK": now_iso,
        "ttl": case_ttl,
    }

    report_dict = json.loads(report.model_dump_json(), parse_float=Decimal)
    report_item = {
        "PK": f"CASE#{case_id}",
        "SK": "REPORT",
        "case_id": case_id,
        "report": report_dict,
        "GSI1PK": f"RISK#{report.risk_level}",
        "GSI1SK": now_iso,
        "ttl": case_ttl,
    }

    evidence_items = []
    for ev in report.evidence:
        ev_dict = json.loads(ev.model_dump_json(), parse_float=Decimal)
        evidence_items.append({
            "PK": f"CASE#{case_id}",
            "SK": f"EV#{ev.id}",
            "case_id": case_id,
            "evidence_id": ev.id,
            "evidence": ev_dict,
            "ttl": case_ttl,
        })

    trace_items = []
    for idx, step in enumerate(trace):
        step_dict = asdict(step) if is_dataclass(step) else dict(step)
        raw_args = step_dict.get("args", {})
        args_str = json.dumps(raw_args, default=str)
        trace_items.append({
            "PK": f"CASE#{case_id}",
            "SK": f"TRC#{idx + 1:03d}",
            "case_id": case_id,
            "step_index": idx + 1,
            "tool": step_dict.get("tool", ""),
            "args": args_str,
            "result_type": step_dict.get("result_type", "ok"),
            "elapsed_ms": step_dict.get("elapsed_ms", 0),
            "result_summary": step_dict.get("result_summary", ""),
            "ttl": case_ttl,
        })

    # 2. Batch write to table
    with table.batch_writer() as batch:
        batch.put_item(Item=meta_item)
        batch.put_item(Item=report_item)
        for ev_item in evidence_items:
            batch.put_item(Item=ev_item)
        for trc_item in trace_items:
            batch.put_item(Item=trc_item)


def get_case_report(case_id: str) -> Optional[SafetyReport]:
    """Retrieves the SafetyReport for a given case_id."""
    table = get_table()
    try:
        response = table.get_item(
            Key={
                "PK": f"CASE#{case_id}",
                "SK": "REPORT",
            }
        )
    except ClientError:
        return None

    item = response.get("Item")
    if not item or "report" not in item:
        return None

    report_data = _decimal_to_float(item["report"])
    return SafetyReport.model_validate(report_data)


def get_case_trace(case_id: str) -> Optional[List[Dict[str, Any]]]:
    """Retrieves all ordered trace steps for a given case_id."""
    table = get_table()
    try:
        response = table.query(
            KeyConditionExpression=Key("PK").eq(f"CASE#{case_id}")
            & Key("SK").begins_with("TRC#")
        )
    except ClientError:
        return None

    items = response.get("Items", [])
    if not items:
        # Check if case exists at all
        meta = table.get_item(Key={"PK": f"CASE#{case_id}", "SK": "META"})
        if "Item" not in meta:
            return None
        return []

    items.sort(key=lambda x: x["SK"])
    trace_steps: List[Dict[str, Any]] = []
    for item in items:
        raw_args = item.get("args", "{}")
        try:
            parsed_args = json.loads(raw_args)
        except Exception:
            parsed_args = raw_args

        trace_steps.append({
            "step_index": int(item.get("step_index", 0)),
            "tool": item.get("tool", ""),
            "args": parsed_args,
            "result_type": item.get("result_type", "ok"),
            "elapsed_ms": int(item.get("elapsed_ms", 0)),
            "result_summary": item.get("result_summary", ""),
        })

    return trace_steps
