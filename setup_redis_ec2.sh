#!/bin/bash

echo "=================================="
echo "Redis Installation Script for EC2"
echo "=================================="
echo ""

# Detect OS
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$ID
    echo "Detected OS: $OS"
else
    echo "Cannot detect OS. Please install Redis manually."
    exit 1
fi

echo ""
echo "Step 1: Installing Redis..."
echo ""

if [ "$OS" = "amzn" ] || [ "$OS" = "centos" ] || [ "$OS" = "rhel" ]; then
    # Amazon Linux / CentOS / RHEL
    echo "Installing Redis for Amazon Linux/CentOS..."
    sudo yum update -y

    # Try amazon-linux-extras first (for Amazon Linux 2)
    if command -v amazon-linux-extras &> /dev/null; then
        sudo amazon-linux-extras install redis6 -y
    else
        # Fallback to yum
        sudo yum install redis -y
    fi

    echo ""
    echo "Step 2: Starting Redis service..."
    sudo systemctl start redis
    sudo systemctl enable redis

    echo ""
    echo "Step 3: Checking Redis status..."
    sudo systemctl status redis --no-pager

elif [ "$OS" = "ubuntu" ] || [ "$OS" = "debian" ]; then
    # Ubuntu / Debian
    echo "Installing Redis for Ubuntu/Debian..."
    sudo apt update
    sudo apt install redis-server -y

    echo ""
    echo "Step 2: Starting Redis service..."
    sudo systemctl start redis-server
    sudo systemctl enable redis-server

    echo ""
    echo "Step 3: Checking Redis status..."
    sudo systemctl status redis-server --no-pager

else
    echo "Unsupported OS: $OS"
    echo "Please install Redis manually for your operating system."
    exit 1
fi

echo ""
echo "Step 4: Testing Redis connection..."
echo ""

# Test Redis
if redis-cli ping | grep -q "PONG"; then
    echo "✅ SUCCESS! Redis is installed and running!"
    echo ""
    echo "Redis Info:"
    redis-cli info server | grep redis_version
    echo ""
else
    echo "❌ Redis is installed but not responding to ping."
    echo "Please check the service status manually."
    exit 1
fi

echo "=================================="
echo "Redis Setup Complete!"
echo "=================================="
echo ""
echo "Your Flask application should now be able to connect to Redis."
echo ""
echo "Useful Redis commands:"
echo "  - Check status: sudo systemctl status redis"
echo "  - Restart Redis: sudo systemctl restart redis"
echo "  - Stop Redis:    sudo systemctl stop redis"
echo "  - Test Redis:    redis-cli ping"
echo ""
echo "Your .env configuration should have:"
echo "  REDIS_HOST=localhost"
echo "  REDIS_PORT=6379"
echo "  REDIS_PASSWORD="
echo ""
