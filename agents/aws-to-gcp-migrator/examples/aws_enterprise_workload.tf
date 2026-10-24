# Enterprise AWS Architecture Workload (Live Case)
# E-Commerce & Financial Transaction Processing System
# Components: Multi-tier VPC, ECS Fargate Microservice, RDS Database, S3 Bucket, SQS Queue, IAM

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

# 1. Networking Layer
resource "aws_vpc" "production_vpc" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name        = "prod-fintech-vpc"
    Environment = "production"
  }
}

resource "aws_subnet" "public_subnet" {
  vpc_id                  = aws_vpc.production_vpc.id
  cidr_block              = "10.0.1.0/24"
  map_public_ip_on_launch = true

  tags = {
    Name = "prod-public-subnet"
  }
}

resource "aws_subnet" "private_subnet" {
  vpc_id                  = aws_vpc.production_vpc.id
  cidr_block              = "10.0.2.0/24"
  map_public_ip_on_launch = false

  tags = {
    Name = "prod-private-subnet"
  }
}

resource "aws_security_group" "api_firewall" {
  name        = "api-security-group"
  description = "Allow inbound HTTPS and internal API traffic"
  vpc_id      = aws_vpc.production_vpc.id

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# 2. Storage & Messaging
resource "aws_s3_bucket" "transaction_vault" {
  bucket        = "fintech-encrypted-transactions-2026"
  force_destroy = false

  tags = {
    Compliance = "PCI-DSS"
    DataClass  = "Confidential"
  }
}

resource "aws_sqs_queue" "payment_events" {
  name                      = "payment-settlement-events"
  message_retention_seconds = 1209600  # 14 days
  visibility_timeout_seconds = 600
}

# 3. IAM Execution Role
resource "aws_iam_role" "microservice_role" {
  name = "payment_processor_execution_role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })
}

# 4. Containerized Microservice (ECS Fargate)
resource "aws_ecs_task_definition" "payment_api" {
  family                   = "payment-gateway"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "1024"
  memory                   = "2048"
  execution_role_arn       = aws_iam_role.microservice_role.arn

  container_definitions = jsonencode([
    {
      name      = "payment-service"
      image     = "123456789012.dkr.ecr.us-east-1.amazonaws.com/payment:v2.4"
      essential = true
      portMappings = [
        {
          containerPort = 8080
          hostPort      = 8080
        }
      ]
    }
  ])
}

# 5. Relational Database (RDS PostgreSQL)
resource "aws_db_instance" "ledger_db" {
  identifier           = "fintech-ledger-db"
  allocated_storage    = 50
  engine               = "postgres"
  engine_version       = "15.4"
  instance_class       = "db.t3.small"
  username             = "ledgeradmin"
  password             = "super-secure-change-me"
  skip_final_snapshot  = true
}
