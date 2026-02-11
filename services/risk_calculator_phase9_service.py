"""
Risk Calculator Phase 9: Broker API Integration Service (Read-Only)

Provides OAuth integration with brokers, position and trade syncing,
with encrypted token storage for security.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from bson import ObjectId
import os
from pymongo import MongoClient
from cryptography.fernet import Fernet
import logging
import requests
import base64
import hashlib

logger = logging.getLogger(__name__)


class RiskCalculatorPhase9Service:
    """Service for broker API integration (read-only)"""

    # Supported brokers
    SUPPORTED_BROKERS = ['zerodha', 'upstox', 'angel', 'fyers']

    def __init__(self):
        mongo_uri = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/')
        db_name = os.getenv('DB_NAME', 'welthwest')
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self.connections_collection = self.db['risk_calculator_broker_connections']
        self.sync_log_collection = self.db['risk_calculator_broker_sync_log']
        self.portfolio_collection = self.db['risk_calculator_portfolio']
        self.trades_collection = self.db['risk_calculator_trades']

        # Initialize encryption
        encryption_key = os.getenv('BROKER_TOKEN_ENCRYPTION_KEY')
        if not encryption_key:
            # Generate a key if not provided (for development)
            # In production, this should always be set in environment
            encryption_key = Fernet.generate_key().decode()
            logger.warning("No encryption key found. Generated temporary key for development.")

        self.cipher = Fernet(encryption_key.encode())

    def initiate_broker_oauth(self, user_id: str, broker: str) -> Dict[str, Any]:
        """
        Initiate OAuth flow for broker connection

        Args:
            user_id: User's ID
            broker: Broker name (zerodha, upstox, etc.)

        Returns:
            OAuth URL and state for redirection
        """
        try:
            if broker.lower() not in self.SUPPORTED_BROKERS:
                raise ValueError(f"Broker '{broker}' not supported. Supported brokers: {', '.join(self.SUPPORTED_BROKERS)}")

            # Get broker OAuth configuration
            broker_config = self._get_broker_config(broker.lower())

            # Generate state for CSRF protection
            state = self._generate_state(user_id, broker.lower())

            # Build OAuth URL
            oauth_url = f"{broker_config['auth_url']}?" \
                       f"client_id={broker_config['client_id']}&" \
                       f"redirect_uri={broker_config['redirect_uri']}&" \
                       f"response_type=code&" \
                       f"state={state}&" \
                       f"scope={broker_config['scope']}"

            return {
                'oauth_url': oauth_url,
                'state': state,
                'broker': broker.lower()
            }

        except Exception as e:
            raise Exception(f"Error initiating OAuth: {str(e)}")

    def complete_broker_oauth(
        self,
        user_id: str,
        broker: str,
        code: str,
        state: str
    ) -> Dict[str, Any]:
        """
        Complete OAuth flow and store encrypted tokens

        Args:
            user_id: User's ID
            broker: Broker name
            code: Authorization code from OAuth callback
            state: State parameter for validation

        Returns:
            Connection status
        """
        try:
            # Validate state
            if not self._validate_state(state, user_id, broker.lower()):
                raise ValueError("Invalid state parameter - possible CSRF attack")

            # Get broker configuration
            broker_config = self._get_broker_config(broker.lower())

            # Exchange code for tokens
            token_response = self._exchange_code_for_token(broker.lower(), code, broker_config)

            # Encrypt access token
            encrypted_access_token = self._encrypt_token(token_response['access_token'])
            encrypted_refresh_token = None

            if 'refresh_token' in token_response:
                encrypted_refresh_token = self._encrypt_token(token_response['refresh_token'])

            # Store connection
            connection = {
                'user_id': user_id,
                'broker': broker.lower(),
                'encrypted_access_token': encrypted_access_token,
                'encrypted_refresh_token': encrypted_refresh_token,
                'token_expiry': datetime.now() + timedelta(seconds=token_response.get('expires_in', 86400)),
                'scopes': broker_config['scope'].split(','),
                'status': 'active',
                'connected_at': datetime.now(),
                'last_synced': None,
                'metadata': {
                    'broker_user_id': token_response.get('user_id'),
                    'broker_user_name': token_response.get('user_name')
                }
            }

            # Upsert connection
            self.connections_collection.update_one(
                {'user_id': user_id, 'broker': broker.lower()},
                {'$set': connection},
                upsert=True
            )

            return {
                'success': True,
                'broker': broker.lower(),
                'status': 'connected',
                'connected_at': connection['connected_at']
            }

        except Exception as e:
            raise Exception(f"Error completing OAuth: {str(e)}")

    def disconnect_broker(self, user_id: str, broker: str) -> Dict[str, Any]:
        """
        Disconnect broker and remove stored tokens

        Args:
            user_id: User's ID
            broker: Broker name

        Returns:
            Disconnection status
        """
        try:
            # Delete connection
            result = self.connections_collection.delete_one({
                'user_id': user_id,
                'broker': broker.lower()
            })

            if result.deleted_count == 0:
                raise ValueError(f"No active connection found for {broker}")

            return {
                'success': True,
                'broker': broker.lower(),
                'status': 'disconnected',
                'message': f'Successfully disconnected from {broker}'
            }

        except Exception as e:
            raise Exception(f"Error disconnecting broker: {str(e)}")

    def sync_broker_positions(self, user_id: str, broker: str) -> Dict[str, Any]:
        """
        Sync positions from broker to Phase 4 portfolio (read-only)

        Args:
            user_id: User's ID
            broker: Broker name

        Returns:
            Sync results
        """
        try:
            # Get connection
            connection = self._get_active_connection(user_id, broker.lower())

            # Decrypt token
            access_token = self._decrypt_token(connection['encrypted_access_token'])

            # Fetch positions from broker
            positions = self._call_broker_api(broker.lower(), 'positions', access_token)

            # Transform and sync to portfolio
            synced_positions = []
            for position in positions:
                # Transform broker position to our format
                transformed_position = self._transform_broker_position(broker.lower(), position)

                # Add/update in portfolio (using Phase 4 service)
                from services.risk_calculator_phase4_service import risk_phase4_service

                try:
                    risk_phase4_service.add_position(user_id, transformed_position)
                    synced_positions.append(transformed_position['symbol'])
                except Exception as e:
                    logger.error(f"Error syncing position {transformed_position.get('symbol')}: {str(e)}")

            # Update last sync time
            self.connections_collection.update_one(
                {'user_id': user_id, 'broker': broker.lower()},
                {'$set': {'last_synced': datetime.now()}}
            )

            # Log sync
            self._log_sync(user_id, broker.lower(), 'positions', len(synced_positions), True)

            return {
                'success': True,
                'broker': broker.lower(),
                'synced_positions': synced_positions,
                'count': len(synced_positions),
                'synced_at': datetime.now()
            }

        except Exception as e:
            self._log_sync(user_id, broker.lower(), 'positions', 0, False, str(e))
            raise Exception(f"Error syncing positions: {str(e)}")

    def sync_broker_trades(
        self,
        user_id: str,
        broker: str,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Sync trades from broker to Phase 5 journal (read-only)

        Args:
            user_id: User's ID
            broker: Broker name
            from_date: Start date for trade history
            to_date: End date for trade history

        Returns:
            Sync results
        """
        try:
            # Get connection
            connection = self._get_active_connection(user_id, broker.lower())

            # Decrypt token
            access_token = self._decrypt_token(connection['encrypted_access_token'])

            # Default to last 30 days if no dates provided
            if not from_date:
                from_date = datetime.now() - timedelta(days=30)
            if not to_date:
                to_date = datetime.now()

            # Fetch trades from broker
            trades = self._call_broker_api(
                broker.lower(),
                'trades',
                access_token,
                params={'from': from_date.isoformat(), 'to': to_date.isoformat()}
            )

            # Transform and sync to trade journal
            synced_trades = []
            for trade in trades:
                # Transform broker trade to our format
                transformed_trade = self._transform_broker_trade(broker.lower(), trade, user_id)

                # Check if trade already exists (avoid duplicates)
                existing = self.trades_collection.find_one({
                    'user_id': user_id,
                    'broker_trade_id': transformed_trade.get('broker_trade_id')
                })

                if not existing:
                    result = self.trades_collection.insert_one(transformed_trade)
                    synced_trades.append(transformed_trade['symbol'])

            # Update last sync time
            self.connections_collection.update_one(
                {'user_id': user_id, 'broker': broker.lower()},
                {'$set': {'last_synced': datetime.now()}}
            )

            # Log sync
            self._log_sync(user_id, broker.lower(), 'trades', len(synced_trades), True)

            return {
                'success': True,
                'broker': broker.lower(),
                'synced_trades': len(synced_trades),
                'date_range': {
                    'from': from_date.isoformat(),
                    'to': to_date.isoformat()
                },
                'synced_at': datetime.now()
            }

        except Exception as e:
            self._log_sync(user_id, broker.lower(), 'trades', 0, False, str(e))
            raise Exception(f"Error syncing trades: {str(e)}")

    def get_connection_status(self, user_id: str, broker: Optional[str] = None) -> Dict[str, Any]:
        """
        Get broker connection status

        Args:
            user_id: User's ID
            broker: Optional broker name (if None, returns all connections)

        Returns:
            Connection status
        """
        try:
            query = {'user_id': user_id}
            if broker:
                query['broker'] = broker.lower()

            connections = list(self.connections_collection.find(query))

            # Format response
            connection_statuses = []
            for conn in connections:
                # Check if token is expired
                is_expired = conn.get('token_expiry', datetime.now()) < datetime.now()

                connection_statuses.append({
                    'broker': conn['broker'],
                    'status': 'expired' if is_expired else conn.get('status', 'active'),
                    'connected_at': conn.get('connected_at'),
                    'last_synced': conn.get('last_synced'),
                    'scopes': conn.get('scopes', []),
                    'metadata': conn.get('metadata', {})
                })

            return {
                'connections': connection_statuses,
                'total_connections': len(connection_statuses)
            }

        except Exception as e:
            raise Exception(f"Error getting connection status: {str(e)}")

    def get_sync_history(
        self,
        user_id: str,
        broker: Optional[str] = None,
        limit: int = 20
    ) -> Dict[str, Any]:
        """
        Get sync history logs

        Args:
            user_id: User's ID
            broker: Optional broker filter
            limit: Maximum number of logs to return

        Returns:
            Sync history
        """
        try:
            query = {'user_id': user_id}
            if broker:
                query['broker'] = broker.lower()

            logs = list(self.sync_log_collection.find(query)
                       .sort('sync_timestamp', -1)
                       .limit(limit))

            # Convert ObjectIds
            for log in logs:
                log['_id'] = str(log['_id'])

            return {
                'sync_history': logs,
                'count': len(logs)
            }

        except Exception as e:
            raise Exception(f"Error getting sync history: {str(e)}")

    # Private helper methods

    def _get_broker_config(self, broker: str) -> Dict[str, Any]:
        """Get OAuth configuration for broker"""
        # In production, these would come from environment variables
        configs = {
            'zerodha': {
                'client_id': os.getenv('ZERODHA_CLIENT_ID', ''),
                'client_secret': os.getenv('ZERODHA_CLIENT_SECRET', ''),
                'auth_url': 'https://kite.zerodha.com/connect/login',
                'token_url': 'https://api.kite.trade/session/token',
                'redirect_uri': os.getenv('ZERODHA_REDIRECT_URI', 'http://localhost:3000/broker-callback'),
                'scope': 'read',  # Read-only scope
                'api_base': 'https://api.kite.trade'
            },
            'upstox': {
                'client_id': os.getenv('UPSTOX_CLIENT_ID', ''),
                'client_secret': os.getenv('UPSTOX_CLIENT_SECRET', ''),
                'auth_url': 'https://api.upstox.com/v2/login/authorization/dialog',
                'token_url': 'https://api.upstox.com/v2/login/authorization/token',
                'redirect_uri': os.getenv('UPSTOX_REDIRECT_URI', 'http://localhost:3000/broker-callback'),
                'scope': 'read',
                'api_base': 'https://api.upstox.com/v2'
            },
            'angel': {
                'client_id': os.getenv('ANGEL_CLIENT_ID', ''),
                'client_secret': os.getenv('ANGEL_CLIENT_SECRET', ''),
                'auth_url': 'https://smartapi.angelbroking.com/publisher-login',
                'token_url': 'https://apiconnect.angelbroking.com/rest/auth/angelbroking/user/v1/loginByPassword',
                'redirect_uri': os.getenv('ANGEL_REDIRECT_URI', 'http://localhost:3000/broker-callback'),
                'scope': 'read',
                'api_base': 'https://apiconnect.angelbroking.com'
            },
            'fyers': {
                'client_id': os.getenv('FYERS_CLIENT_ID', ''),
                'client_secret': os.getenv('FYERS_CLIENT_SECRET', ''),
                'auth_url': 'https://api.fyers.in/api/v2/generate-authcode',
                'token_url': 'https://api.fyers.in/api/v2/validate-authcode',
                'redirect_uri': os.getenv('FYERS_REDIRECT_URI', 'http://localhost:3000/broker-callback'),
                'scope': 'read',
                'api_base': 'https://api.fyers.in/data-rest/v2'
            }
        }

        return configs.get(broker, {})

    def _generate_state(self, user_id: str, broker: str) -> str:
        """Generate CSRF state parameter"""
        # Combine user_id, broker, timestamp and hash
        timestamp = str(int(datetime.now().timestamp()))
        state_string = f"{user_id}:{broker}:{timestamp}"
        state_hash = hashlib.sha256(state_string.encode()).hexdigest()
        # Encode to base64 for URL safety
        return base64.urlsafe_b64encode(state_hash.encode()).decode()

    def _validate_state(self, state: str, user_id: str, broker: str) -> bool:
        """Validate state parameter (basic validation)"""
        # In production, this should verify against stored state in database
        # For now, we just check if it's a valid base64 hash
        try:
            decoded = base64.urlsafe_b64decode(state.encode()).decode()
            return len(decoded) == 64  # SHA256 hash length
        except Exception:
            return False

    def _exchange_code_for_token(
        self,
        broker: str,
        code: str,
        config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Exchange authorization code for access token"""
        try:
            # This is a simplified example - actual implementation depends on broker API
            token_data = {
                'code': code,
                'client_id': config['client_id'],
                'client_secret': config['client_secret'],
                'redirect_uri': config['redirect_uri'],
                'grant_type': 'authorization_code'
            }

            response = requests.post(config['token_url'], data=token_data)
            response.raise_for_status()

            return response.json()

        except Exception as e:
            raise Exception(f"Token exchange failed: {str(e)}")

    def _encrypt_token(self, token: str) -> str:
        """Encrypt token using Fernet"""
        return self.cipher.encrypt(token.encode()).decode()

    def _decrypt_token(self, encrypted_token: str) -> str:
        """Decrypt token using Fernet"""
        return self.cipher.decrypt(encrypted_token.encode()).decode()

    def _get_active_connection(self, user_id: str, broker: str) -> Dict[str, Any]:
        """Get active broker connection"""
        connection = self.connections_collection.find_one({
            'user_id': user_id,
            'broker': broker.lower(),
            'status': 'active'
        })

        if not connection:
            raise ValueError(f"No active connection found for {broker}. Please connect first.")

        # Check if token is expired
        if connection.get('token_expiry', datetime.now()) < datetime.now():
            raise ValueError(f"Token expired for {broker}. Please reconnect.")

        return connection

    def _call_broker_api(
        self,
        broker: str,
        endpoint: str,
        access_token: str,
        params: Optional[Dict] = None
    ) -> List[Dict[str, Any]]:
        """
        Call broker API endpoint

        Args:
            broker: Broker name
            endpoint: API endpoint (positions, trades, etc.)
            access_token: Decrypted access token
            params: Optional query parameters

        Returns:
            API response data
        """
        try:
            config = self._get_broker_config(broker)
            base_url = config['api_base']

            # Map endpoint to broker-specific URL
            endpoint_map = {
                'zerodha': {
                    'positions': '/portfolio/positions',
                    'trades': '/trades'
                },
                'upstox': {
                    'positions': '/portfolio/long-term-holdings',
                    'trades': '/order/trades'
                },
                'angel': {
                    'positions': '/rest/secure/angelbroking/order/v1/getPosition',
                    'trades': '/rest/secure/angelbroking/order/v1/getOrderBook'
                },
                'fyers': {
                    'positions': '/positions',
                    'trades': '/tradebook'
                }
            }

            url = base_url + endpoint_map[broker][endpoint]

            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            }

            response = requests.get(url, headers=headers, params=params or {})
            response.raise_for_status()

            data = response.json()

            # Extract data based on broker response format
            if broker == 'zerodha':
                return data.get('data', [])
            elif broker == 'upstox':
                return data.get('data', [])
            elif broker == 'angel':
                return data.get('data', [])
            elif broker == 'fyers':
                return data.get('positions', []) if endpoint == 'positions' else data.get('tradeBook', [])

            return []

        except requests.exceptions.RequestException as e:
            raise Exception(f"Broker API call failed: {str(e)}")

    def _transform_broker_position(self, broker: str, position: Dict[str, Any]) -> Dict[str, Any]:
        """Transform broker position to our format"""
        # This is a simplified transformation - actual mapping depends on broker API structure

        if broker == 'zerodha':
            return {
                'symbol': position.get('tradingsymbol'),
                'quantity': position.get('quantity', 0),
                'avg_entry_price': position.get('average_price', 0),
                'current_price': position.get('last_price', 0),
                'stop_loss': position.get('average_price', 0) * 0.95,  # Default 5% SL
                'sector': 'Unknown',
                'correlation_group': 'uncorrelated',
                'source': 'broker_sync',
                'broker': broker
            }
        elif broker == 'upstox':
            return {
                'symbol': position.get('symbol'),
                'quantity': position.get('quantity', 0),
                'avg_entry_price': position.get('avg_price', 0),
                'current_price': position.get('ltp', 0),
                'stop_loss': position.get('avg_price', 0) * 0.95,
                'sector': 'Unknown',
                'correlation_group': 'uncorrelated',
                'source': 'broker_sync',
                'broker': broker
            }

        # Add more broker-specific transformations as needed
        return {}

    def _transform_broker_trade(self, broker: str, trade: Dict[str, Any], user_id: str) -> Dict[str, Any]:
        """Transform broker trade to our format"""
        # This is a simplified transformation

        if broker == 'zerodha':
            return {
                'user_id': user_id,
                'symbol': trade.get('tradingsymbol'),
                'trade_type': trade.get('transaction_type', '').lower(),
                'quantity': trade.get('quantity', 0),
                'entry_price': trade.get('average_price', 0),
                'exit_price': trade.get('average_price', 0),
                'actual_pnl': trade.get('pnl', 0),
                'broker_trade_id': trade.get('trade_id'),
                'created_at': datetime.fromisoformat(trade.get('order_timestamp')) if trade.get('order_timestamp') else datetime.now(),
                'exit_timestamp': datetime.fromisoformat(trade.get('exchange_timestamp')) if trade.get('exchange_timestamp') else None,
                'source': 'broker_sync',
                'broker': broker
            }

        # Add more broker-specific transformations as needed
        return {}

    def _log_sync(
        self,
        user_id: str,
        broker: str,
        sync_type: str,
        items_synced: int,
        success: bool,
        error_message: Optional[str] = None
    ) -> None:
        """Log sync operation"""
        try:
            log_entry = {
                'user_id': user_id,
                'broker': broker,
                'sync_type': sync_type,
                'items_synced': items_synced,
                'success': success,
                'error_message': error_message,
                'sync_timestamp': datetime.now()
            }

            self.sync_log_collection.insert_one(log_entry)

        except Exception as e:
            logger.error(f"Error logging sync: {str(e)}")


# Singleton instance
risk_phase9_service = RiskCalculatorPhase9Service()
