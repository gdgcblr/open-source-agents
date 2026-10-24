# RDS demo: Postgres major version bump (14 → 16) with parameter group family change

resource "aws_db_parameter_group" "analytics_postgres14" {
  name   = "analytics-postgres14"
  family = "postgres14"

  parameter {
    name  = "log_connections"
    value = "1"
  }
}

resource "aws_db_instance" "analytics-db" {
  identifier             = "analytics-db"
  engine                 = "postgres"
  engine_version         = "14.10"
  instance_class         = "db.r4.large"
  allocated_storage      = 100
  db_name                = "analytics"
  username               = "dbadmin"
  password               = "changeme-demo-only"
  parameter_group_name   = aws_db_parameter_group.analytics_postgres14.name
  skip_final_snapshot    = true
  publicly_accessible    = false
  vpc_security_group_ids = ["sg-analytics-demo"]
}
