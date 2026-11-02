# 小We Prompt Change Review（自动生成草稿）

- 基准 Commit：`a8f00fb9c5ab78725c4871858be54a54c2ef371e`
- 当前 HEAD：`a8f00fb9c5ab78725c4871858be54a54c2ef371e`（包含工作区内相关未提交修改）
- 范围：静态 System/Guard/Recovery Prompt、动态装配及与行为有关的硬编码策略。
- 安全：只读取 Git 源码和本地静态 Prompt；不访问银行数据库、密钥或模型 API。
- 审核状态：**待人工填写 UX 决策与行为证据；此文档不代表批准修改。**

## 1. 静态 System Prompt — Before / After

| 角色 | Before SHA-256 前16位 | After SHA-256 前16位 | 是否变化 |
|---|---|---|---|
| `SYSTEM_PROMPT` | `976ac34290cb8a39` | `976ac34290cb8a39` | 否 |
| `GUARD_SYSTEM_PROMPT` | `03e814d7bb7ea71d` | `03e814d7bb7ea71d` | 否 |
| `RESPONSE_RECOVERY_PROMPT` | `b6fe66023300d62a` | `b6fe66023300d62a` | 否 |

### 静态 Prompt 原文差异

**SYSTEM_PROMPT**

```diff
(无变化)
```

**GUARD_SYSTEM_PROMPT**

```diff
(无变化)
```

**RESPONSE_RECOVERY_PROMPT**

```diff
(无变化)
```

## 2. 当前实际装配版本（不是模型表现评测）

| 装配入口 | Version |
|---|---|
| `agent` | `agent:976ac34290cb8a39` |
| `agent:collect` | `agent:cb004ee5d68762a7` |
| `agent:convert` | `agent:67b9da4bc7f8c6ba` |
| `agent:internal_transfer` | `agent:5f88f97514f7cec4` |
| `agent:purchase` | `agent:293f98322a40e2ce` |
| `agent:redeem` | `agent:99b476628139c9cc` |
| `agent:transfer` | `agent:5702dbd3ebea98b6` |
| `agent_loop` | `agent_loop:a3eefbc744f7e69b` |
| `chat_request_recovery` | `chat_request_recovery:7f69cdc969238d95` |
| `compound_read_summary` | `compound_read_summary:4a8ba5eebfd1587f` |
| `grounded_summary` | `grounded_summary:914aba9adc782878` |
| `guard` | `guard:03e814d7bb7ea71d` |
| `read_completion` | `read_completion:6d839f7daa46db59` |
| `read_result_recovery` | `read_result_recovery:74e3bc01f24acef4` |
| `recovery` | `recovery:b6fe66023300d62a` |
| `recovery_policy` | `recovery_policy:1614c9f9d00ace67` |
| `reply_policy` | `reply_policy:151e5a792f70e031` |
| `scope_contract` | `scope_contract:d5d1151bd5920a21` |
| `snapshot_contract` | `snapshot_contract:07a0f81d7cc55634` |
| `tool_executor` | `tool_executor:57745137ae0a760d` |
| `tools` | `tools:ccd9da728d8535d0` |

## 3. 关联行为代码的 Git 差异

```diff
diff --git a/backend/app/agent/context_assembly.py b/backend/app/agent/context_assembly.py
index a0b91d1..f132e45 100644
--- a/backend/app/agent/context_assembly.py
+++ b/backend/app/agent/context_assembly.py
@@ -19,3 +19,3 @@ NoteSource = Literal[
     "validated_intent", "verified_object", "temporary_phone_reference",
-    "trusted_bill_context", "readonly_selection",
+    "trusted_bill_context", "readonly_selection", "trusted_view_context",
 ]
@@ -24,3 +24,3 @@ _ALLOWED_NOTE_SOURCES = frozenset((
     "validated_intent", "verified_object", "temporary_phone_reference",
-    "trusted_bill_context", "readonly_selection",
+    "trusted_bill_context", "readonly_selection", "trusted_view_context",
 ))
diff --git a/backend/app/agent/loop.py b/backend/app/agent/loop.py
index 3fae322..d1f4ae0 100644
--- a/backend/app/agent/loop.py
+++ b/backend/app/agent/loop.py
@@ -57,3 +57,4 @@ class AgentLoop:
                      original_request: str | None = None,
-                     conversation_id: int | None = None) -> AsyncIterator[AgentEvent]:
+                     conversation_id: int | None = None,
+                     view_selection: dict[str, Any] | None = None) -> AsyncIterator[AgentEvent]:
         # One canonical system-prompt assembly. Intent is already verified
@@ -64,2 +65,10 @@ class AgentLoop:
         messages.extend(history)
+        # A selected view contains a server-verified aggregate that can answer
+        # a narrow follow-up without another bank query or model-authored facts.
+        from app.agent.view_followup import render_view_followup
+        view_reply = (render_view_followup(original_request or "", view_selection)
+                      if intent_action is None else None)
+        if view_reply is not None:
+            yield AgentEvent("delta", {"text": view_reply})
+            return
         registry = create_agent_registry()
diff --git a/backend/app/agent/read_completion.py b/backend/app/agent/read_completion.py
index 56fb478..9f9391d 100644
--- a/backend/app/agent/read_completion.py
+++ b/backend/app/agent/read_completion.py
@@ -29,3 +29,3 @@ _OTHER_GOALS = (
     "计算", "算出", "算一下", "手续费", "利息",
-    "逐笔", "每笔", "分类", "类别", "异常", "识别",
+    "逐笔", "每笔", "异常", "识别",
     "为什么", "原因", "解释", "建议", "推荐", "预测", "趋势",
@@ -66,2 +66,20 @@ def completed_readonly_summary(
         return None
+    wants_categories = any(cue in request for cue in ("分类", "类别"))
+    if wants_categories:
+        # A monthly aggregate supports displaying category totals, not
+        # transaction details, rankings, proportions or causal analysis.
+        if any(cue in request for cue in ("占比", "比例", "排行", "排名", "最多", "最少",
+                                           "最高", "最低", "明细", "详情", "筛选", "过滤",
+                                           "只看", "仅看", "单独", "选中", "指定", "商户")):
+            return None
+        bills = [result.get("data") for tool, result in results if tool == "get_monthly_bill"]
+        if not bills or any(
+            not isinstance(data, dict) or not isinstance(data.get("categories"), list)
+            or any(not isinstance(row, dict) or not isinstance(row.get("category"), str)
+                   or type(row.get("amount_fen")) is not int or row["amount_fen"] < 0
+                   or type(row.get("count")) is not int or row["count"] < 0
+                   for row in data["categories"])
+            for data in bills
+        ):
+            return None
     # Two explicitly named months require more evidence than one result card.
@@ -91,3 +109,4 @@ def completed_readonly_summary(
     if wants_bill:
-        return "账单已查询，明细见下方结果卡。"
+        return ("账单已查询，消费分类汇总见下方结果卡。" if wants_categories
+                else "账单已查询，明细见下方结果卡。")
     return "银行卡状态已查询，详见下方卡片。"
diff --git a/backend/app/agent/tool_executor.py b/backend/app/agent/tool_executor.py
index 25bc367..54d2fb0 100644
--- a/backend/app/agent/tool_executor.py
+++ b/backend/app/agent/tool_executor.py
@@ -60,2 +60,5 @@ class VerifiedToolContext:
     intent_amount_fen: int | None = None
+    # Internal server identity for trusted result provenance; never serialized
+    # into model messages or client events.
+    verified_account_id: int | None = None

@@ -308,2 +311,5 @@ class ToolExecutor:
             )
+        # Tool handlers may attach server-only provenance for Chat persistence.
+        # Remove it before the observation is returned to the model.
+        trusted_metadata = result.pop("_trusted_metadata", None) if isinstance(result, dict) else None
         # Hide sensitive fields before both model observations and client read cards.
@@ -311,3 +317,11 @@ class ToolExecutor:
         if spec is not None and spec.name == "get_monthly_bill" and result.get("ok") and isinstance(result.get("data"), dict):
-            events.append(ToolClientEvent("bill_result", {"data": result["data"]}))
+            event_data: dict[str, Any] = {"data": result["data"]}
+            if (isinstance(trusted_metadata, dict)
+                    and set(trusted_metadata) == {"account_id"}
+                    and type(trusted_metadata.get("account_id")) is int
+                    and trusted_metadata["account_id"] > 0):
+                event_data["trusted_metadata"] = {
+                    "account_id": trusted_metadata["account_id"],
+                }
+            events.append(ToolClientEvent("bill_result", event_data))
         if spec is not None and spec.name == "get_card_status" and result.get("ok"):
diff --git a/backend/app/api/routes/chat.py b/backend/app/api/routes/chat.py
index 311f73a..ed4e7bb 100644
--- a/backend/app/api/routes/chat.py
+++ b/backend/app/api/routes/chat.py
@@ -173,2 +173,15 @@ async def send_message(
     conversation = _require_conversation(session, user, conversation_id)
+    view_snapshot = None
+    if payload.view_context is not None:
+        from app.services.view_service import ViewConflict, ViewNotFound, load_view_snapshot
+        try:
+            view_snapshot = load_view_snapshot(
+                session, user_id=user.id, conversation_id=conversation_id,
+                view_id=payload.view_context.view_id,
+                revision=payload.view_context.revision, validate_sources=True,
+            )
+        except ViewNotFound:
+            raise HTTPException(status_code=404, detail="视图不可用") from None
+        except ViewConflict:
+            raise HTTPException(status_code=409, detail="视图数据来源不可用，请重新查询") from None

@@ -220,2 +233,19 @@ async def send_message(

+    view_account_ids = {
+        item["metadata"]["account_id"] for item in (view_snapshot.trusted_results if view_snapshot else [])
+        if item["kind"] == "monthly_bill"
+    }
+    if selected_account is not None and view_account_ids and selected_account.id not in view_account_ids:
+        raise HTTPException(status_code=400, detail="所选账户与分析视图不一致，请重新选择")
+    if selected_card is not None and view_account_ids and selected_card[1].id not in view_account_ids:
+        raise HTTPException(status_code=400, detail="所选银行卡与分析视图不一致，请重新选择")
+    if (view_snapshot is not None and len(view_account_ids) == 1 and selected_account is None
+            and payload.intent is None and allow_readonly_followup(payload.content)):
+        selected_account = session.exec(select(Account).where(
+            Account.id == next(iter(view_account_ids)), Account.user_id == user.id,
+            Account.status == "active", Account.currency == "CNY")).first()
+        if selected_account is None:
+            raise HTTPException(status_code=409, detail="视图账户不可用，请重新查询")
+        reused_readonly_selection = True
+
     if selected_account is not None and selected_card is not None and selected_card[1].id != selected_account.id:
@@ -226,2 +256,16 @@ async def send_message(
     injection = detect_injection(display_content)
+    view_selection = None
+    if view_snapshot is not None and not injection.blocked:
+        from app.services.trusted_ui_results import resolve_view_selection_context
+        view_selection = resolve_view_selection_context(
+            trusted_results=view_snapshot.trusted_results,
+            selected_category_id=view_snapshot.envelope.interaction_state.selected_category,
+            selected_ids=view_snapshot.envelope.interaction_state.selected_ids,
+        )
+        if view_selection:
+            trusted_notes.append(TrustedContextNote(
+                source="trusted_view_context",
+                content="[服务端核验的只读视图选择，非金融操作授权："
+                        + json.dumps(view_selection, ensure_ascii=False) + "]",
+            ))
     intent_prompt = None
@@ -246,3 +290,4 @@ async def send_message(
                 request_id=payload.request_id,
-                payload_digest=fingerprint(payload.content, payload.references, payload.intent),
+                payload_digest=fingerprint(payload.content, payload.references, payload.intent,
+                                           payload.view_context),
             )
@@ -358,2 +403,3 @@ async def send_message(
             session.rollback()
+            advance_submission(submission_id=submission_id, state="failed")
             raise HTTPException(status_code=503, detail="对象引用服务暂时不可用") from None
@@ -405,2 +451,6 @@ async def send_message(
             verified_account_token=verified_account_token,
+            verified_account_id=(
+                selected_account.id if selected_account is not None else
+                selected_card[1].id if selected_card is not None else None
+            ),
             verified_card_id=verified_card_id,
@@ -419,2 +469,4 @@ async def send_message(
         intent_needs_amount=intent_needs_amount,
+        view_snapshot=view_snapshot,
+        view_selection=view_selection,
     )
diff --git a/backend/app/services/chat_messages.py b/backend/app/services/chat_messages.py
index 75ebfe1..e4b60d3 100644
--- a/backend/app/services/chat_messages.py
+++ b/backend/app/services/chat_messages.py
@@ -6,4 +6,5 @@ from app.core.time import utcnow
 from app.db.session import session_scope
-from app.models import Conversation, Message, MessageResult, ChatSubmission
+from app.models import Conversation, Message, MessageResult, MessageView, ChatSubmission
 from app.schemas.chat import MessageOut
+from app.schemas.generative_ui import ViewEnvelope
 from app.schemas.tool_results import ToolResultBundle, ToolResultItem
@@ -19,2 +20,3 @@ def present_message(
     snapshot: MessageResult | None | object = _UNSET_SNAPSHOT,
+    view_snapshots: dict[int, object] | None = None,
 ) -> MessageOut:
@@ -23,2 +25,8 @@ def present_message(
         return output
+    if view_snapshots is None:
+        from app.services.view_service import load_views_for_messages
+        view_snapshots = load_views_for_messages(session, [message])
+    view = view_snapshots.get(message.id)
+    if view is not None:
+        output = output.model_copy(update={"ui_view": view.model_dump(mode="json")})
     if snapshot is _UNSET_SNAPSHOT:
@@ -49,3 +57,4 @@ def persist_assistant(conversation_id: int, content: str,
                        tool_results: list[dict] | None = None,
-                       submission_id: int | None = None) -> dict | None:
+                      submission_id: int | None = None, *, finalize: bool = True,
+                      view: ViewEnvelope | None = None) -> dict | None:
     if not content and not (tool_results or bill_result or card_result):
@@ -79,2 +88,7 @@ def persist_assistant(conversation_id: int, content: str,
                 ciphertext=ciphertext, key_version=key_version))
+        if view is not None:
+            if view.conversation_id != conversation_id:
+                raise RuntimeError("View ownership invariant failed")
+            session.add(MessageView(message_id=message.id, view_id=view.view_id,
+                                    revision=view.revision))
         if submission_id is not None:
@@ -88,3 +102,3 @@ def persist_assistant(conversation_id: int, content: str,
             # state with "completed".
-            if submission.state != "action_pending":
+            if finalize and submission.state != "action_pending":
                 submission.state = "completed"
@@ -97,2 +111,27 @@ def persist_assistant(conversation_id: int, content: str,

+def finalize_assistant(conversation_id: int, message_id: int, *,
+                       submission_id: int | None = None, view=None) -> dict:
+    """Complete a saved reply after optional view generation."""
+    with session_scope() as session:
+        message = session.get(Message, message_id)
+        if message is None or message.conversation_id != conversation_id or message.role != "assistant":
+            raise RuntimeError("Assistant message ownership invariant failed")
+        if view is not None:
+            from app.models import MessageView
+            if view.conversation_id != conversation_id:
+                raise RuntimeError("View ownership invariant failed")
+            session.add(MessageView(message_id=message_id, view_id=view.view_id, revision=view.revision))
+        if submission_id is not None:
+            submission = session.get(ChatSubmission, submission_id)
+            if (submission is None or submission.conversation_id != conversation_id
+                    or submission.assistant_message_id != message_id):
+                raise RuntimeError("Chat submission ownership invariant failed")
+            if submission.state != "action_pending":
+                submission.state = "completed"
+            submission.updated_at = utcnow()
+            session.add(submission)
+        session.commit()
+        return present_message(session, message).model_dump(mode="json")
+
+
 def present_messages(session: Session, messages: list[Message]) -> list[MessageOut]:
@@ -111,3 +150,6 @@ def present_messages(session: Session, messages: list[Message]) -> list[MessageO
         })
-    return [present_message(session, message, snapshot=snapshots.get(message.id))
+    from app.services.view_service import load_views_for_messages
+    views = load_views_for_messages(session, messages)
+    return [present_message(session, message, snapshot=snapshots.get(message.id),
+                            view_snapshots=views)
             for message in messages]
diff --git a/backend/app/services/chat_turn.py b/backend/app/services/chat_turn.py
index 6c4d75d..f748871 100644
--- a/backend/app/services/chat_turn.py
+++ b/backend/app/services/chat_turn.py
@@ -7,3 +7,5 @@ from dataclasses import dataclass
 from typing import Any, TypeVar
+from uuid import uuid4

+from pydantic import ValidationError
 from app.agent.loop import AgentLoop
@@ -14,3 +16,6 @@ from app.schemas.tool_results import InternalTransferReceipt
 from app.services.audit_service import conversation_context, record_separately
-from app.services.chat_messages import persist_assistant
+from app.services.chat_messages import persist_assistant, finalize_assistant
+from app.core.config import settings
+from app.core.time import utcnow
+from app.agent.ui_composer import get_ui_composer
 from app.services.chat_submissions import advance_submission
@@ -20,2 +25,13 @@ logger = logging.getLogger(__name__)
 EventT = TypeVar("EventT")
+_SAFE_VIEW_VALIDATION_REASONS = frozenset({
+    "view root does not exist", "view contains too many elements",
+    "unsupported view component", "component props do not match its catalog schema",
+    "view children must be unique within a parent", "leaf components cannot contain children",
+    "view child does not exist", "unsupported section title", "unsupported action link",
+    "metric reference does not exist", "dataset reference does not exist",
+    "dataset reference has the wrong semantic kind", "data reference is not bound to a result",
+    "view nesting is too deep", "view graph contains a cycle",
+    "view components may have only one parent", "view root cannot have a parent",
+    "view contains unreachable elements",
+})

@@ -34,2 +50,4 @@ class ChatTurn:
     intent_needs_amount: bool = False
+    view_snapshot: Any = None
+    view_selection: dict | None = None

@@ -54,5 +72,7 @@ async def stream_chat_turn(
                      cards: dict | None = None,
-                     results: list[dict] | None = None) -> dict | None:
+                     results: list[dict] | None = None,
+                     view=None) -> dict | None:
         return persist_assistant(
-            conversation_id, content, bill, cards, results, submission_id=submission_id
+            conversation_id, content, bill, cards, results,
+            submission_id=submission_id, view=view,
         )
@@ -62,2 +82,5 @@ async def stream_chat_turn(
     trusted_results: list[dict] = []
+    ui_results: list[dict] = []
+    saved_message: dict | None = None
+    action_pending = False
     audit_token = conversation_context.set(conversation_id)
@@ -91,2 +114,3 @@ async def stream_chat_turn(
             conversation_id=conversation_id,
+            **({"view_selection": turn.view_selection} if turn.view_selection else {}),
         ):
@@ -110,2 +134,17 @@ async def stream_chat_turn(
                 trusted_results.append({"kind": "monthly_bill", "data": trusted_bill})
+                metadata = event.data.get("trusted_metadata")
+                account_id = None
+                if (type(turn.verified.verified_account_id) is int
+                        and turn.verified.verified_account_id > 0):
+                    # The authenticated route identity is authoritative: the
+                    # executor rebinds this bill call to that account token.
+                    account_id = turn.verified.verified_account_id
+                elif isinstance(metadata, dict):
+                    candidate_id = metadata.get("account_id")
+                    if type(candidate_id) is int and candidate_id > 0:
+                        account_id = candidate_id
+                if type(account_id) is int and account_id > 0:
+                    ui_results.append({"kind": "monthly_bill", "data": trusted_bill,
+                                       "metadata": {"account_id": account_id},
+                                       "result_ref": uuid4().hex, "observed_at": utcnow().isoformat()})
                 yield encode({"type": "bill_result", "data": trusted_bill})
@@ -145,2 +184,3 @@ async def stream_chat_turn(
             elif event.type == "action_required":
+                action_pending = True
                 pending = event.data.get("action") or {}
@@ -165,7 +205,60 @@ async def stream_chat_turn(
                 yield encode({"type": "delta", "text": explanation})
-                yield encode({"type": "done", "message": finish_reply(
-                    "".join(collected), trusted_bill, trusted_cards, trusted_results)})
-                return
+                # Preserve the verified results through the normal persistence
+                # and optional view composition path below.
+                break

-        message = finish_reply("".join(collected), trusted_bill, trusted_cards, trusted_results)
+        if ui_results and not action_pending:
+            # Persist the trustworthy bank result before any model presentation work.
+            saved_message = persist_assistant(conversation_id, "".join(collected), trusted_bill,
+                                              trusted_cards, trusted_results,
+                                              submission_id=submission_id, finalize=False)
+            view = None
+            if settings.generative_ui_enabled:
+                try:
+                    from app.services.view_service import (prepare_view_composition,
+                        create_or_append_view, view_context_for_composer)
+                    combined, catalog = prepare_view_composition(turn.view_snapshot, ui_results)
+                    yield encode({"type": "ui_status", "status": "composing"})
+                    spec = await get_ui_composer().compose(
+                        question=turn.original_request, catalog=catalog,
+                        context=view_context_for_composer(turn.view_snapshot))
+                    if spec is not None:
+                        view = create_or_append_view(user_id=user_id, conversation_id=conversation_id,
+                                                     results=combined, spec=spec, context=turn.view_snapshot)
+                except ValidationError as exc:
+                    reasons = set()
+                    for error in exc.errors(include_input=False):
+                        reason = str(error.get("ctx", {}).get("error", ""))
+                        reasons.add(reason if reason in _SAFE_VIEW_VALIDATION_REASONS else "schema_validation")
+                    logger.warning("view composition rejected: %s", ", ".join(sorted(reasons)))
+                except Exception as exc:
+                    logger.warning("view composition failed: %s", type(exc).__name__)
+            if saved_message is not None:
+                try:
+                    message = finalize_assistant(conversation_id, saved_message["id"],
+                                                 submission_id=submission_id, view=view)
+                except Exception:
+                    if view is None:
+                        raise
+                    logger.warning("view binding failed; keeping trusted result")
+                    view = None
+                    message = finalize_assistant(conversation_id, saved_message["id"],
+                                                 submission_id=submission_id)
+                if view is None:
+                    yield encode({"type": "ui_status", "status": "fallback"})
+                if view is not None:
+                    yield encode({"type": "ui_view", "view": view.model_dump(mode="json")})
+            else:
+                message = None
+        else:
+            if trusted_bill is not None and not ui_results:
+                yield encode({"type": "ui_status", "status": "fallback",
+                              "reason": "trusted_source_unavailable"})
+            context_view = (
+                turn.view_snapshot.envelope
+                if turn.view_snapshot is not None and not trusted_results and not action_pending
+                else None
+            )
+            message = finish_reply("".join(collected), trusted_bill, trusted_cards,
+                                   trusted_results, view=context_view)
         yield encode({"type": "done", "message": message})
@@ -174,4 +267,10 @@ async def stream_chat_turn(
         # client received completion. Never execute this ID twice.
-        advance_submission(submission_id=submission_id, state="interrupted")
-        persist_assistant(conversation_id, "".join(collected), trusted_bill, trusted_cards, trusted_results)
+        if saved_message is not None:
+            try:
+                finalize_assistant(conversation_id, saved_message["id"], submission_id=submission_id)
+            except Exception:
+                advance_submission(submission_id=submission_id, state="interrupted")
+        else:
+            advance_submission(submission_id=submission_id, state="interrupted")
+            persist_assistant(conversation_id, "".join(collected), trusted_bill, trusted_cards, trusted_results)
         raise
diff --git a/frontend/src/features/chat/useChatController.ts b/frontend/src/features/chat/useChatController.ts
index c9a7690..71e312a 100644
--- a/frontend/src/features/chat/useChatController.ts
+++ b/frontend/src/features/chat/useChatController.ts
@@ -1,3 +1,3 @@
 import { useCallback, useEffect, useRef, useState } from 'react'
-import { ApiError, api, type Conversation, type Health, type Message } from '@/lib/api'
+import { ApiError, api, type ChatViewContext, type Conversation, type Health, type Message } from '@/lib/api'
 import { streamChat, type ChatIntentPayload, type StreamEvent } from '@/lib/sse'
@@ -40,2 +40,5 @@ export function useChatController({ token, actionBlocked, onActionRequired, onAc
   const [streamingText, setStreamingText] = useState('')
+  const [streamingUiStatus, setStreamingUiStatus] = useState<'composing' | 'fallback' | null>(null)
+  const [streamingUiView, setStreamingUiView] = useState<unknown>(null)
+  const [uiStatusByMessage, setUiStatusByMessage] = useState<Record<number, 'fallback'>>({})
   const [loadingMessages, setLoadingMessages] = useState(true)
@@ -233,3 +236,3 @@ export function useChatController({ token, actionBlocked, onActionRequired, onAc
     async (raw: string, references: BankObjectReference[] = [], intent?: ChatIntentPayload,
-           intentDisplay?: string) => {
+           intentDisplay?: string, viewContext?: ChatViewContext) => {
       const content = composeReferenceContext(raw, references)
@@ -242,2 +245,4 @@ export function useChatController({ token, actionBlocked, onActionRequired, onAc
       setStreamingText('')
+      setStreamingUiStatus(null)
+      setStreamingUiView(null)

@@ -271,3 +276,3 @@ export function useChatController({ token, actionBlocked, onActionRequired, onAc
         // A terminal "failed" state still does NOT prove no write happened.
-        const signature = JSON.stringify([conversationId, content, references.map(ref => [ref.kind, ref.id]), intent ?? null])
+        const signature = JSON.stringify([conversationId, content, references.map(ref => [ref.kind, ref.id]), intent ?? null, viewContext ?? null])
         const earlier = pendingRequest.current?.signature === signature ? pendingRequest.current : null
@@ -333,2 +338,5 @@ export function useChatController({ token, actionBlocked, onActionRequired, onAc
         let receivedDone = false
+        let pendingUiStatus: 'composing' | 'fallback' | null = null
+        let pendingUiView: unknown = null
+        const pendingSubscriptionResults: Array<{ kind: 'subscriptions' | 'subscription_candidates'; data: unknown }> = []

@@ -343,2 +351,3 @@ export function useChatController({ token, actionBlocked, onActionRequired, onAc
           intent,
+          viewContext,
           requestId,
@@ -347,3 +356,12 @@ export function useChatController({ token, actionBlocked, onActionRequired, onAc
             if (!isCurrent()) return
-            if (event.type === 'bill_result') {
+            if (event.type === 'ui_status') {
+              pendingUiStatus = event.status
+              setStreamingUiStatus(event.status)
+            } else if (event.type === 'ui_view') {
+              pendingUiView = event.view
+              setStreamingUiView(event.view)
+            } else if (event.type === 'subscription_result') {
+              if (pendingSubscriptionResults.length < 4)
+                pendingSubscriptionResults.push({ kind: event.kind, data: event.data })
+            } else if (event.type === 'bill_result') {
               if (billResultCard(event.data) && pendingToolResults.length < 8)
@@ -371,6 +389,16 @@ export function useChatController({ token, actionBlocked, onActionRequired, onAc
               if (!event.message) return
-              savedReply = event.message
+              const completedMessage: Message = {
+                ...event.message,
+                ...(event.message.ui_view == null && pendingUiView != null ? { ui_view: pendingUiView } : {}),
+                ...(event.message.subscription_results == null && pendingSubscriptionResults.length
+                  ? { subscription_results: pendingSubscriptionResults }
+                  : {}),
+              }
+              savedReply = completedMessage
               const validated = toolResultListSchema.safeParse(pendingToolResults)
-              if (validated.success && validated.data.length) setToolResultLists(current => ({...current,[event.message!.id]:validated.data}))
-              setMessages((prev) => [...prev, event.message as Message])
+              if (validated.success && validated.data.length) setToolResultLists(current => ({...current,[completedMessage.id]:validated.data}))
+              if (pendingUiStatus === 'fallback') setUiStatusByMessage(current => ({ ...current, [completedMessage.id]: 'fallback' }))
+              setStreamingUiStatus(null)
+              setStreamingUiView(null)
+              setMessages((prev) => [...prev, completedMessage])
             }
@@ -426,2 +454,4 @@ export function useChatController({ token, actionBlocked, onActionRequired, onAc
           setStreamingText('')
+          setStreamingUiStatus(null)
+          setStreamingUiView(null)
         }
@@ -519,3 +549,3 @@ export function useChatController({ token, actionBlocked, onActionRequired, onAc
   function stopReceiving() { receiveController.current?.abort() }
-  return { renameConversation, conversations, activeId, messages, toolResultLists, draft, sending, receiving, streamingText, loadingMessages, loadingOlder, hasOlder, loadOlder, historyUnavailable, creatingConversation, error, health, healthUnavailable, scrollRef, hasNewContent, onScroll, jumpToLatest, openConversation, createConversation, sendMessage, updateDraft, stopReceiving }
+  return { renameConversation, conversations, activeId, messages, toolResultLists, uiStatusByMessage, streamingUiStatus, streamingUiView, draft, sending, receiving, streamingText, loadingMessages, loadingOlder, hasOlder, loadOlder, historyUnavailable, creatingConversation, error, health, healthUnavailable, scrollRef, hasNewContent, onScroll, jumpToLatest, openConversation, createConversation, sendMessage, updateDraft, stopReceiving }
 }
```

## 4. 人工审查（在批准前填写）

- **修改意图与设计依据：** 待填写。
- **影响的用户路径 / UI 可发现性：** 待填写。
- **替代方案及 UX 取舍：** 待填写。
- **安全/权限/可信事实不变量：** 待填写。
- **同场景对照（固定输入、模型、工具轨迹、最终回复）：** 待填写。
- **回滚方案与决策人：** 待填写。

> 提醒：自动测试通过仅代表现有代码契约成立；不代表 UX 设计已经获批。
