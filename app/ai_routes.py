from flask import Blueprint, request, jsonify
from flask_login import current_user
from app import csrf
from app.ai_service import generate_chat_response

ai_bp = Blueprint('ai', __name__)


@ai_bp.route('/api/ai/chat', methods=['POST'])
@csrf.exempt
def chat():
    """
    Primary API Endpoint for CareerPearls AI Assistant.
    Detects user role, fetches full conversation history,
    and generates dynamic LLM responses via Gemini / Groq fallback.
    """
    try:
        data = request.get_json(silent=True) or {}
        messages = data.get('messages', [])

        if not messages:
            return jsonify({
                "success": False,
                "error": "No message content provided in request."
            }), 400

        # 1. Role Detection (Candidate vs Employer)
        role = 'candidate'
        user_obj = None

        if current_user.is_authenticated:
            user_obj = current_user
            if current_user.is_employer():
                role = 'employer'
            elif current_user.is_candidate():
                role = 'candidate'

        # 2. Generate Chatbot Response using Gemini primary engine
        result = generate_chat_response(messages=messages, role=role, user=user_obj)
        return jsonify(result)

    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Internal chatbot routing error: {str(e)}",
            "reply": "⚠️ An internal error occurred while connecting to the AI Assistant. Please refresh and try again."
        }), 500
