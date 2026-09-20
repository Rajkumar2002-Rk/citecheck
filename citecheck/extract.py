"""Run the extraction. This is the only place an LLM is allowed to run."""
from __future__ import annotations

import time
from dataclasses import dataclass

import anthropic
import httpx2
from pydantic import ValidationError

from .prompts import SYSTEM, build_user_prompt
from .schema import QuoteExtraction, SpanExtraction

MODEL = "claude-opus-5"
# Span mode needs a large output budget: the model works out character offsets
# in its reasoning, and a 6kB Item 9A blew straight through 16,000 tokens and
# returned a truncated, unparseable response. Large budgets require streaming so
# the request does not hit the SDK's HTTP timeout.
MAX_TOKENS = 64_000

MODES = {"span": SpanExtraction, "quote": QuoteExtraction}


@dataclass
class Attempt:
    mode: str
    parsed: object | None
    error: str | None
    input_tokens: int
    output_tokens: int
    seconds: float
    stop_reason: str | None = None


def extract(client: anthropic.Anthropic, text: str, *, mode: str,
            repair: str | None = None, version: int = 1) -> Attempt:
    """One extraction call. `repair` carries gate feedback on a retry."""
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}; expected one of {sorted(MODES)}")

    prompt = build_user_prompt(text, mode=mode, version=version)
    if repair:
        prompt += (
            "\n\nA previous attempt failed deterministic verification:\n"
            f"{repair}\n\n"
            "Produce a corrected record. Re-read the source before citing."
        )

    started = time.monotonic()
    try:
        return _call(client, prompt, mode, started)
    except (httpx2.HTTPError, anthropic.APIConnectionError) as exc:
        # A dropped connection mid-stream is a transport failure, not a model
        # defect. It killed a 29/30 run on the last filing. Retry once, then
        # record it as an error rather than letting it end the pass.
        try:
            return _call(client, prompt, mode, started)
        except (httpx2.HTTPError, anthropic.APIConnectionError) as retry_exc:
            return Attempt(mode, None, f"transport: {type(retry_exc).__name__}: {retry_exc}",
                           0, 0, time.monotonic() - started)


def _call(client: anthropic.Anthropic, prompt: str, mode: str, started: float) -> Attempt:
    try:
        with client.messages.stream(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM,
            messages=[{"role": "user", "content": prompt}],
            output_format=MODES[mode],
        ) as stream:
            response = stream.get_final_message()
    except anthropic.APIStatusError as exc:
        return Attempt(mode, None, f"{type(exc).__name__}: {exc}", 0, 0,
                       time.monotonic() - started)
    except ValidationError as exc:
        # A response truncated at max_tokens yields unparseable JSON and the
        # SDK raises rather than returning None. Left uncaught this kills the
        # whole run mid-corpus -- and, worse, a truncation scored as a model
        # failure would be a fabricated defect.
        return Attempt(mode, None, f"truncated or invalid JSON: {exc}", 0, 0,
                       time.monotonic() - started)

    parsed = getattr(response, "parsed_output", None)
    if parsed is None:
        # Truncation is the common cause and must never be silently scored as a
        # model defect -- it is a budget failure, not a citation failure.
        error = (f"no parsed output (stop_reason={response.stop_reason}, "
                 f"output_tokens={response.usage.output_tokens})")
    else:
        error = None

    return Attempt(
        mode=mode,
        parsed=parsed,
        error=error,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        seconds=time.monotonic() - started,
        stop_reason=response.stop_reason,
    )
