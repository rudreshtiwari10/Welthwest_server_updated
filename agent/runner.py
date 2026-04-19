"""
WelthAgent — the core agent loop.

Flow:
    1. Build messages: system prompt + conversation history + user query
    2. Call LLM with tool definitions
    3. If LLM returns tool_calls → execute tools → append results → loop (step 2)
    4. If LLM returns text → apply compliance check → return final response
    5. Max iterations: 6. Wall-clock timeout: 25 seconds.

The agent is stateless — conversation history is passed in, not stored here.
Persistence (Phase 5) will wrap the agent externally.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from agent.compliance import moderate_response
from agent.llm.base import LLMResponse, Message, ToolCall
from agent.llm.router import LLMRouter, get_llm_router
from agent.prompts import DISCLAIMER, PLANNER_PROMPT, SYNTHESIZER_PROMPT, SYSTEM_PROMPT
from agent.security import validate_input, redact_pii
from agent.tools import ToolRegistry, get_tool_registry
from agent.tools.base import ToolResult

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 6
WALL_CLOCK_TIMEOUT = 25  # seconds


@dataclass
class AgentResponse:
    """Final response from the agent."""
    content: str
    disclaimer: str = DISCLAIMER
    tool_calls_made: list[dict] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    iterations: int = 0
    elapsed_ms: int = 0
    error: Optional[str] = None


class WelthAgent:
    """
    Agentic loop for the Welth assistant.

    Usage:
        agent = WelthAgent()
        response = agent.run("What is RELIANCE's current price?")
        print(response.content)
        print(response.disclaimer)
    """

    def __init__(
        self,
        llm: Optional[LLMRouter] = None,
        tools: Optional[ToolRegistry] = None,
    ):
        self._llm = llm or get_llm_router()
        self._tools = tools or get_tool_registry()

    def run(
        self,
        user_query: str,
        *,
        conversation_history: Optional[list[dict]] = None,
        prefer_model: str = "auto",
    ) -> AgentResponse:
        """
        Run the agent loop for a single user query.

        Args:
            user_query: The user's message.
            conversation_history: Prior messages as [{role, content}, ...].
                Only the most recent N are used (context management).
            prefer_model: "auto", "fast", or "powerful" — hint for LLM router.

        Returns:
            AgentResponse with the final text + metadata.
        """
        start = time.time()
        total_tokens_in = 0
        total_tokens_out = 0
        tool_calls_log: list[dict] = []

        # ---- 0. Input validation --------------------------------------------
        conv_len = len(conversation_history) if conversation_history else 0
        validation = validate_input(user_query, conversation_length=conv_len)
        if not validation.valid:
            return AgentResponse(
                content=validation.error or "Invalid input.",
                elapsed_ms=int((time.time() - start) * 1000),
            )
        user_query = validation.sanitized_query

        # Log with PII redacted
        logger.info("Agent query: %s", redact_pii(user_query[:200]))

        # ---- 1. Build initial messages --------------------------------------
        messages = self._build_messages(user_query, conversation_history)

        # ---- 2. Agent loop ---------------------------------------------------
        for iteration in range(1, MAX_ITERATIONS + 1):
            elapsed = time.time() - start
            if elapsed > WALL_CLOCK_TIMEOUT:
                logger.warning("Agent wall-clock timeout after %.1fs", elapsed)
                return AgentResponse(
                    content="I'm taking too long to process this. Could you try a simpler question?",
                    tool_calls_made=tool_calls_log,
                    tokens_in=total_tokens_in,
                    tokens_out=total_tokens_out,
                    iterations=iteration,
                    elapsed_ms=int(elapsed * 1000),
                )

            # Call LLM
            tool_schemas = self._tools.get_schemas()
            try:
                llm_response = self._llm.chat(
                    messages,
                    tools=tool_schemas if tool_schemas else None,
                    prefer=prefer_model,
                )
            except Exception as e:
                logger.error("LLM call failed: %s", e)
                return AgentResponse(
                    content="I'm having trouble processing your request right now. Please try again in a moment.",
                    error=str(e),
                    tool_calls_made=tool_calls_log,
                    iterations=iteration,
                    elapsed_ms=int((time.time() - start) * 1000),
                )

            total_tokens_in += llm_response.tokens_in
            total_tokens_out += llm_response.tokens_out

            # ---- 2a. If LLM returned tool calls, execute them ---------------
            if llm_response.tool_calls:
                # Append the assistant message with tool calls to history
                messages.append(Message(
                    role="assistant",
                    content=llm_response.content,
                    tool_calls=llm_response.tool_calls,
                ))

                for tc in llm_response.tool_calls:
                    result = self._execute_tool(tc)
                    tool_calls_log.append({
                        "tool": tc.name,
                        "args": tc.arguments,
                        "success": result.success,
                    })

                    # Append tool result as a message
                    messages.append(Message(
                        role="tool",
                        content=result.to_content(),
                        tool_call_id=tc.id,
                        name=tc.name,
                    ))

                # If this wasn't the last iteration, add synthesizer guidance
                if iteration < MAX_ITERATIONS:
                    # Continue loop — LLM will see tool results and either
                    # call more tools or generate a final response.
                    continue

            # ---- 2b. LLM returned text (final answer) ----------------------
            content = llm_response.content.strip()
            if not content:
                content = "I wasn't able to generate a response. Could you rephrase your question?"

            # ---- 3. Compliance filter ----------------------------------------
            moderation = moderate_response(content)
            if moderation.violations:
                logger.info(
                    "Compliance filter: %d violation(s) caught, fallback=%s",
                    len(moderation.violations),
                    moderation.used_fallback,
                )
            content = moderation.sanitized

            elapsed_ms = int((time.time() - start) * 1000)
            return AgentResponse(
                content=content,
                tool_calls_made=tool_calls_log,
                tokens_in=total_tokens_in,
                tokens_out=total_tokens_out,
                iterations=iteration,
                elapsed_ms=elapsed_ms,
            )

        # Exhausted iterations (shouldn't normally reach here)
        elapsed_ms = int((time.time() - start) * 1000)
        return AgentResponse(
            content="I've been working on this but couldn't complete the analysis. Could you try a more specific question?",
            tool_calls_made=tool_calls_log,
            tokens_in=total_tokens_in,
            tokens_out=total_tokens_out,
            iterations=MAX_ITERATIONS,
            elapsed_ms=elapsed_ms,
        )

    # ---- Private helpers ----------------------------------------------------

    def _build_messages(
        self,
        user_query: str,
        conversation_history: Optional[list[dict]],
    ) -> list[Message]:
        """Assemble the message list for the LLM."""
        messages: list[Message] = []

        # System prompt with planner guidance
        system_text = SYSTEM_PROMPT + "\n\n" + PLANNER_PROMPT
        messages.append(Message(role="system", content=system_text))

        # Conversation history (last 8 turns for context)
        if conversation_history:
            for msg in conversation_history[-8:]:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role in ("user", "assistant") and content:
                    messages.append(Message(role=role, content=content))

        # Current user query (wrapped in delimiters for injection defense)
        messages.append(Message(
            role="user",
            content=f"<user_query>{user_query}</user_query>",
        ))

        return messages

    def _execute_tool(self, tc: ToolCall) -> ToolResult:
        """Execute a single tool call safely."""
        try:
            return self._tools.execute(tc.name, **tc.arguments)
        except Exception as e:
            logger.error("Tool %s execution error: %s", tc.name, e)
            return ToolResult(success=False, error="Tool execution failed")
