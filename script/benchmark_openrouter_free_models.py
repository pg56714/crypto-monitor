"""Benchmark OpenRouter free models with small, automatically graded tasks."""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import math
import os
import statistics
import sys
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiohttp
from dotenv import load_dotenv

CHAT_COMPLETIONS_URL = "https://openrouter.ai/api/v1/chat/completions"
KEY_INFO_URL = "https://openrouter.ai/api/v1/key"
MODELS_URL = "https://openrouter.ai/api/v1/models"
REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True, slots=True)
class _Task:
    name: str
    prompt: str
    max_tokens: int
    grader: Callable[[str], tuple[float, str]]


@dataclass(frozen=True, slots=True)
class _AttemptResult:
    task: str
    score: float
    latency_seconds: float | None
    note: str
    error: str | None
    response_preview: str


@dataclass(frozen=True, slots=True)
class _ModelResult:
    model: str
    name: str
    score: float
    success_count: int
    failure_count: int
    average_latency_seconds: float | None
    attempts: list[_AttemptResult]


def _grade_price_math(content: str) -> tuple[float, str]:
    data = _extract_json_object(content)
    answer = _get_number(data, "answer") if data else None
    if answer is not None and math.isclose(answer, 100.8, rel_tol=0.0, abs_tol=0.01):
        return 1.0, "correct final price"
    if "100.8" in content:
        return 0.7, "answer appears in non-strict output"
    return 0.0, "expected answer 100.8"


def _grade_box_logic(content: str) -> tuple[float, str]:
    data = _extract_json_object(content)
    if not data:
        return 0.0, "missing JSON object"

    expected = {
        "red": "apple+orange",
        "blue": "orange",
        "green": "apple",
    }
    matches = 0
    for key, expected_value in expected.items():
        value = _normalize_label(_get_string(data, key))
        if value == expected_value:
            matches += 1
    return matches / len(expected), f"{matches}/{len(expected)} box labels correct"


def _grade_crypto_risk(content: str) -> tuple[float, str]:
    data = _extract_json_object(content)
    if not data:
        return 0.0, "missing JSON object"

    risk = _normalize_word(_get_string(data, "risk"))
    action = _normalize_word(_get_string(data, "action"))
    score = 0.0
    if risk == "high":
        score += 0.5
    if action == "avoid_long":
        score += 0.5
    return score, f"risk={risk or 'missing'}, action={action or 'missing'}"


def _grade_traditional_chinese(content: str) -> tuple[float, str]:
    data = _extract_json_object(content)
    summary = _get_string(data, "summary") if data else None
    if not summary:
        return 0.0, "missing summary"

    score = 0.0
    notes: list[str] = []
    if "槓桿風險" in summary:
        score += 0.4
        notes.append("keyword ok")
    else:
        notes.append("keyword missing")

    compact_length = len(summary.replace(" ", "").replace("\n", ""))
    if compact_length <= 35:
        score += 0.3
        notes.append("length ok")
    else:
        notes.append(f"too long ({compact_length})")

    simplified_to_traditional = str.maketrans(
        {
            chr(0x98CE): "風",
            chr(0x9669): "險",
            chr(0x6760): "槓",
            chr(0x6746): "桿",
            chr(0x8FC7): "過",
            chr(0x70ED): "熱",
            chr(0x8D44): "資",
            chr(0x8D39): "費",
            chr(0x5E94): "應",
        }
    )
    if summary.translate(simplified_to_traditional) == summary:
        score += 0.3
        notes.append("traditional ok")
    else:
        notes.append("simplified text found")
    return score, ", ".join(notes)


def _tasks() -> list[_Task]:
    return [
        _Task(
            name="price_math",
            max_tokens=80,
            prompt=(
                'Return only valid JSON in this exact shape: {"answer": number}.\n'
                "A token starts at 100, rises by 12%, then falls by 10%. "
                "What is the final price?"
            ),
            grader=_grade_price_math,
        ),
        _Task(
            name="box_logic",
            max_tokens=120,
            prompt=(
                "Return only valid JSON with keys red, blue, green.\n"
                "There are three boxes. The red box label says apple. The blue box label "
                "says orange. The green box label says apple+orange. Every label is wrong. "
                "You draw one fruit from the green box and it is an apple. "
                "Use only these values: apple, orange, apple+orange."
            ),
            grader=_grade_box_logic,
        ),
        _Task(
            name="crypto_risk",
            max_tokens=120,
            prompt=(
                "Return only valid JSON in this exact shape: "
                '{"risk":"low|medium|high","action":"avoid_long|watch|long"}.\n'
                "Market data: hourly funding rate is +0.18%, open interest is up 42% in "
                "six hours, price is down 3%, and the long/short ratio is 3.1. "
                "Classify long-side liquidation risk."
            ),
            grader=_grade_crypto_risk,
        ),
        _Task(
            name="zh_tw_summary",
            max_tokens=100,
            prompt=(
                'Return only valid JSON in this exact shape: {"summary":"..."}.\n'
                "Write one Traditional Chinese sentence, no more than 35 Chinese "
                "characters, summarizing this: funding is overheated, leverage is crowded, "
                "and traders should avoid chasing long entries. The sentence must contain "
                "the exact phrase: 槓桿風險."
            ),
            grader=_grade_traditional_chinese,
        ),
    ]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark OpenRouter :free models with a small scored prompt set.",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=REPO_ROOT / ".env",
        help="Path to a dotenv file containing OPENROUTER_API_KEY.",
    )
    parser.add_argument(
        "--models",
        nargs="+",
        help="Explicit model IDs to test. When omitted, models ending in :free are fetched.",
    )
    parser.add_argument(
        "--include-router",
        action="store_true",
        help="Also test openrouter/free as a routing baseline.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=6,
        help="Maximum fetched free models to test. Ignored when --models is supplied.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Test every fetched :free model, subject to --max-requests.",
    )
    parser.add_argument(
        "--sort",
        choices=("created", "context", "id"),
        default="created",
        help="How to sort fetched models before applying --limit.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=7.5,
        help="Seconds to wait between requests to reduce free-model rate limit errors.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=45.0,
        help="HTTP timeout in seconds for each request.",
    )
    parser.add_argument(
        "--max-requests",
        type=int,
        default=45,
        help="Safety cap for benchmark chat requests.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        help="Optional path to write detailed JSON results.",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        help="Optional path to write a compact CSV ranking.",
    )
    parser.add_argument(
        "--skip-key-info",
        action="store_true",
        help="Skip the /key request that prints remaining credit metadata.",
    )
    return parser.parse_args()


async def _main() -> int:
    args = _parse_args()
    load_dotenv(args.env_file)
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("OPENROUTER_API_KEY is not set. Add it to .env or the environment.", file=sys.stderr)
        return 2

    timeout = aiohttp.ClientTimeout(total=args.timeout)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        if not args.skip_key_info:
            await _print_key_info(session, api_key)

        candidates = await _select_candidates(session, api_key, args)
        benchmark_tasks = _tasks()
        request_count = len(candidates) * len(benchmark_tasks)
        if request_count == 0:
            print("No free models found to benchmark.", file=sys.stderr)
            return 2
        if request_count > args.max_requests:
            print(
                f"Benchmark would send {request_count} chat requests, above "
                f"--max-requests={args.max_requests}. Increase --max-requests or lower --limit.",
                file=sys.stderr,
            )
            return 2

        print(f"Testing {len(candidates)} model(s), {len(benchmark_tasks)} task(s) each.")
        results: list[_ModelResult] = []
        for model_index, candidate in enumerate(candidates, start=1):
            model_id = str(candidate["id"])
            model_name = str(candidate.get("name") or model_id)
            print(f"[{model_index}/{len(candidates)}] {model_id}")
            result = await _benchmark_model(
                session=session,
                api_key=api_key,
                model_id=model_id,
                model_name=model_name,
                benchmark_tasks=benchmark_tasks,
                delay_seconds=args.delay,
            )
            results.append(result)

    results = sorted(
        results,
        key=lambda item: (
            -item.score,
            item.average_latency_seconds
            if item.average_latency_seconds is not None
            else float("inf"),
        ),
    )
    payload = _result_payload(results)
    _print_ranking(results)
    if args.output_json:
        _write_json(args.output_json, payload)
        print(f"JSON written to {args.output_json}")
    if args.output_csv:
        _write_csv(args.output_csv, results)
        print(f"CSV written to {args.output_csv}")
    return 0


async def _print_key_info(session: aiohttp.ClientSession, api_key: str) -> None:
    try:
        async with session.get(KEY_INFO_URL, headers=_headers(api_key)) as response:
            text = await response.text()
            if response.status >= 400:
                print(f"Key info unavailable: HTTP {response.status} {_shorten(text, 100)}")
                return
            data = json.loads(text)
    except (TimeoutError, aiohttp.ClientError, json.JSONDecodeError) as exc:
        print(f"Key info unavailable: {exc}")
        return

    key_data = data.get("data", {}) if isinstance(data, dict) else {}
    if not isinstance(key_data, dict):
        print("Key info unavailable: unexpected response shape")
        return
    fields = {
        "is_free_tier": key_data.get("is_free_tier"),
        "limit_remaining": key_data.get("limit_remaining"),
        "usage_daily": key_data.get("usage_daily"),
        "usage": key_data.get("usage"),
    }
    rendered = ", ".join(f"{key}={value}" for key, value in fields.items())
    print(f"Key info: {rendered}")


async def _select_candidates(
    session: aiohttp.ClientSession,
    api_key: str,
    args: argparse.Namespace,
) -> list[dict[str, Any]]:
    if args.models:
        candidates = [{"id": model_id, "name": model_id} for model_id in args.models]
    else:
        candidates = await _fetch_free_models(session, api_key)
        candidates = _sort_models(candidates, args.sort)
        if not args.all:
            candidates = candidates[: max(args.limit, 0)]

    if args.include_router:
        router = {"id": "openrouter/free", "name": "OpenRouter Free Router"}
        candidates = [router, *[model for model in candidates if model.get("id") != router["id"]]]
    return candidates


async def _fetch_free_models(
    session: aiohttp.ClientSession,
    api_key: str,
) -> list[dict[str, Any]]:
    async with session.get(MODELS_URL, headers=_headers(api_key)) as response:
        text = await response.text()
        if response.status >= 400:
            raise RuntimeError(
                f"Failed to fetch models: HTTP {response.status} {_shorten(text, 200)}"
            )
        data = json.loads(text)

    models = data.get("data", []) if isinstance(data, dict) else []
    if not isinstance(models, list):
        return []

    free_models: list[dict[str, Any]] = []
    for model in models:
        if not isinstance(model, dict):
            continue
        model_id = model.get("id")
        if isinstance(model_id, str) and model_id.endswith(":free"):
            free_models.append(model)
    return free_models


def _sort_models(models: list[dict[str, Any]], sort_mode: str) -> list[dict[str, Any]]:
    if sort_mode == "context":
        return sorted(models, key=lambda model: _model_context(model), reverse=True)
    if sort_mode == "id":
        return sorted(models, key=lambda model: str(model.get("id") or ""))
    return sorted(models, key=lambda model: _model_created(model), reverse=True)


async def _benchmark_model(
    session: aiohttp.ClientSession,
    api_key: str,
    model_id: str,
    model_name: str,
    benchmark_tasks: list[_Task],
    delay_seconds: float,
) -> _ModelResult:
    attempts: list[_AttemptResult] = []
    for task_index, task in enumerate(benchmark_tasks):
        if task_index > 0 and delay_seconds > 0:
            await asyncio.sleep(delay_seconds)
        attempts.append(await _run_task(session, api_key, model_id, task))

    success_count = sum(1 for attempt in attempts if attempt.error is None)
    latencies = [
        attempt.latency_seconds
        for attempt in attempts
        if attempt.latency_seconds is not None and attempt.error is None
    ]
    average_latency = statistics.fmean(latencies) if latencies else None
    return _ModelResult(
        model=model_id,
        name=model_name,
        score=sum(attempt.score for attempt in attempts) / len(benchmark_tasks),
        success_count=success_count,
        failure_count=len(attempts) - success_count,
        average_latency_seconds=average_latency,
        attempts=attempts,
    )


async def _run_task(
    session: aiohttp.ClientSession,
    api_key: str,
    model_id: str,
    task: _Task,
) -> _AttemptResult:
    payload = {
        "model": model_id,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are evaluated by an automated benchmark. Follow the requested "
                    "output schema exactly and do not include markdown fences."
                ),
            },
            {"role": "user", "content": task.prompt},
        ],
        "temperature": 0,
        "max_tokens": task.max_tokens,
    }
    started_at = time.perf_counter()
    try:
        async with session.post(
            CHAT_COMPLETIONS_URL,
            headers=_headers(api_key),
            json=payload,
        ) as response:
            text = await response.text()
            latency = time.perf_counter() - started_at
            if response.status >= 400:
                return _AttemptResult(
                    task=task.name,
                    score=0.0,
                    latency_seconds=latency,
                    note="request failed",
                    error=f"HTTP {response.status}: {_shorten(text, 180)}",
                    response_preview="",
                )
            data = json.loads(text)
    except (TimeoutError, aiohttp.ClientError, json.JSONDecodeError) as exc:
        return _AttemptResult(
            task=task.name,
            score=0.0,
            latency_seconds=None,
            note="request failed",
            error=str(exc),
            response_preview="",
        )

    content = _extract_message_content(data)
    if content is None:
        return _AttemptResult(
            task=task.name,
            score=0.0,
            latency_seconds=latency,
            note="missing assistant content",
            error="unexpected response shape",
            response_preview="",
        )
    score, note = task.grader(content)
    return _AttemptResult(
        task=task.name,
        score=score,
        latency_seconds=latency,
        note=note,
        error=None,
        response_preview=_shorten(content, 160),
    )


def _headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "X-Title": "crypto-monitor-free-model-benchmark",
    }


def _extract_message_content(data: dict[str, Any]) -> str | None:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        return None
    message = first_choice.get("message")
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    return content.strip() if isinstance(content, str) and content.strip() else None


def _extract_json_object(content: str) -> dict[str, Any] | None:
    decoder = json.JSONDecoder()
    for index, character in enumerate(content):
        if character != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(content[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _get_number(data: dict[str, Any] | None, key: str) -> float | None:
    if not data:
        return None
    value = data.get(key)
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _get_string(data: dict[str, Any] | None, key: str) -> str | None:
    if not data:
        return None
    value = data.get(key)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _normalize_word(value: str | None) -> str:
    if value is None:
        return ""
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def _normalize_label(value: str | None) -> str:
    normalized = _normalize_word(value)
    normalized = normalized.replace("apples", "apple").replace("oranges", "orange")
    mixed_aliases = {
        "apple_and_orange",
        "apple+orange",
        "orange+apple",
        "mixed",
        "both",
    }
    if normalized in mixed_aliases:
        return "apple+orange"
    return normalized


def _model_context(model: dict[str, Any]) -> int:
    context = model.get("context_length")
    return int(context) if isinstance(context, int | float) else 0


def _model_created(model: dict[str, Any]) -> int:
    created = model.get("created")
    return int(created) if isinstance(created, int | float) else 0


def _shorten(value: str, max_length: int = 120) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= max_length:
        return normalized
    return f"{normalized[: max_length - 3]}..."


def _result_payload(results: list[_ModelResult]) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "tasks": [task.name for task in _tasks()],
        "results": [asdict(result) for result in results],
    }


def _print_ranking(results: list[_ModelResult]) -> None:
    rows = []
    for rank, result in enumerate(results, start=1):
        latency = (
            f"{result.average_latency_seconds:.2f}s"
            if result.average_latency_seconds is not None
            else "n/a"
        )
        rows.append(
            [
                str(rank),
                f"{result.score * 100:.1f}",
                f"{result.success_count}/{result.success_count + result.failure_count}",
                latency,
                result.model,
            ],
        )

    headers = ["rank", "score", "ok", "avg_latency", "model"]
    widths = [
        max(len(row[column_index]) for row in [headers, *rows])
        for column_index in range(len(headers))
    ]
    print("\nRanking")
    print("  ".join(header.ljust(widths[index]) for index, header in enumerate(headers)))
    for row in rows:
        print("  ".join(value.ljust(widths[index]) for index, value in enumerate(row)))

    if results:
        print("\nTop model task notes")
        top = results[0]
        for attempt in top.attempts:
            status = "error" if attempt.error else f"{attempt.score * 100:.0f}%"
            detail = attempt.error or attempt.note
            print(f"- {attempt.task}: {status} ({detail})")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_csv(path: Path, results: list[_ModelResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file_obj:
        writer = csv.DictWriter(
            file_obj,
            fieldnames=[
                "rank",
                "model",
                "name",
                "score",
                "success_count",
                "failure_count",
                "average_latency_seconds",
            ],
        )
        writer.writeheader()
        for rank, result in enumerate(results, start=1):
            writer.writerow(
                {
                    "rank": rank,
                    "model": result.model,
                    "name": result.name,
                    "score": f"{result.score:.4f}",
                    "success_count": result.success_count,
                    "failure_count": result.failure_count,
                    "average_latency_seconds": (
                        f"{result.average_latency_seconds:.4f}"
                        if result.average_latency_seconds is not None
                        else ""
                    ),
                },
            )


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
