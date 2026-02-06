"""
Notification Service
Central service for managing user notifications
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime
from models.notification import Notification
from services.user_service import get_db_connection

logger = logging.getLogger(__name__)

class NotificationService:
    """Service for creating and managing notifications"""

    def __init__(self):
        self.db = get_db_connection()
        self.notification_model = Notification(self.db)

    # Notification Type Constants
    TYPE_LOGIN = 'login'
    TYPE_LOGOUT = 'logout'
    TYPE_PASSWORD_CHANGE = 'password_change'
    TYPE_PAYMENT_SUCCESS = 'payment_success'
    TYPE_PAYMENT_FAILED = 'payment_failed'
    TYPE_SUBSCRIPTION_UPGRADE = 'subscription_upgrade'
    TYPE_SUBSCRIPTION_DOWNGRADE = 'subscription_downgrade'
    TYPE_SUBSCRIPTION_EXPIRY = 'subscription_expiry'
    TYPE_USAGE_LIMIT = 'usage_limit'
    TYPE_SYSTEM = 'system'
    TYPE_INFO = 'info'

    def create_notification(
        self,
        user_id: str,
        notification_type: str,
        title: str,
        message: str,
        action_url: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create a notification for a user"""
        try:
            notification_data = {
                'user_id': user_id,
                'type': notification_type,
                'title': title,
                'message': message,
                'action_url': action_url,
                'metadata': metadata or {}
            }

            notification = self.notification_model.create(notification_data)

            # Convert ObjectId to string for JSON serialization
            if '_id' in notification:
                notification['_id'] = str(notification['_id'])

            logger.info(f"Created notification for user {user_id}: {notification_type}")
            return notification

        except Exception as e:
            logger.error(f"Error creating notification: {str(e)}")
            return {}

    # Convenience methods for common notification types
    def notify_login(self, user_id: str, metadata: Optional[Dict] = None) -> Dict:
        """Create login notification"""
        return self.create_notification(
            user_id=user_id,
            notification_type=self.TYPE_LOGIN,
            title='Welcome back!',
            message=f'You logged in successfully at {datetime.utcnow().strftime("%I:%M %p")}',
            metadata=metadata
        )

    def notify_logout(self, user_id: str) -> Dict:
        """Create logout notification"""
        return self.create_notification(
            user_id=user_id,
            notification_type=self.TYPE_LOGOUT,
            title='Logged out',
            message='You have been logged out successfully',
        )

    def notify_password_change(self, user_id: str, success: bool = True) -> Dict:
        """Create password change notification"""
        if success:
            return self.create_notification(
                user_id=user_id,
                notification_type=self.TYPE_PASSWORD_CHANGE,
                title='Password Changed',
                message='Your password has been changed successfully',
                action_url='/profile'
            )
        else:
            return self.create_notification(
                user_id=user_id,
                notification_type=self.TYPE_PASSWORD_CHANGE,
                title='Password Change Failed',
                message='Failed to change your password. Please try again.',
                action_url='/profile'
            )

    def notify_payment_success(
        self,
        user_id: str,
        amount: float,
        plan_name: str,
        transaction_id: str
    ) -> Dict:
        """Create payment success notification"""
        return self.create_notification(
            user_id=user_id,
            notification_type=self.TYPE_PAYMENT_SUCCESS,
            title='Payment Successful',
            message=f'Your payment of ₹{amount:.2f} for {plan_name} plan was successful',
            action_url='/profile',
            metadata={
                'amount': amount,
                'plan_name': plan_name,
                'transaction_id': transaction_id
            }
        )

    def notify_payment_failed(
        self,
        user_id: str,
        amount: float,
        plan_name: str,
        reason: str = 'Unknown error'
    ) -> Dict:
        """Create payment failure notification"""
        return self.create_notification(
            user_id=user_id,
            notification_type=self.TYPE_PAYMENT_FAILED,
            title='Payment Failed',
            message=f'Your payment of ₹{amount:.2f} for {plan_name} plan failed. Reason: {reason}',
            action_url='/premium',
            metadata={
                'amount': amount,
                'plan_name': plan_name,
                'reason': reason
            }
        )

    def notify_subscription_upgrade(
        self,
        user_id: str,
        from_tier: str,
        to_tier: str
    ) -> Dict:
        """Create subscription upgrade notification"""
        return self.create_notification(
            user_id=user_id,
            notification_type=self.TYPE_SUBSCRIPTION_UPGRADE,
            title='Plan Upgraded!',
            message=f'Your subscription has been upgraded from {from_tier} to {to_tier}',
            action_url='/profile',
            metadata={
                'from_tier': from_tier,
                'to_tier': to_tier
            }
        )

    def notify_subscription_downgrade(
        self,
        user_id: str,
        from_tier: str,
        to_tier: str
    ) -> Dict:
        """Create subscription downgrade notification"""
        return self.create_notification(
            user_id=user_id,
            notification_type=self.TYPE_SUBSCRIPTION_DOWNGRADE,
            title='Plan Changed',
            message=f'Your subscription has been changed from {from_tier} to {to_tier}',
            action_url='/profile',
            metadata={
                'from_tier': from_tier,
                'to_tier': to_tier
            }
        )

    def notify_subscription_expiry(
        self,
        user_id: str,
        tier: str,
        days_until_expiry: int
    ) -> Dict:
        """Create subscription expiry warning notification"""
        return self.create_notification(
            user_id=user_id,
            notification_type=self.TYPE_SUBSCRIPTION_EXPIRY,
            title='Subscription Expiring Soon',
            message=f'Your {tier} plan expires in {days_until_expiry} days',
            action_url='/premium',
            metadata={
                'tier': tier,
                'days_until_expiry': days_until_expiry
            }
        )

    def notify_usage_limit(
        self,
        user_id: str,
        remaining: int,
        limit: int,
        feature_name: str = 'AI queries'
    ) -> Dict:
        """Create usage limit warning notification"""
        return self.create_notification(
            user_id=user_id,
            notification_type=self.TYPE_USAGE_LIMIT,
            title='Usage Limit Warning',
            message=f'You have {remaining} {feature_name} remaining out of {limit}',
            action_url='/premium',
            metadata={
                'remaining': remaining,
                'limit': limit,
                'feature_name': feature_name
            }
        )

    def notify_system(
        self,
        user_id: str,
        title: str,
        message: str,
        action_url: Optional[str] = None
    ) -> Dict:
        """Create system notification"""
        return self.create_notification(
            user_id=user_id,
            notification_type=self.TYPE_SYSTEM,
            title=title,
            message=message,
            action_url=action_url
        )

    def get_user_notifications(
        self,
        user_id: str,
        page: int = 1,
        limit: int = 50,
        unread_only: bool = False
    ) -> Dict:
        """Get notifications for a user"""
        result = self.notification_model.get_user_notifications(
            user_id=user_id,
            page=page,
            limit=limit,
            unread_only=unread_only
        )

        # Convert ObjectIds to strings
        for notification in result['notifications']:
            if '_id' in notification:
                notification['_id'] = str(notification['_id'])

        return result

    def get_unread_count(self, user_id: str) -> int:
        """Get count of unread notifications"""
        return self.notification_model.get_unread_count(user_id)

    def mark_as_read(self, notification_id: str, user_id: str) -> bool:
        """Mark notification as read"""
        return self.notification_model.mark_as_read(notification_id, user_id)

    def mark_all_as_read(self, user_id: str) -> int:
        """Mark all notifications as read"""
        return self.notification_model.mark_all_as_read(user_id)

    def delete_notification(self, notification_id: str, user_id: str) -> bool:
        """Delete a notification"""
        return self.notification_model.delete_notification(notification_id, user_id)

    def clear_all_notifications(self, user_id: str) -> int:
        """Delete all notifications for a user"""
        return self.notification_model.delete_all_user_notifications(user_id)


# Singleton instance
notification_service = NotificationService()
