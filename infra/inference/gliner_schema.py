"""The core financial-news extraction contract requested in one joint pass.

Article form and subject are separate axes, following IPTC NewsCodes:
https://iptc.org/std/NewsCodes/guidelines/
Event families are coarse project rollups of SENTiVENT's event types:
https://github.com/GillesJ/sentivent-event-annotation-guidelines
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gliner2 import AttributeGroup

if TYPE_CHECKING:
    from gliner2.inference.runtime import ExtractorRuntimeMixin
    from gliner2.inference.schema import Schema

ENTITIES = {
    "company": "Named businesses, excluding people and places",
    "person": "Named people, including executives and analysts",
    "public body": "Named governments, courts, regulators or central banks",
    "place": "Named countries, cities or geographic regions",
}
# Company-specific labels describe the local passage, not whole-article primacy.
# Sentiment is investor-facing valence; "not assessable" differs from neutral.
ATTRIBUTES = {
    "local_relevance": ["substantive", "incidental", "uncertain"],
    "financial_sentiment": [
        "positive",
        "negative",
        "neutral",
        "mixed",
        "not assessable",
    ],
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


def build_schema(model: ExtractorRuntimeMixin) -> Schema:
    """Request typed mentions, company attributes, article form and event families."""
    return (
        model.create_schema()
        .entities(ENTITIES)
        .entity_attributes(
            {
                name: AttributeGroup(
                    labels, applies_to=["company"], qualify_labels=True
                )
                for name, labels in ATTRIBUTES.items()
            }
        )
        .classification("article_form", ARTICLE_FORMS)
        .classification("event_family", EVENT_FAMILIES, multi_label=True)
    )
