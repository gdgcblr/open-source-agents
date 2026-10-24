# Example AWS S3 Bucket with Versioning and Lifecycle Rules

resource "aws_s3_bucket" "logs_bucket" {
  bucket        = "audit-compliance-logs"
  force_destroy = false

  tags = {
    Department = "Security"
    Compliance = "SOC2"
  }
}

resource "aws_s3_bucket_versioning" "logs_versioning" {
  bucket = aws_s3_bucket.logs_bucket.id
  versioning_configuration {
    status = "Enabled"
  }
}
