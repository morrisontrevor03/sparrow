import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import anthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.agent_run import AgentRun

logger = logging.getLogger(__name__)


class BaseAgent:
    """
    Base class for all ApplyNow agents.

    Wraps the Anthropic Claude tool-use loop and provides:
    - Automatic tool dispatch via subclass implementation of `dispatch_tool`
    - Agent run logging to the database
    - Token tracking
    """

    agent_type: str = "base"
    model: str = "claude-sonnet-4-6"
    max_iterations: int = 20

    def __init__(self, db: AsyncSession, user_id: uuid.UUID):
        self.db = db
        self.user_id = user_id
        self.client = anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key,
            max_retries=6,  # up from default 2; SDK uses exponential backoff on 429/529
        )
        self._tool_calls_log: list[dict] = []
        self._total_tokens: int = 0
        self._run: AgentRun | None = None

    async def run(self, trigger: str = "scheduled", _run_id: uuid.UUID | None = None, **kwargs) -> dict:
        """Entry point. Creates (or updates a pre-created) AgentRun record, executes the agent."""
        if _run_id:
            result = await self.db.execute(select(AgentRun).where(AgentRun.id == _run_id))
            self._run = result.scalar_one_or_none()

        if not self._run:
            self._run = AgentRun(
                user_id=self.user_id,
                agent_type=self.agent_type,
                trigger=trigger,
                status="running",
                input_data=kwargs,
            )
            self.db.add(self._run)
        else:
            self._run.status = "running"

        await self.db.commit()

        start_ms = int(time.time() * 1000)
        result: dict = {}
        try:
            result = await self._execute(**kwargs)
            self._run.status = "completed"
            self._run.output_summary = result.get("summary", "")
            self._run.jobs_found = result.get("jobs_found", 0)
            self._run.contacts_found = result.get("contacts_found", 0)
            self._run.applications_created = result.get("applications_created", 0)
        except Exception as exc:
            self._run.status = "failed"
            self._run.error_message = str(exc)
            raise
        finally:
            self._run.current_step = None
            self._run.tool_calls = self._tool_calls_log
            self._run.tokens_used = self._total_tokens
            self._run.completed_at = datetime.now(timezone.utc)
            self._run.duration_ms = int(time.time() * 1000) - start_ms
            await self.db.commit()

        return result

    async def _update_progress(self, message: str) -> None:
        """Commit a live status message visible to the dashboard poller."""
        if self._run:
            self._run.current_step = message
            await self.db.commit()

    async def _execute(self, **kwargs) -> dict:
        """Override in subclasses to implement agent logic."""
        raise NotImplementedError

    async def run_tool_loop(
        self,
        system_prompt: str,
        initial_message: str,
        tools: list[dict],
    ) -> str:
        """Try Anthropic first; fall back to OpenAI on auth or service errors."""
        try:
            return await self._run_tool_loop_anthropic(system_prompt, initial_message, tools)
        except anthropic.AuthenticationError as exc:
            logger.warning("Anthropic auth error — falling back to OpenAI: %s", exc)
        except anthropic.APIStatusError as exc:
            if exc.status_code in (500, 529):
                logger.warning("Anthropic service error %d — falling back to OpenAI", exc.status_code)
            elif exc.status_code == 400 and "credit balance" in str(exc).lower():
                logger.warning("Anthropic credit balance too low — falling back to OpenAI")
            else:
                raise

        if not settings.openai_api_key:
            raise RuntimeError(
                "Anthropic API unavailable and OPENAI_API_KEY is not configured — cannot run agent"
            )
        logger.info("Running agent via OpenAI fallback (%s)", settings.openai_fallback_model)
        return await self._run_tool_loop_openai(system_prompt, initial_message, tools)

    async def _run_tool_loop_anthropic(
        self,
        system_prompt: str,
        initial_message: str,
        tools: list[dict],
    ) -> str:
        messages: list[dict] = [{"role": "user", "content": initial_message}]

        for _ in range(self.max_iterations):
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=system_prompt,
                tools=tools,
                messages=messages,
            )

            self._total_tokens += response.usage.input_tokens + response.usage.output_tokens
            messages.append({"role": "assistant", "content": response.content})

            tool_use_blocks = [b for b in response.content if b.type == "tool_use"]

            if tool_use_blocks:
                # Always respond with a tool_result for every tool_use block,
                # regardless of stop_reason (guards against "max_tokens" edge cases).
                tool_results = []
                for block in tool_use_blocks:
                    self._tool_calls_log.append({
                        "tool": block.name,
                        "input": block.input,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
                    try:
                        result = await self.dispatch_tool(block.name, block.input)
                        result_str = str(result)
                        self._tool_calls_log[-1]["output"] = result_str[:500]
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result_str,
                        })
                    except Exception as exc:
                        err_str = f"Error: {exc}"
                        self._tool_calls_log[-1]["output"] = err_str
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": err_str,
                            "is_error": True,
                        })
                messages.append({"role": "user", "content": tool_results})
            else:
                for block in response.content:
                    if hasattr(block, "text"):
                        return block.text
                return ""

        return "Max iterations reached"

    @staticmethod
    def _tools_to_openai(tools: list[dict]) -> list[dict]:
        """Convert Anthropic tool schema format to OpenAI function format."""
        return [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t["input_schema"],
                },
            }
            for t in tools
        ]

    async def _run_tool_loop_openai(
        self,
        system_prompt: str,
        initial_message: str,
        tools: list[dict],
    ) -> str:
        import openai as _openai

        client = _openai.AsyncOpenAI(api_key=settings.openai_api_key)
        openai_tools = self._tools_to_openai(tools)

        messages: list[dict] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": initial_message},
        ]

        for _ in range(self.max_iterations):
            response = await client.chat.completions.create(
                model=settings.openai_fallback_model,
                messages=messages,
                tools=openai_tools if openai_tools else _openai.NOT_GIVEN,
                tool_choice="auto" if openai_tools else _openai.NOT_GIVEN,
            )

            choice = response.choices[0]
            msg = choice.message
            usage = response.usage
            if usage:
                self._total_tokens += (usage.prompt_tokens or 0) + (usage.completion_tokens or 0)

            # Reconstruct a serialisable assistant message
            asst_msg: dict = {"role": "assistant", "content": msg.content or ""}
            if msg.tool_calls:
                asst_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in msg.tool_calls
                ]
            messages.append(asst_msg)

            if choice.finish_reason == "tool_calls" and msg.tool_calls:
                for tc in msg.tool_calls:
                    self._tool_calls_log.append({
                        "tool": tc.function.name,
                        "input": tc.function.arguments,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
                    try:
                        input_data = json.loads(tc.function.arguments)
                        result = await self.dispatch_tool(tc.function.name, input_data)
                        result_str = str(result)
                        self._tool_calls_log[-1]["output"] = result_str[:500]
                    except Exception as exc:
                        result_str = f"Error: {exc}"
                        self._tool_calls_log[-1]["output"] = result_str

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result_str,
                    })
            else:
                return msg.content or ""

        return "Max iterations reached"

    async def complete(self, prompt: str, model: str = "claude-haiku-4-5-20251001", max_tokens: int = 400) -> str:
        """Single-turn text completion with automatic OpenAI fallback."""
        use_openai = False
        try:
            resp = await self.client.messages.create(
                model=model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            self._total_tokens += resp.usage.input_tokens + resp.usage.output_tokens
            return resp.content[0].text.strip()
        except anthropic.AuthenticationError as exc:
            logger.warning("Anthropic auth error in complete() — falling back to OpenAI: %s", exc)
            use_openai = True
        except anthropic.APIStatusError as exc:
            if exc.status_code in (500, 529):
                logger.warning("Anthropic service error %d in complete() — falling back to OpenAI", exc.status_code)
                use_openai = True
            elif exc.status_code == 400 and "credit balance" in str(exc).lower():
                logger.warning("Anthropic credit balance too low in complete() — falling back to OpenAI")
                use_openai = True
            else:
                raise

        if not use_openai:
            raise RuntimeError("complete() reached unexpected state")

        if not settings.openai_api_key:
            raise RuntimeError("Anthropic API unavailable and OPENAI_API_KEY is not configured")

        import openai as _openai
        oa_client = _openai.AsyncOpenAI(api_key=settings.openai_api_key)
        oa_resp = await oa_client.chat.completions.create(
            model=settings.openai_fallback_model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        if oa_resp.usage:
            self._total_tokens += (oa_resp.usage.prompt_tokens or 0) + (oa_resp.usage.completion_tokens or 0)
        return (oa_resp.choices[0].message.content or "").strip()

    async def dispatch_tool(self, name: str, input_data: dict) -> Any:
        """Override in subclasses to handle tool calls."""
        raise NotImplementedError(f"Tool '{name}' not implemented in {self.__class__.__name__}")
