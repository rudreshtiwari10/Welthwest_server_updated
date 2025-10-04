# Complete EC2 Deployment Guide
## From Git Pull to Running Server

---

## Prerequisites

- EC2 instance running (Amazon Linux 2 or Ubuntu)
- SSH access to EC2
- Git repository with your code
- Domain/IP address of your EC2 instance

---

## Step 1: Connect to EC2

### **Using SSH:**
```bash
# From your local machine
ssh -i "your-key.pem" ec2-user@your-ec2-public-ip

# For Ubuntu
ssh -i "your-key.pem" ubuntu@your-ec2-public-ip
```

**Example:**
```bash
ssh -i "welthwest-key.pem" ec2-user@52.23.45.67
```

---

## Step 2: Install System Dependencies

### **For Amazon Linux 2:**
```bash
# Update system
sudo yum update -y

# Install Python 3.11 (or latest available)
sudo yum install python3.11 -y
sudo yum install python3.11-pip -y

# Install Git
sudo yum install git -y

# Install development tools (needed for some Python packages)
sudo yum groupinstall "Development Tools" -y
sudo yum install python3-devel -y
```

### **For Ubuntu:**
```bash
# Update system
sudo apt update
sudo apt upgrade -y

# Install Python 3.11
sudo apt install python3.11 -y
sudo apt install python3-pip -y

# Install Git
sudo apt install git -y

# Install development tools
sudo apt install build-essential python3-dev -y
```

---

## Step 3: Clone Your Repository

### **First Time Setup:**
```bash
# Navigate to home directory
cd ~

# Clone your repository
git clone https://github.com/your-username/your-repo-name.git

# OR if using SSH
git clone git@github.com:your-username/your-repo-name.git
```

### **If Already Cloned (Update Code):**
```bash
# Navigate to your project directory
cd ~/your-repo-name/WelthWestServer2_aws

# Pull latest changes
git pull origin main

# OR if you have uncommitted changes
git stash
git pull origin main
git stash pop
```

**Example:**
```bash
cd ~/WelthWest/WelthWestServer2_aws
git pull origin main
```

---

## Step 4: Set Up Python Virtual Environment

```bash
# Navigate to your backend directory
cd ~/your-repo-name/WelthWestServer2_aws

# Create virtual environment
python3.11 -m venv venv

# Activate virtual environment
source venv/bin/activate

# You should see (venv) in your terminal prompt
```

---

## Step 5: Install Python Dependencies

```bash
# Make sure virtual environment is activated
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install all requirements
pip install -r requirements.txt

# This may take 2-5 minutes
```

**If you get errors, install missing system packages:**
```bash
# For Amazon Linux
sudo yum install gcc python3-devel libffi-devel openssl-devel -y

# For Ubuntu
sudo apt install gcc python3-dev libffi-dev libssl-dev -y

# Then retry
pip install -r requirements.txt
```

---

## Step 6: Configure Environment Variables

### **Create/Update .env file:**
```bash
# Copy example env file
cp ENV_EXAMPLE .env

# Edit .env file
nano .env
```

### **Important .env Settings:**
```env
# Flask Configuration
FLASK_DEBUG=False
PORT=8000
FRONTEND_URL=http://your-frontend-url.com

# MongoDB (your existing connection string)
MONGODB_URI=mongodb+srv://your-connection-string
DB_NAME=welthwest

# JWT Secret (CHANGE THIS!)
JWT_SECRET_KEY=your-super-secret-key-here-change-in-production

# Redis (Optional - will use in-memory if not available)
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=

# API Keys
OPENAI_API_KEY=your-openai-key
OPENROUTER_API_KEY=your-openrouter-key
CLAUDE_API_KEY=your-claude-key

# Razorpay
RAZORPAY_KEY_ID=your-razorpay-key
RAZORPAY_KEY_SECRET=your-razorpay-secret

# Email (Gmail SMTP)
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-password
MAIL_DEFAULT_SENDER=your-email@gmail.com

# Anonymous Trial Limits
ANON_TRIAL_LIMIT=10
ANON_AI_ANALYSIS_LIMIT=10
ANON_BACKTEST_LIMIT=10
ANON_CHAT_LIMIT=5
```

**Save and exit:** Press `Ctrl+X`, then `Y`, then `Enter`

---

## Step 7: Test Run (Optional but Recommended)

```bash
# Make sure virtual environment is activated
source venv/bin/activate

# Test run the server
python app.py
```

**You should see:**
```
⚠ Redis connection failed: ... Using in-memory storage as fallback.
 * Running on http://0.0.0.0:8000
```

**Press `Ctrl+C` to stop the test run.**

---

## Step 8: Set Up Production Server with Gunicorn

### **Install Gunicorn:**
```bash
pip install gunicorn
```

### **Test Gunicorn:**
```bash
gunicorn -w 4 -b 0.0.0.0:8000 app:app
```

**Press `Ctrl+C` to stop.**

---

## Step 9: Create Systemd Service (Auto-start on Boot)

### **Create service file:**
```bash
sudo nano /etc/systemd/system/welthwest.service
```

### **Add this content:**
```ini
[Unit]
Description=WelthWest Flask Application
After=network.target

[Service]
User=ec2-user
WorkingDirectory=/home/ec2-user/your-repo-name/WelthWestServer2_aws
Environment="PATH=/home/ec2-user/your-repo-name/WelthWestServer2_aws/venv/bin"
ExecStart=/home/ec2-user/your-repo-name/WelthWestServer2_aws/venv/bin/gunicorn -w 4 -b 0.0.0.0:8000 app:app
Restart=always

[Install]
WantedBy=multi-user.target
```

**For Ubuntu, change `User=ec2-user` to `User=ubuntu`**

**Update paths to match your setup!**

---

## Step 10: Start the Service

```bash
# Reload systemd to recognize new service
sudo systemctl daemon-reload

# Enable service to start on boot
sudo systemctl enable welthwest

# Start the service
sudo systemctl start welthwest

# Check status
sudo systemctl status welthwest
```

**You should see:** `Active: active (running)`

---

## Step 11: Configure Security Group (Firewall)

### **In AWS Console:**
1. Go to EC2 Dashboard
2. Select your instance
3. Click "Security" tab
4. Click on the Security Group
5. Click "Edit inbound rules"
6. Add rules:

```
Type: Custom TCP
Port: 8000
Source: 0.0.0.0/0 (or your IP for testing)
Description: Flask API

Type: HTTP
Port: 80
Source: 0.0.0.0/0
Description: HTTP

Type: HTTPS
Port: 443
Source: 0.0.0.0/0
Description: HTTPS
```

7. Save rules

---

## Step 12: Set Up Nginx (Optional but Recommended)

### **Install Nginx:**
```bash
# Amazon Linux
sudo amazon-linux-extras install nginx1 -y

# Ubuntu
sudo apt install nginx -y
```

### **Configure Nginx:**
```bash
sudo nano /etc/nginx/conf.d/welthwest.conf
```

### **Add this configuration:**
```nginx
server {
    listen 80;
    server_name your-domain.com www.your-domain.com;

    # Or use your EC2 public IP
    # server_name 52.23.45.67;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### **Start Nginx:**
```bash
# Start and enable Nginx
sudo systemctl start nginx
sudo systemctl enable nginx

# Check status
sudo systemctl status nginx
```

---

## Step 13: Verify Deployment

### **Test from EC2:**
```bash
curl http://localhost:8000/health
```

**Expected:** `{"status": "healthy"}`

### **Test from Browser:**
```
http://your-ec2-ip:8000/health
```

### **Test API endpoints:**
```bash
# Test anonymous backtesting
curl -X POST http://your-ec2-ip:8000/api/backtest/anonymous \
  -H "Content-Type: application/json" \
  -d '{"ticker":"RELIANCE","strategy":"sma_crossover","initial_capital":100000}'
```

---

## Step 14: Optional - Install Redis (Recommended)

```bash
# Run the provided setup script
cd ~/your-repo-name/WelthWestServer2_aws
chmod +x setup_redis_ec2.sh
./setup_redis_ec2.sh

# Restart your Flask service
sudo systemctl restart welthwest
```

---

## Common Commands Reference

### **Service Management:**
```bash
# Check service status
sudo systemctl status welthwest

# Start service
sudo systemctl start welthwest

# Stop service
sudo systemctl stop welthwest

# Restart service
sudo systemctl restart welthwest

# View logs
sudo journalctl -u welthwest -f

# View last 100 lines of logs
sudo journalctl -u welthwest -n 100
```

### **Update Code:**
```bash
# Navigate to project
cd ~/your-repo-name/WelthWestServer2_aws

# Pull latest changes
git pull origin main

# Activate virtual environment
source venv/bin/activate

# Install any new dependencies
pip install -r requirements.txt

# Restart service
sudo systemctl restart welthwest

# Check status
sudo systemctl status welthwest
```

### **Check Application Logs:**
```bash
# Follow logs in real-time
sudo journalctl -u welthwest -f

# View errors only
sudo journalctl -u welthwest -p err

# View logs from last hour
sudo journalctl -u welthwest --since "1 hour ago"
```

---

## Troubleshooting

### **Service won't start:**
```bash
# Check detailed logs
sudo journalctl -u welthwest -n 50

# Check if port is in use
sudo netstat -tulpn | grep 8000

# Test manually
cd ~/your-repo-name/WelthWestServer2_aws
source venv/bin/activate
python app.py
```

### **Permission errors:**
```bash
# Fix ownership
sudo chown -R ec2-user:ec2-user ~/your-repo-name

# For Ubuntu
sudo chown -R ubuntu:ubuntu ~/your-repo-name
```

### **Port already in use:**
```bash
# Find process using port 8000
sudo lsof -i :8000

# Kill the process
sudo kill -9 <PID>

# Restart service
sudo systemctl restart welthwest
```

### **Module not found errors:**
```bash
# Reinstall dependencies
cd ~/your-repo-name/WelthWestServer2_aws
source venv/bin/activate
pip install -r requirements.txt --force-reinstall
```

---

## Quick Deployment Script

**Create this file for easy deployment:**
```bash
nano ~/deploy.sh
```

**Add this content:**
```bash
#!/bin/bash

echo "=== WelthWest Deployment Script ==="
echo ""

# Navigate to project
cd ~/your-repo-name/WelthWestServer2_aws

# Pull latest code
echo "Pulling latest code..."
git pull origin main

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt --quiet

# Restart service
echo "Restarting service..."
sudo systemctl restart welthwest

# Wait a moment
sleep 2

# Check status
echo ""
echo "Service status:"
sudo systemctl status welthwest --no-pager

echo ""
echo "=== Deployment Complete ==="
echo "Check logs: sudo journalctl -u welthwest -f"
```

**Make it executable:**
```bash
chmod +x ~/deploy.sh
```

**Use it:**
```bash
~/deploy.sh
```

---

## Security Checklist

✅ Change `JWT_SECRET_KEY` in `.env` to a strong random value
✅ Set `FLASK_DEBUG=False` in production
✅ Use HTTPS (SSL certificate) for production
✅ Restrict Security Group to only necessary IPs
✅ Use strong passwords for MongoDB
✅ Enable Redis password if installing Redis
✅ Keep system and packages updated
✅ Set up monitoring and alerts

---

## Monitoring (Optional)

### **Install monitoring tools:**
```bash
# Install htop for resource monitoring
sudo yum install htop -y   # Amazon Linux
sudo apt install htop -y   # Ubuntu

# Monitor resources
htop
```

### **Set up log rotation:**
```bash
sudo nano /etc/logrotate.d/welthwest
```

```
/var/log/welthwest/*.log {
    daily
    rotate 7
    compress
    delaycompress
    notifempty
    create 0640 ec2-user ec2-user
}
```

---

## Done! 🎉

Your Flask server is now:
- ✅ Running on EC2
- ✅ Auto-starts on boot
- ✅ Handles crashes with auto-restart
- ✅ Accessible via HTTP
- ✅ Production-ready

**Access your API:**
```
http://your-ec2-ip:8000/api/endpoint
```

**Next Steps:**
1. Set up domain name (optional)
2. Install SSL certificate (Let's Encrypt)
3. Set up monitoring and alerts
4. Configure backup strategy
5. Set up CI/CD pipeline
