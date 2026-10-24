from migrator.parser import TerraformParser, AWSResource


def test_parse_simple_s3():
    content = '''
resource "aws_s3_bucket" "test_bucket" {
  bucket = "my-test-bucket-123"
  force_destroy = true
}
'''
    parser = TerraformParser()
    resources = parser.parse_content(content)
    assert len(resources) == 1
    assert resources[0].resource_type == "aws_s3_bucket"
    assert resources[0].resource_name == "test_bucket"
    assert resources[0].attributes.get("bucket") == "my-test-bucket-123"


def test_parse_multiple_resources():
    content = '''
resource "aws_s3_bucket" "bucket1" {
  bucket = "b1"
}

resource "aws_sqs_queue" "queue1" {
  name = "q1"
}

resource "aws_lambda_function" "func1" {
  function_name = "f1"
}
'''
    parser = TerraformParser()
    resources = parser.parse_content(content)
    assert len(resources) == 3
    types = [r.resource_type for r in resources]
    assert "aws_s3_bucket" in types
    assert "aws_sqs_queue" in types
    assert "aws_lambda_function" in types
