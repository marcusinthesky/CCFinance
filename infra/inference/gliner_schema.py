"""The shared extraction contract used by local GLiNER experiments."""

from __future__ import annotations

from typing import TYPE_CHECKING

from gliner2 import AttributeGroup

if TYPE_CHECKING:
    from gliner2.inference.runtime import ExtractorRuntimeMixin
    from gliner2.inference.schema import Schema

# Coarse rollups of SENTiVENT's event types, not exact taxonomy equivalences.
# https://github.com/GillesJ/sentivent-event-annotation-guidelines
EVENT_FAMILIES = {
    "performance": "Financial reports, earnings, guidance, revenue, costs or sales",
    "financing": "Borrowing, capital raising, dividends or share repurchases",
    "transactions": "Acquisitions, disposals, investments, partnerships or contracts",
    "operations": "Executives, employment, facilities, products or services",
    "legal and reputation": (
        "Litigation, regulation, approvals or corporate responsibility"
    ),
    "markets and macroeconomics": "Ratings, security prices or economic developments",
}

ARTICLE_FORMS = {
    "reporting": "A journalist reports news and attributed statements",
    "analysis": "An explanation or interpretation of news and its implications",
    "opinion": "A commentary expressing the author's views or recommendations",
    "interview": "An interview or question-and-answer discussion",
    "roundup": "A digest covering several stories, companies or market movements",
    "press release": "An announcement issued by a company or its representative",
    "other": "Content outside the listed journalistic forms",
}


def build_schema(model: ExtractorRuntimeMixin) -> Schema:
    """Request company spans, per-mention roles, and the article's text type."""
    return (
        model.create_schema()
        .entities({"company": "Names of companies and businesses"})
        .entity_attributes(
            {
                "article_role": AttributeGroup(
                    ["primary", "secondary", "incidental", "uncertain"],
                    applies_to=["company"],
                    qualify_labels=True,
                )
            }
        )
        .classification(
            "article_type",
            ["reporting", "opinion", "press release", "promotional", "other"],
        )
    )


def build_metadata_schema(
    model: ExtractorRuntimeMixin, *, records: bool = False
) -> Schema:
    """Compose local mention attributes and news classifications in one request.

    Sentiment is investor-facing valence toward the named company in the observed
    passage. Relevance is local substantive coverage, not whole-article primacy.
    Genre and subject vocabulary design follows IPTC's separation of these axes:
    https://iptc.org/std/NewsCodes/guidelines/
    """
    schema = (
        model.create_schema()
        .entities(
            {
                "company": "Named businesses, excluding people and places",
                "person": "Named people, including executives and analysts",
                "public body": "Named governments, courts, regulators or central banks",
                "place": "Named countries, cities or geographic regions",
            }
        )
        .entity_attributes(
            {
                "local_relevance": AttributeGroup(
                    ["substantive", "incidental", "uncertain"],
                    applies_to=["company"],
                    qualify_labels=True,
                ),
                "financial_sentiment": AttributeGroup(
                    ["positive", "negative", "neutral", "mixed", "not assessable"],
                    applies_to=["company"],
                    qualify_labels=True,
                ),
            }
        )
        .classification("article_form", ARTICLE_FORMS)
        .classification("event_family", EVENT_FAMILIES, multi_label=True)
    )
    if records:
        event = schema.structure("events", mode="natural", anchor="trigger")
        event.field(
            "trigger",
            dtype="str",
            cardinality="required_one",
            description="Words naming one specific economic occurrence or action",
        )
        event.field(
            "family",
            dtype="str",
            choices=list(EVENT_FAMILIES),
            cardinality="optional_one",
        )
        for name, description in {
            "actor": "The named company or public body performing this event",
            "counterparty": "The other named company or party in this event",
            "amount": "The monetary amount or percentage for this event, with units",
            "metric": "The financial metric, such as revenue or earnings per share",
            "period": "The reporting period for this metric, such as Q3 2025",
            "comparison": "The stated comparison or expectation for this metric",
            "time": "When this event occurs, as explicitly written",
            "place": "Where this event occurs, as explicitly written",
            "attribution": "The named speaker or source making this statement",
        }.items():
            event.field(
                name,
                dtype="str",
                cardinality="optional_one",
                description=description,
            )
        event.field(
            "assertion",
            dtype="str",
            choices=["affirmed", "negated", "uncertain"],
            cardinality="optional_one",
            description="Whether the text affirms, denies or questions this occurrence",
        )
        event.field(
            "stage",
            dtype="str",
            choices=["proposed", "announced", "approved", "completed", "cancelled"],
            cardinality="optional_one",
            description="The stated lifecycle stage, distinct from assertion certainty",
        )
    return schema


def build_transaction_schema(model: ExtractorRuntimeMixin) -> Schema:
    """Test focused acquisition records anchored by each acquiring company."""
    schema = model.create_schema().entities({"company": "Names of businesses"})
    record = schema.structure("acquisitions", mode="natural", anchor="acquirer")
    for name, description in {
        "acquirer": "Company buying or proposing to buy another company",
        "target": "Company being bought by this acquirer",
        "amount": "The purchase price of this acquisition, including currency",
    }.items():
        record.field(
            name,
            dtype="str",
            description=description,
            cardinality="required_one" if name == "acquirer" else "optional_one",
        )
    record.field(
        "assertion",
        dtype="str",
        choices=["affirmed", "negated", "uncertain"],
        cardinality="optional_one",
    )
    record.field(
        "stage",
        dtype="str",
        choices=["proposed", "announced", "approved", "completed", "cancelled"],
        cardinality="optional_one",
    )
    return schema
