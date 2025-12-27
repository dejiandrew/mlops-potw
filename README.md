# ML-Ops Infrastructure for NBA Player of the Week Predictions

This Pulumi project adds ML-Ops capabilities to an existing Google Cloud Functions ML endpoint for NBA Player of the Week predictions.

## Features

### 1. **Prediction Logging to BigQuery**
- Automatically logs all predictions to BigQuery for analysis
- Tracks: timestamp, input (week_start), predictions array, client IP, response time, and status code
- Dataset: `ml_prediction_logs`
- Table: `potw_predictions`

### 2. **Cloud Monitoring & Alerting**
- **High Latency Alert**: Triggers when 95th percentile response time > 2 seconds
- **High Error Rate Alert**: Triggers when error rate > 5%
- **Volume Anomaly Alert**: Triggers when request volume > 1000 requests in 5 minutes
- Email notifications sent to: `adeji9@gmail.com`

### 3. **API Gateway with Rate Limiting**
- Public API Gateway endpoint with 50 requests/minute rate limiting
- Routes traffic through an instrumented Cloud Function that logs to BigQuery
- Provides centralized access control and monitoring

## Architecture

```
Client Request
    ↓
API Gateway (rate limiting: 50 req/min)
    ↓
Instrumented Cloud Function (logs to BigQuery)
    ↓
Original Cloud Function (predict-potw)
    ↓
Response + Logging
```

## Infrastructure Components

- **BigQuery Dataset & Table**: Stores prediction logs
- **Cloud Monitoring Alert Policies**: 3 alert policies for latency, errors, and volume
- **Notification Channel**: Email alerts to adeji9@gmail.com
- **API Gateway**: Rate-limited public endpoint
- **Cloud Function (Gen 2)**: Instrumented wrapper with BigQuery logging
- **Storage Bucket**: Stores Cloud Function source code

## Prerequisites

- Google Cloud Project: `cis-5450-final-project`
- Region: `us-central1`
- GCP Service Account with appropriate permissions
- Pulumi CLI installed
- Python 3.11+

## Setup

### 1. Install Dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure GCP Credentials

You have two options:

**Option A: Using Pulumi ESC (Recommended)**

The ESC environment `dejiandrew-org/mlops-potw/gcp-creds` has been created. To complete the setup:

1. Edit the environment to add your GCP credentials:
   ```bash
   pulumi env edit dejiandrew-org/mlops-potw/gcp-creds
   ```

2. Add this configuration:
   ```yaml
   values:
     gcpCredsJson:
       fn::secret: '<your-gcp-json-key-as-string>'
     
     environmentVariables:
       GOOGLE_CREDENTIALS: ${gcpCredsJson}
       CLOUDSDK_CORE_PROJECT: cis-5450-final-project
       CLOUDSDK_COMPUTE_REGION: us-central1
     
     pulumiConfig:
       gcp:project: cis-5450-final-project
       gcp:region: us-central1
   ```

3. The environment is already linked to the stack

**Option B: Using gcloud CLI**

```bash
gcloud auth activate-service-account --key-file=path/to/your/key.json
gcloud config set project cis-5450-final-project
```

### 3. Deploy the Infrastructure

```bash
pulumi up
```

## Configuration

The stack is configured with:

- `gcp:project`: cis-5450-final-project
- `gcp:region`: us-central1
- `functionName`: predict-potw (original function)
- `alertEmail`: adeji9@gmail.com
- `rateLimit`: 50 (requests per minute)

## Outputs

After deployment, you'll get:

- `bigquery_dataset`: Dataset ID for prediction logs
- `bigquery_table`: Table ID for prediction logs
- `bigquery_table_full_id`: Full table reference
- `notification_channel_id`: Cloud Monitoring notification channel ID
- `alert_policies`: List of alert policy IDs
- `api_gateway_url`: Base URL for the API Gateway
- `api_endpoint`: Full endpoint URL for predictions
- `instrumented_function_url`: Direct URL to the instrumented function
- `function_source_bucket`: Bucket containing function source code

## Usage

### Making Predictions

Use the API Gateway endpoint:

```bash
curl -X POST https://<api-gateway-url>/predict \
  -H "Content-Type: application/json" \
  -d '{"week_start": "2025-12-08"}'
```

### Querying Prediction Logs

```sql
SELECT 
  timestamp,
  week_start,
  client_ip,
  response_time_ms,
  status_code,
  predictions
FROM `cis-5450-final-project.ml_prediction_logs.potw_predictions`
ORDER BY timestamp DESC
LIMIT 100;
```

### Analyzing Performance

```sql
SELECT 
  DATE(timestamp) as date,
  COUNT(*) as total_requests,
  AVG(response_time_ms) as avg_response_time,
  APPROX_QUANTILES(response_time_ms, 100)[OFFSET(95)] as p95_response_time,
  COUNTIF(status_code != 200) as errors
FROM `cis-5450-final-project.ml_prediction_logs.potw_predictions`
GROUP BY date
ORDER BY date DESC;
```

## Monitoring

- **Cloud Monitoring Dashboard**: View metrics in the GCP Console
- **Email Alerts**: Configured to send to adeji9@gmail.com
- **BigQuery Logs**: Query historical prediction data

## Project Structure

```
.
├── __main__.py              # Main Pulumi program
├── function/
│   ├── main.py             # Instrumented Cloud Function code
│   └── requirements.txt    # Function dependencies
├── Pulumi.yaml             # Pulumi project configuration
├── Pulumi.dev.yaml         # Stack configuration
├── requirements.txt        # Pulumi dependencies
└── README.md              # This file
```

## Notes

- The instrumented function proxies requests to the original `predict-potw` function
- All predictions are logged asynchronously to avoid impacting response times
- Rate limiting is enforced at the API Gateway level
- The original function remains unchanged and operational

## Troubleshooting

### Preview/Deploy Fails with Auth Errors

Ensure GCP credentials are properly configured (see Setup section above).

### Function Deployment Takes Long

Cloud Functions Gen 2 can take 3-5 minutes to deploy. This is normal.

### BigQuery Insert Errors

Check that the service account has `bigquery.dataEditor` role on the dataset.

## Future Enhancements

- Add A/B testing capabilities
- Implement model versioning
- Add custom metrics for model-specific monitoring
- Create Cloud Monitoring dashboards
- Add request/response validation
