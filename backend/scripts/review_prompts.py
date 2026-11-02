"""Produce an inspectable Prompt change review from committed source.

No model calls, banking session, .env values or runtime customer data are read.
Use before approving a Prompt/response-policy change:
    uv run python scripts/review_prompts.py --base <commit> --output ../docs/prompt-reviews/<name>.md
"""
from __future__ import annotations

import argparse
import ast
import difflib
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

REPO = Path(__file__).resolve().parents[2]
PROMPTS_FILE = "backend/app/agent/prompts.py"
PROMPT_NAMES = ("SYSTEM_PROMPT", "GUARD_SYSTEM_PROMPT", "RESPONSE_RECOVERY_PROMPT")
REVIEW_PATHS = (
    "backend/app/agent/prompts.py",
    "backend/app/agent/prompt_assembly.py",
    "backend/app/agent/context_assembly.py",
    "backend/app/agent/response_policy.py",
    "backend/app/agent/response_recovery.py",
    "backend/app/agent/read_completion.py",
    "backend/app/agent/financial_summary.py",
    "backend/app/agent/compound_read_summary.py",
    "backend/app/agent/read_result_recovery.py",
    "backend/app/agent/loop.py",
    "backend/app/agent/guard.py",
    "backend/app/services/intent_service.py",
    "backend/app/services/chat_turn.py",
    "backend/app/services/chat_messages.py",
    "backend/app/schemas/tool_results.py",
    "backend/app/tools/register.py",
    "backend/app/tools/account_tools.py",
    "backend/app/tools/subscription_tools.py",
    "backend/app/services/subscription_service.py",
    "backend/app/tools/presentation.py",
    "backend/app/risk/injection.py",
    "backend/app/api/routes/chat.py",
    "backend/app/agent/llm.py",
)


def git(*args: str) -> str:
    process = subprocess.run(
        ["git", "-C", str(REPO), "--no-pager", *args],
        capture_output=True, text=True, encoding="utf-8",
    )
    if process.returncode:
        raise RuntimeError(f"git failed (code {process.returncode}): {' '.join(args)}")
    return process.stdout


def extract_literals(source: str) -> dict[str, str]:
    """Only inspect static prompt literals; never eval source."""
    module = ast.parse(source)
    values: dict[str, str] = {}
    for stmt in module.body:
        if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Constant):
            for target in stmt.targets:
                if (isinstance(target, ast.Name)
                        and target.id in PROMPT_NAMES
                        and isinstance(stmt.value.value, str)):
                    values[target.id] = stmt.value.value
    if set(values) != set(PROMPT_NAMES):
        raise ValueError("Expected three static, explicitly named system prompts")
    return values


def manifest_for_source(source: str) -> dict[str, str]:
    values = extract_literals(source)
    return {key: sha256(values[key].encode("utf-8")).hexdigest()[:16]
            for key in PROMPT_NAMES}


def runtime_versions() -> dict[str, str]:
    sys.path.insert(0, str(REPO / "backend"))
    from app.agent.prompt_assembly import (
        assemble_agent_prompt, assemble_guard_prompt, assemble_recovery_prompt,
    )
    from app.agent.tool_executor import required_intent_tool
    from app.tools.register import create_agent_registry
    # Explicitly enumerated supported intents. An unknown action must never be
    # passed to the real prompt assembly by this review helper.
    actions = ("transfer", "internal_transfer", "collect",
               "purchase", "redeem", "convert")
    versions = {
        "agent": assemble_agent_prompt().version,
        "guard": assemble_guard_prompt().version,
        "recovery": assemble_recovery_prompt().version,
    }
    for action in actions:
        if required_intent_tool(action) is None:
            raise ValueError("Expected validated intent tool is missing: " + action)
        versions["agent:" + action] = assemble_agent_prompt(
            verified_intent_action=action,
        ).version
    # Registry descriptions and schemas are prompts presented to the model,
    # even though they are not part of the main System Prompt text.
    registry = create_agent_registry()
    contracts = []
    for schema in registry.definitions():
        spec = registry.get(schema["function"]["name"])
        if spec is None:
            raise ValueError("Missing Tool spec")
        contracts.append({
            "schema": schema,
            "risk": spec.risk.value,
            "execution": spec.execution.value,
        })
    encoded = json.dumps(contracts, ensure_ascii=False, sort_keys=True)
    versions["tools"] = "tools:" + sha256(encoded.encode("utf-8")).hexdigest()[:16]
    # Deterministic response policies are also user-visible behavioral assets.
    # Track these targeted files without forcing every unrelated Runtime change
    # to update the Prompt review baseline.
    for label, relative in (
        ("reply_policy", "backend/app/agent/response_policy.py"),
        ("recovery_policy", "backend/app/agent/response_recovery.py"),
        ("read_completion", "backend/app/agent/read_completion.py"),
        ("grounded_summary", "backend/app/agent/financial_summary.py"),
        ("compound_read_summary", "backend/app/agent/compound_read_summary.py"),
        ("read_result_recovery", "backend/app/agent/read_result_recovery.py"),
        ("agent_loop", "backend/app/agent/loop.py"),
    ):
        source = (REPO / relative).read_text(encoding="utf-8").replace("\r\n", "\n")
        versions[label] = label + ":" + sha256(source.encode("utf-8")).hexdigest()[:16]
    scope_sources = (
        "backend/app/tools/account_tools.py",
        "backend/app/tools/subscription_tools.py",
        "backend/app/services/subscription_service.py",
    )
    scope_bytes = "\n".join(
        (REPO / relative).read_text(encoding="utf-8").replace("\r\n", "\n")
        for relative in scope_sources
    ).encode("utf-8")
    versions["scope_contract"] = "scope_contract:" + sha256(scope_bytes).hexdigest()[:16]
    snapshot_files = (
        "backend/app/schemas/tool_results.py",
        "backend/app/services/chat_messages.py",
        "backend/app/services/chat_turn.py",
    )
    snapshot_bytes = "\n".join(
        (REPO / relative).read_text(encoding="utf-8").replace("\r\n", "\n")
        for relative in snapshot_files
    ).encode("utf-8")
    versions["snapshot_contract"] = "snapshot_contract:" + sha256(snapshot_bytes).hexdigest()[:16]
    return versions


def render_review(base: str) -> str:
    base_commit = git("rev-parse", "--verify", base + "^{commit}").strip()
    head = git("rev-parse", "--verify", "HEAD").strip()
    old_source = git("show", f"{base_commit}:{PROMPTS_FILE}")
    new_source = (REPO / PROMPTS_FILE).read_text(encoding="utf-8")
    before, after = extract_literals(old_source), extract_literals(new_source)
    versions = runtime_versions()
    lines = [
        "# 小We Prompt Change Review（自动生成草稿）",
        "",
        f"- 基准 Commit：`{base_commit}`",
        f"- 当前 HEAD：`{head}`（包含工作区内相关未提交修改）",
        "- 范围：静态 System/Guard/Recovery Prompt、动态装配及与行为有关的硬编码策略。",
        "- 安全：只读取 Git 源码和本地静态 Prompt；不访问银行数据库、密钥或模型 API。",
        "- 审核状态：**待人工填写 UX 决策与行为证据；此文档不代表批准修改。**",
        "",
        "## 1. 静态 System Prompt — Before / After",
        "",
        "| 角色 | Before SHA-256 前16位 | After SHA-256 前16位 | 是否变化 |",
        "|---|---|---|---|",
    ]
    for name in PROMPT_NAMES:
        old_hash = sha256(before[name].encode("utf-8")).hexdigest()[:16]
        new_hash = sha256(after[name].encode("utf-8")).hexdigest()[:16]
        lines.append(
            f"| `{name}` | `{old_hash}` | `{new_hash}` | "
            + ("是" if old_hash != new_hash else "否") + " |"
        )
    lines.extend(["", "### 静态 Prompt 原文差异", ""])
    for name in PROMPT_NAMES:
        patch = "\n".join(line.rstrip() for line in difflib.unified_diff(
            before[name].splitlines(), after[name].splitlines(),
            fromfile=name + " (Before)", tofile=name + " (After)", lineterm="",
            n=1,
        ))
        lines.append(f"**{name}**")
        lines.append("")
        lines.append("```diff")
        lines.append(patch or "(无变化)")
        lines.append("```")
        lines.append("")
    lines.extend([
        "## 2. 当前实际装配版本（不是模型表现评测）", "",
        "| 装配入口 | Version |", "|---|---|",
    ])
    for key, value in sorted(versions.items()):
        lines.append(f"| `{key}` | `{value}` |")
    lines.extend(["", "## 3. 关联行为代码的 Git 差异", ""])
    patch = git("diff", "--no-ext-diff", "--unified=1", base_commit, "--", *REVIEW_PATHS)
    lines.extend(["```diff", patch.rstrip() or "(无变化)", "```", ""])
    lines.extend([
        "## 4. 人工审查（在批准前填写）", "",
        "- **修改意图与设计依据：** 待填写。",
        "- **影响的用户路径 / UI 可发现性：** 待填写。",
        "- **替代方案及 UX 取舍：** 待填写。",
        "- **安全/权限/可信事实不变量：** 待填写。",
        "- **同场景对照（固定输入、模型、工具轨迹、最终回复）：** 待填写。",
        "- **回滚方案与决策人：** 待填写。",
        "",
        "> 提醒：自动测试通过仅代表现有代码契约成立；不代表 UX 设计已经获批。",
        "",
    ])
    # Markdown review files must pass git diff --check. Some source patches
    # encode whitespace-only context as "+ "; normalize display whitespace
    # without changing the original files or semantic diff content.
    return "\n".join(line.rstrip() for line in "\n".join(lines).splitlines()) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="base Git revision")
    parser.add_argument("--output", type=Path, help="optional Markdown review output")
    parser.add_argument("--manifest-output", type=Path,
                        help="optional current prompt-version JSON snapshot")
    args = parser.parse_args()
    review = render_review(args.base)
    if args.output:
        path = args.output if args.output.is_absolute() else Path.cwd() / args.output
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(review, encoding="utf-8")
        print(f"Review saved: {path}")
    else:
        print(review)
    if args.manifest_output:
        path = (args.manifest_output if args.manifest_output.is_absolute()
                else Path.cwd() / args.manifest_output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "source_revision": git("rev-parse", "HEAD").strip(),
            "static_prompts": manifest_for_source(
                (REPO / PROMPTS_FILE).read_text(encoding="utf-8"),
            ),
            "effective_versions": runtime_versions(),
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Manifest saved: {path}")


if __name__ == "__main__":
    main()
