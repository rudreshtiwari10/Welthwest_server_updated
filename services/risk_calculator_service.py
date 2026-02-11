"""
Risk Calculator Service - Phase 1
Core Position & Cost Calculator (MVP)

SEBI-Safe Implementation: This service provides analytical calculations only.
No trading recommendations or advice is provided.
"""

from typing import Dict, Any, Optional
from decimal import Decimal, ROUND_HALF_UP


class RiskCalculatorService:
    """
    Service for calculating position sizes, risk, and trading costs.
    All calculations are theoretical illustrations based on user inputs.
    """

    # Broker cost profiles
    BROKER_PROFILES = {
        'zerodha': {
            'equity_delivery_brokerage': 0,  # Zero brokerage
            'equity_intraday_brokerage': 0.0003,  # 0.03% or ₹20 per order (whichever is lower)
            'equity_intraday_brokerage_max': 20,
            'fno_brokerage': 20,  # Flat ₹20 per order
            'equity_delivery_stt': 0.001,  # 0.1% on buy and sell
            'equity_intraday_stt': 0.00025,  # 0.025% on sell side
            'fno_stt': 0.0001,  # 0.01% on sell side (futures), 0.05% on options on sell
            'exchange_txn_charge': 0.0000345,  # NSE: 0.00345%
            'stamp_duty': 0.00015,  # 0.015% on buy side (Maharashtra - varies by state)
            'gst': 0.18  # 18% on brokerage + exchange + SEBI
        },
        'upstox': {
            'equity_delivery_brokerage': 0.0025,  # 0.25% or ₹20 per order (whichever is lower)
            'equity_delivery_brokerage_max': 20,
            'equity_intraday_brokerage': 0.0005,  # 0.05% or ₹20 per order (whichever is lower)
            'equity_intraday_brokerage_max': 20,
            'fno_brokerage': 20,  # Flat ₹20 per order
            'equity_delivery_stt': 0.001,  # 0.1% on buy and sell
            'equity_intraday_stt': 0.00025,  # 0.025% on sell side
            'fno_stt': 0.0001,  # 0.01% on sell side
            'exchange_txn_charge': 0.0000345,  # NSE: 0.00345%
            'stamp_duty': 0.00015,  # 0.015% on buy side
            'gst': 0.18
        },
        'custom': {
            'equity_delivery_brokerage': 0.0005,  # 0.05%
            'equity_intraday_brokerage': 0.0003,  # 0.03%
            'fno_brokerage': 20,
            'equity_delivery_stt': 0.001,
            'equity_intraday_stt': 0.00025,
            'fno_stt': 0.0001,
            'exchange_txn_charge': 0.0000345,
            'stamp_duty': 0.00015,
            'gst': 0.18
        }
    }

    # SEBI turnover charge
    SEBI_TURNOVER_CHARGE = 10 / 10000000  # ₹10 per crore

    @staticmethod
    def calculate_position_size(
        capital_available: float,
        max_risk_per_trade: float,
        max_risk_type: str,  # 'percentage' or 'rupees'
        buy_price: float,
        stop_loss_price: float
    ) -> Dict[str, Any]:
        """
        Calculate the theoretical maximum position size based on risk parameters.

        Returns:
            dict: Contains max_quantity, risk_per_share, risk_amount, risk_percentage
        """
        if buy_price <= 0 or stop_loss_price <= 0:
            raise ValueError("Buy price and stop loss must be positive")

        if stop_loss_price >= buy_price:
            raise ValueError("Stop loss must be below buy price for long positions")

        # Calculate risk per share
        risk_per_share = buy_price - stop_loss_price

        # Determine max risk in rupees
        if max_risk_type == 'percentage':
            max_risk_rupees = capital_available * (max_risk_per_trade / 100)
        else:
            max_risk_rupees = max_risk_per_trade

        # Calculate max quantity
        max_quantity = int(max_risk_rupees / risk_per_share)

        # Calculate actual risk with this quantity
        actual_risk_amount = max_quantity * risk_per_share
        actual_risk_percentage = (actual_risk_amount / capital_available) * 100

        # Calculate stop loss distance
        sl_distance_percentage = ((buy_price - stop_loss_price) / buy_price) * 100

        return {
            'max_quantity': max_quantity,
            'risk_per_share': round(risk_per_share, 2),
            'risk_amount': round(actual_risk_amount, 2),
            'risk_percentage': round(actual_risk_percentage, 2),
            'sl_distance_percentage': round(sl_distance_percentage, 2),
            'position_value': round(max_quantity * buy_price, 2)
        }

    @staticmethod
    def calculate_risk_reward_ratio(
        buy_price: float,
        stop_loss_price: float,
        target_price: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Calculate risk:reward ratio if target is provided.

        Returns:
            dict: Contains risk, reward, ratio
        """
        if not target_price or target_price <= buy_price:
            return {
                'has_target': False,
                'risk': 0,
                'reward': 0,
                'ratio': 'N/A'
            }

        risk = buy_price - stop_loss_price
        reward = target_price - buy_price

        if risk <= 0:
            ratio_value = 'Invalid'
        else:
            ratio_value = reward / risk

        return {
            'has_target': True,
            'risk': round(risk, 2),
            'reward': round(reward, 2),
            'ratio': round(ratio_value, 2) if isinstance(ratio_value, float) else ratio_value,
            'ratio_text': f"1:{round(ratio_value, 2)}" if isinstance(ratio_value, float) else 'Invalid'
        }

    @staticmethod
    def calculate_trading_costs(
        trade_type: str,  # 'delivery', 'intraday', 'fno'
        broker: str,  # 'zerodha', 'upstox', 'custom'
        buy_price: float,
        quantity: int,
        sell_price: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Calculate all trading costs including brokerage, STT, exchange charges, SEBI, stamp duty, and GST.

        Args:
            trade_type: Type of trade (delivery/intraday/fno)
            broker: Broker name
            buy_price: Entry price
            quantity: Number of shares/lots
            sell_price: Exit price (optional, defaults to buy_price for estimation)

        Returns:
            dict: Detailed breakdown of all costs
        """
        if broker.lower() not in RiskCalculatorService.BROKER_PROFILES:
            broker = 'custom'

        profile = RiskCalculatorService.BROKER_PROFILES[broker.lower()]

        # If sell price not provided, estimate with buy price
        if sell_price is None:
            sell_price = buy_price

        buy_value = buy_price * quantity
        sell_value = sell_price * quantity
        total_turnover = buy_value + sell_value

        costs = {
            'buy_value': round(buy_value, 2),
            'sell_value': round(sell_value, 2),
            'total_turnover': round(total_turnover, 2)
        }

        # 1. Calculate Brokerage
        if trade_type == 'delivery':
            if broker.lower() == 'zerodha':
                buy_brokerage = 0
                sell_brokerage = 0
            else:
                buy_brokerage = min(
                    buy_value * profile.get('equity_delivery_brokerage', 0),
                    profile.get('equity_delivery_brokerage_max', 20)
                )
                sell_brokerage = min(
                    sell_value * profile.get('equity_delivery_brokerage', 0),
                    profile.get('equity_delivery_brokerage_max', 20)
                )
        elif trade_type == 'intraday':
            buy_brokerage = min(
                buy_value * profile.get('equity_intraday_brokerage', 0),
                profile.get('equity_intraday_brokerage_max', 20)
            )
            sell_brokerage = min(
                sell_value * profile.get('equity_intraday_brokerage', 0),
                profile.get('equity_intraday_brokerage_max', 20)
            )
        else:  # fno
            buy_brokerage = profile.get('fno_brokerage', 20)
            sell_brokerage = profile.get('fno_brokerage', 20)

        total_brokerage = buy_brokerage + sell_brokerage
        costs['brokerage'] = round(total_brokerage, 2)
        costs['brokerage_buy'] = round(buy_brokerage, 2)
        costs['brokerage_sell'] = round(sell_brokerage, 2)

        # 2. Calculate STT/CTT
        if trade_type == 'delivery':
            # STT on both buy and sell
            stt = (buy_value + sell_value) * profile['equity_delivery_stt']
        elif trade_type == 'intraday':
            # STT only on sell side
            stt = sell_value * profile['equity_intraday_stt']
        else:  # fno
            # STT only on sell side for futures
            stt = sell_value * profile['fno_stt']

        costs['stt_ctt'] = round(stt, 2)

        # 3. Exchange Transaction Charges
        exchange_charges = total_turnover * profile['exchange_txn_charge']
        costs['exchange_txn_charge'] = round(exchange_charges, 2)

        # 4. SEBI Turnover Charges (₹10 per crore)
        sebi_charges = total_turnover * RiskCalculatorService.SEBI_TURNOVER_CHARGE
        costs['sebi_charges'] = round(sebi_charges, 2)

        # 5. Stamp Duty (only on buy side)
        stamp_duty = buy_value * profile['stamp_duty']
        costs['stamp_duty'] = round(stamp_duty, 2)

        # 6. GST (18% on brokerage + exchange charges + SEBI charges)
        gst_base = total_brokerage + exchange_charges + sebi_charges
        gst = gst_base * profile['gst']
        costs['gst'] = round(gst, 2)

        # Total costs
        total_cost = total_brokerage + stt + exchange_charges + sebi_charges + stamp_duty + gst
        costs['total_cost'] = round(total_cost, 2)

        # Cost as percentage of turnover
        costs['cost_percentage'] = round((total_cost / total_turnover) * 100, 4)

        return costs

    @staticmethod
    def calculate_net_profit_loss(
        buy_price: float,
        sell_price: float,
        quantity: int,
        trading_costs: float
    ) -> Dict[str, Any]:
        """
        Calculate net profit/loss after deducting all costs.

        Returns:
            dict: Gross P&L, net P&L, and cost impact
        """
        gross_pl = (sell_price - buy_price) * quantity
        net_pl = gross_pl - trading_costs

        return {
            'gross_pl': round(gross_pl, 2),
            'net_pl': round(net_pl, 2),
            'total_costs': round(trading_costs, 2),
            'cost_impact_on_pl': round(trading_costs, 2) if gross_pl >= 0 else round(trading_costs, 2),
            'net_return_percentage': round((net_pl / (buy_price * quantity)) * 100, 2)
        }

    @staticmethod
    def calculate_breakeven_price(
        buy_price: float,
        quantity: int,
        total_costs: float
    ) -> float:
        """
        Calculate the breakeven price considering all costs.

        Returns:
            float: Price at which profit = 0 after costs
        """
        cost_per_share = total_costs / quantity
        breakeven = buy_price + cost_per_share
        return round(breakeven, 2)

    @staticmethod
    def generate_phase1_response(
        symbol: str,
        trade_type: str,
        buy_price: float,
        stop_loss_price: float,
        target_price: Optional[float],
        capital_available: float,
        max_risk_per_trade: float,
        max_risk_type: str,
        broker: str
    ) -> Dict[str, Any]:
        """
        Main function to generate complete Phase 1 response with all calculations.

        This is a theoretical risk and cost illustration based on the details provided.
        It is not a recommendation to trade this security.
        """
        try:
            # 1. Calculate Position Size
            position_calc = RiskCalculatorService.calculate_position_size(
                capital_available=capital_available,
                max_risk_per_trade=max_risk_per_trade,
                max_risk_type=max_risk_type,
                buy_price=buy_price,
                stop_loss_price=stop_loss_price
            )

            # 2. Calculate Risk:Reward Ratio
            rr_calc = RiskCalculatorService.calculate_risk_reward_ratio(
                buy_price=buy_price,
                stop_loss_price=stop_loss_price,
                target_price=target_price
            )

            # 3. Calculate Trading Costs (at buy price, and at target/SL if provided)
            costs_at_entry = RiskCalculatorService.calculate_trading_costs(
                trade_type=trade_type,
                broker=broker,
                buy_price=buy_price,
                quantity=position_calc['max_quantity'],
                sell_price=buy_price  # Estimate with same price
            )

            # Calculate costs at stop loss
            costs_at_sl = RiskCalculatorService.calculate_trading_costs(
                trade_type=trade_type,
                broker=broker,
                buy_price=buy_price,
                quantity=position_calc['max_quantity'],
                sell_price=stop_loss_price
            )

            # Calculate net loss at stop loss
            pl_at_sl = RiskCalculatorService.calculate_net_profit_loss(
                buy_price=buy_price,
                sell_price=stop_loss_price,
                quantity=position_calc['max_quantity'],
                trading_costs=costs_at_sl['total_cost']
            )

            # 4. If target provided, calculate profit at target
            if target_price:
                costs_at_target = RiskCalculatorService.calculate_trading_costs(
                    trade_type=trade_type,
                    broker=broker,
                    buy_price=buy_price,
                    quantity=position_calc['max_quantity'],
                    sell_price=target_price
                )

                pl_at_target = RiskCalculatorService.calculate_net_profit_loss(
                    buy_price=buy_price,
                    sell_price=target_price,
                    quantity=position_calc['max_quantity'],
                    trading_costs=costs_at_target['total_cost']
                )
            else:
                costs_at_target = None
                pl_at_target = None

            # 5. Calculate breakeven price
            breakeven_price = RiskCalculatorService.calculate_breakeven_price(
                buy_price=buy_price,
                quantity=position_calc['max_quantity'],
                total_costs=costs_at_entry['total_cost']
            )

            # Construct response
            response = {
                'symbol': symbol.upper(),
                'trade_type': trade_type,
                'broker': broker,
                'inputs': {
                    'buy_price': buy_price,
                    'stop_loss_price': stop_loss_price,
                    'target_price': target_price,
                    'capital_available': capital_available,
                    'max_risk_per_trade': max_risk_per_trade,
                    'max_risk_type': max_risk_type
                },
                'position_sizing': {
                    'max_quantity': position_calc['max_quantity'],
                    'position_value': position_calc['position_value'],
                    'risk_per_share': position_calc['risk_per_share'],
                    'message': f"With your risk settings, maximum quantity is {position_calc['max_quantity']} shares."
                },
                'risk_analysis': {
                    'risk_amount': position_calc['risk_amount'],
                    'risk_percentage': position_calc['risk_percentage'],
                    'sl_distance_percentage': position_calc['sl_distance_percentage'],
                    'sl_distance_rupees': round(buy_price - stop_loss_price, 2)
                },
                'risk_reward': rr_calc,
                'cost_breakdown': {
                    'estimated_costs_at_entry': costs_at_entry,
                    'costs_at_stop_loss': costs_at_sl,
                    'costs_at_target': costs_at_target
                },
                'scenario_analysis': {
                    'breakeven_price': breakeven_price,
                    'at_stop_loss': {
                        'gross_loss': pl_at_sl['gross_pl'],
                        'net_loss_after_costs': pl_at_sl['net_pl'],
                        'total_costs': pl_at_sl['total_costs'],
                        'message': f"If stop-loss hits, estimated loss (after costs): ₹{abs(pl_at_sl['net_pl'])}"
                    },
                    'at_target': pl_at_target and {
                        'gross_profit': pl_at_target['gross_pl'],
                        'net_profit_after_costs': pl_at_target['net_pl'],
                        'total_costs': pl_at_target['total_costs'],
                        'message': f"If target hits, estimated net gain (after costs): ₹{pl_at_target['net_pl']}"
                    } or None
                },
                'disclaimer': "This is a theoretical risk and cost illustration based on the details you entered. It is not a recommendation to trade this security. All trading involves risk of loss."
            }

            return response

        except Exception as e:
            raise Exception(f"Error in risk calculation: {str(e)}")
