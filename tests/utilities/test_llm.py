import pytest
from google.genai import errors, types

from tracegraph.agent.phase_runner import submit_tool
from tracegraph.config import Settings
from tracegraph.errors import Errors
from tracegraph.utilities.llm import create_llm_client, inline_refs
from tracegraph.utilities.llm.anthropic_client import AnthropicLlmClient
from tracegraph.utilities.llm.gemini_client import GeminiLlmClient

SIGNATURE = b"opaque-thought-signature"
TOOLS = [{"name": "get_node", "description": "node", "input_schema": {
    "type": "object", "properties": {"ref": {"type": "string"}}, "required": ["ref"], "additionalProperties": False}}]


def response(parts: list[types.Part], finish: str = "STOP") -> types.GenerateContentResponse:
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=parts), finish_reason=finish)],
        usage_metadata=types.GenerateContentResponseUsageMetadata(prompt_token_count=11, candidates_token_count=5,
                                                                  thoughts_token_count=7),
        model_version="gemini-test")


class FakeModels:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    async def generate_content(self, *, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


class FakeClient:
    def __init__(self, replies):
        self.models = FakeModels(replies)
        self.aio = self


async def test_gemini_round_trip_preserves_thought_signatures():
    call = types.Part(function_call=types.FunctionCall(name="get_node", args={"ref": "app.f"}), thought_signature=SIGNATURE)
    fake = FakeClient([response([types.Part(text="looking", thought=True), call]),
                       response([types.Part(text="done")])])
    llm = GeminiLlmClient("gemini-test", 1024, client=fake)
    messages = [{"role": "user", "content": "start"}]

    first = await llm.turn("system", messages, TOOLS)
    assert first.stop_reason == "tool_use" and first.output_tokens == 12 and first.input_tokens == 11
    assert first.tool_calls[0]["name"] == "get_node" and first.tool_calls[0]["input"] == {"ref": "app.f"}
    assert not any(b.get("type") == "text" for b in first.content)  # thoughts are not surfaced as text

    messages += [{"role": "assistant", "content": first.content},
                 {"role": "user", "content": [{"type": "tool_result", "tool_use_id": first.tool_calls[0]["id"],
                                               "content": "Function app.f", "is_error": False}]}]
    second = await llm.turn("system", messages, TOOLS)
    assert second.stop_reason == "end_turn" and second.content[-1] == {"type": "text", "text": "done"}

    sent = fake.models.calls[1]["contents"]
    assert sent[1].parts[1].thought_signature == SIGNATURE  # model turn replayed unchanged
    reply = sent[2].parts[0].function_response
    assert reply.name == "get_node" and reply.response == {"output": "Function app.f"}
    config = fake.models.calls[0]["config"]
    assert config.automatic_function_calling.disable and config.temperature == 0.0
    assert config.tools[0].function_declarations[0].name == "get_node"


async def test_gemini_refusals_and_errors():
    blocked = types.GenerateContentResponse(prompt_feedback=types.GenerateContentResponsePromptFeedback(
        block_reason="SAFETY"))
    fake = FakeClient([blocked, response([types.Part(text="x")], finish="PROHIBITED_CONTENT"),
                       errors.ClientError(400, {"error": {"message": "bad schema", "status": "INVALID_ARGUMENT"}}),
                       errors.ServerError(503, {"error": {"message": "unavailable", "status": "UNAVAILABLE"}})])
    llm = GeminiLlmClient("gemini-test", 1024, client=fake)
    assert (await llm.turn("s", [{"role": "user", "content": "q"}], [])).refusal == "SAFETY"
    assert (await llm.turn("s", [{"role": "user", "content": "q"}], [])).refusal == "PROHIBITED_CONTENT"
    with pytest.raises(Errors.HTTP.BadRequest):
        await llm.turn("s", [{"role": "user", "content": "q"}], [])
    with pytest.raises(Errors.HTTP.InternalServerError):
        await llm.turn("s", [{"role": "user", "content": "q"}], [])


def test_inline_refs_flattens_artifact_schemas():
    schema = submit_tool("plan")["input_schema"]
    assert "$defs" in schema
    flat = inline_refs(schema)
    assert "$defs" not in str(flat) and "$ref" not in str(flat)
    assert flat["properties"]["steps"]["items"]["properties"]["files"]["type"] == "array"


def test_factory_selects_provider_from_settings(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "env-key")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    gemini = create_llm_client(Settings(llm_provider="gemini", llm_model="gemini-2.5-pro", llm_api_key=""))
    assert isinstance(gemini, GeminiLlmClient)
    claude = create_llm_client(Settings(llm_provider="anthropic", llm_api_key="sk-test"))
    assert isinstance(claude, AnthropicLlmClient) and claude._model == "claude-opus-5-5"
    with pytest.raises(ValueError, match="TG_LLM_MODEL"):
        create_llm_client(Settings(llm_provider="gemini", llm_model=None))
