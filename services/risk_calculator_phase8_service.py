"""
Risk Calculator Phase 8: Notifications & Periodic Reports Service

Provides notification preferences management, periodic report generation,
and email delivery for daily/weekly/monthly trading reports.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from bson import ObjectId
import os
from pymongo import MongoClient
from services.email_service import email_service
import logging

logger = logging.getLogger(__name__)


class RiskCalculatorPhase8Service:
    """Service for notifications and periodic reports"""

    def __init__(self):
        mongo_uri = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/')
        db_name = os.getenv('DB_NAME', 'welthwest')
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self.reports_collection = self.db['risk_calculator_reports']
        self.preferences_collection = self.db['risk_calculator_notification_preferences']
        self.trades_collection = self.db['risk_calculator_trades']
        self.sessions_collection = self.db['risk_calculator_sessions']
        self.portfolio_collection = self.db['risk_calculator_portfolio']
        self.settings_collection = self.db['risk_calculator_settings']

    def get_notification_preferences(self, user_id: str) -> Dict[str, Any]:
        """
        Get user's notification preferences

        Args:
            user_id: User's ID

        Returns:
            Notification preferences
        """
        try:
            prefs = self.preferences_collection.find_one({'user_id': user_id})

            if not prefs:
                # Create default preferences
                default_prefs = {
                    'user_id': user_id,
                    'daily_report_enabled': True,
                    'daily_report_time': '18:00',  # 6 PM
                    'weekly_report_enabled': True,
                    'weekly_report_day': 'Saturday',
                    'weekly_report_time': '09:00',
                    'monthly_report_enabled': True,
                    'monthly_report_day': 1,  # First day of month
                    'monthly_report_time': '09:00',
                    'email_notifications': True,
                    'report_sections': {
                        'performance_summary': True,
                        'portfolio_overview': True,
                        'risk_metrics': True,
                        'behavioral_insights': True,
                        'top_trades': True,
                        'ai_recommendations': True
                    },
                    'created_at': datetime.now(),
                    'updated_at': datetime.now()
                }

                result = self.preferences_collection.insert_one(default_prefs)
                default_prefs['_id'] = result.inserted_id
                return default_prefs

            return prefs

        except Exception as e:
            raise Exception(f"Error getting notification preferences: {str(e)}")

    def update_notification_preferences(
        self,
        user_id: str,
        preferences: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Update user's notification preferences

        Args:
            user_id: User's ID
            preferences: Preferences to update

        Returns:
            Updated preferences
        """
        try:
            # Ensure user preferences exist
            self.get_notification_preferences(user_id)

            # Update preferences
            preferences['updated_at'] = datetime.now()

            self.preferences_collection.update_one(
                {'user_id': user_id},
                {'$set': preferences}
            )

            return self.get_notification_preferences(user_id)

        except Exception as e:
            raise Exception(f"Error updating notification preferences: {str(e)}")

    def generate_daily_report(self, user_id: str, report_date: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Generate daily trading report

        Args:
            user_id: User's ID
            report_date: Date for the report (defaults to yesterday)

        Returns:
            Daily report data
        """
        try:
            if not report_date:
                report_date = datetime.now() - timedelta(days=1)

            # Set to start of day
            start_date = report_date.replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = start_date + timedelta(days=1)

            # Get trades for the day
            trades = list(self.trades_collection.find({
                'user_id': user_id,
                'created_at': {'$gte': start_date, '$lt': end_date},
                'exit_timestamp': {'$ne': None}
            }))

            # Get session data
            session = self.sessions_collection.find_one({
                'user_id': user_id,
                'session_date': start_date
            })

            # Calculate metrics
            total_trades = len(trades)
            winning_trades = [t for t in trades if t.get('actual_pnl', 0) > 0]
            losing_trades = [t for t in trades if t.get('actual_pnl', 0) < 0]

            total_pnl = sum(t.get('actual_pnl', 0) for t in trades)
            win_rate = (len(winning_trades) / total_trades * 100) if total_trades > 0 else 0

            avg_win = sum(t.get('actual_pnl', 0) for t in winning_trades) / len(winning_trades) if winning_trades else 0
            avg_loss = sum(t.get('actual_pnl', 0) for t in losing_trades) / len(losing_trades) if losing_trades else 0

            # Get portfolio snapshot
            portfolio = self.portfolio_collection.find_one({'user_id': user_id})

            # Get user settings
            settings = self.settings_collection.find_one({'user_id': user_id})

            # Build report
            report = {
                'user_id': user_id,
                'report_type': 'daily',
                'report_date': start_date,
                'generated_at': datetime.now(),
                'summary': {
                    'total_trades': total_trades,
                    'winning_trades': len(winning_trades),
                    'losing_trades': len(losing_trades),
                    'win_rate': round(win_rate, 2),
                    'total_pnl': round(total_pnl, 2),
                    'avg_win': round(avg_win, 2),
                    'avg_loss': round(avg_loss, 2),
                    'largest_win': max([t.get('actual_pnl', 0) for t in trades], default=0),
                    'largest_loss': min([t.get('actual_pnl', 0) for t in trades], default=0)
                },
                'session_data': {
                    'max_drawdown': session.get('max_drawdown_percent', 0) if session else 0,
                    'risk_rule_violations': session.get('risk_rule_violations', 0) if session else 0,
                    'discipline_score': session.get('discipline_score', 0) if session else 0
                },
                'portfolio_snapshot': {
                    'total_value': portfolio.get('total_portfolio_value', 0) if portfolio else 0,
                    'positions_count': len(portfolio.get('positions', [])) if portfolio else 0,
                    'total_risk': portfolio.get('total_risk_if_all_sl_hit', 0) if portfolio else 0
                },
                'top_trades': sorted(trades, key=lambda x: abs(x.get('actual_pnl', 0)), reverse=True)[:5],
                'behavioral_notes': self._generate_behavioral_notes(trades, session)
            }

            # Save report
            result = self.reports_collection.insert_one(report)
            report['_id'] = result.inserted_id

            return report

        except Exception as e:
            raise Exception(f"Error generating daily report: {str(e)}")

    def generate_weekly_report(self, user_id: str, week_end_date: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Generate weekly trading report

        Args:
            user_id: User's ID
            week_end_date: End date for the week (defaults to last Saturday)

        Returns:
            Weekly report data
        """
        try:
            if not week_end_date:
                # Get last Saturday
                today = datetime.now()
                days_since_saturday = (today.weekday() + 2) % 7
                week_end_date = today - timedelta(days=days_since_saturday)

            # Set to end of day
            end_date = week_end_date.replace(hour=23, minute=59, second=59, microsecond=999999)
            start_date = (week_end_date - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)

            # Get trades for the week
            trades = list(self.trades_collection.find({
                'user_id': user_id,
                'created_at': {'$gte': start_date, '$lte': end_date},
                'exit_timestamp': {'$ne': None}
            }))

            # Get sessions for the week
            sessions = list(self.sessions_collection.find({
                'user_id': user_id,
                'session_date': {'$gte': start_date, '$lte': end_date}
            }))

            # Calculate metrics
            total_trades = len(trades)
            winning_trades = [t for t in trades if t.get('actual_pnl', 0) > 0]
            losing_trades = [t for t in trades if t.get('actual_pnl', 0) < 0]

            total_pnl = sum(t.get('actual_pnl', 0) for t in trades)
            win_rate = (len(winning_trades) / total_trades * 100) if total_trades > 0 else 0

            # Calculate daily averages
            trading_days = len(sessions)
            avg_trades_per_day = total_trades / trading_days if trading_days > 0 else 0
            avg_pnl_per_day = total_pnl / trading_days if trading_days > 0 else 0

            # Get best and worst days
            daily_pnls = {}
            for session in sessions:
                session_date = session['session_date']
                session_trades = [t for t in trades if start_date <= t['created_at'] < session_date + timedelta(days=1)]
                daily_pnls[session_date] = sum(t.get('actual_pnl', 0) for t in session_trades)

            best_day = max(daily_pnls.items(), key=lambda x: x[1]) if daily_pnls else (None, 0)
            worst_day = min(daily_pnls.items(), key=lambda x: x[1]) if daily_pnls else (None, 0)

            # Get portfolio snapshot
            portfolio = self.portfolio_collection.find_one({'user_id': user_id})

            # Build report
            report = {
                'user_id': user_id,
                'report_type': 'weekly',
                'report_start_date': start_date,
                'report_end_date': end_date,
                'generated_at': datetime.now(),
                'summary': {
                    'total_trades': total_trades,
                    'winning_trades': len(winning_trades),
                    'losing_trades': len(losing_trades),
                    'win_rate': round(win_rate, 2),
                    'total_pnl': round(total_pnl, 2),
                    'avg_trades_per_day': round(avg_trades_per_day, 2),
                    'avg_pnl_per_day': round(avg_pnl_per_day, 2),
                    'trading_days': trading_days
                },
                'daily_breakdown': {
                    'best_day': {'date': best_day[0], 'pnl': round(best_day[1], 2)},
                    'worst_day': {'date': worst_day[0], 'pnl': round(worst_day[1], 2)},
                    'daily_pnls': {str(k): round(v, 2) for k, v in daily_pnls.items()}
                },
                'portfolio_snapshot': {
                    'total_value': portfolio.get('total_portfolio_value', 0) if portfolio else 0,
                    'positions_count': len(portfolio.get('positions', [])) if portfolio else 0,
                    'total_risk': portfolio.get('total_risk_if_all_sl_hit', 0) if portfolio else 0
                },
                'top_trades': sorted(trades, key=lambda x: abs(x.get('actual_pnl', 0)), reverse=True)[:10],
                'behavioral_insights': self._generate_weekly_insights(trades, sessions)
            }

            # Save report
            result = self.reports_collection.insert_one(report)
            report['_id'] = result.inserted_id

            return report

        except Exception as e:
            raise Exception(f"Error generating weekly report: {str(e)}")

    def generate_monthly_report(self, user_id: str, month_date: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Generate monthly trading report (aggregates data from all phases)

        Args:
            user_id: User's ID
            month_date: Any date in the month (defaults to last month)

        Returns:
            Monthly report data
        """
        try:
            if not month_date:
                # Get last month
                today = datetime.now()
                month_date = today.replace(day=1) - timedelta(days=1)

            # Get first and last day of month
            start_date = month_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            if start_date.month == 12:
                end_date = start_date.replace(year=start_date.year + 1, month=1, day=1)
            else:
                end_date = start_date.replace(month=start_date.month + 1, day=1)

            # Get all trades for the month
            trades = list(self.trades_collection.find({
                'user_id': user_id,
                'created_at': {'$gte': start_date, '$lt': end_date},
                'exit_timestamp': {'$ne': None}
            }))

            # Get all sessions for the month
            sessions = list(self.sessions_collection.find({
                'user_id': user_id,
                'session_date': {'$gte': start_date, '$lt': end_date}
            }))

            # Calculate comprehensive metrics
            total_trades = len(trades)
            winning_trades = [t for t in trades if t.get('actual_pnl', 0) > 0]
            losing_trades = [t for t in trades if t.get('actual_pnl', 0) < 0]

            total_pnl = sum(t.get('actual_pnl', 0) for t in trades)
            win_rate = (len(winning_trades) / total_trades * 100) if total_trades > 0 else 0

            # Profit factor
            total_wins = sum(t.get('actual_pnl', 0) for t in winning_trades) if winning_trades else 0
            total_losses = abs(sum(t.get('actual_pnl', 0) for t in losing_trades)) if losing_trades else 0
            profit_factor = (total_wins / total_losses) if total_losses > 0 else 0

            # Calculate weekly breakdown
            weekly_data = {}
            current_week_start = start_date
            week_num = 1

            while current_week_start < end_date:
                week_end = min(current_week_start + timedelta(days=7), end_date)
                week_trades = [t for t in trades if current_week_start <= t['created_at'] < week_end]
                week_pnl = sum(t.get('actual_pnl', 0) for t in week_trades)

                weekly_data[f'Week {week_num}'] = {
                    'trades': len(week_trades),
                    'pnl': round(week_pnl, 2),
                    'start': current_week_start,
                    'end': week_end
                }

                current_week_start = week_end
                week_num += 1

            # Get portfolio snapshot
            portfolio = self.portfolio_collection.find_one({'user_id': user_id})

            # Build comprehensive report
            report = {
                'user_id': user_id,
                'report_type': 'monthly',
                'report_month': start_date.strftime('%B %Y'),
                'report_start_date': start_date,
                'report_end_date': end_date,
                'generated_at': datetime.now(),
                'performance_summary': {
                    'total_trades': total_trades,
                    'winning_trades': len(winning_trades),
                    'losing_trades': len(losing_trades),
                    'win_rate': round(win_rate, 2),
                    'total_pnl': round(total_pnl, 2),
                    'total_wins': round(total_wins, 2),
                    'total_losses': round(total_losses, 2),
                    'profit_factor': round(profit_factor, 2),
                    'avg_win': round(total_wins / len(winning_trades), 2) if winning_trades else 0,
                    'avg_loss': round(total_losses / len(losing_trades), 2) if losing_trades else 0,
                    'largest_win': max([t.get('actual_pnl', 0) for t in trades], default=0),
                    'largest_loss': min([t.get('actual_pnl', 0) for t in trades], default=0),
                    'trading_days': len(sessions)
                },
                'weekly_breakdown': weekly_data,
                'portfolio_overview': {
                    'total_value': portfolio.get('total_portfolio_value', 0) if portfolio else 0,
                    'positions_count': len(portfolio.get('positions', [])) if portfolio else 0,
                    'total_risk': portfolio.get('total_risk_if_all_sl_hit', 0) if portfolio else 0,
                    'cash_balance': portfolio.get('cash_balance', 0) if portfolio else 0
                },
                'risk_metrics': {
                    'avg_max_drawdown': sum(s.get('max_drawdown_percent', 0) for s in sessions) / len(sessions) if sessions else 0,
                    'total_violations': sum(s.get('risk_rule_violations', 0) for s in sessions),
                    'avg_discipline_score': sum(s.get('discipline_score', 0) for s in sessions) / len(sessions) if sessions else 0
                },
                'behavioral_insights': self._generate_monthly_insights(trades, sessions),
                'top_10_trades': sorted(trades, key=lambda x: abs(x.get('actual_pnl', 0)), reverse=True)[:10],
                'recommendations': self._generate_monthly_recommendations(trades, sessions)
            }

            # Save report
            result = self.reports_collection.insert_one(report)
            report['_id'] = result.inserted_id

            return report

        except Exception as e:
            raise Exception(f"Error generating monthly report: {str(e)}")

    def send_report_email(self, user_id: str, report_id: str, user_email: str, user_name: str) -> bool:
        """
        Send report via email

        Args:
            user_id: User's ID
            report_id: Report ID
            user_email: User's email address
            user_name: User's name

        Returns:
            True if email sent successfully, False otherwise
        """
        try:
            # Get report
            report = self.reports_collection.find_one({'_id': ObjectId(report_id), 'user_id': user_id})

            if not report:
                raise Exception("Report not found")

            # Render HTML
            html_content = self._render_report_html(report, user_name)

            # Prepare subject
            report_type = report['report_type'].capitalize()
            if report_type == 'Daily':
                date_str = report['report_date'].strftime('%B %d, %Y')
            elif report_type == 'Weekly':
                date_str = f"{report['report_start_date'].strftime('%b %d')} - {report['report_end_date'].strftime('%b %d, %Y')}"
            else:  # Monthly
                date_str = report['report_month']

            subject = f"WelthWest {report_type} Trading Report - {date_str}"

            # Send email
            success = email_service.send_email(
                to=user_email,
                subject=subject,
                template=html_content,
                context={}
            )

            return success

        except Exception as e:
            logger.error(f"Error sending report email: {str(e)}")
            return False

    def _render_report_html(self, report: Dict[str, Any], user_name: str) -> str:
        """
        Render report as HTML email

        Args:
            report: Report data
            user_name: User's name

        Returns:
            HTML string
        """
        report_type = report['report_type'].capitalize()

        # Base template
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>{report_type} Trading Report</title>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 800px; margin: 0 auto; padding: 20px; }}
                .header {{ background: #4F46E5; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; background: #f9f9f9; }}
                .section {{ background: white; padding: 20px; margin: 20px 0; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
                .metric {{ display: inline-block; margin: 10px 20px 10px 0; }}
                .metric-label {{ font-size: 12px; color: #666; text-transform: uppercase; }}
                .metric-value {{ font-size: 24px; font-weight: bold; color: #4F46E5; }}
                .positive {{ color: #10B981; }}
                .negative {{ color: #EF4444; }}
                .footer {{ background: #333; color: white; padding: 20px; text-align: center; margin-top: 20px; }}
                table {{ width: 100%; border-collapse: collapse; margin: 10px 0; }}
                th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }}
                th {{ background: #f0f0f0; font-weight: bold; }}
                .trade-row {{ font-size: 14px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>{report_type} Trading Report</h1>
                    <p>WelthWest Risk Calculator</p>
                </div>

                <div class="content">
                    <h2>Hi {user_name},</h2>
                    <p>Here's your {report_type.lower()} trading performance report.</p>
        """

        # Add performance summary
        if 'summary' in report:
            summary = report['summary']
            pnl_class = 'positive' if summary.get('total_pnl', 0) >= 0 else 'negative'

            html += f"""
                    <div class="section">
                        <h3>Performance Summary</h3>
                        <div class="metric">
                            <div class="metric-label">Total P&L</div>
                            <div class="metric-value {pnl_class}">₹{summary.get('total_pnl', 0):,.2f}</div>
                        </div>
                        <div class="metric">
                            <div class="metric-label">Total Trades</div>
                            <div class="metric-value">{summary.get('total_trades', 0)}</div>
                        </div>
                        <div class="metric">
                            <div class="metric-label">Win Rate</div>
                            <div class="metric-value">{summary.get('win_rate', 0):.1f}%</div>
                        </div>
                        <div class="metric">
                            <div class="metric-label">Winners</div>
                            <div class="metric-value positive">{summary.get('winning_trades', 0)}</div>
                        </div>
                        <div class="metric">
                            <div class="metric-label">Losers</div>
                            <div class="metric-value negative">{summary.get('losing_trades', 0)}</div>
                        </div>
                    </div>
            """

        # Add performance summary for monthly reports
        if 'performance_summary' in report:
            perf = report['performance_summary']
            pnl_class = 'positive' if perf.get('total_pnl', 0) >= 0 else 'negative'

            html += f"""
                    <div class="section">
                        <h3>Performance Summary</h3>
                        <div class="metric">
                            <div class="metric-label">Total P&L</div>
                            <div class="metric-value {pnl_class}">₹{perf.get('total_pnl', 0):,.2f}</div>
                        </div>
                        <div class="metric">
                            <div class="metric-label">Win Rate</div>
                            <div class="metric-value">{perf.get('win_rate', 0):.1f}%</div>
                        </div>
                        <div class="metric">
                            <div class="metric-label">Profit Factor</div>
                            <div class="metric-value">{perf.get('profit_factor', 0):.2f}</div>
                        </div>
                        <div class="metric">
                            <div class="metric-label">Trading Days</div>
                            <div class="metric-value">{perf.get('trading_days', 0)}</div>
                        </div>
                    </div>
            """

        # Add portfolio overview
        if 'portfolio_snapshot' in report or 'portfolio_overview' in report:
            portfolio = report.get('portfolio_snapshot') or report.get('portfolio_overview', {})

            html += f"""
                    <div class="section">
                        <h3>Portfolio Overview</h3>
                        <div class="metric">
                            <div class="metric-label">Portfolio Value</div>
                            <div class="metric-value">₹{portfolio.get('total_value', 0):,.2f}</div>
                        </div>
                        <div class="metric">
                            <div class="metric-label">Open Positions</div>
                            <div class="metric-value">{portfolio.get('positions_count', 0)}</div>
                        </div>
                        <div class="metric">
                            <div class="metric-label">Total Risk</div>
                            <div class="metric-value negative">₹{portfolio.get('total_risk', 0):,.2f}</div>
                        </div>
                    </div>
            """

        # Add behavioral insights
        insights = report.get('behavioral_notes') or report.get('behavioral_insights', [])
        if insights:
            html += """
                    <div class="section">
                        <h3>Behavioral Insights</h3>
                        <ul>
            """
            for insight in insights:
                html += f"<li>{insight}</li>"
            html += """
                        </ul>
                    </div>
            """

        # Add recommendations for monthly reports
        if 'recommendations' in report and report['recommendations']:
            html += """
                    <div class="section">
                        <h3>AI Recommendations</h3>
                        <ul>
            """
            for rec in report['recommendations']:
                html += f"<li>{rec}</li>"
            html += """
                        </ul>
                    </div>
            """

        # Close HTML
        html += """
                    <p>Keep tracking your progress and stay disciplined!</p>
                    <p><em>This is an analytical report based on your own trading rules. It does not provide investment advice.</em></p>
                </div>

                <div class="footer">
                    <p>Thank you for using WelthWest Risk Calculator!</p>
                    <p>Happy Trading!</p>
                </div>
            </div>
        </body>
        </html>
        """

        return html

    def get_past_reports(
        self,
        user_id: str,
        report_type: Optional[str] = None,
        limit: int = 20,
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        Get past reports with filters

        Args:
            user_id: User's ID
            report_type: Filter by report type (daily/weekly/monthly)
            limit: Maximum number of reports to return
            offset: Pagination offset

        Returns:
            Reports list with pagination info
        """
        try:
            # Build query
            query = {'user_id': user_id}

            if report_type:
                query['report_type'] = report_type.lower()

            # Get total count
            total_count = self.reports_collection.count_documents(query)

            # Get reports with pagination
            reports = list(self.reports_collection.find(query)
                          .sort('generated_at', -1)
                          .skip(offset)
                          .limit(limit))

            return {
                'reports': reports,
                'total_count': total_count,
                'limit': limit,
                'offset': offset,
                'has_more': (offset + limit) < total_count
            }

        except Exception as e:
            raise Exception(f"Error getting past reports: {str(e)}")

    # Private helper methods

    def _generate_behavioral_notes(self, trades: List[Dict], session: Optional[Dict]) -> List[str]:
        """Generate behavioral notes for daily report"""
        notes = []

        if not trades:
            return ["No trades today - was it a planned rest day?"]

        # Check overtrading
        if len(trades) > 10:
            notes.append(f"High activity: {len(trades)} trades. Consider if all were high-conviction setups.")

        # Check discipline
        if session and session.get('risk_rule_violations', 0) > 0:
            notes.append(f"⚠️ {session['risk_rule_violations']} risk rule violation(s) detected today.")

        # Check win/loss pattern
        consecutive_losses = 0
        for trade in sorted(trades, key=lambda x: x.get('created_at', datetime.now())):
            if trade.get('actual_pnl', 0) < 0:
                consecutive_losses += 1
            else:
                consecutive_losses = 0

        if consecutive_losses >= 3:
            notes.append("Detected consecutive losses - did you stick to your stop loss rules?")

        return notes if notes else ["Good trading discipline observed today!"]

    def _generate_weekly_insights(self, trades: List[Dict], sessions: List[Dict]) -> List[str]:
        """Generate insights for weekly report"""
        insights = []

        if not trades:
            return ["No trading activity this week."]

        # Analyze trading frequency
        avg_trades_per_day = len(trades) / len(sessions) if sessions else 0
        if avg_trades_per_day > 8:
            insights.append(f"High trading frequency: {avg_trades_per_day:.1f} trades/day on average.")

        # Check consistency
        daily_pnls = []
        for session in sessions:
            session_trades = [t for t in trades if t['created_at'].date() == session['session_date'].date()]
            daily_pnl = sum(t.get('actual_pnl', 0) for t in session_trades)
            daily_pnls.append(daily_pnl)

        if daily_pnls:
            positive_days = sum(1 for pnl in daily_pnls if pnl > 0)
            insights.append(f"{positive_days}/{len(daily_pnls)} profitable days this week.")

        return insights

    def _generate_monthly_insights(self, trades: List[Dict], sessions: List[Dict]) -> List[str]:
        """Generate insights for monthly report"""
        insights = []

        if not trades:
            return ["No trading activity this month."]

        total_pnl = sum(t.get('actual_pnl', 0) for t in trades)

        # Overall performance
        if total_pnl > 0:
            insights.append(f"Profitable month with total P&L of ₹{total_pnl:,.2f}")
        else:
            insights.append(f"Month ended with loss of ₹{abs(total_pnl):,.2f} - review your strategy")

        # Trading frequency
        insights.append(f"Traded on {len(sessions)} days this month")

        # Discipline analysis
        total_violations = sum(s.get('risk_rule_violations', 0) for s in sessions)
        if total_violations == 0:
            insights.append("Excellent discipline - no risk rule violations!")
        else:
            insights.append(f"{total_violations} risk rule violations detected - work on discipline")

        return insights

    def _generate_monthly_recommendations(self, trades: List[Dict], sessions: List[Dict]) -> List[str]:
        """Generate recommendations for monthly report"""
        recommendations = []

        if not trades:
            return ["Start tracking your trades to unlock personalized recommendations!"]

        # Win rate analysis
        winning_trades = [t for t in trades if t.get('actual_pnl', 0) > 0]
        win_rate = (len(winning_trades) / len(trades) * 100) if trades else 0

        if win_rate < 40:
            recommendations.append("Win rate below 40% - review your entry criteria and strategy")
        elif win_rate > 60:
            recommendations.append("Strong win rate - maintain your current approach")

        # Risk management
        avg_violations = sum(s.get('risk_rule_violations', 0) for s in sessions) / len(sessions) if sessions else 0
        if avg_violations > 1:
            recommendations.append("Focus on risk management - too many rule violations")

        # Trading frequency
        if len(sessions) > 20:
            recommendations.append("High trading frequency - ensure quality over quantity")

        return recommendations if recommendations else ["Keep up the good work!"]


# Singleton instance
risk_phase8_service = RiskCalculatorPhase8Service()
