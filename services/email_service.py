import os
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from flask import current_app
from flask_mail import Mail, Message
from jinja2 import Template

logger = logging.getLogger(__name__)

class EmailService:
    def __init__(self, app=None):
        self.mail = None
        if app:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize Flask-Mail with the app"""
        app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
        app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', '587'))
        app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'true').lower() == 'true'
        app.config['MAIL_USE_SSL'] = os.environ.get('MAIL_USE_SSL', 'false').lower() == 'true'
        app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
        app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
        app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER', 
                                                          os.environ.get('MAIL_USERNAME'))
        
        self.mail = Mail(app)
        
    def send_email(self, 
                   to: str, 
                   subject: str, 
                   template: str, 
                   context: Dict[str, Any] = None,
                   attachments: List[Dict[str, Any]] = None) -> bool:
        """
        Send an email using template
        
        Args:
            to: Recipient email address
            subject: Email subject
            template: HTML template string
            context: Variables to pass to template
            attachments: List of attachments with 'filename', 'content_type', 'data' keys
        
        Returns:
            bool: True if email sent successfully, False otherwise
        """
        try:
            if not self.mail:
                logger.error("Email service not initialized")
                return False
                
            if not context:
                context = {}
                
            # Render template
            template_obj = Template(template)
            html_content = template_obj.render(**context)
            
            # Create message
            msg = Message(
                subject=subject,
                recipients=[to],
                html=html_content
            )
            
            # Add attachments if provided
            if attachments:
                for attachment in attachments:
                    msg.attach(
                        filename=attachment.get('filename'),
                        content_type=attachment.get('content_type'),
                        data=attachment.get('data')
                    )
            
            # Send email
            self.mail.send(msg)
            logger.info(f"Email sent successfully to {to}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email to {to}: {str(e)}")
            return False
    
    def send_payment_confirmation_email(self, 
                                      user_email: str, 
                                      user_name: str,
                                      plan_details: Dict[str, Any],
                                      payment_details: Dict[str, Any]) -> bool:
        """Send payment confirmation email with invoice"""
        
        # Generate invoice data
        invoice_data = self._generate_invoice_data(user_name, plan_details, payment_details)
        
        template = self._get_payment_confirmation_template()
        
        context = {
            'user_name': user_name,
            'plan_name': plan_details.get('name', 'Unknown Plan'),
            'plan_price': plan_details.get('price', 0),
            'billing_cycle': plan_details.get('billing_cycle', 'monthly'),
            'payment_id': payment_details.get('razorpay_payment_id'),
            'order_id': payment_details.get('razorpay_order_id'),
            'payment_date': datetime.now().strftime('%B %d, %Y'),
            'invoice_data': invoice_data,
            'features': plan_details.get('features', [])
        }
        
        subject = f"Payment Confirmation - {plan_details.get('name', 'Subscription')} Plan"
        
        return self.send_email(user_email, subject, template, context)
    
    def send_subscription_upgrade_email(self, 
                                      user_email: str,
                                      user_name: str,
                                      old_plan: str,
                                      new_plan: str,
                                      upgrade_date: str) -> bool:
        """Send subscription upgrade notification email"""
        
        template = self._get_subscription_upgrade_template()
        
        context = {
            'user_name': user_name,
            'old_plan': old_plan,
            'new_plan': new_plan,
            'upgrade_date': upgrade_date
        }
        
        subject = f"Subscription Upgraded to {new_plan} Plan"
        
        return self.send_email(user_email, subject, template, context)
    
    def send_welcome_email(self, user_email: str, user_name: str) -> bool:
        """Send welcome email to new users"""
        
        template = self._get_welcome_template()
        
        context = {
            'user_name': user_name,
            'COMPANY_EMAIL': os.environ.get('COMPANY_EMAIL', 'contact@WelthWest.com')
        }
        
        subject = "Welcome to WelthWest - Your Trading Journey Begins!"
        
        return self.send_email(user_email, subject, template, context)
    
    def send_password_reset_otp(self, user_email: str, user_name: str, otp: str) -> bool:
        """Send password reset OTP email"""
        
        template = self._get_password_reset_template()
        
        context = {
            'user_name': user_name,
            'otp': otp,
            'expiry_minutes': 15
        }
        
        subject = "Password Reset OTP - WelthWest"
        
        return self.send_email(user_email, subject, template, context)
    
    def send_registration_otp(self, user_email: str, otp: str) -> bool:
        """Send registration OTP email for email verification"""
        
        template = self._get_registration_otp_template()
        
        context = {
            'user_email': user_email,
            'otp': otp,
            'expiry_minutes': 15
        }
        
        subject = "Email Verification OTP - WelthWest"
        
        return self.send_email(user_email, subject, template, context)
    
    def send_new_user_notification_to_company(self, user_email: str, user_name: str, registration_date: str, registration_method: str = "Email & Password") -> bool:
        """Send new user registration notification to company"""
        
        template = self._get_new_user_notification_template()
        
        context = {
            'user_name': user_name,
            'user_email': user_email,
            'registration_date': registration_date,
            'registration_method': registration_method,
            'total_users_count': "N/A"  # Can be updated to show actual count if needed
        }
        
        subject = f"New User Registration - {user_name}"
        
        company_email = os.environ.get('COMPANY_EMAIL', os.environ.get('COMPANY_EMAIL', 'contact@welthwest.com'))
        return self.send_email(company_email, subject, template, context)
    
    def _generate_invoice_data(self, user_name: str, plan_details: Dict[str, Any], payment_details: Dict[str, Any]) -> Dict[str, Any]:
        """Generate invoice data for email"""
        
        return {
            'invoice_number': f"INV-{payment_details.get('razorpay_order_id', 'UNKNOWN')}",
            'invoice_date': datetime.now().strftime('%B %d, %Y'),
            'customer_name': user_name,
            'plan_name': plan_details.get('name', 'Unknown Plan'),
            'amount': plan_details.get('amount', 0) / 100,  # Convert from paise to rupees
            'currency': 'INR',
            'payment_method': 'Razorpay',
            'transaction_id': payment_details.get('razorpay_payment_id')
        }
    
    def _get_payment_confirmation_template(self) -> str:
        """Get payment confirmation email template"""
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Payment Confirmation</title>
            <style>
                body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
                .container { max-width: 600px; margin: 0 auto; padding: 20px; }
                .header { background: #4F46E5; color: white; padding: 20px; text-align: center; }
                .content { padding: 20px; background: #f9f9f9; }
                .invoice { background: white; padding: 20px; margin: 20px 0; border: 1px solid #ddd; }
                .features { background: white; padding: 15px; margin: 10px 0; }
                .feature-item { padding: 5px 0; }
                .footer { background: #333; color: white; padding: 20px; text-align: center; }
                .success { color: #10B981; font-weight: bold; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Payment Successful!</h1>
                    <p class="success">Thank you for upgrading to {{ plan_name }}</p>
                </div>
                
                <div class="content">
                    <h2>Hi {{ user_name }},</h2>
                    <p>We've successfully processed your payment for the <strong>{{ plan_name }}</strong> plan. Your subscription is now active!</p>
                    
                    <div class="invoice">
                        <h3>Invoice Details</h3>
                        <p><strong>Invoice Number:</strong> {{ invoice_data.invoice_number }}</p>
                        <p><strong>Date:</strong> {{ invoice_data.invoice_date }}</p>
                        <p><strong>Plan:</strong> {{ plan_name }}</p>
                        <p><strong>Amount:</strong> ₹{{ invoice_data.amount }} {{ invoice_data.currency }}</p>
                        <p><strong>Billing Cycle:</strong> {{ billing_cycle|title }}</p>
                        <p><strong>Payment ID:</strong> {{ payment_id }}</p>
                        <p><strong>Order ID:</strong> {{ order_id }}</p>
                    </div>
                    
                    <div class="features">
                        <h3>Your Plan Features:</h3>
                        {% for feature in features %}
                        <div class="feature-item">✅ {{ feature }}</div>
                        {% endfor %}
                    </div>
                    
                    <p>You can now access all the premium features of your {{ plan_name }} plan. Log in to your dashboard to get started!</p>
                    
                    <p>If you have any questions, feel free to contact our support team.</p>
                </div>
                
                <div class="footer">
                    <p>Thank you for choosing WelthWest!</p>
                    <p>Happy Trading! 📈</p>
                </div>
            </div>
        </body>
        </html>
        """
    
    def _get_subscription_upgrade_template(self) -> str:
        """Get subscription upgrade email template"""
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Subscription Upgraded</title>
            <style>
                body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
                .container { max-width: 600px; margin: 0 auto; padding: 20px; }
                .header { background: #10B981; color: white; padding: 20px; text-align: center; }
                .content { padding: 20px; background: #f9f9f9; }
                .upgrade-info { background: white; padding: 20px; margin: 20px 0; border: 1px solid #ddd; }
                .footer { background: #333; color: white; padding: 20px; text-align: center; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Subscription Upgraded! 🎉</h1>
                </div>
                
                <div class="content">
                    <h2>Hi {{ user_name }},</h2>
                    <p>Great news! Your subscription has been successfully upgraded.</p>
                    
                    <div class="upgrade-info">
                        <h3>Upgrade Details</h3>
                        <p><strong>Previous Plan:</strong> {{ old_plan }}</p>
                        <p><strong>New Plan:</strong> {{ new_plan }}</p>
                        <p><strong>Upgrade Date:</strong> {{ upgrade_date }}</p>
                    </div>
                    
                    <p>You now have access to all the enhanced features of your new plan. Log in to explore the upgraded capabilities!</p>
                </div>
                
                <div class="footer">
                    <p>Thank you for choosing WelthWest!</p>
                </div>
            </div>
        </body>
        </html>
        """
    
    def _get_welcome_template(self) -> str:
        """Get welcome email template"""
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Welcome to WelthWest</title>
            <style>
                body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
                .container { max-width: 600px; margin: 0 auto; padding: 20px; }
                .header { background: #4F46E5; color: white; padding: 20px; text-align: center; }
                .content { padding: 20px; background: #f9f9f9; }
                .footer { background: #333; color: white; padding: 20px; text-align: center; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Welcome to WelthWest! 🚀</h1>
                </div>
                
                <div class="content">
                    <h2>Hi {{ user_name }},</h2>
                    <p>Welcome to WelthWest! We're excited to have you on board.</p>
                    
                    <p>You can now access our powerful trading and analysis tools. Start exploring:</p>
                    <ul>
                        <li>Stock Analysis & Research</li>
                        <li>AI-Powered Trading Insights</li>
                        <li>Backtesting Strategies</li>
                        <li>Real-time Market Data</li>
                    </ul>
                    
                    <p>If you need any help getting started, don't hesitate to reach out to our support team at {{ COMPANY_EMAIL }}.</p>
                </div>
                
                <div class="footer">
                    <p>Happy Trading!</p>
                    <p>The WelthWest Team</p>
                </div>
            </div>
        </body>
        </html>
        """
    
    def _get_password_reset_template(self) -> str:
        """Get password reset OTP email template"""
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Password Reset OTP</title>
            <style>
                body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
                .container { max-width: 600px; margin: 0 auto; padding: 20px; }
                .header { background: #EF4444; color: white; padding: 20px; text-align: center; }
                .content { padding: 20px; background: #f9f9f9; }
                .otp-box { background: white; padding: 20px; margin: 20px 0; border: 2px solid #EF4444; text-align: center; border-radius: 8px; }
                .otp-code { font-size: 32px; font-weight: bold; color: #EF4444; letter-spacing: 8px; margin: 20px 0; }
                .warning { background: #FEF2F2; border: 1px solid #FECACA; padding: 15px; border-radius: 6px; margin: 15px 0; }
                .footer { background: #333; color: white; padding: 20px; text-align: center; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🔒 Password Reset Request</h1>
                </div>
                
                <div class="content">
                    <h2>Hi {{ user_name }},</h2>
                    <p>We received a request to reset your password for your WelthWest account.</p>
                    
                    <div class="otp-box">
                        <h3>Your OTP Code:</h3>
                        <div class="otp-code">{{ otp }}</div>
                        <p><strong>This code expires in {{ expiry_minutes }} minutes.</strong></p>
                    </div>
                    
                    <p>Enter this code in the password reset form to continue with resetting your password.</p>
                    
                    <div class="warning">
                        <p><strong>⚠️ Security Notice:</strong></p>
                        <ul>
                            <li>If you didn't request this password reset, please ignore this email</li>
                            <li>Never share this OTP with anyone</li>
                            <li>This code will expire automatically after {{ expiry_minutes }} minutes</li>
                        </ul>
                    </div>
                    
                    <p>If you're having trouble, contact our support team.</p>
                </div>
                
                <div class="footer">
                    <p>Stay secure!</p>
                    <p>The WelthWest Team</p>
                </div>
            </div>
        </body>
        </html>
        """
    
    def _get_registration_otp_template(self) -> str:
        """Get registration OTP email template"""
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Email Verification OTP</title>
            <style>
                body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
                .container { max-width: 600px; margin: 0 auto; padding: 20px; }
                .header { background: #4F46E5; color: white; padding: 20px; text-align: center; }
                .content { padding: 20px; background: #f9f9f9; }
                .otp-box { background: white; padding: 20px; margin: 20px 0; border: 2px solid #4F46E5; text-align: center; border-radius: 8px; }
                .otp-code { font-size: 32px; font-weight: bold; color: #4F46E5; letter-spacing: 8px; margin: 20px 0; }
                .info { background: #F0F9FF; border: 1px solid #BAE6FD; padding: 15px; border-radius: 6px; margin: 15px 0; }
                .footer { background: #333; color: white; padding: 20px; text-align: center; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🎉 Welcome to WelthWest!</h1>
                    <p>Verify your email to get started</p>
                </div>
                
                <div class="content">
                    <h2>Email Verification Required</h2>
                    <p>Thank you for registering with WelthWest! To complete your account setup, please verify your email address.</p>
                    
                    <div class="otp-box">
                        <h3>Your Verification Code:</h3>
                        <div class="otp-code">{{ otp }}</div>
                        <p><strong>This code expires in {{ expiry_minutes }} minutes.</strong></p>
                    </div>
                    
                    <p>Enter this code in the verification form to activate your account and start your trading journey!</p>
                    
                    <div class="info">
                        <p><strong>ℹ️ What's next?</strong></p>
                        <ul>
                            <li>Enter the verification code above</li>
                            <li>Complete your profile setup</li>
                            <li>Start exploring our powerful trading tools</li>
                            <li>Join thousands of successful traders</li>
                        </ul>
                    </div>
                    
                    <p>If you didn't create this account, you can safely ignore this email.</p>
                </div>
                
                <div class="footer">
                    <p>Welcome aboard! 🚀</p>
                    <p>The WelthWest Team</p>
                </div>
            </div>
        </body>
        </html>
        """
    
    def _get_new_user_notification_template(self) -> str:
        """Get new user registration notification email template for company"""
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>New User Registration Notification</title>
            <style>
                body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
                .container { max-width: 600px; margin: 0 auto; padding: 20px; }
                .header { background: #10B981; color: white; padding: 20px; text-align: center; }
                .content { padding: 20px; background: #f9f9f9; }
                .user-info { background: white; padding: 20px; margin: 20px 0; border: 1px solid #ddd; border-radius: 8px; }
                .stats { background: #F0F9FF; border: 1px solid #BAE6FD; padding: 15px; border-radius: 6px; margin: 15px 0; }
                .footer { background: #333; color: white; padding: 20px; text-align: center; }
                .highlight { color: #10B981; font-weight: bold; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🎉 New User Registration!</h1>
                    <p>A new user has joined WelthWest</p>
                </div>
                
                <div class="content">
                    <h2>Registration Details</h2>
                    <p>We have a new user registration on the platform!</p>
                    
                    <div class="user-info">
                        <h3>User Information</h3>
                        <p><strong>Name:</strong> {{ user_name }}</p>
                        <p><strong>Email:</strong> {{ user_email }}</p>
                        <p><strong>Registration Date:</strong> {{ registration_date }}</p>
                        <p><strong>Registration Method:</strong> {{ registration_method }}</p>
                    </div>
                    
                    <div class="stats">
                        <h3>📊 Platform Statistics</h3>
                        <p><strong>Total Registered Users:</strong> <span class="highlight">{{ total_users_count }}</span></p>
                        <p><em>Note: This count can be updated to show actual statistics</em></p>
                    </div>
                    
                    <p>The user has completed the email verification process and has been successfully registered with a free subscription plan.</p>
                    
                    <h3>Next Steps:</h3>
                    <ul>
                        <li>User will receive a welcome email with platform details</li>
                        <li>Free subscription has been initialized</li>
                        <li>User can now access the platform features</li>
                        <li>Monitor user engagement and onboarding progress</li>
                    </ul>
                </div>
                
                <div class="footer">
                    <p>WelthWest Admin Notification System</p>
                    <p>Growing stronger every day! 📈</p>
                </div>
            </div>
        </body>
        </html>
        """

# Global email service instance
email_service = EmailService()