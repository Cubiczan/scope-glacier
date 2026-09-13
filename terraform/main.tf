# Scope.Glacier AWS Infrastructure
# S3 + Iceberg + Glue + Athena + Lambda + Step Functions + EventBridge

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# ============================================================
# S3 Buckets
# ============================================================

resource "aws_s3_bucket" "raw" {
  bucket = "${var.project_name}-raw-${var.environment}"

  lifecycle_rule {
    id      = "transition-to-ia"
    enabled = true
    transition {
      days          = 90
      storage_class = "STANDARD_IA"
    }
    transition {
      days          = 365
      storage_class = "GLACIER"
    }
  }
}

resource "aws_s3_bucket" "iceberg_warehouse" {
  bucket = "${var.project_name}-warehouse-${var.environment}"
}

resource "aws_s3_bucket" "athena_output" {
  bucket = "${var.project_name}-queries-${var.environment}"

  lifecycle_rule {
    id      = "cleanup"
    enabled = true
    expiration {
      days = 30
    }
  }
}

resource "aws_s3_bucket_public_access_block" "all" {
  for_each = toset([aws_s3_bucket.raw.id, aws_s3_bucket.iceberg_warehouse.id, aws_s3_bucket.athena_output.id])

  bucket                  = each.value
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ============================================================
# Glue Database & Tables
# ============================================================

resource "aws_glue_catalog_database" "glacier" {
  name = var.glue_database
}

resource "aws_glue_catalog_table" "price_series" {
  name          = "price_series"
  database_name = aws_glue_catalog_database.glacier.name

  table_type = "ICEBERG"
  parameters = {
    "table_type"           = "ICEBERG"
    "format_version"       = "2"
    "metadata_compression" = "gzip"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.iceberg_warehouse.bucket}/price_series/"
    input_format  = "org.apache.hadoop.mapred.FileInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
      parameters = {
        "serialization.format" = "1"
      }
    }

    columns {
      name = "commodity_code"
      type = "string"
    }
    columns {
      name = "commodity_name"
      type = "string"
    }
    columns {
      name = "price_date"
      type = "date"
    }
    columns {
      name = "price_value"
      type = "double"
    }
    columns {
      name = "source"
      type = "string"
    }
    columns {
      name = "ingested_at"
      type = "timestamp"
    }
  }
}

resource "aws_glue_catalog_table" "supply_demand_balance" {
  name          = "supply_demand_balance"
  database_name = aws_glue_catalog_database.glacier.name

  table_type = "ICEBERG"
  parameters = {
    "table_type"     = "ICEBERG"
    "format_version" = "2"
  }

  storage_descriptor {
    location = "s3://${aws_s3_bucket.iceberg_warehouse.bucket}/supply_demand_balance/"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    columns {
      name = "commodity_code"
      type = "string"
    }
    columns {
      name = "period"
      type = "string"
    }
    columns {
      name = "date"
      type = "date"
    }
    columns {
      name = "production_mbd"
      type = "double"
    }
    columns {
      name = "consumption_mbd"
      type = "double"
    }
    columns {
      name = "imports_mbd"
      type = "double"
    }
    columns {
      name = "exports_mbd"
      type = "double"
    }
    columns {
      name = "inventory_mmbl"
      type = "double"
    }
    columns {
      name = "inventory_change_mmbl"
      type = "double"
    }
    columns {
      name = "spare_capacity_mbd"
      type = "double"
    }
    columns {
      name = "utilization_pct"
      type = "double"
    }
  }
}

resource "aws_glue_catalog_table" "pipelines" {
  name          = "pipelines"
  database_name = aws_glue_catalog_database.glacier.name

  table_type = "ICEBERG"
  parameters = {
    "table_type"     = "ICEBERG"
    "format_version" = "2"
  }

  storage_descriptor {
    location = "s3://${aws_s3_bucket.iceberg_warehouse.bucket}/pipelines/"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    columns {
      name = "pipeline_id"
      type = "string"
    }
    columns {
      name = "name"
      type = "string"
    }
    columns {
      name = "commodity"
      type = "string"
    }
    columns {
      name = "origin"
      type = "string"
    }
    columns {
      name = "destination"
      type = "string"
    }
    columns {
      name = "capacity_bpd"
      type = "double"
    }
    columns {
      name = "current_flow_bpd"
      type = "double"
    }
    columns {
      name = "status"
      type = "string"
    }
    columns {
      name = "length_miles"
      type = "double"
    }
    columns {
      name = "countries_crossed"
      type = "string"
    }
  }
}

resource "aws_glue_catalog_table" "refineries" {
  name          = "refineries"
  database_name = aws_glue_catalog_database.glacier.name

  table_type = "ICEBERG"
  parameters = {
    "table_type"     = "ICEBERG"
    "format_version" = "2"
  }

  storage_descriptor {
    location = "s3://${aws_s3_bucket.iceberg_warehouse.bucket}/refineries/"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    columns {
      name = "refinery_id"
      type = "string"
    }
    columns {
      name = "name"
      type = "string"
    }
    columns {
      name = "region"
      type = "string"
    }
    columns {
      name = "country"
      type = "string"
    }
    columns {
      name = "capacity_bpd"
      type = "double"
    }
    columns {
      name = "utilization_pct"
      type = "double"
    }
    columns {
      name = "status"
      type = "string"
    }
    columns {
      name = "crude_type"
      type = "string"
    }
    columns {
      name = "throughput_bpd"
      type = "double"
    }
  }
}

resource "aws_glue_catalog_table" "glacier_signals" {
  name          = "glacier_signals"
  database_name = aws_glue_catalog_database.glacier.name

  table_type = "ICEBERG"
  parameters = {
    "table_type"     = "ICEBERG"
    "format_version" = "2"
  }

  storage_descriptor {
    location = "s3://${aws_s3_bucket.iceberg_warehouse.bucket}/glacier_signals/"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    columns {
      name = "signal_id"
      type = "string"
    }
    columns {
      name = "commodity_code"
      type = "string"
    }
    columns {
      name = "generated_at"
      type = "timestamp"
    }
    columns {
      name = "supply_demand_score"
      type = "double"
    }
    columns {
      name = "price_momentum_score"
      type = "double"
    }
    columns {
      name = "geopolitical_score"
      type = "double"
    }
    columns {
      name = "seasonal_score"
      type = "double"
    }
    columns {
      name = "glacier_score"
      type = "double"
    }
    columns {
      name = "signal_rating"
      type = "string"
    }
    columns {
      name = "ai_analysis"
      type = "string"
    }
    columns {
      name = "confidence_score"
      type = "double"
    }
    columns {
      name = "data_sources"
      type = "string"
    }
  }
}

resource "aws_glue_catalog_table" "energy_commodities" {
  name          = "energy_commodities"
  database_name = aws_glue_catalog_database.glacier.name

  table_type = "ICEBERG"
  parameters = {
    "table_type"     = "ICEBERG"
    "format_version" = "2"
  }

  storage_descriptor {
    location = "s3://${aws_s3_bucket.iceberg_warehouse.bucket}/energy_commodities/"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    columns {
      name = "commodity_id"
      type = "string"
    }
    columns {
      name = "code"
      type = "string"
    }
    columns {
      name = "name"
      type = "string"
    }
    columns {
      name = "energy_type"
      type = "string"
    }
    columns {
      name = "current_price"
      type = "double"
    }
    columns {
      name = "unit"
      type = "string"
    }
    columns {
      name = "eia_series_id"
      type = "string"
    }
    columns {
      name = "updated_at"
      type = "timestamp"
    }
  }
}

# ============================================================
# Athena Workgroup
# ============================================================

resource "aws_athena_workgroup" "glacier" {
  name = "${var.project_name}-wg"

  configuration {
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = true

    result_configuration {
      output_location = "s3://${aws_s3_bucket.athena_output.bucket}/"

      encryption_configuration {
        encryption_option = "SSE_S3"
      }
    }
  }
}

# ============================================================
# IAM Role for Lambda
# ============================================================

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role" "lambda" {
  name               = "${var.project_name}-lambda-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy" "lambda" {
  name = "${var.project_name}-lambda-policy"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject", "s3:PutObject", "s3:ListBucket",
          "athena:StartQueryExecution", "athena:GetQueryExecution", "athena:GetQueryResults",
          "glue:*",
          "bedrock:Converse",
          "logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents",
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = ["ssm:GetParameter"]
        Resource = [
          aws_ssm_parameter.eia_api_key.arn,
          aws_ssm_parameter.fred_api_key.arn,
        ]
      },
      {
        Effect = "Allow"
        Action = ["sqs:SendMessage"]
        Resource = [
          aws_sqs_queue.eia_ingestion_dlq.arn,
          aws_sqs_queue.glacier_analysis_dlq.arn,
        ]
      }
    ]
  })
}

# ============================================================
# Dead Letter Queues — capture failed (e.g. async EventBridge)
# Lambda invocations so they are not silently dropped.
# ============================================================

resource "aws_sqs_queue" "eia_ingestion_dlq" {
  name                      = "${var.project_name}-eia-ingestion-dlq"
  message_retention_seconds = 1209600 # 14 days
  sqs_managed_sse_enabled   = true
}

resource "aws_sqs_queue" "glacier_analysis_dlq" {
  name                      = "${var.project_name}-analysis-dlq"
  message_retention_seconds = 1209600 # 14 days
  sqs_managed_sse_enabled   = true
}

# ============================================================
# Secrets (SSM SecureString) — keep API keys out of plaintext
# Lambda environment variables. The Lambda reads these at cold start.
# ============================================================

resource "aws_ssm_parameter" "eia_api_key" {
  name        = "/${var.project_name}/eia_api_key"
  description = "US EIA Open Data API key"
  type        = "SecureString"
  value       = var.eia_api_key
}

resource "aws_ssm_parameter" "fred_api_key" {
  name        = "/${var.project_name}/fred_api_key"
  description = "FRED API key"
  type        = "SecureString"
  value       = var.fred_api_key
}

# ============================================================
# Lambda Functions
# ============================================================

resource "aws_lambda_function" "eia_ingestion" {
  function_name = "${var.project_name}-eia-ingestion"
  role          = aws_iam_role.lambda.arn
  handler       = "src.lambda.eia_ingestion_handler.handler"
  runtime       = "python3.12"
  timeout       = 300
  memory_size   = 512

  dead_letter_config {
    target_arn = aws_sqs_queue.eia_ingestion_dlq.arn
  }

  environment {
    variables = {
      RAW_BUCKET             = aws_s3_bucket.raw.id
      GLUE_DATABASE          = var.glue_database
      EIA_API_KEY_PARAM      = aws_ssm_parameter.eia_api_key.name
      FRED_API_KEY_PARAM     = aws_ssm_parameter.fred_api_key.name
      AWS_REGION             = var.aws_region
      ATHENA_OUTPUT          = "s3://${aws_s3_bucket.athena_output.bucket}/"
    }
  }
}

resource "aws_lambda_function" "glacier_analysis" {
  function_name = "${var.project_name}-analysis"
  role          = aws_iam_role.lambda.arn
  handler       = "src.lambda.glacier_analysis_handler.handler"
  runtime       = "python3.12"
  timeout       = 300
  memory_size   = 1024

  dead_letter_config {
    target_arn = aws_sqs_queue.glacier_analysis_dlq.arn
  }

  environment {
    variables = {
      RAW_BUCKET       = aws_s3_bucket.raw.id
      GLUE_DATABASE    = var.glue_database
      AWS_REGION       = var.aws_region
      BEDROCK_MODEL_ID = var.bedrock_model_id
      ATHENA_OUTPUT    = "s3://${aws_s3_bucket.athena_output.bucket}/"
    }
  }
}

# ============================================================
# EventBridge Rules
# ============================================================

resource "aws_cloudwatch_event_rule" "daily_eia_sync" {
  name                = "${var.project_name}-daily-eia"
  description         = "Daily EIA price data sync at 1 AM UTC (8 PM ET previous day)"
  schedule_expression = "cron(0 1 * * ? *)"
}

resource "aws_cloudwatch_event_target" "daily_eia_sync" {
  rule      = aws_cloudwatch_event_rule.daily_eia_sync.name
  target_id = "eia-ingestion"
  arn       = aws_lambda_function.eia_ingestion.arn
}

resource "aws_lambda_permission" "daily_eia" {
  statement_id  = "AllowEventBridgeInvokeEIA"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.eia_ingestion.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily_eia_sync.arn
}

resource "aws_cloudwatch_event_rule" "daily_glacier_signal" {
  name                = "${var.project_name}-daily-signal"
  description         = "Daily Glacier signal generation at 7 AM UTC (2 AM ET)"
  schedule_expression = "cron(0 7 * * ? *)"
}

resource "aws_cloudwatch_event_target" "daily_glacier_signal" {
  rule      = aws_cloudwatch_event_rule.daily_glacier_signal.name
  target_id = "glacier-analysis"
  arn       = aws_lambda_function.glacier_analysis.arn
}

resource "aws_lambda_permission" "daily_glacier" {
  statement_id  = "AllowEventBridgeInvokeGlacier"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.glacier_analysis.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily_glacier_signal.arn
}

resource "aws_cloudwatch_event_rule" "weekly_infrastructure" {
  name                = "${var.project_name}-weekly-infra"
  description         = "Weekly infrastructure metrics on Mondays at 3 AM UTC"
  schedule_expression = "cron(0 3 ? * MON *)"
}

# ============================================================
# Step Functions State Machine
# ============================================================

resource "aws_iam_role" "step_functions" {
  name = "${var.project_name}-sf-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = { Service = "states.amazonaws.com" }
      Action = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "step_functions" {
  name = "${var.project_name}-sf-policy"
  role = aws_iam_role.step_functions.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = ["lambda:InvokeFunction"]
      Resource = [
        aws_lambda_function.eia_ingestion.arn,
        aws_lambda_function.glacier_analysis.arn,
      ]
    }]
  })
}

resource "aws_sfn_state_machine" "glacier_pipeline" {
  name     = "${var.project_name}-pipeline"
  role_arn = aws_iam_role.step_functions.arn

  definition = jsonencode({
    Comment = "Scope.Glacier Energy Intelligence Pipeline"
    StartAt = "IngestEIA"
    States = {
      "IngestEIA" = {
        Type     = "Task"
        Resource = aws_lambda_function.eia_ingestion.arn
        Parameters = {
          "commodities.$" = "$.commodities"
          "days"          = 30
        }
        ResultPath = "$.ingestion"
        Retry = [{
          ErrorEquals     = ["States.ALL"]
          IntervalSeconds = 2
          MaxAttempts     = 3
          BackoffRate     = 2.0
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          ResultPath  = "$.error"
          Next        = "PipelineFailed"
        }]
        Next = "ComputeScores"
      }
      "ComputeScores" = {
        Type     = "Task"
        Resource = aws_lambda_function.glacier_analysis.arn
        Parameters = {
          "step"             = "compute_scores"
          "commodity_codes.$" = "$.commodity_codes"
          "utilization_pct"  = 92.0
          "inventory_days"   = 28.0
        }
        ResultPath = "$.scores"
        Retry = [{
          ErrorEquals     = ["States.ALL"]
          IntervalSeconds = 2
          MaxAttempts     = 3
          BackoffRate     = 2.0
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          ResultPath  = "$.error"
          Next        = "PipelineFailed"
        }]
        Next = "BedrockAnalysis"
      }
      "BedrockAnalysis" = {
        Type     = "Task"
        Resource = aws_lambda_function.glacier_analysis.arn
        Parameters = {
          "step"     = "bedrock_analysis"
          "signals.$" = "$.scores.body"
        }
        ResultPath = "$.analysis"
        Retry = [{
          ErrorEquals     = ["States.ALL"]
          IntervalSeconds = 2
          MaxAttempts     = 3
          BackoffRate     = 2.0
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          ResultPath  = "$.error"
          Next        = "PipelineFailed"
        }]
        Next = "WriteSignals"
      }
      "WriteSignals" = {
        Type     = "Task"
        Resource = aws_lambda_function.glacier_analysis.arn
        Parameters = {
          "step"     = "write_signals"
          "signals.$" = "$.analysis.body"
        }
        Retry = [{
          ErrorEquals     = ["States.ALL"]
          IntervalSeconds = 2
          MaxAttempts     = 3
          BackoffRate     = 2.0
        }]
        Catch = [{
          ErrorEquals = ["States.ALL"]
          ResultPath  = "$.error"
          Next        = "PipelineFailed"
        }]
        End = true
      }
      # Terminal failure state — surfaces the error details captured by the
      # Catch blocks above so a failed run is explicit rather than silent.
      "PipelineFailed" = {
        Type  = "Fail"
        Error = "GlacierPipelineError"
        Cause = "A pipeline task failed after exhausting retries; see $.error."
      }
    }
  })
}
