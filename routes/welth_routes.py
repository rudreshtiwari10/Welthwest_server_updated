"""
Welth Agent API — new agentic endpoint for the WelthAI assistant.

Blueprint: /api/welth/
Coexists alongside the old /api/finance-ai/ blueprint. Both work simultaneously.
Frontend can switch to this endpoint when ready.

Endpoints:
    POST   /api/welth/chat                         — send message + get response
    POST   /api/welth/conversations                — create new conversation
    GET    /api/welth/conversations                — list user's conversations
    GET    /api/welth/conversations/<id>           — load full conversation
    DELETE /api/welth/conversations/<id>           — soft-delete
    POST   /api/welth/conversations/<id>/feedback  — thumbs up/down
    GET    /api/welth/status                        — health check
"""

import logging

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

welth_bp = Blueprint("welth", __name__, url_prefix="/api/welth")


# ---- Helper: get current user ID from JWT -----------------------------------

def _get_user_id() -> str | None:
    """Extract user_id from the JWT token in the request. Returns None if unauthenticated."""
    try:
        from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
        verify_jwt_in_request(optional=True)
        identity = get_jwt_identity()
        return str(identity) if identity else None
    except Exception:
        return None


# ---- Chat endpoint ----------------------------------------------------------


@welth_bp.route("/chat", methods=["POST"])
def chat():
    """
    Main chat endpoint. Runs the Welth agent on a user message.

    Request body:
        {
            "message": "What is RELIANCE stock price?",
            "conversation_id": "optional-existing-conversation-id"
        }

    Response:
        {
            "response": "RELIANCE is trading at ₹2,450...",
            "disclaimer": "This is informational analysis...",
            "conversation_id": "...",
            "tools_used": [...],
            "tokens": {"in": 500, "out": 200},
            "elapsed_ms": 1200
        }
    """
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    conversation_id = data.get("conversation_id")
    user_id = _get_user_id()

    if not message:
        return jsonify({"error": "Message is required"}), 400

    # Load or create conversation
    store = None
    conversation_history = []
    try:
        from agent.persistence import ConversationStore
        store = ConversationStore()

        if user_id:
            if conversation_id:
                conv = store.get_conversation(conversation_id, user_id)
                if conv:
                    conversation_history = conv.get("messages", [])
                else:
                    # Invalid conversation_id — create new
                    conversation_id = store.create_conversation(user_id)
            else:
                conversation_id = store.create_conversation(user_id)

            # Persist user message
            store.append_message(conversation_id, user_id, "user", message)
    except Exception as e:
        logger.warning("Persistence unavailable: %s", e)
        store = None

    # Run the agent
    try:
        from agent.runner import WelthAgent
        agent = WelthAgent()
        result = agent.run(
            message,
            conversation_history=conversation_history,
        )
    except Exception as e:
        logger.error("Agent error: %s", e)
        return jsonify({
            "error": "Something went wrong. Please try again.",
            "conversation_id": conversation_id,
        }), 500

    # Persist assistant response
    if store and user_id and conversation_id:
        try:
            store.append_message(
                conversation_id,
                user_id,
                "assistant",
                result.content,
                tool_calls=result.tool_calls_made,
            )
        except Exception as e:
            logger.warning("Failed to persist response: %s", e)

    # ---- Rich data: generate indicators + chart if stock tools were used ----
    indicators_data = None
    chart_base64 = None
    stock_symbol = None

    stock_tools = {"get_stock_quote", "compute_indicator", "get_fundamentals", "get_price_history"}
    used_stock_tool = False
    for tc in result.tool_calls_made:
        if tc.get("tool") in stock_tools:
            used_stock_tool = True
            if tc.get("args", {}).get("symbol"):
                stock_symbol = tc["args"]["symbol"]
                break

    if used_stock_tool and stock_symbol:
        try:
            from services.indicators_service import get_indicators
            ind_result = get_indicators(stock_symbol, period="6mo")
            if "error" not in ind_result:
                indicators_data = ind_result.get("indicators")
                # Generate chart from raw data
                raw_data = ind_result.get("raw_data")
                if raw_data:
                    try:
                        from services.chart_service import generate_chart
                        chart_base64 = generate_chart(
                            raw_data,
                            chart_type="comprehensive",
                            symbol=stock_symbol,
                        )
                    except Exception as e:
                        logger.warning("Chart generation failed: %s", e)
        except Exception as e:
            logger.warning("Indicator enrichment failed: %s", e)

    response_data = {
        "response": result.content,
        "disclaimer": result.disclaimer,
        "conversation_id": conversation_id,
        "tools_used": result.tool_calls_made,
        "tokens": {"in": result.tokens_in, "out": result.tokens_out},
        "elapsed_ms": result.elapsed_ms,
        "iterations": result.iterations,
    }

    if indicators_data:
        response_data["indicators"] = indicators_data
        response_data["symbol"] = stock_symbol
    if chart_base64:
        response_data["chart_base64"] = chart_base64

    return jsonify(response_data)


# ---- Conversation CRUD endpoints --------------------------------------------


@welth_bp.route("/conversations", methods=["POST"])
def create_conversation():
    """Create a new conversation."""
    user_id = _get_user_id()
    if not user_id:
        return jsonify({"error": "Authentication required"}), 401

    from agent.persistence import ConversationStore
    store = ConversationStore()
    conv_id = store.create_conversation(user_id)
    return jsonify({"conversation_id": conv_id}), 201


@welth_bp.route("/conversations", methods=["GET"])
def list_conversations():
    """List user's conversations (newest first)."""
    user_id = _get_user_id()
    if not user_id:
        return jsonify({"error": "Authentication required"}), 401

    skip = request.args.get("skip", 0, type=int)
    limit = request.args.get("limit", 20, type=int)

    from agent.persistence import ConversationStore
    store = ConversationStore()
    conversations = store.list_conversations(user_id, skip=skip, limit=limit)

    return jsonify({"conversations": conversations})


@welth_bp.route("/conversations/<conversation_id>", methods=["GET"])
def get_conversation(conversation_id: str):
    """Load a full conversation."""
    user_id = _get_user_id()
    if not user_id:
        return jsonify({"error": "Authentication required"}), 401

    from agent.persistence import ConversationStore
    store = ConversationStore()
    conv = store.get_conversation(conversation_id, user_id)
    if not conv:
        return jsonify({"error": "Conversation not found"}), 404

    return jsonify(conv)


@welth_bp.route("/conversations/<conversation_id>", methods=["DELETE"])
def delete_conversation(conversation_id: str):
    """Soft-delete a conversation."""
    user_id = _get_user_id()
    if not user_id:
        return jsonify({"error": "Authentication required"}), 401

    from agent.persistence import ConversationStore
    store = ConversationStore()
    deleted = store.delete_conversation(conversation_id, user_id)
    if not deleted:
        return jsonify({"error": "Conversation not found"}), 404

    return jsonify({"deleted": True})


@welth_bp.route("/conversations/<conversation_id>/feedback", methods=["POST"])
def add_feedback(conversation_id: str):
    """Add thumbs up/down feedback on a message."""
    user_id = _get_user_id()
    if not user_id:
        return jsonify({"error": "Authentication required"}), 401

    data = request.get_json(silent=True) or {}
    message_index = data.get("message_index")
    rating = data.get("rating")  # "up" or "down"
    comment = data.get("comment")

    if message_index is None or rating not in ("up", "down"):
        return jsonify({"error": "message_index and rating ('up'/'down') required"}), 400

    from agent.persistence import ConversationStore
    store = ConversationStore()
    feedback_id = store.add_feedback(
        conversation_id, message_index, user_id, rating, comment
    )
    return jsonify({"feedback_id": feedback_id}), 201


# ---- Health check -----------------------------------------------------------


@welth_bp.route("/status", methods=["GET"])
def status():
    """Health check for the Welth agent stack."""
    from agent.tools import get_tool_registry

    registry = get_tool_registry()
    return jsonify({
        "status": "ok",
        "agent": "welth",
        "tools": registry.list_tools(),
        "tool_count": len(registry),
    })
