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
            'support_email': os.environ.get('SUPPORT_EMAIL', 'support@wealthwest.com')
        }
        
        subject = "Welcome to WealthWest - Your Trading Journey Begins!"
        
        return self.send_email(user_email, subject, template, context)
    
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
                    <p>Thank you for choosing WealthWest!</p>
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
                    <p>Thank you for choosing WealthWest!</p>
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
            <title>Welcome to WealthWest</title>
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
                    <h1>Welcome to WealthWest! 🚀</h1>
                </div>
                
                <div class="content">
                    <h2>Hi {{ user_name }},</h2>
                    <p>Welcome to WealthWest! We're excited to have you on board.</p>
                    
                    <p>You can now access our powerful trading and analysis tools. Start exploring:</p>
                    <ul>
                        <li>Stock Analysis & Research</li>
                        <li>AI-Powered Trading Insights</li>
                        <li>Backtesting Strategies</li>
                        <li>Real-time Market Data</li>
                    </ul>
                    
                    <p>If you need any help getting started, don't hesitate to reach out to our support team at {{ support_email }}.</p>
                </div>
                
                <div class="footer">
                    <p>Happy Trading!</p>
                    <p>The WealthWest Team</p>
                </div>
            </div>
        </body>
        </html>
        """

# Global email service instance
email_service = EmailService()