"""
Risk Calculator Phase 5: Trade Journal with AI Insights Service

Provides trade journal management with AI-powered insights, performance analytics,
and pattern recognition across trading history.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from bson import ObjectId
import os
from pymongo import MongoClient
import csv
from io import StringIO


class RiskCalculatorPhase5Service:
    """Service for trade journal management and AI insights"""

    def __init__(self):
        mongo_uri = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/')
        db_name = os.getenv('DB_NAME', 'welthwest')
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self.trades_collection = self.db['risk_calculator_trades']
        self.journal_entries = self.db['risk_calculator_journal']

    def update_trade_journal_entry(
        self,
        user_id: str,
        trade_id: str,
        journal_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Update or create journal entry for a trade

        Args:
            user_id: User's ID
            trade_id: Trade ID
            journal_data: Journal entry data (tags, notes, lessons, emotions)

        Returns:
            Updated journal entry
        """
        try:
            # Verify trade belongs to user
            trade = self.trades_collection.find_one({
                '_id': ObjectId(trade_id),
                'user_id': user_id
            })

            if not trade:
                raise Exception("Trade not found or unauthorized")

            # Prepare journal entry
            entry = {
                'user_id': user_id,
                'trade_id': trade_id,
                'tags': journal_data.get('tags', []),
                'notes': journal_data.get('notes', ''),
                'lessons_learned': journal_data.get('lessons_learned', ''),
                'emotional_state': journal_data.get('emotional_state', ''),
                'strategy_used': journal_data.get('strategy_used', ''),
                'what_went_right': journal_data.get('what_went_right', ''),
                'what_went_wrong': journal_data.get('what_went_wrong', ''),
                'updated_at': datetime.now()
            }

            # Upsert journal entry
            result = self.journal_entries.update_one(
                {'trade_id': trade_id, 'user_id': user_id},
                {'$set': entry, '$setOnInsert': {'created_at': datetime.now()}},
                upsert=True
            )

            # Return updated entry
            updated_entry = self.journal_entries.find_one({
                'trade_id': trade_id,
                'user_id': user_id
            })

            return updated_entry

        except Exception as e:
            raise Exception(f"Error updating journal entry: {str(e)}")

    def get_journal_entries(
        self,
        user_id: str,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        Get filtered journal entries with trade data

        Args:
            user_id: User's ID
            filters: Optional filters (tags, strategy, date_range, emotion)
            limit: Maximum number of entries to return
            offset: Pagination offset

        Returns:
            Journal entries with trade data and pagination info
        """
        try:
            # Build query
            query = {'user_id': user_id}

            if filters:
                # Filter by tags
                if filters.get('tags'):
                    query['tags'] = {'$in': filters['tags']}

                # Filter by strategy
                if filters.get('strategy'):
                    query['strategy_used'] = filters['strategy']

                # Filter by emotional state
                if filters.get('emotional_state'):
                    query['emotional_state'] = filters['emotional_state']

                # Filter by date range
                if filters.get('date_from') or filters.get('date_to'):
                    date_filter = {}
                    if filters.get('date_from'):
                        date_filter['$gte'] = datetime.fromisoformat(filters['date_from'])
                    if filters.get('date_to'):
                        date_filter['$lte'] = datetime.fromisoformat(filters['date_to'])
                    query['created_at'] = date_filter

            # Get total count
            total_count = self.journal_entries.count_documents(query)

            # Get entries with pagination
            entries = list(self.journal_entries.find(query)
                          .sort('created_at', -1)
                          .skip(offset)
                          .limit(limit))

            # Enrich with trade data
            enriched_entries = []
            for entry in entries:
                trade = self.trades_collection.find_one({'_id': ObjectId(entry['trade_id'])})
                if trade:
                    enriched_entry = {
                        **entry,
                        'trade_data': {
                            'symbol': trade.get('symbol'),
                            'entry_price': trade.get('entry_price'),
                            'exit_price': trade.get('exit_price'),
                            'quantity': trade.get('quantity'),
                            'trade_type': trade.get('trade_type'),
                            'actual_pnl': trade.get('actual_pnl'),
                            'entry_timestamp': trade.get('created_at'),
                            'exit_timestamp': trade.get('exit_timestamp'),
                            'trade_duration_minutes': trade.get('trade_duration_minutes')
                        }
                    }
                    enriched_entries.append(enriched_entry)

            return {
                'entries': enriched_entries,
                'total_count': total_count,
                'limit': limit,
                'offset': offset,
                'has_more': (offset + limit) < total_count
            }

        except Exception as e:
            raise Exception(f"Error getting journal entries: {str(e)}")

    def generate_ai_insights(self, user_id: str, lookback_days: int = 30) -> Dict[str, Any]:
        """
        Generate AI insights from trade journal entries

        Args:
            user_id: User's ID
            lookback_days: Number of days to analyze

        Returns:
            AI-generated insights and patterns
        """
        try:
            # Get trades from lookback period
            start_date = datetime.now() - timedelta(days=lookback_days)

            trades = list(self.trades_collection.find({
                'user_id': user_id,
                'created_at': {'$gte': start_date},
                'exit_timestamp': {'$ne': None}
            }))

            if not trades:
                return {
                    'message': 'Not enough trade data for AI insights',
                    'total_trades': 0
                }

            # Get journal entries
            journal_entries = list(self.journal_entries.find({
                'user_id': user_id,
                'created_at': {'$gte': start_date}
            }))

            # Calculate basic metrics
            total_trades = len(trades)
            winning_trades = [t for t in trades if t.get('actual_pnl', 0) > 0]
            losing_trades = [t for t in trades if t.get('actual_pnl', 0) < 0]

            win_rate = (len(winning_trades) / total_trades * 100) if total_trades > 0 else 0

            # Analyze by strategy
            strategy_performance = self._analyze_by_strategy(trades, journal_entries)

            # Analyze by emotion
            emotion_performance = self._analyze_by_emotion(trades, journal_entries)

            # Analyze by holding period
            holding_period_performance = self._analyze_by_holding_period(trades)

            # Identify patterns
            patterns = self._identify_patterns(trades, journal_entries)

            # Generate recommendations
            recommendations = self._generate_recommendations(
                strategy_performance,
                emotion_performance,
                holding_period_performance,
                patterns
            )

            return {
                'lookback_days': lookback_days,
                'total_trades': total_trades,
                'win_rate': round(win_rate, 2),
                'winning_trades': len(winning_trades),
                'losing_trades': len(losing_trades),
                'strategy_performance': strategy_performance,
                'emotion_performance': emotion_performance,
                'holding_period_performance': holding_period_performance,
                'patterns': patterns,
                'recommendations': recommendations,
                'generated_at': datetime.now()
            }

        except Exception as e:
            raise Exception(f"Error generating AI insights: {str(e)}")

    def export_journal_csv(self, user_id: str, filters: Optional[Dict[str, Any]] = None) -> str:
        """
        Export journal entries to CSV format

        Args:
            user_id: User's ID
            filters: Optional filters

        Returns:
            CSV string
        """
        try:
            # Get all matching entries
            journal_data = self.get_journal_entries(user_id, filters, limit=10000, offset=0)
            entries = journal_data['entries']

            # Create CSV in memory
            output = StringIO()
            writer = csv.writer(output)

            # Write header
            writer.writerow([
                'Trade Date',
                'Symbol',
                'Trade Type',
                'Entry Price',
                'Exit Price',
                'Quantity',
                'P&L',
                'Duration (min)',
                'Strategy',
                'Emotional State',
                'Tags',
                'Notes',
                'Lessons Learned',
                'What Went Right',
                'What Went Wrong'
            ])

            # Write data
            for entry in entries:
                trade_data = entry.get('trade_data', {})
                writer.writerow([
                    trade_data.get('entry_timestamp', '').strftime('%Y-%m-%d %H:%M:%S') if trade_data.get('entry_timestamp') else '',
                    trade_data.get('symbol', ''),
                    trade_data.get('trade_type', ''),
                    trade_data.get('entry_price', ''),
                    trade_data.get('exit_price', ''),
                    trade_data.get('quantity', ''),
                    trade_data.get('actual_pnl', ''),
                    trade_data.get('trade_duration_minutes', ''),
                    entry.get('strategy_used', ''),
                    entry.get('emotional_state', ''),
                    ', '.join(entry.get('tags', [])),
                    entry.get('notes', ''),
                    entry.get('lessons_learned', ''),
                    entry.get('what_went_right', ''),
                    entry.get('what_went_wrong', '')
                ])

            return output.getvalue()

        except Exception as e:
            raise Exception(f"Error exporting journal to CSV: {str(e)}")

    # Private helper methods

    def _analyze_by_strategy(self, trades: List[Dict], journal_entries: List[Dict]) -> List[Dict[str, Any]]:
        """Analyze performance by strategy"""
        strategy_map = {}

        # Map trade IDs to journal entries
        journal_map = {str(j['trade_id']): j for j in journal_entries}

        for trade in trades:
            trade_id = str(trade['_id'])
            journal = journal_map.get(trade_id, {})
            strategy = journal.get('strategy_used', 'Unknown')

            if strategy not in strategy_map:
                strategy_map[strategy] = {'trades': [], 'total_pnl': 0, 'wins': 0, 'losses': 0}

            pnl = trade.get('actual_pnl', 0)
            strategy_map[strategy]['trades'].append(trade)
            strategy_map[strategy]['total_pnl'] += pnl
            if pnl > 0:
                strategy_map[strategy]['wins'] += 1
            elif pnl < 0:
                strategy_map[strategy]['losses'] += 1

        # Calculate metrics
        results = []
        for strategy, data in strategy_map.items():
            total = len(data['trades'])
            win_rate = (data['wins'] / total * 100) if total > 0 else 0
            avg_pnl = data['total_pnl'] / total if total > 0 else 0

            results.append({
                'strategy': strategy,
                'total_trades': total,
                'win_rate': round(win_rate, 2),
                'total_pnl': round(data['total_pnl'], 2),
                'avg_pnl': round(avg_pnl, 2),
                'wins': data['wins'],
                'losses': data['losses']
            })

        return sorted(results, key=lambda x: x['win_rate'], reverse=True)

    def _analyze_by_emotion(self, trades: List[Dict], journal_entries: List[Dict]) -> List[Dict[str, Any]]:
        """Analyze performance by emotional state"""
        emotion_map = {}

        # Map trade IDs to journal entries
        journal_map = {str(j['trade_id']): j for j in journal_entries}

        for trade in trades:
            trade_id = str(trade['_id'])
            journal = journal_map.get(trade_id, {})
            emotion = journal.get('emotional_state', 'Not Recorded')

            if emotion not in emotion_map:
                emotion_map[emotion] = {'trades': [], 'total_pnl': 0, 'wins': 0, 'losses': 0}

            pnl = trade.get('actual_pnl', 0)
            emotion_map[emotion]['trades'].append(trade)
            emotion_map[emotion]['total_pnl'] += pnl
            if pnl > 0:
                emotion_map[emotion]['wins'] += 1
            elif pnl < 0:
                emotion_map[emotion]['losses'] += 1

        # Calculate metrics
        results = []
        for emotion, data in emotion_map.items():
            total = len(data['trades'])
            win_rate = (data['wins'] / total * 100) if total > 0 else 0
            avg_pnl = data['total_pnl'] / total if total > 0 else 0

            results.append({
                'emotional_state': emotion,
                'total_trades': total,
                'win_rate': round(win_rate, 2),
                'total_pnl': round(data['total_pnl'], 2),
                'avg_pnl': round(avg_pnl, 2),
                'wins': data['wins'],
                'losses': data['losses']
            })

        return sorted(results, key=lambda x: x['win_rate'], reverse=True)

    def _analyze_by_holding_period(self, trades: List[Dict]) -> List[Dict[str, Any]]:
        """Analyze performance by holding period"""
        period_map = {
            'Scalp (0-5 min)': {'trades': [], 'total_pnl': 0, 'wins': 0, 'losses': 0},
            'Intraday (5-60 min)': {'trades': [], 'total_pnl': 0, 'wins': 0, 'losses': 0},
            'Short-term (1-4 hours)': {'trades': [], 'total_pnl': 0, 'wins': 0, 'losses': 0},
            'Swing (>4 hours)': {'trades': [], 'total_pnl': 0, 'wins': 0, 'losses': 0}
        }

        for trade in trades:
            duration = trade.get('trade_duration_minutes', 0)
            pnl = trade.get('actual_pnl', 0)

            # Categorize by duration
            if duration <= 5:
                period = 'Scalp (0-5 min)'
            elif duration <= 60:
                period = 'Intraday (5-60 min)'
            elif duration <= 240:
                period = 'Short-term (1-4 hours)'
            else:
                period = 'Swing (>4 hours)'

            period_map[period]['trades'].append(trade)
            period_map[period]['total_pnl'] += pnl
            if pnl > 0:
                period_map[period]['wins'] += 1
            elif pnl < 0:
                period_map[period]['losses'] += 1

        # Calculate metrics
        results = []
        for period, data in period_map.items():
            total = len(data['trades'])
            if total == 0:
                continue

            win_rate = (data['wins'] / total * 100) if total > 0 else 0
            avg_pnl = data['total_pnl'] / total if total > 0 else 0

            results.append({
                'holding_period': period,
                'total_trades': total,
                'win_rate': round(win_rate, 2),
                'total_pnl': round(data['total_pnl'], 2),
                'avg_pnl': round(avg_pnl, 2),
                'wins': data['wins'],
                'losses': data['losses']
            })

        return results

    def _identify_patterns(self, trades: List[Dict], journal_entries: List[Dict]) -> List[str]:
        """Identify trading patterns"""
        patterns = []

        if len(trades) < 5:
            return ['Not enough trades to identify patterns']

        # Pattern: Best time of day
        morning_trades = [t for t in trades if t.get('created_at', datetime.now()).hour < 12]
        afternoon_trades = [t for t in trades if t.get('created_at', datetime.now()).hour >= 12]

        morning_win_rate = len([t for t in morning_trades if t.get('actual_pnl', 0) > 0]) / len(morning_trades) * 100 if morning_trades else 0
        afternoon_win_rate = len([t for t in afternoon_trades if t.get('actual_pnl', 0) > 0]) / len(afternoon_trades) * 100 if afternoon_trades else 0

        if morning_win_rate > afternoon_win_rate + 10:
            patterns.append(f"You perform better in morning sessions ({morning_win_rate:.1f}% vs {afternoon_win_rate:.1f}% win rate)")
        elif afternoon_win_rate > morning_win_rate + 10:
            patterns.append(f"You perform better in afternoon sessions ({afternoon_win_rate:.1f}% vs {morning_win_rate:.1f}% win rate)")

        # Pattern: Average winner vs loser size
        winners = [abs(t.get('actual_pnl', 0)) for t in trades if t.get('actual_pnl', 0) > 0]
        losers = [abs(t.get('actual_pnl', 0)) for t in trades if t.get('actual_pnl', 0) < 0]

        if winners and losers:
            avg_win = sum(winners) / len(winners)
            avg_loss = sum(losers) / len(losers)

            if avg_win > avg_loss * 1.5:
                patterns.append(f"Your average winner (₹{avg_win:.2f}) is significantly larger than average loser (₹{avg_loss:.2f})")
            elif avg_loss > avg_win * 1.2:
                patterns.append(f"Your average loser (₹{avg_loss:.2f}) is larger than average winner (₹{avg_win:.2f}) - consider tighter stops")

        # Pattern: Consecutive losses
        consecutive_losses = 0
        max_consecutive_losses = 0
        for trade in sorted(trades, key=lambda x: x.get('created_at', datetime.now())):
            if trade.get('actual_pnl', 0) < 0:
                consecutive_losses += 1
                max_consecutive_losses = max(max_consecutive_losses, consecutive_losses)
            else:
                consecutive_losses = 0

        if max_consecutive_losses >= 3:
            patterns.append(f"Maximum consecutive losses detected: {max_consecutive_losses} trades - consider taking breaks")

        return patterns if patterns else ['Gathering data to identify patterns']

    def _generate_recommendations(
        self,
        strategy_performance: List[Dict],
        emotion_performance: List[Dict],
        holding_period_performance: List[Dict],
        patterns: List[str]
    ) -> List[str]:
        """Generate personalized recommendations"""
        recommendations = []

        # Strategy recommendations
        if strategy_performance and len(strategy_performance) >= 2:
            best_strategy = strategy_performance[0]
            worst_strategy = strategy_performance[-1]

            if best_strategy['win_rate'] > 60:
                recommendations.append(f"Focus more on '{best_strategy['strategy']}' strategy (Win rate: {best_strategy['win_rate']:.1f}%)")

            if worst_strategy['win_rate'] < 40 and worst_strategy['total_trades'] >= 5:
                recommendations.append(f"Review or avoid '{worst_strategy['strategy']}' strategy (Win rate: {worst_strategy['win_rate']:.1f}%)")

        # Emotion recommendations
        if emotion_performance:
            best_emotion = max(emotion_performance, key=lambda x: x['win_rate'])
            worst_emotion = min(emotion_performance, key=lambda x: x['win_rate'])

            if best_emotion['win_rate'] - worst_emotion['win_rate'] > 20:
                recommendations.append(f"Emotional state matters: Best performance when '{best_emotion['emotional_state']}' vs '{worst_emotion['emotional_state']}'")

        # Holding period recommendations
        if holding_period_performance:
            best_period = max(holding_period_performance, key=lambda x: x['win_rate'])
            recommendations.append(f"Your best holding period: {best_period['holding_period']} (Win rate: {best_period['win_rate']:.1f}%)")

        if not recommendations:
            recommendations.append("Keep journaling to unlock personalized insights!")

        return recommendations


# Singleton instance
risk_phase5_service = RiskCalculatorPhase5Service()
