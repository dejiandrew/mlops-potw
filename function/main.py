"""
Cloud Function wrapper that adds ML-Ops logging to the POTW prediction endpoint.
This function proxies requests to the original predict-potw function and logs
predictions to BigQuery for analysis.
"""

import json
import os
import time
from datetime import datetime

import functions_framework
import requests
from google.cloud import bigquery


# Initialize BigQuery client
bq_client = bigquery.Client()

# Configuration from environment variables
PROJECT_ID = os.environ.get("GCP_PROJECT")
DATASET_ID = os.environ.get("BIGQUERY_DATASET", "ml_prediction_logs")
TABLE_ID = os.environ.get("BIGQUERY_TABLE", "potw_predictions")
ORIGINAL_FUNCTION_URL = os.environ.get(
    "ORIGINAL_FUNCTION_URL",
    "https://us-central1-cis-5450-final-project.cloudfunctions.net/predict-potw",
)


@functions_framework.http
def predict_with_logging(request):
    """
    HTTP Cloud Function that wraps the original prediction endpoint
    and logs requests/responses to BigQuery.
    """
    start_time = time.time()

    # Get client IP
    client_ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    if client_ip and "," in client_ip:
        client_ip = client_ip.split(",")[0].strip()

    # Set CORS headers
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
    }

    # Handle preflight OPTIONS request
    if request.method == "OPTIONS":
        return ("", 204, headers)

    try:
        # Get request data
        request_json = request.get_json(silent=True)
        if not request_json:
            return (
                json.dumps({"error": "Request must be JSON"}),
                400,
                {"Content-Type": "application/json", **headers},
            )

        week_start = request_json.get("week_start")
        if not week_start:
            return (
                json.dumps({"error": "week_start is required"}),
                400,
                {"Content-Type": "application/json", **headers},
            )

        # Call the original prediction function
        response = requests.post(
            ORIGINAL_FUNCTION_URL,
            json=request_json,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )

        response_time_ms = (time.time() - start_time) * 1000
        status_code = response.status_code

        # Parse response
        predictions = []
        if status_code == 200:
            try:
                predictions = response.json()
            except json.JSONDecodeError:
                predictions = []

        # Log to BigQuery
        try:
            table_ref = f"{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}"
            row = {
                "timestamp": datetime.utcnow().isoformat(),
                "week_start": week_start,
                "predictions": predictions,
                "client_ip": client_ip,
                "response_time_ms": response_time_ms,
                "status_code": status_code,
            }

            errors = bq_client.insert_rows_json(table_ref, [row])
            if errors:
                print(f"BigQuery insert errors: {errors}")
        except Exception as e:
            # Log error but don't fail the request
            print(f"Failed to log to BigQuery: {e}")

        # Return the original response
        return (
            response.content,
            status_code,
            {"Content-Type": "application/json", **headers},
        )

    except requests.exceptions.RequestException as e:
        response_time_ms = (time.time() - start_time) * 1000
        print(f"Error calling original function: {e}")

        # Log the error to BigQuery
        try:
            table_ref = f"{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}"
            row = {
                "timestamp": datetime.utcnow().isoformat(),
                "week_start": request_json.get("week_start", "unknown"),
                "predictions": [],
                "client_ip": client_ip,
                "response_time_ms": response_time_ms,
                "status_code": 500,
            }
            bq_client.insert_rows_json(table_ref, [row])
        except Exception as log_error:
            print(f"Failed to log error to BigQuery: {log_error}")

        return (
            json.dumps({"error": "Failed to get predictions"}),
            500,
            {"Content-Type": "application/json", **headers},
        )

    except Exception as e:
        print(f"Unexpected error: {e}")
        return (
            json.dumps({"error": "Internal server error"}),
            500,
            {"Content-Type": "application/json", **headers},
        )
