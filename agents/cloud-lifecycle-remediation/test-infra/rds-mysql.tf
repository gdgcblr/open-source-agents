# RDS demo: MySQL minor engine maintenance

resource "aws_db_parameter_group" "payments_mysql80" {
  name   = "payments-mysql80"
  family = "mysql8.0"

  parameter {
    name  = "slow_query_log"
    value = "1"
  }
}

resource "aws_db_instance" "payments-ledger" {
  identifier             = "payments-ledger"
  engine                 = "mysql"
  engine_version         = "8.0.35"
  instance_class         = "db.m6g.large"
  allocated_storage      = 200
  username               = "admin"
  password               = "changeme-demo-only"
  parameter_group_name   = aws_db_parameter_group.payments_mysql80.name
  skip_final_snapshot    = true
  publicly_accessible    = false
  vpc_security_group_ids = ["sg-payments-demo"]
}
