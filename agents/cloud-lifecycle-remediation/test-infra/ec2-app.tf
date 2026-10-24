# EC2 instance type deprecation demo (m5 → m7i)

resource "aws_instance" "api-server" {
  ami           = "ami-0c55b159cbfafe1f0"
  instance_type = "m5.large"

  tags = {
    Name = "api-server"
  }
}
