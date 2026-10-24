# Example AWS Serverless Architecture
# Components: S3 Bucket, SQS Queue, Lambda Function, and IAM Execution Role

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = "us-east-1"
}

# 1. Ingestion S3 Bucket
resource "aws_s3_bucket" "data_ingest" {
  bucket        = "company-raw-data-ingest"
  force_destroy = true

  tags = {
    Environment = "production"
    Application = "data-pipeline"
  }
}

resource "aws_s3_bucket_versioning" "data_ingest_versioning" {
  bucket = aws_s3_bucket.data_ingest.id
  versioning_configuration {
    status = "Enabled"
  }
}

# 2. Event SQS Queue
resource "aws_sqs_queue" "task_queue" {
  name                      = "data-processing-tasks"
  message_retention_seconds = 86400
  visibility_timeout_seconds = 300
}

# 3. IAM Role for Lambda Execution
resource "aws_iam_role" "lambda_exec_role" {
  name = "data_processor_exec_role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

# 4. Processing Lambda Function
resource "aws_lambda_function" "processor" {
  function_name = "data-processor-func"
  role          = aws_iam_role.lambda_exec_role.arn
  handler       = "index.handler"
  runtime       = "python3.11"
  memory_size   = 512
  timeout       = 60

  environment {
    variables = {
      QUEUE_URL   = aws_sqs_queue.task_queue.id
      BUCKET_NAME = aws_s3_bucket.data_ingest.bucket
    }
  }
}
