# Example AWS Containerized Web Application
# Components: ECS Fargate Task Definition & Service, RDS PostgreSQL, S3, IAM

resource "aws_s3_bucket" "assets_bucket" {
  bucket = "prod-app-static-assets"
}

resource "aws_iam_role" "ecs_execution_role" {
  name = "ecs_task_execution_role"

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

resource "aws_ecs_task_definition" "web_app" {
  family                   = "web-api"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.ecs_execution_role.arn

  container_definitions = jsonencode([
    {
      name      = "api-server"
      image     = "123456789012.dkr.ecr.us-east-1.amazonaws.com/api:latest"
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

resource "aws_db_instance" "app_db" {
  identifier           = "app-postgres-db"
  allocated_storage    = 20
  engine               = "postgres"
  engine_version       = "15.4"
  instance_class       = "db.t3.micro"
  username             = "dbadmin"
  password             = "sensitive-change-me"
  parameter_group_name = "default.postgres15"
  skip_final_snapshot  = true
}
