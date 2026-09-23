import json
import os
from datetime import datetime, timedelta, timezone
from flask import Flask, jsonify, render_template, request
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False

DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() == "true"
AWS_REGION = os.getenv("AWS_REGION", "ap-south-1")

def demo_events():
    now = datetime.now(timezone.utc)
    samples = [
        ("ConsoleLogin", "signin.amazonaws.com", "demo-admin", "SUCCESS", "us-east-1"),
        ("CreateBucket", "s3.amazonaws.com", "demo-user", "SUCCESS", AWS_REGION),
        ("RunInstances", "ec2.amazonaws.com", "demo-user", "SUCCESS", AWS_REGION),
        ("AuthorizeSecurityGroupIngress", "ec2.amazonaws.com", "demo-admin", "REVIEW", AWS_REGION),
        ("DeleteTrail", "cloudtrail.amazonaws.com", "demo-user", "REVIEW", AWS_REGION),
    ]
    return [{
        "event_id": f"DEMO-{i+1:03}",
        "event_time": (now - timedelta(minutes=i*17)).isoformat(),
        "event_name": name,
        "event_source": source,
        "username": user,
        "region": region,
        "account_id": "DEMO-ACCOUNT",
        "read_only": "false",
        "status": status,
        "source": "DEMO DATA — NOT AWS",
        "raw_event": {"note": "Illustrative demonstration record. Not retrieved from AWS."}
    } for i, (name, source, user, status, region) in enumerate(samples)]

def get_aws_events():
    """Retrieve recent management events from the configured account/region."""
    import boto3
    client = boto3.client("cloudtrail", region_name=AWS_REGION)
    response = client.lookup_events(MaxResults=50)
    results = []
    for event in response.get("Events", []):
        raw = {}
        try:
            raw = json.loads(event.get("CloudTrailEvent") or "{}")
        except json.JSONDecodeError:
            pass
        event_name = event.get("EventName", "Unknown")
        results.append({
            "event_id": event.get("EventId", ""),
            "event_time": event.get("EventTime").isoformat() if event.get("EventTime") else "",
            "event_name": event_name,
            "event_source": event.get("EventSource", ""),
            "username": event.get("Username") or "Unknown",
            "region": raw.get("awsRegion", AWS_REGION),
            "account_id": raw.get("recipientAccountId", "Unknown"),
            "read_only": event.get("ReadOnly", "Unknown"),
            "status": "REVIEW" if event_name in {"DeleteTrail", "StopLogging", "DeleteBucket", "AuthorizeSecurityGroupIngress"} else "RECORDED",
            "source": "AWS CloudTrail LookupEvents",
            "raw_event": raw
        })
    return results

def load_events():
    if DEMO_MODE:
        return demo_events()
    return get_aws_events()

@app.route("/")
def index():
    return render_template("index.html", demo_mode=DEMO_MODE, region=AWS_REGION)

@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "mode": "demo" if DEMO_MODE else "aws", "region": AWS_REGION})

@app.route("/api/events")
def events():
    try:
        data = load_events()
        q = request.args.get("q", "").strip().lower()
        if q:
            data = [e for e in data if q in " ".join(str(e.get(k, "")) for k in
                    ("event_name", "event_source", "username", "account_id", "status")).lower()]
        status = request.args.get("status", "").upper()
        if status:
            data = [e for e in data if e["status"].upper() == status]
        return jsonify({"count": len(data), "events": data})
    except Exception as exc:
        app.logger.exception("Unable to load CloudTrail events")
        return jsonify({"error": "Unable to retrieve events. Check AWS credentials, region, and IAM permissions.",
                        "detail": str(exc)}), 502

@app.route("/api/summary")
def summary():
    try:
        data = load_events()
        return jsonify({
            "total_events": len(data),
            "accounts_seen": len(set(e["account_id"] for e in data)),
            "review_events": sum(e["status"] == "REVIEW" for e in data),
            "sources": sorted(set(e["source"] for e in data)),
            "mode": "demo" if DEMO_MODE else "aws"
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 502

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5000")), debug=False)
