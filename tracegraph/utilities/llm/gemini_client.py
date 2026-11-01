import logging
import uuid
from typing import Any

from google import genai
from google.genai import errors, types

from tracegraph.constants import llm as c
from tracegraph.errors import Errors
from tracegraph.interfaces.llm import ILlmClient, LlmTurn
from tracegraph.utilities.llm.schema import inline_refs

logger = logging.getLogger(__name__)


def _is_key_failure(exc: errors.ClientError) -> bool:
    """
    #Feature: LLM utility (Gemini adapter)
    #Scenario: 401, 403 and 429, plus the 400 Gemini returns for an invalid API key
    #Complexity: Time O(s) - error text
    """
    return exc.code in c.KEY_FAILURE_STATUS_CODES or "API_KEY_INVALID" in str(exc) or "API key" in (exc.message or "")


def _tool_call_names(messages: list[dict[str, Any]]) -> dict[str, tuple[str, str | None]]:
    """
    #Feature: LLM utility (Gemini adapter)
    #Scenario: Neutral tool_use id -> (function name, Gemini's own call id) for building function responses
    #Complexity: Time O(m) - message blocks
    """
    out = {}
    for message in messages:
        if message["role"] == "assistant" and isinstance(message["content"], list):
            for block in message["content"]:
                if block.get("type") == "tool_use":
                    out[block["id"]] = (block["name"], block.get("native_id"))
    return out


def _assistant_content(blocks: list[dict[str, Any]]) -> types.Content:
    """
    #Feature: LLM utility (Gemini adapter)
    #Scenario: Replay the model's own turn unchanged (keeps thought signatures); rebuild only when it is absent
    #Complexity: Time O(b) - blocks
    """
    native = next((b["content"] for b in blocks if b.get("type") == c.GEMINI_NATIVE_BLOCK), None)
    if native is not None:
        return native
    parts = [types.Part(text=b["text"]) if b["type"] == "text" else
             types.Part(function_call=types.FunctionCall(id=b.get("native_id"), name=b["name"], args=b["input"]))
             for b in blocks if b.get("type") in ("text", "tool_use")]
    return types.Content(role="model", parts=parts)


def _user_content(content: str | list[dict[str, Any]], calls: dict[str, tuple[str, str | None]]) -> types.Content:
    """
    #Feature: LLM utility (Gemini adapter)
    #Scenario: Text and tool_result blocks -> user parts with function responses (errors under "error")
    #Complexity: Time O(b) - blocks
    """
    if isinstance(content, str):
        return types.Content(role="user", parts=[types.Part(text=content)])
    parts = []
    for block in content:
        if block.get("type") == "tool_result":
            name, native_id = calls.get(block["tool_use_id"], ("unknown_tool", None))
            key = "error" if block.get("is_error") else "output"
            parts.append(types.Part(function_response=types.FunctionResponse(
                id=native_id, name=name, response={key: block["content"]})))
        elif block.get("type") == "text":
            parts.append(types.Part(text=block["text"]))
    return types.Content(role="user", parts=parts)


def to_gemini_contents(messages: list[dict[str, Any]]) -> list[types.Content]:
    """
    #Feature: LLM utility (Gemini adapter)
    #Scenario: Translate the neutral conversation (Messages API shape) into Gemini contents
    #Complexity: Time O(m) - message blocks

    Raises:
        ValueError: When messages is None.
    """
    if messages is None:
        raise ValueError("[to_gemini_contents] 'messages' is required.")
    calls = _tool_call_names(messages)
    return [_assistant_content(m["content"]) if m["role"] == "assistant" else _user_content(m["content"], calls)
            for m in messages]


def to_gemini_tools(tools: list[dict[str, Any]]) -> list[types.Tool]:
    """
    #Feature: LLM utility (Gemini adapter)
    #Scenario: Neutral tool definitions -> one Tool with function declarations (JSON Schema, refs inlined)
    #Complexity: Time O(t * s) - tools times schema size
    """
    declarations = [types.FunctionDeclaration(name=t["name"], description=t.get("description", ""),
                                              parameters_json_schema=inline_refs(t["input_schema"])) for t in tools]
    return [types.Tool(function_declarations=declarations)] if declarations else []


def from_gemini_response(response: types.GenerateContentResponse) -> LlmTurn:
    """
    #Feature: LLM utility (Gemini adapter)
    #Scenario: Gemini response -> neutral turn: text and tool_use blocks plus the native content for replay;
               blocked prompts and safety finishes become refusals
    #Complexity: Time O(p) - parts
    """
    usage = response.usage_metadata
    tokens_in = (usage.prompt_token_count or 0) if usage else 0
    tokens_out = ((usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0)) if usage else 0
    candidate = response.candidates[0] if response.candidates else None
    if candidate is None or candidate.content is None:
        feedback = response.prompt_feedback
        reason = (feedback.block_reason.name if feedback and feedback.block_reason else
                  candidate.finish_reason.name if candidate and candidate.finish_reason else "EMPTY")
        return LlmTurn([], c.STOP_REFUSAL, tokens_in, tokens_out, response.model_version or "", reason, [])
    blocks: list[dict[str, Any]] = [{"type": c.GEMINI_NATIVE_BLOCK, "content": candidate.content}]
    for part in candidate.content.parts or []:
        if part.function_call is not None:
            call = part.function_call
            blocks.append({"type": "tool_use", "id": call.id or f"gemini_{uuid.uuid4().hex[:12]}",
                           "native_id": call.id, "name": call.name, "input": dict(call.args or {})})
        elif part.text and not part.thought:
            blocks.append({"type": "text", "text": part.text})
    finish = candidate.finish_reason.name if candidate.finish_reason else "STOP"
    tool_calls = [b for b in blocks if b["type"] == "tool_use"]
    stop = (c.STOP_TOOL_USE if tool_calls else c.STOP_MAX_TOKENS if finish == "MAX_TOKENS" else
            c.STOP_REFUSAL if finish in c.GEMINI_REFUSAL_REASONS else c.STOP_END_TURN)
    refusal = finish if stop == c.STOP_REFUSAL else None
    return LlmTurn(blocks, stop, tokens_in, tokens_out, response.model_version or "", refusal, tool_calls)


class GeminiLlmClient(ILlmClient):
    """
    #Feature: LLM utility (Gemini adapter)
    #Scenario: Gemini via google-genai: manual function calling (the state machine owns the loop), temperature 0,
               SDK retries for transient HTTP errors
    #Complexity: Time O(1) per call excluding the model
    """

    def __init__(self, model: str, max_tokens: int, api_key: str | None = None, client: genai.Client | None = None
                 ) -> None:
        """
        #Feature: LLM utility (Gemini adapter)
        #Scenario: Without api_key the SDK reads GOOGLE_API_KEY, then GEMINI_API_KEY
        #Complexity: Time O(1) - constant

        Raises:
            ValueError: When model is empty.
        """
        if not model:
            raise ValueError("[GeminiLlmClient.__init__] 'model' is required (set TG_LLM_MODEL).")
        retry = types.HttpRetryOptions(attempts=c.GEMINI_RETRY_ATTEMPTS, http_status_codes=list(c.GEMINI_RETRY_STATUS_CODES))
        self._client = client or genai.Client(api_key=api_key, http_options=types.HttpOptions(retry_options=retry))
        self._model, self._max_tokens = model, max_tokens

    def _config(self, system: str, tools: list[dict[str, Any]]) -> types.GenerateContentConfig:
        """
        #Feature: LLM utility (Gemini adapter)
        #Scenario: Request config: system instruction, declared tools in AUTO mode, automatic calling disabled
        #Complexity: Time O(t * s) - tool schemas
        """
        return types.GenerateContentConfig(
            system_instruction=system,
            tools=to_gemini_tools(tools),
            tool_config=types.ToolConfig(function_calling_config=types.FunctionCallingConfig(mode="AUTO")),
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            temperature=c.GEMINI_TEMPERATURE,
            max_output_tokens=self._max_tokens,
        )

    async def turn(self, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LlmTurn:
        """
        #Feature: LLM utility (Gemini adapter)
        #Scenario: One turn; key failures become KeyUnavailable, other 4xx BadRequest, persistent 5xx InternalServerError
        #Complexity: Time O(1) excluding the model

        Raises:
            Errors.LLM.KeyUnavailable: When the key is invalid, forbidden or out of quota after retries.
            Errors.HTTP.BadRequest: When the request is rejected.
            Errors.HTTP.InternalServerError: When the API stays unavailable after retries.
        """
        try:
            response = await self._client.aio.models.generate_content(
                model=self._model, contents=to_gemini_contents(messages), config=self._config(system, tools))
        except errors.ClientError as exc:
            if _is_key_failure(exc):
                raise Errors.LLM.KeyUnavailable(f"Gemini key failed ({exc.code} {exc.status}).",
                                                {"status": exc.code}) from exc
            raise Errors.HTTP.BadRequest(f"Gemini request rejected ({exc.code}): {exc.message}") from exc
        except errors.APIError as exc:
            raise Errors.HTTP.InternalServerError(f"Gemini API error {exc.code}: {exc.message}") from exc
        turn = from_gemini_response(response)
        logger.info("LLM turn", extra={"provider": "gemini", "model": turn.model or self._model,
                                       "stop_reason": turn.stop_reason, "output_tokens": turn.output_tokens})
        return turn
