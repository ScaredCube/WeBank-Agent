"""Build UI catalogs only from validated, server-issued tool results."""
from datetime import datetime, timezone
import hashlib
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.bills import MonthlyBill
from app.schemas.generative_ui import TrustedData, allowed_components_for_dataset
from app.schemas.subscriptions import SubscriptionCandidateData, SubscriptionData
from app.risk.injection import detect_injection
from app.services.redaction import mask_text


TrustedKind = Literal["monthly_bill", "subscriptions", "subscription_candidates"]


class TrustedResultRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    kind: TrustedKind
    result_ref: str = Field(min_length=8, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    observed_at: str = Field(min_length=20, max_length=40)
    data: dict | list[dict]
    metadata: dict[str, int | str] = Field(default_factory=dict)


class TrustedResultError(ValueError):
    pass


def _stable_id(namespace: str, value: str) -> str:
    return f"{namespace}:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def sanitize_subscription_result(kind: str, data: Any) -> list[dict]:
    """Validate subscription tool data while dropping Agent-only references."""
    if not isinstance(data, list):
        raise TrustedResultError("订阅查询结果无效")
    rows: list[dict] = []
    model = SubscriptionData if kind == "subscriptions" else SubscriptionCandidateData
    if kind not in {"subscriptions", "subscription_candidates"}:
        raise TrustedResultError("订阅结果类型无效")
    fields = set(model.model_fields)
    for item in data:
        if not isinstance(item, dict):
            raise TrustedResultError("订阅查询结果无效")
        try:
            visible = {key: value for key, value in item.items() if key in fields}
            if kind == "subscriptions" and visible.get("status") not in {"active", "cancelled"}:
                raise ValueError("unknown subscription status")
            rows.append(model.model_validate(visible).model_dump(mode="json"))
        except Exception as exc:
            raise TrustedResultError("订阅查询结果无效") from exc
    return rows


def validate_trusted_result(value: dict[str, Any]) -> dict[str, Any]:
    """Return a canonical JSON-compatible trusted result record."""
    try:
        record = TrustedResultRecord.model_validate(value)
        observed_value = (record.observed_at[:-1] + "+00:00"
                          if record.observed_at.endswith("Z") else record.observed_at)
        if datetime.fromisoformat(observed_value).tzinfo is None:
            raise ValueError("trusted result observed_at must include a timezone")
        result = record.model_dump(mode="json")
        if record.kind == "monthly_bill":
            bill = MonthlyBill.model_validate(record.data)
            account_id = record.metadata.get("account_id")
            if type(account_id) is not int or account_id < 1:
                raise ValueError("trusted bill account metadata is required")
            result["data"] = bill.model_dump(mode="json")
            result["metadata"] = {"account_id": account_id}
        else:
            result["data"] = sanitize_subscription_result(record.kind, record.data)
            result["metadata"] = {}
        return result
    except TrustedResultError:
        raise
    except Exception as exc:
        raise TrustedResultError("可信结果无效") from exc


def _columns(*items: tuple[str, str, str]) -> list[dict[str, str]]:
    return [{"key": key, "label": label, "format": format_name}
            for key, label, format_name in items]


def build_trusted_data(results: list[dict[str, Any]], *,
                       selected_category: str | None = None) -> TrustedData:
    metrics: dict[str, dict[str, Any]] = {}
    datasets: dict[str, dict[str, Any]] = {}
    bills: list[dict[str, Any]] = []
    for raw in results:
        item = validate_trusted_result(raw)
        ref = item["result_ref"]
        if item["kind"] == "monthly_bill":
            data = item["data"]
            if data["currency"] != "CNY":
                raise TrustedResultError("仅支持人民币账单视图")
            bills.append(item)
            metric_fields = (
                ("income_fen", "收入", "currency"),
                ("expense_fen", "支出", "currency"),
                ("consumption_fen", "消费", "currency"),
                ("consumption_count", "消费笔数", "number"),
                ("transfer_out_fen", "转出", "currency"),
                ("transfer_in_fen", "转入", "currency"),
                ("investment_out_fen", "理财转出", "currency"),
                ("investment_in_fen", "理财转入", "currency"),
                ("ignored_count", "未计入笔数", "number"),
            )
            for key, label, format_name in metric_fields:
                metrics[f"{ref}:{key}"] = {
                    "label": label,
                    "value": data[key],
                    "format": format_name,
                    "period": data["month"],
                }
            category_rows = [
                {"id": _stable_id(ref, row["category"]), "label": row["category"],
                 "amount_fen": row["amount_fen"], "count": row["count"]}
                for row in data["categories"]
            ]
            if len(category_rows) <= 200:
                datasets[f"{ref}:categories"] = {
                    "kind": "categories", "title": f"{data['month']} 消费分类",
                    "columns": _columns(("label", "分类", "text"),
                                        ("amount_fen", "消费金额", "currency"),
                                        ("count", "笔数", "number")),
                    "rows": category_rows,
                }
            anomaly_rows = [
                {"id": f"{index}", "reason": row["reason"],
                 "counterparty": row["counterparty"], "amount_fen": row["amount_fen"],
                 "occurred_at": row["occurred_at"],
                 "previous_occurred_at": row["previous_occurred_at"]}
                for index, row in enumerate(data["anomalies"])
            ]
            if anomaly_rows and len(anomaly_rows) <= 200:
                datasets[f"{ref}:anomalies"] = {
                    "kind": "records", "title": f"{data['month']} 需核对",
                    "columns": _columns(("reason", "核对原因", "text"),
                                        ("counterparty", "商户", "text"),
                                        ("amount_fen", "金额", "currency"),
                                        ("occurred_at", "发生时间", "text"),
                                        ("previous_occurred_at", "前次时间", "text")),
                    "rows": anomaly_rows,
                }
        elif item["kind"] == "subscriptions":
            rows = item["data"]
            if len(rows) > 200:
                raise TrustedResultError("订阅查询结果过多，暂无法生成视图")
            visible_rows = [{
                "id": f"{ref}:{row['subscription_id']}",
                "merchant": row["merchant"],
                "amount_fen": row["amount_fen"],
                "cycle": row["cycle"],
                "next_charge_date": row["next_charge_date"],
                "days_until_charge": row["days_until_charge"],
                "renewal_status": "即将续费" if row["renewal_soon"] else "正常",
                "status": {"active": "生效中", "cancelled": "已取消"}.get(row["status"]),
            } for row in rows]
            if any(row["status"] is None for row in visible_rows):
                raise TrustedResultError("订阅状态无效")
            datasets[f"{ref}:subscriptions"] = {
                "kind": "subscriptions", "title": "模拟订阅",
                "columns": _columns(("merchant", "商户", "text"),
                                    ("amount_fen", "金额", "currency"),
                                    ("cycle", "周期", "text"),
                                    ("next_charge_date", "下次扣费", "text"),
                                    ("days_until_charge", "距扣费天数", "number"),
                                    ("renewal_status", "续费状态", "text"),
                                    ("status", "状态", "text")),
                "rows": visible_rows,
            }
        else:
            rows = item["data"]
            if len(rows) > 200:
                raise TrustedResultError("疑似订阅结果过多，暂无法生成视图")
            datasets[f"{ref}:candidates"] = {
                "kind": "candidates", "title": "可能的重复订阅",
                "columns": _columns(("merchant", "商户", "text"),
                                    ("amount_fen", "金额", "currency"),
                                    ("occurrences", "出现次数", "number"),
                                    ("last_occurred_at", "最近一次", "text"),
                                    ("suggested_cycle", "可能周期", "text")),
                "rows": [{"id": _stable_id(ref,
                                             f"{row['merchant']}\0{row['amount_fen']}\0{row['last_occurred_at']}"),
                          **row}
                         for row in rows],
            }

    if len(bills) >= 2:
        account_ids = {bill["metadata"]["account_id"] for bill in bills}
        currencies = {bill["data"]["currency"] for bill in bills}
        months = [bill["data"]["month"] for bill in bills]
        if len(account_ids) == 1 and len(currencies) == 1 and len(set(months)) == len(months):
            ordered = sorted(bills, key=lambda item: item["data"]["month"])
            older, newer = ordered[-2:]
            old_data, new_data = older["data"], newer["data"]
            rows: list[dict[str, Any]] = []
            comparison_fields = (
                ("income_fen", "总收入"),
                ("expense_fen", "总支出"),
                ("consumption_fen", "消费"),
                ("transfer_out_fen", "转出"),
                ("transfer_in_fen", "转入"),
                ("investment_out_fen", "理财转出"),
                ("investment_in_fen", "理财转入"),
            )
            for field, label in comparison_fields:
                previous = old_data[field]
                current = new_data[field]
                change = current - previous
                percent = round(change * 100 / previous, 1) if previous != 0 else None
                rows.append({
                    "id": field, "metric": label,
                    "previous_month": old_data["month"], "current_month": new_data["month"],
                    "previous_fen": previous, "current_fen": current,
                    "delta_fen": change, "change_percent": percent,
                })
            if selected_category:
                old_categories = {row["category"]: row["amount_fen"] for row in old_data["categories"]}
                new_categories = {row["category"]: row["amount_fen"] for row in new_data["categories"]}
                if selected_category in old_categories or selected_category in new_categories:
                    previous = old_categories.get(selected_category, 0)
                    current = new_categories.get(selected_category, 0)
                    change = current - previous
                    percent = round(change * 100 / previous, 1) if previous != 0 else None
                    rows.append({
                        "id": _stable_id("category", selected_category),
                        "metric": selected_category,
                        "previous_month": old_data["month"], "current_month": new_data["month"],
                        "previous_fen": previous, "current_fen": current,
                        "delta_fen": change, "change_percent": percent,
                    })
            datasets[f"{ordered[-1]['result_ref']}:comparison"] = {
                "kind": "comparison", "title": "账单月度比较",
                "columns": _columns(("metric", "指标", "text"),
                                    ("previous_month", "上月", "text"),
                                    ("current_month", "本月", "text"),
                                    ("previous_fen", "上月金额", "currency"),
                                    ("current_fen", "本月金额", "currency"),
                                    ("delta_fen", "差额", "currency"),
                                    ("change_percent", "变化比例", "percent")),
                "rows": rows,
            }

    return TrustedData.model_validate({"metrics": metrics, "datasets": datasets})


def _safe_context_text(value: Any, *, max_length: int = 120) -> str | None:
    if (type(value) is not str or not value.strip() or len(value) > max_length
            or detect_injection(value).blocked):
        return None
    masked = mask_text(value)
    if not masked.strip() or detect_injection(masked).blocked:
        return None
    return masked


def _selected_record_summary(kind: str, row: Any) -> dict[str, Any] | None:
    merchant = _safe_context_text(getattr(row, "merchant", None), max_length=100)
    amount_fen = getattr(row, "amount_fen", None)
    if merchant is None or type(amount_fen) is not int or amount_fen < 0:
        return None
    if kind == "subscriptions":
        cycle = _safe_context_text(getattr(row, "cycle", None), max_length=32)
        next_charge_date = _safe_context_text(
            getattr(row, "next_charge_date", None), max_length=40,
        )
        days_until_charge = getattr(row, "days_until_charge", None)
        renewal_status = _safe_context_text(
            getattr(row, "renewal_status", None), max_length=32,
        )
        status = _safe_context_text(getattr(row, "status", None), max_length=32)
        if (cycle is None or next_charge_date is None
                or type(days_until_charge) is not int
                or renewal_status is None or status is None):
            return None
        return {
            "merchant": merchant,
            "amount_fen": amount_fen,
            "cycle": cycle,
            "next_charge_date": next_charge_date,
            "days_until_charge": days_until_charge,
            "renewal_status": renewal_status,
            "status": status,
        }
    if kind == "candidates":
        occurrences = getattr(row, "occurrences", None)
        last_occurred_at = _safe_context_text(
            getattr(row, "last_occurred_at", None), max_length=40,
        )
        suggested_cycle = _safe_context_text(
            getattr(row, "suggested_cycle", None), max_length=32,
        )
        if (type(occurrences) is not int or occurrences < 0
                or last_occurred_at is None or suggested_cycle is None):
            return None
        return {
            "merchant": merchant,
            "amount_fen": amount_fen,
            "occurrences": occurrences,
            "last_occurred_at": last_occurred_at,
            "suggested_cycle": suggested_cycle,
        }
    return None


def resolve_view_selection_context(*, trusted_results: list[dict[str, Any]],
                                   selected_category_id: str | None,
                                   selected_ids: list[str],
                                   max_selected_records: int = 10) -> dict[str, Any] | None:
    """Resolve snapshot selections into bounded facts from validated results.

    Stable IDs are treated only as lookup keys. The returned context contains no
    account/subscription IDs and is rebuilt from the encrypted snapshot's
    server-issued source records, never from client-supplied row values.
    """
    limit = (max_selected_records if type(max_selected_records) is int
             and 0 <= max_selected_records <= 20 else 10)
    normalized = [validate_trusted_result(item) for item in trusted_results]
    trusted_data = build_trusted_data(normalized)
    context: dict[str, Any] = {
        "selected_category": None,
        "selected_category_amount_fen": None,
        "selected_category_count": None,
        "selected_category_month": None,
        "selected_record_count": 0,
        "selected_records": [],
    }

    if type(selected_category_id) is str and 1 <= len(selected_category_id) <= 160:
        result_by_ref = {item["result_ref"]: item for item in normalized}
        for dataset_ref, dataset in trusted_data.datasets.items():
            if dataset.kind != "categories":
                continue
            row = next((item for item in dataset.rows
                        if item.id == selected_category_id), None)
            if row is None:
                continue
            source_ref = dataset_ref.removesuffix(":categories")
            source = result_by_ref.get(source_ref)
            label = _safe_context_text(getattr(row, "label", None), max_length=80)
            if source is None or source["kind"] != "monthly_bill" or label is None:
                break
            category = next((item for item in source["data"]["categories"]
                             if item["category"] == label), None)
            if (category is None or type(category["amount_fen"]) is not int
                    or category["amount_fen"] < 0 or type(category["count"]) is not int
                    or category["count"] < 0):
                break
            context.update({
                "selected_category": label,
                "selected_category_amount_fen": category["amount_fen"],
                "selected_category_count": category["count"],
                "selected_category_month": source["data"]["month"],
            })
            break

    selected_lookup = {
        row.id: (dataset.kind, row)
        for dataset in trusted_data.datasets.values()
        if dataset.kind in {"subscriptions", "candidates"}
        for row in dataset.rows
    }
    if isinstance(selected_ids, list):
        seen: set[str] = set()
        for selected_id in selected_ids[:100]:
            if type(selected_id) is not str or not 1 <= len(selected_id) <= 160 or selected_id in seen:
                continue
            seen.add(selected_id)
            selected = selected_lookup.get(selected_id)
            if selected is None:
                continue
            context["selected_record_count"] += 1
            summary = _selected_record_summary(*selected)
            if summary is not None and len(context["selected_records"]) < limit:
                context["selected_records"].append(summary)

    if (context["selected_category"] is None
            and context["selected_record_count"] == 0):
        return None
    return context


def build_composer_catalog(data: TrustedData, result_refs: list[str]) -> dict[str, Any]:
    """Expose reference semantics and labels, never bank values or raw records."""
    return {
        "result_refs": list(result_refs),
        "metrics": [{"metric_ref": ref, "label": value.label,
                     "format": value.format, "period": value.period}
                    for ref, value in data.metrics.items()],
        "datasets": [{"dataset_ref": ref, "kind": value.kind,
                      "title": value.title, "row_count": len(value.rows),
                      "allowed_components": allowed_components_for_dataset(value.kind),
                      "columns": [column.model_dump() for column in value.columns]}
                     for ref, value in data.datasets.items()],
    }


def available_actions(data: TrustedData) -> list[str]:
    actions: list[str] = []
    kinds = {dataset.kind for dataset in data.datasets.values()}
    if "categories" in kinds:
        actions.extend(["select_category", "set_sort", "clear_filters"])
    if kinds & {"subscriptions", "candidates"}:
        actions.extend(["select_ids", "set_sort", "clear_filters"])
    if "subscriptions" in kinds:
        actions.append("set_filter")
    if "records" in kinds:
        actions.extend(["set_sort", "clear_filters"])
    return list(dict.fromkeys(actions))


def latest_observed_at(results: list[dict[str, Any]]) -> str:
    values = [item["observed_at"] for item in results]
    return max(values, key=lambda value: datetime.fromisoformat(
        value[:-1] + "+00:00" if value.endswith("Z") else value).astimezone(timezone.utc))
