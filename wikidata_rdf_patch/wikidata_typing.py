from typing import Literal, TypedDict, Union

from typing_extensions import Required

# https://josh.github.io/wikidata-api-schemas/multilingual-text-value.schema.json#/$defs/values
Labels = dict[str, "MultilingualTextValue"]

# https://josh.github.io/wikidata-api-schemas/multilingual-text-value.schema.json#/$defs/values
Descriptions = dict[str, "MultilingualTextValue"]

# https://josh.github.io/wikidata-api-schemas/multilingual-text-value.schema.json#/$defs/multi-values
Aliases = dict[str, list["MultilingualTextValue"]]


# https://josh.github.io/wikidata-api-schemas/multilingual-text-value.schema.json
class MultilingualTextValue(TypedDict):
    language: str
    value: str


# https://josh.github.io/wikidata-api-schemas/statement.schema.json
Statement = TypedDict(
    "Statement",
    {
        "type": Required[str],
        "id": Required[str],
        "mainsnak": Required["Snak"],
        "rank": Required[Literal["preferred", "normal", "deprecated"]],
        "qualifiers": dict[str, list["Snak"]],
        "qualifiers-order": list[str],
        "references": list["Reference"],
    },
    total=False,
)

# https://josh.github.io/wikidata-api-schemas/snak.schema.json
Snak = Union["SnakValue", "SnakSomeValue", "SnakNoValue"]


# https://josh.github.io/wikidata-api-schemas/snak.schema.json#/$defs/value
class SnakValue(TypedDict, total=False):
    snaktype: Required[Literal["value"]]
    property: Required[str]
    hash: str
    datavalue: Required["DataValue"]
    datatype: Required["DataType"]


# https://josh.github.io/wikidata-api-schemas/snak.schema.json#/$defs/somevalue
class SnakSomeValue(TypedDict, total=False):
    snaktype: Required[Literal["somevalue"]]
    property: Required[str]
    hash: str
    datatype: "DataType"


# https://josh.github.io/wikidata-api-schemas/snak.schema.json#/$defs/novalue
class SnakNoValue(TypedDict, total=False):
    snaktype: Required[Literal["novalue"]]
    property: Required[str]
    hash: str
    datatype: "DataType"


# https://josh.github.io/wikidata-api-schemas/property.schema.json#/$defs/datatype
DataType = Literal[
    "commonsMedia",
    "geo-shape",
    "tabular-data",
    "url",
    "external-id",
    "wikibase-item",
    "wikibase-property",
    "globe-coordinate",
    "monolingualtext",
    "quantity",
    "string",
    "time",
    "musical-notation",
    "math",
    "wikibase-lexeme",
    "wikibase-form",
    "wikibase-sense",
]

# https://josh.github.io/wikidata-api-schemas/data-value.schema.json
DataValue = Union[
    "GlobecoordinateDataValue",
    "MonolingualTextDataValue",
    "QuantityDataValue",
    "StringDataValue",
    "TimeDataValue",
    "WikibaseEntityIdDataValue",
]


# https://josh.github.io/wikidata-api-schemas/data-values/globecoordinate.schema.json
class GlobecoordinateDataValue(TypedDict):
    type: Literal["globecoordinate"]
    value: "GlobecoordinateValue"


# https://josh.github.io/wikidata-api-schemas/data-values/globecoordinate.schema.json#/properties/value
class GlobecoordinateValue(TypedDict, total=False):
    latitude: Required[float]
    longitude: Required[float]
    altitude: None
    precision: Required[float | None]
    globe: Required[str]


# https://josh.github.io/wikidata-api-schemas/data-values/monolingualtext.schema.json
class MonolingualTextDataValue(TypedDict):
    type: Literal["monolingualtext"]
    value: "MonolingualTextValue"


# https://josh.github.io/wikidata-api-schemas/data-values/monolingualtext.schema.json#/properties/value
class MonolingualTextValue(TypedDict):
    language: str
    text: str


# https://josh.github.io/wikidata-api-schemas/data-values/quantity.schema.json
class QuantityDataValue(TypedDict):
    type: Literal["quantity"]
    value: "QuantityValue"


# https://josh.github.io/wikidata-api-schemas/data-values/quantity.schema.json#/properties/value
class QuantityValue(TypedDict, total=False):
    amount: Required[str]
    upperBound: str
    lowerBound: str
    unit: Required[str]


# https://josh.github.io/wikidata-api-schemas/data-values/string.schema.json
class StringDataValue(TypedDict):
    type: Literal["string"]
    value: str


# https://josh.github.io/wikidata-api-schemas/data-values/time.schema.json
class TimeDataValue(TypedDict):
    type: Literal["time"]
    value: "TimeValue"


# https://josh.github.io/wikidata-api-schemas/data-values/time.schema.json#/properties/value
class TimeValue(TypedDict):
    time: str
    timezone: int
    before: int
    after: int
    precision: int
    calendarmodel: str


# https://josh.github.io/wikidata-api-schemas/data-values/wikibase-entityid.schema.json
class WikibaseEntityIdDataValue(TypedDict):
    type: Literal["wikibase-entityid"]
    value: Union["WikibaseItemIDValue", "WikibasePropertyIDValue"]


# https://josh.github.io/wikidata-api-schemas/data-values/wikibase-entityid.schema.json#/$defs/item-id
WikibaseItemIDValue = TypedDict(
    "WikibaseItemIDValue",
    {
        "entity-type": Literal["item"],
        "numeric-id": int,
        "id": str,
    },
)

# https://josh.github.io/wikidata-api-schemas/data-values/wikibase-entityid.schema.json#/$defs/property-id
WikibasePropertyIDValue = TypedDict(
    "WikibasePropertyIDValue",
    {
        "entity-type": Literal["property"],
        "numeric-id": int,
        "id": str,
    },
)


# https://josh.github.io/wikidata-api-schemas/statement.schema.json#/$defs/reference
Reference = TypedDict(
    "Reference",
    {
        "hash": str,
        "snaks": dict[str, list["Snak"]],
        "snaks-order": list[str],
    },
)
