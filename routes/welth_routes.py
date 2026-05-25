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
            user_id=user_id,
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
        "display_payloads": result.display_payloads,
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


# ---- Personal money context (profile / goals / portfolio) -------------------


def _require_user():
    """Resolve user_id from JWT or return a 401 response."""
    uid = _get_user_id()
    if not uid:
        return None, (jsonify({"error": "authentication_required"}), 401)
    return uid, None


@welth_bp.route("/me/profile", methods=["GET"])
def me_profile_get():
    user_id, err = _require_user()
    if err:
        return err
    from services.user_context_service import get_profile
    return jsonify({"profile": get_profile(user_id)})


@welth_bp.route("/me/profile", methods=["PUT"])
def me_profile_put():
    user_id, err = _require_user()
    if err:
        return err
    from services.user_context_service import upsert_profile
    payload = request.get_json(silent=True) or {}
    try:
        saved = upsert_profile(user_id, payload)
        return jsonify({"profile": saved})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@welth_bp.route("/me/goals", methods=["GET"])
def me_goals_get():
    user_id, err = _require_user()
    if err:
        return err
    from services.user_context_service import get_goals
    return jsonify({"goals": get_goals(user_id)})


@welth_bp.route("/me/goals", methods=["POST"])
def me_goals_add():
    user_id, err = _require_user()
    if err:
        return err
    from services.user_context_service import add_goal
    payload = request.get_json(silent=True) or {}
    try:
        goal = add_goal(user_id, payload)
        return jsonify({"goal": goal}), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@welth_bp.route("/me/goals/<goal_id>", methods=["PUT"])
def me_goals_update(goal_id: str):
    user_id, err = _require_user()
    if err:
        return err
    from services.user_context_service import update_goal
    payload = request.get_json(silent=True) or {}
    if update_goal(user_id, goal_id, payload):
        return jsonify({"ok": True})
    return jsonify({"error": "goal_not_found"}), 404


@welth_bp.route("/me/goals/<goal_id>", methods=["DELETE"])
def me_goals_delete(goal_id: str):
    user_id, err = _require_user()
    if err:
        return err
    from services.user_context_service import delete_goal
    if delete_goal(user_id, goal_id):
        return jsonify({"ok": True})
    return jsonify({"error": "goal_not_found"}), 404


@welth_bp.route("/me/portfolio", methods=["GET"])
def me_portfolio_get():
    user_id, err = _require_user()
    if err:
        return err
    from services.user_context_service import get_portfolio
    return jsonify({"portfolio": get_portfolio(user_id)})


@welth_bp.route("/me/portfolio", methods=["PUT"])
def me_portfolio_put():
    user_id, err = _require_user()
    if err:
        return err
    from services.user_context_service import replace_portfolio
    payload = request.get_json(silent=True) or {}
    holdings = payload.get("holdings") if isinstance(payload, dict) else payload
    try:
        saved = replace_portfolio(user_id, holdings or [])
        return jsonify({"portfolio": saved})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


# ---- Document upload / parse ------------------------------------------------


@welth_bp.route("/me/documents", methods=["POST"])
def me_documents_upload():
    """Multipart upload: form fields `file` (the PDF) and `document_type`."""
    user_id, err = _require_user()
    if err:
        return err
    from services.document_service import parse_and_store, SUPPORTED_TYPES

    if "file" not in request.files:
        return jsonify({"error": "missing file"}), 400
    f = request.files["file"]
    document_type = (request.form.get("document_type") or "").strip().lower()
    if document_type not in SUPPORTED_TYPES:
        return jsonify({"error": f"document_type must be one of {SUPPORTED_TYPES}"}), 400

    try:
        file_bytes = f.read()
        doc = parse_and_store(user_id, document_type, f.filename or "uploaded.pdf", file_bytes)
        # ensure datetime is JSON-serialisable
        if hasattr(doc.get("uploaded_at"), "isoformat"):
            doc["uploaded_at"] = doc["uploaded_at"].isoformat()
        return jsonify({"document": doc}), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error("document upload failed: %s", e)
        return jsonify({"error": "Upload failed. Please try again."}), 500


@welth_bp.route("/me/documents", methods=["GET"])
def me_documents_list():
    user_id, err = _require_user()
    if err:
        return err
    from services.document_service import list_documents
    document_type = (request.args.get("type") or "").strip().lower() or None
    docs = list_documents(user_id, document_type=document_type, limit=50)
    return jsonify({"documents": docs})


@welth_bp.route("/me/documents/<document_id>", methods=["DELETE"])
def me_documents_delete(document_id: str):
    user_id, err = _require_user()
    if err:
        return err
    from services.document_service import delete_document
    if delete_document(user_id, document_id):
        return jsonify({"ok": True})
    return jsonify({"error": "document_not_found"}), 404


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
