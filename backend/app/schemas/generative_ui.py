"""Strict wire schemas for server trusted, model composed banking views."""
from datetime import datetime
import math
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


ActionName = Literal[
    "select_category", "select_ids", "set_sort", "set_filter", "clear_filters",
]
SortOrder = Literal["default", "amount_desc", "amount_asc"]
FilterName = Literal["all", "active", "renewal_soon"]
DatasetKind = Literal["categories", "comparison", "records", "subscriptions", "candidates"]
DataFormat = Literal["text", "currency", "number", "percent"]
ViewAction = Literal["open_workspace", "view_source", "follow_up"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ViewContext(StrictModel):
    view_id: str = Field(min_length=8, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    revision: int = Field(ge=1)


class ViewInteractionRequest(StrictModel):
    event_id: str = Field(min_length=8, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    base_revision: int = Field(ge=1)
    action: ActionName
    value: Any = None

    @model_validator(mode="after")
    def bound_value_shape(self):
        if self.action == "select_category":
            if type(self.value) is not str or not 1 <= len(self.value) <= 160:
                raise ValueError("分类选择无效")
        elif self.action == "select_ids":
            if (not isinstance(self.value, list) or len(self.value) > 100
                    or any(type(item) is not str or not 1 <= len(item) <= 160 for item in self.value)
                    or len(self.value) != len(set(self.value))):
                raise ValueError("选择项无效")
        elif self.action == "set_sort":
            if type(self.value) is not str or self.value not in {"default", "amount_desc", "amount_asc"}:
                raise ValueError("排序方式无效")
        elif self.action == "set_filter":
            if type(self.value) is not str or self.value not in {"all", "active", "renewal_soon"}:
                raise ValueError("筛选条件无效")
        elif self.value is not None:
            raise ValueError("清除筛选不接受参数")
        return self


class MetricValue(StrictModel):
    label: str = Field(min_length=1, max_length=80)
    value: int | float | None
    format: Literal["currency", "number", "percent"]
    period: str | None = Field(default=None, max_length=24)
    note: str | None = Field(default=None, max_length=160)

    @model_validator(mode="after")
    def validate_numeric_value(self):
        if self.value is not None:
            if type(self.value) not in (int, float) or not math.isfinite(self.value):
                raise ValueError("metric value must be a finite number")
            if self.format == "currency" and type(self.value) is not int:
                raise ValueError("currency metrics must use integer minor units")
        return self


class DatasetColumn(StrictModel):
    key: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z][A-Za-z0-9_]*$")
    label: str = Field(min_length=1, max_length=80)
    format: DataFormat


class DatasetRow(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True)

    id: str = Field(min_length=1, max_length=160)

    @model_validator(mode="after")
    def scalar_columns_only(self):
        for value in (self.model_extra or {}).values():
            if value is not None and type(value) not in (str, int, float, bool):
                raise ValueError("dataset rows may contain scalar values only")
        return self


class TrustedDataset(StrictModel):
    kind: DatasetKind
    title: str = Field(min_length=1, max_length=100)
    columns: list[DatasetColumn] = Field(max_length=20)
    rows: list[DatasetRow] = Field(max_length=200)

    @model_validator(mode="after")
    def unique_columns_and_rows(self):
        column_keys = [column.key for column in self.columns]
        row_ids = [row.id for row in self.rows]
        if len(column_keys) != len(set(column_keys)):
            raise ValueError("dataset column keys must be unique")
        if len(row_ids) != len(set(row_ids)):
            raise ValueError("dataset row IDs must be unique")
        for row in self.rows:
            for column in self.columns:
                value = getattr(row, column.key, None)
                if value is None:
                    continue
                if column.format == "text" and type(value) is not str:
                    raise ValueError("text columns must contain strings")
                if column.format == "currency" and type(value) is not int:
                    raise ValueError("currency columns must use integer minor units")
                if column.format in {"number", "percent"} and type(value) not in (int, float):
                    raise ValueError("numeric columns must contain numbers")
                if type(value) is float and not math.isfinite(value):
                    raise ValueError("dataset numeric values must be finite")
        return self


class TrustedData(StrictModel):
    metrics: dict[str, MetricValue] = Field(max_length=100)
    datasets: dict[str, TrustedDataset] = Field(max_length=40)


class ViewElement(StrictModel):
    type: str = Field(min_length=1, max_length=40)
    props: dict[str, Any] = Field(max_length=12)
    children: list[str] | None = Field(default=None, max_length=40)


class ViewSpec(StrictModel):
    root: str = Field(min_length=1, max_length=80)
    elements: dict[str, ViewElement] = Field(min_length=1, max_length=40)


class InteractionState(StrictModel):
    selected_category: str | None = Field(default=None, max_length=160)
    selected_ids: list[str] = Field(default_factory=list, max_length=100)
    sort: SortOrder = "default"
    filter: FilterName = "all"


def _validate_envelope_bindings(
    *, observed_at: str, result_refs: list[str], spec: ViewSpec,
    view_data: TrustedData, allowed_actions: list[ActionName],
) -> None:
    value = observed_at[:-1] + "+00:00" if observed_at.endswith("Z") else observed_at
    try:
        observed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("observed_at must be an ISO 8601 timestamp") from exc
    if observed.tzinfo is None:
        raise ValueError("observed_at must include a timezone")
    if len(result_refs) != len(set(result_refs)):
        raise ValueError("result_refs must be unique")
    validate_view_spec(spec, view_data, result_refs)
    if len(allowed_actions) != len(set(allowed_actions)):
        raise ValueError("allowed_actions must be unique")
    for ref in [*view_data.metrics, *view_data.datasets]:
        if ref.split(":", 1)[0] not in result_refs:
            raise ValueError("view data is not bound to a result")


class ViewEnvelope(StrictModel):
    """Legacy v1 envelope: server-built trusted_data."""

    schema_version: Literal[1]
    catalog_version: Literal[1]
    view_id: str = Field(min_length=8, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    revision: int = Field(ge=1)
    conversation_id: int = Field(gt=0)
    result_refs: list[str] = Field(min_length=1, max_length=12)
    observed_at: str = Field(min_length=20, max_length=40)
    spec: ViewSpec
    interaction_state: InteractionState
    allowed_actions: list[ActionName] = Field(max_length=5)
    trusted_data: TrustedData

    @model_validator(mode="after")
    def validate_composed_spec(self):
        _validate_envelope_bindings(
            observed_at=self.observed_at, result_refs=self.result_refs,
            spec=self.spec, view_data=self.trusted_data,
            allowed_actions=self.allowed_actions,
        )
        return self


class ViewReview(StrictModel):
    reviewer_version: str = Field(min_length=1, max_length=80)
    attempts: int = Field(ge=1, le=3)
    result: Literal["passed"]


class ViewEnvelopeV2(StrictModel):
    """AI-composed view data and layout, validated against source results.

    The result cards remain the authoritative banking facts. This envelope is
    an explanation layer and carries its source digest for provenance.
    """

    schema_version: Literal[2]
    catalog_version: Literal[1]
    view_id: str = Field(min_length=8, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    revision: int = Field(ge=1)
    conversation_id: int = Field(gt=0)
    result_refs: list[str] = Field(min_length=1, max_length=12)
    source_digest: str = Field(min_length=16, max_length=64, pattern=r"^[a-f0-9]+$")
    observed_at: str = Field(min_length=20, max_length=40)
    spec: ViewSpec
    interaction_state: InteractionState
    allowed_actions: list[ActionName] = Field(max_length=5)
    view_data: TrustedData
    review: ViewReview

    @model_validator(mode="after")
    def validate_composed_spec(self):
        _validate_envelope_bindings(
            observed_at=self.observed_at, result_refs=self.result_refs,
            spec=self.spec, view_data=self.view_data,
            allowed_actions=self.allowed_actions,
        )
        return self


AnyViewEnvelope = ViewEnvelope | ViewEnvelopeV2


def view_data_of(envelope: AnyViewEnvelope) -> TrustedData:
    return envelope.view_data if isinstance(envelope, ViewEnvelopeV2) else envelope.trusted_data


_COMPONENT_PROPS: dict[str, tuple[set[str], str | None]] = {
    "Stack": (set(), None),
    "Grid": (set(), None),
    "Section": ({"title_key"}, None),
    "Metric": ({"metric_ref"}, "metric"),
    "MetricComparison": ({"dataset_ref"}, "comparison"),
    "CategoryBarChart": ({"dataset_ref"}, "categories"),
    "ComparisonTable": ({"dataset_ref"}, "comparison"),
    "RecordList": ({"dataset_ref"}, "records"),
    "SelectableList": ({"dataset_ref"}, "selectable"),
    "Filter": ({"dataset_ref"}, "selectable"),
    "Selector": ({"dataset_ref"}, "categories"),
    "ActionLink": ({"action"}, "action"),
}
_SECTION_TITLES = {"overview", "categories", "comparison", "subscriptions", "candidates", "anomalies"}
_SELECTABLE_DATASETS = {"subscriptions", "candidates"}


def allowed_components_for_dataset(kind: DatasetKind) -> list[str]:
    """Describe the same semantic mapping enforced during view validation."""
    return [name for name, (_, reference_kind) in _COMPONENT_PROPS.items()
            if reference_kind == kind
            or (reference_kind == "selectable" and kind in _SELECTABLE_DATASETS)]


def validate_view_spec(spec: ViewSpec, trusted_data: TrustedData,
                       result_refs: list[str] | None = None) -> None:
    """Validate graph limits, closed props, and trusted-reference semantics."""
    elements = spec.elements
    if spec.root not in elements:
        raise ValueError("view root does not exist")
    if len(elements) > 40:
        raise ValueError("view contains too many elements")

    for element in elements.values():
        component = _COMPONENT_PROPS.get(element.type)
        if component is None:
            raise ValueError("unsupported view component")
        expected_props, reference_kind = component
        if set(element.props) != expected_props:
            raise ValueError("component props do not match its catalog schema")
        children = element.children or []
        if len(children) != len(set(children)):
            raise ValueError("view children must be unique within a parent")
        if children and element.type not in {"Stack", "Grid", "Section"}:
            raise ValueError("leaf components cannot contain children")
        for child in children:
            if child not in elements:
                raise ValueError("view child does not exist")
        if (element.type == "Section"
                and (not isinstance(element.props["title_key"], str)
                     or element.props["title_key"] not in _SECTION_TITLES)):
            raise ValueError("unsupported section title")
        if (element.type == "ActionLink"
                and (not isinstance(element.props["action"], str)
                     or element.props["action"] not in {"open_workspace", "view_source", "follow_up"})):
            raise ValueError("unsupported action link")
        if reference_kind == "metric":
            ref = element.props["metric_ref"]
            if type(ref) is not str or ref not in trusted_data.metrics:
                raise ValueError("metric reference does not exist")
        elif reference_kind in {"categories", "comparison", "records", "selectable"}:
            ref = element.props["dataset_ref"]
            dataset = trusted_data.datasets.get(ref) if type(ref) is str else None
            if dataset is None:
                raise ValueError("dataset reference does not exist")
            expected_kind = (_SELECTABLE_DATASETS if reference_kind == "selectable"
                             else {reference_kind})
            if dataset.kind not in expected_kind:
                raise ValueError("dataset reference has the wrong semantic kind")
        if result_refs is not None:
            ref = element.props.get("metric_ref") or element.props.get("dataset_ref")
            if ref is not None and ref.split(":", 1)[0] not in result_refs:
                raise ValueError("data reference is not bound to a result")

    visiting: set[str] = set()
    visited: set[str] = set()
    parents: dict[str, str] = {}

    def walk(node_id: str, depth: int) -> None:
        if depth > 6:
            raise ValueError("view nesting is too deep")
        if node_id in visiting:
            raise ValueError("view graph contains a cycle")
        if node_id in visited:
            return
        visiting.add(node_id)
        for child in elements[node_id].children or []:
            if child in parents and parents[child] != node_id:
                raise ValueError("view components may have only one parent")
            parents[child] = node_id
            walk(child, depth + 1)
        visiting.remove(node_id)
        visited.add(node_id)

    walk(spec.root, 1)
    if spec.root in parents:
        raise ValueError("view root cannot have a parent")
    if len(visited) != len(elements):
        raise ValueError("view contains unreachable elements")
