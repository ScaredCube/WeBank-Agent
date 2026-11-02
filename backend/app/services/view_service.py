"""Encrypted, immutable revisions of server-composed banking views."""
from dataclasses import dataclass
import hashlib
import json
import secrets
from typing import Any

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.core.time import utcnow
from app.db.session import get_engine, session_scope
from app.models import (
    Account, Conversation, Message, MessageView, UIView, ViewInteraction, ViewRevision,
)
from app.risk.injection import detect_injection
from app.services.redaction import mask_text
from app.schemas.generative_ui import (
    ActionName, InteractionState, ViewEnvelope, ViewInteractionRequest, ViewSpec,
)
from app.services.trusted_ui_results import (
    TrustedResultError, available_actions, build_trusted_data,
    build_composer_catalog, latest_observed_at, validate_trusted_result,
)
from app.services.vault import VaultError, decrypt_result_snapshot, encrypt_result_snapshot


class ViewNotFound(LookupError):
    pass


class ViewConflict(ValueError):
    pass


class InvalidViewInteraction(ValueError):
    pass


@dataclass(frozen=True)
class ViewSnapshot:
    envelope: ViewEnvelope
    trusted_results: list[dict[str, Any]]
    current_revision: int


VIEW_HISTORY_BATCH_SIZE = 200


def _decode_revision(row: ViewRevision, *, view_id: str,
                     conversation_id: int) -> ViewSnapshot:
    try:
        payload = decrypt_result_snapshot(row.ciphertext, row.key_version)
        envelope = ViewEnvelope.model_validate(payload.get("envelope"))
        if (envelope.view_id != view_id or envelope.revision != row.revision
                or envelope.conversation_id != conversation_id):
            raise ValueError("view revision binding mismatch")
        trusted_results = payload.get("trusted_results")
        if not isinstance(trusted_results, list) or not trusted_results:
            raise ValueError("view revision lacks trusted results")
        normalized = [validate_trusted_result(item) for item in trusted_results]
        if set(envelope.result_refs) != {item["result_ref"] for item in normalized}:
            raise ValueError("view result binding mismatch")
        return ViewSnapshot(envelope=envelope, trusted_results=normalized,
                            current_revision=0)
    except (VaultError, ValueError, TypeError, AttributeError, KeyError) as exc:
        raise ViewNotFound("视图版本不可用") from exc


def _validate_sources(session: Session, user_id: int,
                      trusted_results: list[dict[str, Any]]) -> None:
    """Re-check bill provenance using encrypted account IDs, never masked text."""
    for item in trusted_results:
        if item["kind"] != "monthly_bill":
            continue
        account_id = item["metadata"].get("account_id")
        account = session.exec(select(Account).where(
            Account.id == account_id, Account.user_id == user_id,
            Account.status == "active",
        )).first()
        if account is None or account.currency != item["data"]["currency"]:
            raise ViewConflict("账单来源账户已不可核验，请重新查询")


def validate_trusted_result_sources(session: Session, user_id: int,
                                    trusted_results: list[dict[str, Any]]) -> None:
    _validate_sources(session, user_id, trusted_results)


def load_view_snapshot(session: Session, *, user_id: int, view_id: str,
                       revision: int | None = None,
                       conversation_id: int | None = None,
                       validate_sources: bool = False) -> ViewSnapshot:
    view = session.exec(select(UIView).where(
        UIView.id == view_id, UIView.user_id == user_id,
    )).first()
    if view is None or (conversation_id is not None and view.conversation_id != conversation_id):
        raise ViewNotFound("视图不存在")
    wanted_revision = revision if revision is not None else view.current_revision
    row = session.exec(select(ViewRevision).where(
        ViewRevision.view_id == view_id,
        ViewRevision.revision == wanted_revision,
    )).first()
    if row is None:
        raise ViewNotFound("视图版本不存在")
    snapshot = _decode_revision(row, view_id=view_id, conversation_id=view.conversation_id)
    if validate_sources:
        _validate_sources(session, user_id, snapshot.trusted_results)
    return ViewSnapshot(envelope=snapshot.envelope,
                        trusted_results=snapshot.trusted_results,
                        current_revision=view.current_revision)


def load_view_for_message(session: Session, *, view_id: str,
                          revision: int, conversation_id: int) -> ViewEnvelope | None:
    view = session.exec(select(UIView).where(
        UIView.id == view_id, UIView.conversation_id == conversation_id,
    )).first()
    if view is None:
        return None
    row = session.exec(select(ViewRevision).where(
        ViewRevision.view_id == view_id, ViewRevision.revision == revision,
    )).first()
    if row is None:
        return None
    try:
        return _decode_revision(row, view_id=view_id,
                                conversation_id=conversation_id).envelope
    except ViewNotFound:
        return None


def load_views_for_messages(session: Session, messages: list[Message]) -> dict[int, ViewEnvelope]:
    """Load valid historical views in bounded queries, keyed by assistant message ID.

    The database joins verify the message/view/revision/conversation/user binding.
    A malformed encrypted snapshot is omitted so one broken card cannot hide
    otherwise readable messages from the same history page.
    """
    requested: dict[int, int] = {}
    ambiguous_message_ids: set[int] = set()
    for message in messages:
        if message.role != "assistant" or message.id is None:
            continue
        previous = requested.get(message.id)
        if previous is not None and previous != message.conversation_id:
            ambiguous_message_ids.add(message.id)
        else:
            requested[message.id] = message.conversation_id
    for message_id in ambiguous_message_ids:
        requested.pop(message_id, None)
    message_ids = list(requested)
    if not message_ids:
        return {}

    restored: dict[int, ViewEnvelope] = {}
    for offset in range(0, len(message_ids), VIEW_HISTORY_BATCH_SIZE):
        chunk = message_ids[offset:offset + VIEW_HISTORY_BATCH_SIZE]
        statement = (
            select(MessageView, ViewRevision, UIView,
                   Message.id, Message.conversation_id, Conversation.user_id)
            .join(Message, Message.id == MessageView.message_id)
            .join(ViewRevision, (ViewRevision.view_id == MessageView.view_id)
                  & (ViewRevision.revision == MessageView.revision))
            .join(UIView, UIView.id == MessageView.view_id)
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(
                MessageView.message_id.in_(chunk),
                Message.role == "assistant",
                UIView.conversation_id == Message.conversation_id,
                UIView.user_id == Conversation.user_id,
            )
        )
        for binding, revision_row, view, message_id, conversation_id, conversation_user_id in session.exec(
            statement
        ).all():
            if (requested.get(message_id) != conversation_id
                    or binding.message_id != message_id
                    or binding.view_id != view.id
                    or binding.revision != revision_row.revision
                    or view.conversation_id != conversation_id
                    or view.user_id != conversation_user_id):
                continue
            try:
                snapshot = _decode_revision(
                    revision_row, view_id=view.id, conversation_id=conversation_id,
                )
            except ViewNotFound:
                continue
            restored[message_id] = snapshot.envelope
    return restored


def _selected_category_label(snapshot: ViewSnapshot | None) -> str | None:
    if snapshot is None:
        return None
    selected_id = snapshot.envelope.interaction_state.selected_category
    if selected_id is None:
        return None
    for dataset in snapshot.envelope.trusted_data.datasets.values():
        if dataset.kind != "categories":
            continue
        for row in dataset.rows:
            if row.id == selected_id:
                label = getattr(row, "label", None)
                return label if isinstance(label, str) else None
    return None


def _selected_category_source(snapshot: ViewSnapshot | None) -> tuple[str, dict[str, Any] | None] | None:
    if snapshot is None:
        return None
    selected_id = snapshot.envelope.interaction_state.selected_category
    if selected_id is None:
        return None
    for ref, dataset in snapshot.envelope.trusted_data.datasets.items():
        if dataset.kind != "categories":
            continue
        row = next((item for item in dataset.rows if item.id == selected_id), None)
        if row is None:
            continue
        source_ref = ref.split(":", 1)[0]
        source = next((item for item in snapshot.trusted_results
                       if item["result_ref"] == source_ref
                       and item["kind"] == "monthly_bill"), None)
        label = getattr(row, "label", None)
        if isinstance(label, str):
            return label, source
    return None


def view_context_for_agent(snapshot: ViewSnapshot | None) -> dict[str, Any] | None:
    """Return only server-derived selection state for the Agent system context."""
    if snapshot is None:
        return None
    state = snapshot.envelope.interaction_state
    category = _selected_category_label(snapshot)
    if category is not None:
        category = mask_text(category)
        if len(category) > 80 or detect_injection(category).blocked:
            category = None
    return {
        "selected_category": category,
        "selected_ids": list(state.selected_ids[:100]),
        "sort": state.sort,
        "filter": state.filter,
        "bill_periods": [
            {"month": item["data"]["month"], "currency": item["data"]["currency"]}
            for item in snapshot.trusted_results if item["kind"] == "monthly_bill"
        ],
    }


def view_context_for_composer(snapshot: ViewSnapshot | None) -> dict[str, Any] | None:
    """Provide the current view's small interaction context to the Composer."""
    if snapshot is None:
        return None
    state = snapshot.envelope.interaction_state
    return {
        "selected_category": _selected_category_label(snapshot),
        "selected_ids": list(state.selected_ids),
        "sort": state.sort,
        "filter": state.filter,
    }


def _merge_results(old: list[dict[str, Any]], new: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    ordered_refs: list[str] = []
    identity_refs: dict[tuple[Any, ...], str] = {}
    for item in [*old, *new]:
        normalized = validate_trusted_result(item)
        ref = normalized["result_ref"]
        if ref in merged and merged[ref] != normalized:
            raise TrustedResultError("同一可信结果引用对应的数据不一致")
        if normalized["kind"] == "monthly_bill":
            identity = ("monthly_bill", normalized["metadata"]["account_id"],
                        normalized["data"]["currency"], normalized["data"]["month"])
        else:
            identity = (normalized["kind"],)
        prior_ref = identity_refs.get(identity)
        if prior_ref is not None and prior_ref != ref:
            merged.pop(prior_ref, None)
            ordered_refs.remove(prior_ref)
        merged[ref] = normalized
        if ref not in ordered_refs:
            ordered_refs.append(ref)
        identity_refs[identity] = ref
    records = [merged[ref] for ref in ordered_refs]
    if not records or len(records) > 12:
        raise TrustedResultError("本次视图可信结果数量无效")
    return records


def prepare_view_composition(context: ViewSnapshot | None,
                             new_results: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    combined = _merge_results(context.trusted_results if context else [], new_results)
    trusted_data = build_trusted_data(
        combined, selected_category=_selected_category_label(context))
    return combined, build_composer_catalog(
        trusted_data, [item["result_ref"] for item in combined])


def create_or_append_view(*, user_id: int, conversation_id: int,
                          results: list[dict[str, Any]], spec: dict[str, Any] | ViewSpec,
                          context: ViewSnapshot | None = None) -> ViewEnvelope:
    combined = _merge_results(context.trusted_results if context else [], results)
    prior_state = context.envelope.interaction_state if context else InteractionState()
    selected_source = _selected_category_source(context)
    selected_label = selected_source[0] if selected_source else None
    trusted_data = build_trusted_data(combined, selected_category=selected_label)
    state_data = prior_state.model_dump()
    if selected_source is not None:
        old_result = selected_source[1]
        target_result = None
        if old_result is not None and old_result["kind"] == "monthly_bill":
            identity = (old_result["metadata"]["account_id"], old_result["data"]["currency"],
                        old_result["data"]["month"])
            target_result = next((item for item in combined
                                  if item["kind"] == "monthly_bill"
                                  and (item["metadata"]["account_id"], item["data"]["currency"],
                                       item["data"]["month"]) == identity), None)
        if target_result is not None:
            category_dataset = trusted_data.datasets.get(f"{target_result['result_ref']}:categories")
            selected_row = (next((row for row in category_dataset.rows
                                  if getattr(row, "label", None) == selected_label), None)
                            if category_dataset is not None else None)
            state_data["selected_category"] = selected_row.id if selected_row is not None else None
        else:
            state_data["selected_category"] = None
    selectable_ids = {
        row.id for dataset in trusted_data.datasets.values()
        if dataset.kind in {"subscriptions", "candidates"} for row in dataset.rows
    }
    state_data["selected_ids"] = [value for value in prior_state.selected_ids
                                   if value in selectable_ids]
    state = InteractionState.model_validate(state_data)
    result_refs = [item["result_ref"] for item in combined]
    spec_model = spec if isinstance(spec, ViewSpec) else ViewSpec.model_validate(spec)

    with session_scope() as session:
        same_view = False
        current_view: UIView | None = None
        if context is not None:
            current_view = session.exec(select(UIView).where(
                UIView.id == context.envelope.view_id,
                UIView.user_id == user_id,
                UIView.conversation_id == conversation_id,
            )).first()
            if current_view is None:
                raise ViewNotFound("视图不存在")
            same_view = current_view.current_revision == context.envelope.revision

        if same_view and current_view is not None:
            view_id = current_view.id
            revision_number = current_view.current_revision + 1
        else:
            view_id = secrets.token_urlsafe(24)
            revision_number = 1

        envelope = ViewEnvelope.model_validate({
            "schema_version": 1,
            "catalog_version": 1,
            "view_id": view_id,
            "revision": revision_number,
            "conversation_id": conversation_id,
            "result_refs": result_refs,
            "observed_at": latest_observed_at(combined),
            "spec": spec_model.model_dump(mode="json"),
            "interaction_state": state.model_dump(mode="json"),
            "allowed_actions": available_actions(trusted_data),
            "trusted_data": trusted_data.model_dump(mode="json"),
        })
        payload = {
            "envelope": envelope.model_dump(mode="json"),
            "trusted_results": combined,
        }
        ciphertext, key_version = encrypt_result_snapshot(payload)

        if same_view and current_view is not None:
            result = session.execute(update(UIView).where(
                UIView.id == view_id,
                UIView.user_id == user_id,
                UIView.current_revision == context.envelope.revision,
            ).values(current_revision=revision_number, updated_at=utcnow()))
            if result.rowcount != 1:
                session.rollback()
                raise ViewConflict("视图已更新，请重新载入后重试")
        else:
            session.add(UIView(id=view_id, user_id=user_id,
                               conversation_id=conversation_id,
                               current_revision=revision_number))

        session.add(ViewRevision(view_id=view_id, revision=revision_number,
                                 ciphertext=ciphertext, key_version=key_version))
        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            raise ViewConflict("视图已更新，请重新载入后重试") from exc
    return envelope


def apply_interaction_state(envelope: ViewEnvelope, action: ActionName,
                            value: Any = None) -> InteractionState:
    if action not in envelope.allowed_actions:
        raise InvalidViewInteraction("该视图不允许此交互")
    state = envelope.interaction_state.model_dump()
    if action == "select_category":
        category_ids = {
            row.id for dataset in envelope.trusted_data.datasets.values()
            if dataset.kind == "categories" for row in dataset.rows
        }
        if type(value) is not str or value not in category_ids:
            raise InvalidViewInteraction("分类选择无效")
        state["selected_category"] = value
    elif action == "select_ids":
        selectable = [dataset for dataset in envelope.trusted_data.datasets.values()
                      if dataset.kind in {"subscriptions", "candidates"}]
        valid_ids = [row.id for dataset in selectable for row in dataset.rows]
        if len(valid_ids) != len(set(valid_ids)):
            raise InvalidViewInteraction("选择列表存在重复引用")
        if (not isinstance(value, list) or len(value) > 100
                or any(type(item) is not str for item in value)
                or len(value) != len(set(value))
                or any(item not in valid_ids for item in value)):
            raise InvalidViewInteraction("选择项无效")
        state["selected_ids"] = value
    elif action == "set_sort":
        if type(value) is not str or value not in {"default", "amount_desc", "amount_asc"}:
            raise InvalidViewInteraction("排序方式无效")
        state["sort"] = value
    elif action == "set_filter":
        if type(value) is not str or value not in {"all", "active", "renewal_soon"}:
            raise InvalidViewInteraction("筛选条件无效")
        if not any(dataset.kind == "subscriptions"
                   for dataset in envelope.trusted_data.datasets.values()):
            raise InvalidViewInteraction("此视图没有可筛选的订阅数据")
        state["filter"] = value
    else:
        if value is not None:
            raise InvalidViewInteraction("清除筛选不接受参数")
        state = InteractionState().model_dump()
    return InteractionState.model_validate(state)


def _interaction_digest(payload: ViewInteractionRequest) -> str:
    canonical = json.dumps({
        "base_revision": payload.base_revision,
        "action": payload.action,
        "value": payload.value,
    }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _read_interaction_result(session: Session, *, view_id: str,
                             receipt: ViewInteraction,
                             conversation_id: int) -> ViewEnvelope:
    row = session.exec(select(ViewRevision).where(
        ViewRevision.view_id == view_id,
        ViewRevision.revision == receipt.result_revision,
    )).first()
    if row is None:
        raise ViewNotFound("交互结果不可用")
    return _decode_revision(row, view_id=view_id,
                            conversation_id=conversation_id).envelope


def _find_duplicate(view_id: str, event_id: str, digest: str,
                    user_id: int) -> ViewEnvelope | None:
    with Session(get_engine()) as session:
        view = session.exec(select(UIView).where(
            UIView.id == view_id, UIView.user_id == user_id,
        )).first()
        if view is None:
            raise ViewNotFound("视图不存在")
        receipt = session.exec(select(ViewInteraction).where(
            ViewInteraction.view_id == view_id,
            ViewInteraction.event_id == event_id,
        )).first()
        if receipt is None:
            return None
        if receipt.payload_digest != digest:
            raise ViewConflict("交互编号已用于其他操作")
        return _read_interaction_result(session, view_id=view_id,
                                        receipt=receipt,
                                        conversation_id=view.conversation_id)


def apply_view_interaction(*, user_id: int, view_id: str,
                           payload: ViewInteractionRequest) -> ViewEnvelope:
    digest = _interaction_digest(payload)
    try:
        with session_scope() as session:
            view = session.exec(select(UIView).where(
                UIView.id == view_id, UIView.user_id == user_id,
            )).first()
            if view is None:
                raise ViewNotFound("视图不存在")
            previous = session.exec(select(ViewInteraction).where(
                ViewInteraction.view_id == view_id,
                ViewInteraction.event_id == payload.event_id,
            )).first()
            if previous is not None:
                if previous.payload_digest != digest:
                    raise ViewConflict("交互编号已用于其他操作")
                return _read_interaction_result(session, view_id=view_id,
                                                receipt=previous,
                                                conversation_id=view.conversation_id)
            if view.current_revision != payload.base_revision:
                raise ViewConflict("视图版本已变化，请重新载入后重试")
            current_row = session.exec(select(ViewRevision).where(
                ViewRevision.view_id == view_id,
                ViewRevision.revision == payload.base_revision,
            )).first()
            if current_row is None:
                raise ViewNotFound("视图版本不存在")
            current = _decode_revision(current_row, view_id=view_id,
                                       conversation_id=view.conversation_id).envelope
            next_state = apply_interaction_state(current, payload.action, payload.value)
            next_envelope = current.model_copy(update={
                "revision": payload.base_revision + 1,
                "interaction_state": next_state,
            })
            ciphertext, key_version = encrypt_result_snapshot({
                "envelope": next_envelope.model_dump(mode="json"),
                "trusted_results": _decode_revision(
                    current_row, view_id=view_id,
                    conversation_id=view.conversation_id).trusted_results,
            })
            updated = session.execute(update(UIView).where(
                UIView.id == view_id,
                UIView.user_id == user_id,
                UIView.current_revision == payload.base_revision,
            ).values(current_revision=payload.base_revision + 1, updated_at=utcnow()))
            if updated.rowcount != 1:
                session.rollback()
                duplicate = _find_duplicate(view_id, payload.event_id, digest, user_id)
                if duplicate is not None:
                    return duplicate
                raise ViewConflict("视图版本已变化，请重新载入后重试")
            session.add(ViewRevision(view_id=view_id, revision=payload.base_revision + 1,
                                     ciphertext=ciphertext, key_version=key_version))
            session.add(ViewInteraction(view_id=view_id, event_id=payload.event_id,
                                        payload_digest=digest,
                                        result_revision=payload.base_revision + 1))
            session.commit()
            return next_envelope
    except IntegrityError:
        duplicate = _find_duplicate(view_id, payload.event_id, digest, user_id)
        if duplicate is not None:
            return duplicate
        raise ViewConflict("视图版本已变化，请重新载入后重试") from None
