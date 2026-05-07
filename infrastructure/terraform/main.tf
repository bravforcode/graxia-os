terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }

  # Remote state for team collaboration
  backend "s3" {
    bucket         = "graxia-terraform-state"
    key            = "infrastructure/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "terraform-state-lock"
  }
}

# Primary region
provider "aws" {
  alias  = "primary"
  region = var.aws_primary_region
}

# Secondary region for disaster recovery
provider "aws" {
  alias  = "secondary"
  region = var.aws_secondary_region
}

variable "aws_region" {
  description = "AWS Region to deploy to"
  default     = "us-east-1"
  type        = string
}

variable "environment" {
  description = "Environment name (e.g., prod, staging)"
  default     = "prod"
  type        = string
}

# --- VPC & Networking ---
resource "aws_vpc" "brav_os_vpc" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags = {
    Name = "brav-os-vpc-${var.environment}"
  }
}

resource "aws_subnet" "public_subnet_1" {
  vpc_id                  = aws_vpc.brav_os_vpc.id
  cidr_block              = "10.0.1.0/24"
  map_public_ip_on_launch = true
  availability_zone       = "${var.aws_region}a"
}

resource "aws_subnet" "public_subnet_2" {
  vpc_id                  = aws_vpc.brav_os_vpc.id
  cidr_block              = "10.0.2.0/24"
  map_public_ip_on_launch = true
  availability_zone       = "${var.aws_region}b"
}

resource "aws_internet_gateway" "igw" {
  vpc_id = aws_vpc.brav_os_vpc.id
}

resource "aws_route_table" "public_rt" {
  vpc_id = aws_vpc.brav_os_vpc.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.igw.id
  }
}

resource "aws_route_table_association" "public_1" {
  subnet_id      = aws_subnet.public_subnet_1.id
  route_table_id = aws_route_table.public_rt.id
}

resource "aws_route_table_association" "public_2" {
  subnet_id      = aws_subnet.public_subnet_2.id
  route_table_id = aws_route_table.public_rt.id
}

# --- Security Groups ---
resource "aws_security_group" "alb_sg" {
  name        = "brav-os-alb-sg-${var.environment}"
  description = "Allow inbound HTTP/HTTPS"
  vpc_id      = aws_vpc.brav_os_vpc.id

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

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

resource "aws_security_group" "ecs_tasks_sg" {
  name        = "brav-os-ecs-tasks-sg-${var.environment}"
  description = "Allow inbound from ALB"
  vpc_id      = aws_vpc.brav_os_vpc.id

  ingress {
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb_sg.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# --- Application Load Balancer ---
resource "aws_lb" "main" {
  name               = "brav-os-alb-${var.environment}"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb_sg.id]
  subnets            = [aws_subnet.public_subnet_1.id, aws_subnet.public_subnet_2.id]
}

resource "aws_lb_target_group" "api_tg" {
  name        = "brav-os-api-tg-${var.environment}"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = aws_vpc.brav_os_vpc.id
  target_type = "ip"

  health_check {
    path                = "/health"
    healthy_threshold   = 3
    unhealthy_threshold = 3
    timeout             = 5
    interval            = 30
    matcher             = "200"
  }
}

resource "aws_lb_listener" "http_listener" {
  load_balancer_arn = aws_lb.main.arn
  port              = "80"
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api_tg.arn
  }
}

# --- ECS Cluster & Fargate Service ---
resource "aws_ecs_cluster" "main" {
  name = "brav-os-cluster-${var.environment}"
}

resource "aws_iam_role" "ecs_task_execution_role" {
  name = "brav-os-ecs-execution-role-${var.environment}"

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

resource "aws_iam_role_policy_attachment" "ecs_task_execution_role_policy" {
  role       = aws_iam_role.ecs_task_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_ecs_task_definition" "api" {
  family                   = "brav-os-api-task"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "1024" # 1 vCPU
  memory                   = "2048" # 2 GB
  execution_role_arn       = aws_iam_role.ecs_task_execution_role.arn

  container_definitions = jsonencode([
    {
      name      = "brav-os-api"
      image     = "your-registry/brav-os-api:latest" # Placeholder for actual ECR/Docker image
      essential = true
      portMappings = [
        {
          containerPort = 8000
          hostPort      = 8000
          protocol      = "tcp"
        }
      ]
      environment = [
        { name = "ENVIRONMENT", value = var.environment },
        { name = "REDIS_HOST", value = "redis" },
        { name = "QDRANT_HOST", value = "qdrant" }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = "/ecs/brav-os-api"
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "ecs"
        }
      }
    },
    {
      name      = "redis"
      image     = "redis:7-alpine"
      essential = false
      portMappings = [
        {
          containerPort = 6379
          hostPort      = 6379
          protocol      = "tcp"
        }
      ]
    },
    {
      name      = "qdrant"
      image     = "qdrant/qdrant:latest"
      essential = false
      portMappings = [
        {
          containerPort = 6333
          hostPort      = 6333
          protocol      = "tcp"
        }
      ]
    }
  ])
}

resource "aws_cloudwatch_log_group" "api_logs" {
  name              = "/ecs/brav-os-api"
  retention_in_days = 14
}

resource "aws_ecs_service" "main" {
  name            = "brav-os-service-${var.environment}"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = 2
  launch_type     = "FARGATE"

  network_configuration {
    security_groups  = [aws_security_group.ecs_tasks_sg.id]
    subnets          = [aws_subnet.public_subnet_1.id, aws_subnet.public_subnet_2.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api_tg.arn
    container_name   = "brav-os-api"
    container_port   = 8000
  }

  depends_on = [aws_lb_listener.http_listener]
}
