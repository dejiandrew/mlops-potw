"""ML-Ops infrastructure for NBA Player of the Week prediction endpoint"""

import base64
import pulumi
import pulumi_gcp as gcp

# Get configuration
config = pulumi.Config()
gcp_config = pulumi.Config("gcp")
project = gcp_config.require("project")
region = gcp_config.require("region")
function_name = config.require("functionName")
alert_email = config.require("alertEmail")
rate_limit = config.require_int("rateLimit")

# Create BigQuery dataset for prediction logs
dataset = gcp.bigquery.Dataset(
    "prediction-logs-dataset",
    dataset_id="ml_prediction_logs",
    description="Stores prediction logs for NBA Player of the Week model",
    location="US",
    delete_contents_on_destroy=False,
)

# Create BigQuery table for prediction logs
table = gcp.bigquery.Table(
    "prediction-logs-table",
    dataset_id=dataset.dataset_id,
    table_id="potw_predictions",
    deletion_protection=False,
    schema=pulumi.Output.all().apply(
        lambda _: """[
    {
      "name": "timestamp",
      "type": "TIMESTAMP",
      "mode": "REQUIRED",
      "description": "When the prediction was made"
    },
    {
      "name": "week_start",
      "type": "STRING",
      "mode": "REQUIRED",
      "description": "Input week start date"
    },
    {
      "name": "predictions",
      "type": "RECORD",
      "mode": "REPEATED",
      "description": "Array of player predictions",
      "fields": [
        {
          "name": "conference",
          "type": "STRING",
          "mode": "NULLABLE"
        },
        {
          "name": "name",
          "type": "STRING",
          "mode": "NULLABLE"
        },
        {
          "name": "probability_pct",
          "type": "FLOAT",
          "mode": "NULLABLE"
        },
        {
          "name": "rank",
          "type": "INTEGER",
          "mode": "NULLABLE"
        }
      ]
    },
    {
      "name": "client_ip",
      "type": "STRING",
      "mode": "NULLABLE",
      "description": "Client IP address"
    },
    {
      "name": "response_time_ms",
      "type": "FLOAT",
      "mode": "NULLABLE",
      "description": "Response time in milliseconds"
    },
    {
      "name": "status_code",
      "type": "INTEGER",
      "mode": "NULLABLE",
      "description": "HTTP status code"
    }
  ]"""
    ),
)

# Create notification channel for email alerts
notification_channel = gcp.monitoring.NotificationChannel(
    "alert-email-channel",
    display_name="ML-Ops Alert Email",
    type="email",
    labels={
        "email_address": alert_email,
    },
)

# Alert policy for high latency (>2 seconds)
latency_alert = gcp.monitoring.AlertPolicy(
    "latency-alert",
    display_name="High Latency Alert - POTW Predictions",
    combiner="OR",
    conditions=[
        {
            "display_name": "Response time > 2 seconds",
            "condition_threshold": {
                "filter": pulumi.Output.concat(
                    'resource.type="cloud_function" AND ',
                    'resource.labels.function_name="',
                    function_name,
                    '" AND ',
                    'metric.type="cloudfunctions.googleapis.com/function/execution_times"',
                ),
                "comparison": "COMPARISON_GT",
                "threshold_value": 2000,  # 2 seconds in milliseconds
                "duration": "60s",
                "aggregations": [
                    {
                        "alignment_period": "60s",
                        "per_series_aligner": "ALIGN_DELTA",
                        "cross_series_reducer": "REDUCE_PERCENTILE_95",
                        "group_by_fields": ["resource.function_name"],
                    }
                ],
            },
        }
    ],
    notification_channels=[notification_channel.id],
    alert_strategy={
        "auto_close": "604800s",  # 7 days
    },
    documentation={
        "content": "The 95th percentile response time for the POTW prediction function has exceeded 2 seconds.",
        "mime_type": "text/markdown",
    },
)

# Alert policy for high error rate (>5%)
error_rate_alert = gcp.monitoring.AlertPolicy(
    "error-rate-alert",
    display_name="High Error Rate Alert - POTW Predictions",
    combiner="OR",
    conditions=[
        {
            "display_name": "Error rate > 5%",
            "condition_threshold": {
                "filter": pulumi.Output.concat(
                    'resource.type="cloud_function" AND ',
                    'resource.labels.function_name="',
                    function_name,
                    '" AND ',
                    'metric.type="cloudfunctions.googleapis.com/function/execution_count" AND ',
                    'metric.labels.status!="ok"',
                ),
                "comparison": "COMPARISON_GT",
                "threshold_value": 0.05,  # 5%
                "duration": "300s",
                "aggregations": [
                    {
                        "alignment_period": "60s",
                        "per_series_aligner": "ALIGN_RATE",
                        "cross_series_reducer": "REDUCE_SUM",
                        "group_by_fields": ["resource.function_name"],
                    }
                ],
            },
        }
    ],
    notification_channels=[notification_channel.id],
    alert_strategy={
        "auto_close": "604800s",
    },
    documentation={
        "content": "The error rate for the POTW prediction function has exceeded 5%.",
        "mime_type": "text/markdown",
    },
)

# Alert policy for request volume anomalies
volume_alert = gcp.monitoring.AlertPolicy(
    "volume-anomaly-alert",
    display_name="Request Volume Anomaly - POTW Predictions",
    combiner="OR",
    conditions=[
        {
            "display_name": "Unusual request volume",
            "condition_threshold": {
                "filter": pulumi.Output.concat(
                    'resource.type="cloud_function" AND ',
                    'resource.labels.function_name="',
                    function_name,
                    '" AND ',
                    'metric.type="cloudfunctions.googleapis.com/function/execution_count"',
                ),
                "comparison": "COMPARISON_GT",
                "threshold_value": 1000,  # Alert if >1000 requests in 5 minutes
                "duration": "300s",
                "aggregations": [
                    {
                        "alignment_period": "300s",
                        "per_series_aligner": "ALIGN_RATE",
                        "cross_series_reducer": "REDUCE_SUM",
                        "group_by_fields": ["resource.function_name"],
                    }
                ],
            },
        }
    ],
    notification_channels=[notification_channel.id],
    alert_strategy={
        "auto_close": "604800s",
    },
    documentation={
        "content": "The POTW prediction function is experiencing unusually high request volume (>1000 requests in 5 minutes).",
        "mime_type": "text/markdown",
    },
)

# Create API Gateway API
api = gcp.apigateway.Api(
    "potw-api",
    api_id="potw-predictions-api",
    display_name="POTW Predictions API",
)

# Create OpenAPI spec for API Gateway with rate limiting
openapi_spec = pulumi.Output.concat(
    """openapi: 2.0.0
info:
  title: NBA Player of the Week Predictions API
  description: ML-Ops enabled API for POTW predictions
  version: 1.0.0
schemes:
  - https
produces:
  - application/json
x-google-backend:
  address: https://""",
    region,
    """-""",
    project,
    """.cloudfunctions.net/""",
    function_name,
    """
  protocol: h2
paths:
  /predict:
    post:
      summary: Get POTW predictions
      operationId: predict
      x-google-quota:
        metricCosts:
          "api-requests": 1
      responses:
        '200':
          description: Successful prediction
          schema:
            type: array
            items:
              type: object
              properties:
                conference:
                  type: string
                name:
                  type: string
                probability_pct:
                  type: number
                rank:
                  type: integer
x-google-management:
  metrics:
    - name: "api-requests"
      valueType: INT64
      metricKind: DELTA
  quota:
    limits:
      - name: "api-requests-per-minute"
        metric: "api-requests"
        unit: "1/min/{project}"
        values:
          STANDARD: """,
    str(rate_limit),
    """
""",
)

# Create API Gateway API Config
api_config = gcp.apigateway.ApiConfig(
    "potw-api-config",
    api=api.api_id,
    api_config_id_prefix="potw-config-",
    display_name="POTW API Config",
    gateway_config={
        "backend_config": {
            "google_service_account": pulumi.Output.concat(
                project, "@appspot.gserviceaccount.com"
            ),
        },
    },
    openapi_documents=[
        {
            "document": {
                "path": "openapi.yaml",
                "contents": openapi_spec.apply(
                    lambda s: base64.b64encode(s.encode("utf-8")).decode("utf-8")
                ),
            },
        }
    ],
)

# Create a storage bucket for the Cloud Function source code
bucket = gcp.storage.Bucket(
    "function-source-bucket",
    location=region.upper(),
    uniform_bucket_level_access=True,
)

# Create an archive of the function code
function_archive = pulumi.AssetArchive(
    {
        "main.py": pulumi.FileAsset("function/main.py"),
        "requirements.txt": pulumi.FileAsset("function/requirements.txt"),
    }
)

# Upload the function code to the bucket
function_source = gcp.storage.BucketObject(
    "function-source",
    bucket=bucket.name,
    source=function_archive,
)

# Create the instrumented Cloud Function
instrumented_function = gcp.cloudfunctionsv2.Function(
    "potw-instrumented-function",
    location=region,
    description="ML-Ops instrumented POTW prediction function with BigQuery logging",
    build_config={
        "runtime": "python311",
        "entry_point": "predict_with_logging",
        "source": {
            "storage_source": {
                "bucket": bucket.name,
                "object": function_source.name,
            },
        },
    },
    service_config={
        "max_instance_count": 10,
        "available_memory": "256M",
        "timeout_seconds": 60,
        "environment_variables": {
            "GCP_PROJECT": project,
            "BIGQUERY_DATASET": dataset.dataset_id,
            "BIGQUERY_TABLE": table.table_id,
            "ORIGINAL_FUNCTION_URL": pulumi.Output.concat(
                "https://",
                region,
                "-",
                project,
                ".cloudfunctions.net/",
                function_name,
            ),
        },
        "ingress_settings": "ALLOW_ALL",
        "all_traffic_on_latest_revision": True,
    },
)

# Make the function publicly accessible
function_iam = gcp.cloudfunctionsv2.FunctionIamMember(
    "function-invoker",
    project=project,
    location=region,
    cloud_function=instrumented_function.name,
    role="roles/cloudfunctions.invoker",
    member="allUsers",
)

# Create API Gateway
gateway = gcp.apigateway.Gateway(
    "potw-gateway",
    api_config=api_config.id,
    gateway_id="potw-gateway",
    display_name="POTW Predictions Gateway",
    region=region,
)

# Export the dataset and table names
pulumi.export("bigquery_dataset", dataset.dataset_id)
pulumi.export("bigquery_table", table.table_id)
pulumi.export(
    "bigquery_table_full_id",
    pulumi.Output.concat(project, ".", dataset.dataset_id, ".", table.table_id),
)
pulumi.export("notification_channel_id", notification_channel.id)
pulumi.export(
    "alert_policies", [latency_alert.id, error_rate_alert.id, volume_alert.id]
)
pulumi.export(
    "api_gateway_url", gateway.default_hostname.apply(lambda h: f"https://{h}")
)
pulumi.export(
    "api_endpoint",
    gateway.default_hostname.apply(lambda h: f"https://{h}/predict"),
)
pulumi.export("instrumented_function_url", instrumented_function.service_config.uri)
pulumi.export("function_source_bucket", bucket.name)
