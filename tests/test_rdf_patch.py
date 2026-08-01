from io import StringIO

from rdflib import XSD, BNode, Graph, Literal

from wikidata_rdf_patch import actions_logging, mediawiki_api
from wikidata_rdf_patch.rdf_patch import (
    PQ,
    PQE,
    PQV,
    PR,
    PRV,
    PS,
    RDF,
    WD,
    WDT,
    WIKIBASE,
    PropertyDatatypes,
    _datavalue_equals,
    _delete_statement_property_qualifiers,
    _format_time_value,
    _prefetch_property_datatypes,
    _resolve_object_bnode_quantity_value,
    _resolve_object_bnode_reference,
    _resolve_object_bnode_time_value,
    _resolve_object_literal,
    _resolve_statement_qualifiers,
    _resolve_statement_qualifiers_order,
    _resolve_statement_snak,
    process_graph,
)
from wikidata_rdf_patch.wikidata_typing import QuantityDataValue, Statement

actions_logging.setup()


def _add_full_time_value(graph: Graph, time: BNode) -> None:
    graph.add((time, RDF.type, WIKIBASE.TimeValue))
    graph.add(
        (
            time,
            WIKIBASE.timeValue,
            Literal("1991-11-25T00:00:00Z", datatype=XSD.dateTime),
        )
    )
    graph.add((time, WIKIBASE.timePrecision, Literal(9, datatype=XSD.integer)))


def test_full_qualifier_value_replaces_simple_value() -> None:
    graph = Graph()
    statement = BNode()
    full_time = BNode()
    graph.add(
        (
            statement,
            PQ.P585,
            Literal("1991-11-25T00:00:00Z", datatype=XSD.dateTime),
        )
    )
    graph.add((statement, PQV.P585, full_time))
    _add_full_time_value(graph, full_time)
    datatypes: PropertyDatatypes = {"P585": "time"}

    qualifiers = _resolve_statement_qualifiers(graph, datatypes, statement, "P585")

    assert _resolve_statement_qualifiers_order(graph, statement) == ["P585"]
    assert len(qualifiers) == 1
    qualifier = qualifiers[0]
    assert qualifier["snaktype"] == "value"
    assert qualifier["datavalue"]["type"] == "time"
    assert qualifier["datavalue"]["value"]["precision"] == 9


def test_full_reference_value_replaces_simple_value() -> None:
    graph = Graph()
    reference_node = BNode()
    full_time = BNode()
    graph.add(
        (
            reference_node,
            PR.P813,
            Literal("1991-11-25T00:00:00Z", datatype=XSD.dateTime),
        )
    )
    graph.add((reference_node, PRV.P813, full_time))
    _add_full_time_value(graph, full_time)
    datatypes: PropertyDatatypes = {"P813": "time"}

    reference = _resolve_object_bnode_reference(graph, datatypes, reference_node)

    assert reference["snaks-order"] == ["P813"]
    assert len(reference["snaks"]["P813"]) == 1
    snak = reference["snaks"]["P813"][0]
    assert snak["snaktype"] == "value"
    assert snak["datavalue"]["type"] == "time"
    assert snak["datavalue"]["value"]["precision"] == 9


def test_prefetch_property_datatypes_batches_51_properties() -> None:
    graph = Graph()
    subject = BNode()
    property_numbers = [
        number for number in range(1000, 1054) if number not in {1008, 1009, 1020}
    ]
    for property_number in property_numbers:
        graph.add((subject, WDT[f"P{property_number}"], Literal(property_number)))

    datatypes = _prefetch_property_datatypes(
        graph, user_agent=mediawiki_api.DEFAULT_USER_AGENT
    )

    assert len(datatypes) == 51
    assert datatypes.keys() == {f"P{number}" for number in property_numbers}


def test_resolve_unitless_quantity_value() -> None:
    graph = Graph()
    quantity = BNode()
    graph.add((quantity, WIKIBASE.quantityAmount, Literal(1, datatype=XSD.decimal)))
    graph.add((quantity, WIKIBASE.quantityUnit, WD.Q199))

    value = _resolve_object_bnode_quantity_value(graph, quantity)

    assert value["value"]["unit"] == "1"


def test_quantity_equality_requires_matching_units() -> None:
    bounded: QuantityDataValue = {
        "type": "quantity",
        "value": {
            "amount": "+1",
            "unit": "http://www.wikidata.org/entity/Q11573",
            "lowerBound": "+0",
            "upperBound": "+2",
        },
    }
    different_unit: QuantityDataValue = {
        "type": "quantity",
        "value": {
            "amount": "+1",
            "unit": "http://www.wikidata.org/entity/Q174728",
        },
    }
    same_unit_without_bounds: QuantityDataValue = {
        "type": "quantity",
        "value": {
            "amount": "+1",
            "unit": "http://www.wikidata.org/entity/Q11573",
        },
    }

    assert not _datavalue_equals(bounded, different_unit)
    assert _datavalue_equals(bounded, same_unit_without_bounds)


def test_quantity_equality_respects_explicit_bounds() -> None:
    first: QuantityDataValue = {
        "type": "quantity",
        "value": {
            "amount": "+1",
            "unit": "1",
            "lowerBound": "+0",
            "upperBound": "+2",
        },
    }
    second: QuantityDataValue = {
        "type": "quantity",
        "value": {
            "amount": "+1",
            "unit": "1",
            "lowerBound": "-1",
            "upperBound": "+3",
        },
    }

    assert not _datavalue_equals(first, second)


def test_delete_missing_statement_qualifier_is_noop() -> None:
    statement: Statement = {
        "id": "Q1$00000000-0000-0000-0000-000000000000",
        "type": "statement",
        "rank": "normal",
        "mainsnak": {
            "snaktype": "novalue",
            "property": "P31",
            "datatype": "wikibase-item",
        },
        "qualifiers": {},
        "qualifiers-order": ["P585"],
    }

    _delete_statement_property_qualifiers(statement, "P580")

    assert statement["qualifiers"] == {}
    assert statement["qualifiers-order"] == ["P585"]


def test_resolve_negative_quantity_values() -> None:
    direct = _resolve_object_literal(Literal(-123, datatype=XSD.decimal))
    assert direct["type"] == "quantity"
    assert direct["value"]["amount"] == "-123"

    graph = Graph()
    quantity = BNode()
    graph.add((quantity, WIKIBASE.quantityAmount, Literal(-123, datatype=XSD.decimal)))
    graph.add(
        (quantity, WIKIBASE.quantityLowerBound, Literal(-124, datatype=XSD.decimal))
    )
    graph.add(
        (quantity, WIKIBASE.quantityUpperBound, Literal(-122, datatype=XSD.decimal))
    )
    full = _resolve_object_bnode_quantity_value(graph, quantity)["value"]
    assert full["amount"] == "-123"
    assert full["lowerBound"] == "-124"
    assert full["upperBound"] == "-122"


def test_resolve_falsy_rdf_values() -> None:
    graph = Graph()

    quantity = BNode()
    graph.add((quantity, WIKIBASE.quantityAmount, Literal(0, datatype=XSD.decimal)))
    graph.add((quantity, WIKIBASE.quantityLowerBound, Literal(0, datatype=XSD.decimal)))
    graph.add((quantity, WIKIBASE.quantityUpperBound, Literal(0, datatype=XSD.decimal)))
    quantity_value = _resolve_object_bnode_quantity_value(graph, quantity)["value"]
    assert quantity_value["amount"] == "+0"
    assert quantity_value["lowerBound"] == "+0"
    assert quantity_value["upperBound"] == "+0"

    time = BNode()
    graph.add(
        (
            time,
            WIKIBASE.timeValue,
            Literal("2000-01-01T00:00:00Z", datatype=XSD.dateTime),
        )
    )
    graph.add((time, WIKIBASE.timePrecision, Literal(0, datatype=XSD.integer)))
    graph.add((time, WIKIBASE.timeTimezone, Literal(0, datatype=XSD.integer)))
    time_value = _resolve_object_bnode_time_value(graph, time)["value"]
    assert time_value["precision"] == 0
    assert time_value["timezone"] == 0

    statement = BNode()
    graph.add((statement, PS.P1106, Literal(0, datatype=XSD.decimal)))
    graph.add((statement, PQE.P1106, Literal(0, datatype=XSD.decimal)))
    datatypes: PropertyDatatypes = {"P1106": "quantity"}
    assert _resolve_statement_snak(graph, datatypes, statement, "P1106") is not None
    assert _resolve_statement_qualifiers(graph, datatypes, statement, "P1106")


def test_format_offset_datetime_as_utc() -> None:
    value = Literal("2012-10-30T03:30:00+03:30", datatype=XSD.dateTime)

    assert _format_time_value(value) == "+2012-10-30T00:00:00Z"


def test_format_naive_datetime_without_conversion() -> None:
    value = Literal("2012-10-30T03:30:00", datatype=XSD.dateTime)

    assert _format_time_value(value) == "+2012-10-30T03:30:00Z"


def test_format_date_without_conversion() -> None:
    value = Literal("2012-10-30", datatype=XSD.date)

    assert _format_time_value(value) == "+2012-10-30T00:00:00Z"


def test_format_timezone_date_without_conversion() -> None:
    offset = Literal("2012-10-30+03:30", datatype=XSD.date)
    utc = Literal("2012-10-30Z", datatype=XSD.date)

    assert _format_time_value(offset) == "+2012-10-30T00:00:00Z"
    assert _format_time_value(utc) == "+2012-10-30T00:00:00Z"


def test_format_offset_datetime_across_year_bounds() -> None:
    lower = Literal("0001-01-01T00:00:00+01:00", datatype=XSD.dateTime)
    upper = Literal("9999-12-31T23:59:59-01:00", datatype=XSD.dateTime)

    assert _format_time_value(lower) == "+0000-12-31T23:00:00Z"
    assert _format_time_value(upper) == "+10000-01-01T00:59:59Z"


def test_item_wdt_add_monolingualtext() -> None:
    triples = """
        wd:Q115569934 wdt:P1450 "hello"@en.
    """
    edits = list(process_graph(StringIO(triples)))
    assert len(edits) == 1
    (qid, _, claims, _) = edits[0]
    assert qid == "Q115569934"
    assert len(claims) == 1
    claim = claims[0]
    assert claim["id"].startswith("Q115569934$")
    assert claim["id"] != "Q115569934$47a71564-44cc-83f4-f53e-352c21c0f983"
    assert claim["mainsnak"]["snaktype"] == "value"
    assert claim["mainsnak"]["property"] == "P1450"
    assert claim["mainsnak"]["datatype"] == "monolingualtext"
    assert claim["mainsnak"]["datavalue"]["type"] == "monolingualtext"
    assert claim["mainsnak"]["datavalue"]["value"]["text"] == "hello"
    assert claim["mainsnak"]["datavalue"]["value"]["language"] == "en"


def test_item_wdt_noop_monolingualtext() -> None:
    triples = """
        wd:Q115569934 wdt:P1450 "hiekkalaatikko"@fi.
    """
    edits = list(process_graph(StringIO(triples)))
    assert len(edits) == 0


def test_item_wdt_add_commonsmediafile() -> None:
    triples = """
        wd:Q115569934 wdt:P368 <http://commons.wikimedia.org/wiki/Special:FilePath/NEW%20Sandbox%20with%20toys%20on%20R%C3%B6e%20g%C3%A5rd%201.jpg>.
    """
    edits = list(process_graph(StringIO(triples)))
    assert len(edits) == 1
    (qid, _, claims, _) = edits[0]
    assert qid == "Q115569934"
    assert len(claims) == 1
    claim = claims[0]
    assert claim["id"].startswith("Q115569934$")
    assert claim["id"] != "Q115569934$48c6e56b-40a2-90a8-85c1-68f39927381c"
    assert claim["mainsnak"]["snaktype"] == "value"
    assert claim["mainsnak"]["property"] == "P368"
    assert claim["mainsnak"]["datatype"] == "commonsMedia"
    assert claim["mainsnak"]["datavalue"]["type"] == "string"
    assert (
        claim["mainsnak"]["datavalue"]["value"]
        == "NEW Sandbox with toys on R\u00f6e g\u00e5rd 1.jpg"
    )


def test_item_wdt_noop_commonsmediafile() -> None:
    triples = """
        wd:Q115569934 wdt:P368 <http://commons.wikimedia.org/wiki/Special:FilePath/Sandbox%20with%20toys%20on%20R%C3%B6e%20g%C3%A5rd%201.jpg>.
    """
    edits = list(process_graph(StringIO(triples)))
    assert len(edits) == 0


def test_item_wdt_add_geocoordinate() -> None:
    triples = """
        wd:Q115569934 wdt:P626 "Point(-3.0 40.0)"^^geo:wktLiteral.
    """
    edits = list(process_graph(StringIO(triples)))
    assert len(edits) == 1
    (qid, _, claims, _) = edits[0]
    assert qid == "Q115569934"
    assert len(claims) == 1
    claim = claims[0]
    assert claim["id"].startswith("Q115569934$")
    assert claim["id"] != "Q115569934$fc0fd4ba-4ca1-b24c-dda7-de9d6fcab16a"
    assert claim["mainsnak"]["snaktype"] == "value"
    assert claim["mainsnak"]["property"] == "P626"
    assert claim["mainsnak"]["datatype"] == "globe-coordinate"
    assert claim["mainsnak"]["datavalue"]["type"] == "globecoordinate"
    assert claim["mainsnak"]["datavalue"]["value"]["latitude"] == 40.0
    assert claim["mainsnak"]["datavalue"]["value"]["longitude"] == -3.0
    assert claim["mainsnak"]["datavalue"]["value"]["altitude"] is None
    assert claim["mainsnak"]["datavalue"]["value"]["precision"] == 0.0001
    assert (
        claim["mainsnak"]["datavalue"]["value"]["globe"]
        == "http://www.wikidata.org/entity/Q2"
    )


def test_item_wdt_noop_geocoordinate() -> None:
    triples = """
        wd:Q115569934 wdt:P626 "Point(-3.6736 40.3929)"^^geo:wktLiteral.
    """
    edits = list(process_graph(StringIO(triples)))
    assert len(edits) == 0


def test_item_wdt_add_item() -> None:
    triples = """
        wd:Q115569934 wdt:P369 wd:Q13406268.
    """
    edits = list(process_graph(StringIO(triples)))
    assert len(edits) == 1
    (qid, _, claims, _) = edits[0]
    assert qid == "Q115569934"
    assert len(claims) == 1
    claim = claims[0]
    assert claim["id"].startswith("Q115569934$")
    assert claim["id"] != "Q115569934$eebff2d7-4a6b-457c-1327-b8a2786e99e7"
    assert claim["mainsnak"]["snaktype"] == "value"
    assert claim["mainsnak"]["property"] == "P369"
    assert claim["mainsnak"]["datatype"] == "wikibase-item"
    assert claim["mainsnak"]["datavalue"]["type"] == "wikibase-entityid"
    assert claim["mainsnak"]["datavalue"]["value"]["entity-type"] == "item"
    assert claim["mainsnak"]["datavalue"]["value"]["numeric-id"] == 13406268
    assert claim["mainsnak"]["datavalue"]["value"]["id"] == "Q13406268"


def test_item_wdt_noop_item() -> None:
    triples = """
        wd:Q115569934 wdt:P369 wd:Q4115189.
    """
    edits = list(process_graph(StringIO(triples)))
    assert len(edits) == 0


def test_item_wdt_add_quantity() -> None:
    triples = """
        wd:Q115569934 wdt:P1106 "+456"^^xsd:decimal.
    """
    edits = list(process_graph(StringIO(triples)))
    assert len(edits) == 1
    (qid, _, claims, _) = edits[0]
    assert qid == "Q115569934"
    assert len(claims) == 1
    claim = claims[0]
    assert claim["id"].startswith("Q115569934$")
    assert claim["id"] != "Q115569934$b40fcbdc-45c7-5aff-afd9-edafac78dfd4"
    assert claim["mainsnak"]["snaktype"] == "value"
    assert claim["mainsnak"]["property"] == "P1106"
    assert claim["mainsnak"]["datatype"] == "quantity"
    assert claim["mainsnak"]["datavalue"]["type"] == "quantity"
    assert claim["mainsnak"]["datavalue"]["value"]["amount"] == "+456"
    assert claim["mainsnak"]["datavalue"]["value"]["unit"] == "1"
    assert claim["mainsnak"]["datavalue"]["value"].get("lowerBound") is None
    assert claim["mainsnak"]["datavalue"]["value"].get("upperBound") is None


def test_item_wdt_noop_quantity() -> None:
    triples = """
        wd:Q115569934 wdt:P1106 "+123"^^xsd:decimal.
    """
    edits = list(process_graph(StringIO(triples)))
    assert len(edits) == 0


def test_item_wdt_add_string() -> None:
    triples = """
        wd:Q115569934 wdt:P370 "Goodbye world!".
    """
    edits = list(process_graph(StringIO(triples)))
    assert len(edits) == 1
    (qid, _, claims, _) = edits[0]
    assert qid == "Q115569934"
    assert len(claims) == 1
    claim = claims[0]
    assert claim["id"].startswith("Q115569934$")
    assert claim["id"] != "Q115569934$4874d203-4feb-def9-b19d-748313b1f9fc"
    assert claim["mainsnak"]["snaktype"] == "value"
    assert claim["mainsnak"]["property"] == "P370"
    assert claim["mainsnak"]["datatype"] == "string"
    assert claim["mainsnak"]["datavalue"]["type"] == "string"
    assert claim["mainsnak"]["datavalue"]["value"] == "Goodbye world!"


def test_item_wdt_noop_string() -> None:
    triples = """
        wd:Q115569934 wdt:P370 "Hello world!".
    """
    edits = list(process_graph(StringIO(triples)))
    assert len(edits) == 0


def test_item_wdt_add_time() -> None:
    triples = """
        wd:Q115569934 wdt:P578 "2012-10-30T00:00:00Z"^^xsd:dateTime.
    """
    edits = list(process_graph(StringIO(triples)))
    assert len(edits) == 1
    (qid, _, claims, _) = edits[0]
    assert qid == "Q115569934"
    assert len(claims) == 1
    claim = claims[0]
    assert claim["id"].startswith("Q115569934$")
    assert claim["id"] != "Q115569934$b2ad899e-42f0-9928-e69e-853715f8d6e6"
    assert claim["mainsnak"]["snaktype"] == "value"
    assert claim["mainsnak"]["property"] == "P578"
    assert claim["mainsnak"]["datatype"] == "time"
    assert claim["mainsnak"]["datavalue"]["type"] == "time"
    assert claim["mainsnak"]["datavalue"]["value"]["time"] == "+2012-10-30T00:00:00Z"
    assert claim["mainsnak"]["datavalue"]["value"]["timezone"] == 0
    assert claim["mainsnak"]["datavalue"]["value"]["before"] == 0
    assert claim["mainsnak"]["datavalue"]["value"]["after"] == 0
    assert claim["mainsnak"]["datavalue"]["value"]["precision"] == 11
    assert (
        claim["mainsnak"]["datavalue"]["value"]["calendarmodel"]
        == "http://www.wikidata.org/entity/Q1985727"
    )


def test_item_wdt_noop_time() -> None:
    triples = """
        wd:Q115569934 wdt:P578 "2012-10-29T00:00:00Z"^^xsd:dateTime.
    """
    edits = list(process_graph(StringIO(triples)))
    assert len(edits) == 0


def test_item_wdt_add_url() -> None:
    triples = """
        wd:Q115569934 wdt:P855 <http://example.org/>.
    """
    edits = list(process_graph(StringIO(triples)))
    assert len(edits) == 1
    (qid, _, claims, _) = edits[0]
    assert qid == "Q115569934"
    assert len(claims) == 1
    claim = claims[0]
    assert claim["id"].startswith("Q115569934$")
    assert claim["id"] != "Q115569934$01b174fc-49a8-650c-891f-aa77224c1794"
    assert claim["mainsnak"]["snaktype"] == "value"
    assert claim["mainsnak"]["property"] == "P855"
    assert claim["mainsnak"]["datatype"] == "url"
    assert claim["mainsnak"]["datavalue"]["type"] == "string"
    assert claim["mainsnak"]["datavalue"]["value"] == "http://example.org/"


def test_item_wdt_noop_url() -> None:
    triples = """
        wd:Q115569934 wdt:P855 <http://example.com/>.
    """
    edits = list(process_graph(StringIO(triples)))
    assert len(edits) == 0


def test_item_wdt_add_externalid() -> None:
    triples = """
        wd:Q115569934 wdt:P2536 "67890".
    """
    edits = list(process_graph(StringIO(triples)))
    assert len(edits) == 1
    (qid, _, claims, _) = edits[0]
    assert qid == "Q115569934"
    assert len(claims) == 1
    claim = claims[0]
    assert claim["id"].startswith("Q115569934$")
    assert claim["id"] != "Q115569934$82f9bf82-4463-35e5-7956-0a3a80b1e58b"
    assert claim["mainsnak"]["snaktype"] == "value"
    assert claim["mainsnak"]["property"] == "P2536"
    assert claim["mainsnak"]["datatype"] == "external-id"
    assert claim["mainsnak"]["datavalue"]["type"] == "string"
    assert claim["mainsnak"]["datavalue"]["value"] == "67890"


def test_item_wdt_noop_externalid() -> None:
    triples = """
        wd:Q115569934 wdt:P2536 "12345".
    """
    edits = list(process_graph(StringIO(triples)))
    assert len(edits) == 0


def test_item_wdt_update_deprecated() -> None:
    triple = """
        wd:Q1292541 wdt:P4947 "429486".
    """
    edits = list(process_graph(StringIO(triple)))
    # TODO: This should probably update the statement rank
    assert len(edits) == 0


def test_item_ps_add_string() -> None:
    triples = """
        wd:Q115569934 p:P370 [ ps:P370 "Hello world!" ].
    """
    edits = list(process_graph(StringIO(triples)))
    assert len(edits) == 1
    (qid, _, claims, _) = edits[0]
    assert qid == "Q115569934"
    assert len(claims) == 1
    claim = claims[0]
    assert claim["id"].startswith("Q115569934$")
    assert claim["id"] != "Q115569934$4874d203-4feb-def9-b19d-748313b1f9fc"
    assert claim["rank"] == "normal"
    assert claim["mainsnak"]["snaktype"] == "value"
    assert claim["mainsnak"]["property"] == "P370"
    assert claim["mainsnak"]["datavalue"]["type"] == "string"
    assert claim["mainsnak"]["datavalue"]["value"] == "Hello world!"


def test_item_ps_add_preferred_string() -> None:
    triples = """
        wd:Q115569934 p:P370 [
          wikibase:rank wikibase:PreferredRank ;
          ps:P370 "Hello world!";
          wikidatabots:editSummary "Added preferred string"
        ].
    """
    edits = list(process_graph(StringIO(triples)))
    assert len(edits) == 1
    (qid, _, claims, summary) = edits[0]
    assert qid == "Q115569934"
    assert summary == "Added preferred string"
    assert len(claims) == 1
    claim = claims[0]
    assert claim["id"].startswith("Q115569934$")
    assert claim["id"] != "Q115569934$4874d203-4feb-def9-b19d-748313b1f9fc"
    assert claim["rank"] == "preferred"
    assert claim["mainsnak"]["snaktype"] == "value"
    assert claim["mainsnak"]["property"] == "P370"
    assert claim["mainsnak"]["datavalue"]["type"] == "string"
    assert claim["mainsnak"]["datavalue"]["value"] == "Hello world!"


def test_item_ps_pq_add_string_time() -> None:
    triples = """
        wd:Q115569934 p:P370 [
          ps:P370 "Hello world!" ;
          pq:P585 "1991-11-25T00:00:00Z"^^xsd:dateTime
        ].
    """
    edits = list(process_graph(StringIO(triples)))
    assert len(edits) == 1
    (qid, _, claims, _) = edits[0]
    assert qid == "Q115569934"
    assert len(claims) == 1
    claim = claims[0]
    assert claim["id"].startswith("Q115569934$")
    assert claim["id"] != "Q115569934$4874d203-4feb-def9-b19d-748313b1f9fc"
    assert claim["rank"] == "normal"
    assert claim["mainsnak"]["snaktype"] == "value"
    assert claim["mainsnak"]["property"] == "P370"
    assert claim["mainsnak"]["datavalue"]["type"] == "string"
    assert claim["mainsnak"]["datavalue"]["value"] == "Hello world!"
    qualifier = claim["qualifiers"]["P585"][0]
    assert qualifier["snaktype"] == "value"
    assert qualifier["datavalue"]["type"] == "time"
    assert qualifier["datavalue"]["value"]["time"] == "+1991-11-25T00:00:00Z"
    assert qualifier["datavalue"]["value"]["precision"] == 11
    assert qualifier["datavalue"]["value"]["timezone"] == 0
    assert (
        qualifier["datavalue"]["value"]["calendarmodel"]
        == "http://www.wikidata.org/entity/Q1985727"
    )


def test_item_ps_pq_add_externalid_url() -> None:
    triples = """
        wd:Q115569934 p:P2536 [
          ps:P2536 "67890" ;
          pq:P854 <http://example.org/>
        ].
    """
    edits = list(process_graph(StringIO(triples)))
    assert len(edits) == 1
    (qid, _, claims, _) = edits[0]
    assert qid == "Q115569934"
    assert len(claims) == 1
    claim = claims[0]
    assert claim["id"].startswith("Q115569934$")
    assert claim["id"] != "Q115569934$82f9bf82-4463-35e5-7956-0a3a80b1e58b"
    assert claim["mainsnak"]["snaktype"] == "value"
    assert claim["mainsnak"]["property"] == "P2536"
    assert claim["mainsnak"]["datatype"] == "external-id"
    assert claim["mainsnak"]["datavalue"]["type"] == "string"
    assert claim["mainsnak"]["datavalue"]["value"] == "67890"
    qualifier = claim["qualifiers"]["P854"][0]
    assert qualifier["snaktype"] == "value"
    assert qualifier["datavalue"]["type"] == "string"
    assert qualifier["datavalue"]["value"] == "http://example.org/"


def test_item_ps_add_monolingualtext() -> None:
    triples = """
        wd:Q115569934 p:P1450 [ ps:P1450 "hello"@en ].
    """
    edits = list(process_graph(StringIO(triples)))
    assert len(edits) == 1
    (qid, _, claims, _) = edits[0]
    assert qid == "Q115569934"
    assert len(claims) == 1
    claim = claims[0]
    assert claim["id"].startswith("Q115569934$")
    assert claim["id"] != "Q115569934$47a71564-44cc-83f4-f53e-352c21c0f983"
    assert claim["mainsnak"]["snaktype"] == "value"
    assert claim["mainsnak"]["property"] == "P1450"
    assert claim["mainsnak"]["datatype"] == "monolingualtext"
    assert claim["mainsnak"]["datavalue"]["type"] == "monolingualtext"
    assert claim["mainsnak"]["datavalue"]["value"]["text"] == "hello"
    assert claim["mainsnak"]["datavalue"]["value"]["language"] == "en"


def test_item_ps_add_url() -> None:
    triples = """
        wd:Q115569934 p:P855 [ ps:P855 <http://example.org/> ].
    """
    edits = list(process_graph(StringIO(triples)))
    assert len(edits) == 1
    (qid, _, claims, _) = edits[0]
    assert qid == "Q115569934"
    assert len(claims) == 1
    claim = claims[0]
    assert claim["id"].startswith("Q115569934$")
    assert claim["id"] != "Q115569934$01b174fc-49a8-650c-891f-aa77224c1794"
    assert claim["mainsnak"]["snaktype"] == "value"
    assert claim["mainsnak"]["property"] == "P855"
    assert claim["mainsnak"]["datatype"] == "url"
    assert claim["mainsnak"]["datavalue"]["type"] == "string"
    assert claim["mainsnak"]["datavalue"]["value"] == "http://example.org/"


def test_item_ps_add_externalid() -> None:
    triples = """
        wd:Q115569934 p:P2536 [ ps:P2536 "67890" ].
    """
    edits = list(process_graph(StringIO(triples)))
    assert len(edits) == 1
    (qid, _, claims, _) = edits[0]
    assert qid == "Q115569934"
    assert len(claims) == 1
    claim = claims[0]
    assert claim["id"].startswith("Q115569934$")
    assert claim["id"] != "Q115569934$82f9bf82-4463-35e5-7956-0a3a80b1e58b"
    assert claim["mainsnak"]["snaktype"] == "value"
    assert claim["mainsnak"]["property"] == "P2536"
    assert claim["mainsnak"]["datatype"] == "external-id"
    assert claim["mainsnak"]["datavalue"]["type"] == "string"
    assert claim["mainsnak"]["datavalue"]["value"] == "67890"


def test_item_ps_add_time() -> None:
    triples = """
        wd:Q115569934 p:P578 [ ps:P578 "2012-10-30T00:00:00Z"^^xsd:dateTime ].
    """
    edits = list(process_graph(StringIO(triples)))
    assert len(edits) == 1
    (qid, _, claims, _) = edits[0]
    assert qid == "Q115569934"
    assert len(claims) == 1
    claim = claims[0]
    assert claim["id"].startswith("Q115569934$")
    assert claim["id"] != "Q115569934$b2ad899e-42f0-9928-e69e-853715f8d6e6"
    assert claim["mainsnak"]["snaktype"] == "value"
    assert claim["mainsnak"]["property"] == "P578"
    assert claim["mainsnak"]["datatype"] == "time"
    assert claim["mainsnak"]["datavalue"]["type"] == "time"
    assert claim["mainsnak"]["datavalue"]["value"]["time"] == "+2012-10-30T00:00:00Z"
    assert claim["mainsnak"]["datavalue"]["value"]["timezone"] == 0
    assert claim["mainsnak"]["datavalue"]["value"]["before"] == 0
    assert claim["mainsnak"]["datavalue"]["value"]["after"] == 0
    assert claim["mainsnak"]["datavalue"]["value"]["precision"] == 11
    assert (
        claim["mainsnak"]["datavalue"]["value"]["calendarmodel"]
        == "http://www.wikidata.org/entity/Q1985727"
    )


def test_item_psv_add_time() -> None:
    triples = """
        wd:Q115569934 p:P578 [
          psv:P578 [
            a wikibase:TimeValue ;
            wikibase:timeValue "2012-10-30T00:00:00Z"^^xsd:dateTime ;
            wikibase:timePrecision "11"^^xsd:integer ;
            wikibase:timeTimezone "0"^^xsd:integer ;
            wikibase:timeCalendarModel <http://www.wikidata.org/entity/Q1985727>
          ]
        ].
    """
    edits = list(process_graph(StringIO(triples)))
    assert len(edits) == 1
    (qid, _, claims, _) = edits[0]
    assert qid == "Q115569934"
    assert len(claims) == 1
    claim = claims[0]
    assert claim["id"].startswith("Q115569934$")
    assert claim["id"] != "Q115569934$b2ad899e-42f0-9928-e69e-853715f8d6e6"
    assert claim["mainsnak"]["snaktype"] == "value"
    assert claim["mainsnak"]["property"] == "P578"
    assert claim["mainsnak"]["datatype"] == "time"
    assert claim["mainsnak"]["datavalue"]["type"] == "time"
    assert claim["mainsnak"]["datavalue"]["value"]["time"] == "+2012-10-30T00:00:00Z"
    assert claim["mainsnak"]["datavalue"]["value"]["timezone"] == 0
    assert claim["mainsnak"]["datavalue"]["value"]["before"] == 0
    assert claim["mainsnak"]["datavalue"]["value"]["after"] == 0
    assert claim["mainsnak"]["datavalue"]["value"]["precision"] == 11
    assert (
        claim["mainsnak"]["datavalue"]["value"]["calendarmodel"]
        == "http://www.wikidata.org/entity/Q1985727"
    )


def test_statement_rank_change() -> None:
    triples = """
      wds:Q172241-6B571F20-7732-47E1-86B2-1DFA6D0A15F5 wikibase:rank wikibase:DeprecatedRank;
        wikidatabots:editSummary "Changed rank".
    """
    edits = list(process_graph(StringIO(triples)))
    assert len(edits) == 1
    (qid, _, claims, summary) = edits[0]
    assert qid == "Q172241"
    assert summary == "Changed rank"
    assert len(claims) == 1
    claim = claims[0]
    assert claim["id"] == "Q172241$6B571F20-7732-47E1-86B2-1DFA6D0A15F5"
    assert claim["rank"] == "deprecated"


def test_statement_rank_noop() -> None:
    triples = """
      wds:Q172241-6B571F20-7732-47E1-86B2-1DFA6D0A15F5 wikibase:rank wikibase:NormalRank;
        wikidatabots:editSummary "Changed rank".
    """
    edits = list(process_graph(StringIO(triples)))
    assert len(edits) == 0


def test_statement_ps_change() -> None:
    triples = """
      wds:Q115569934-4874d203-4feb-def9-b19d-748313b1f9fc ps:P370 "Goodbye world!";
        wikidatabots:editSummary "Changed string".
    """
    edits = list(process_graph(StringIO(triples)))
    assert len(edits) == 1
    (qid, _, claims, summary) = edits[0]
    assert qid == "Q115569934"
    assert summary == "Changed string"
    assert len(claims) == 1
    claim = claims[0]
    assert claim["id"] == "Q115569934$4874d203-4feb-def9-b19d-748313b1f9fc"
    assert claim["mainsnak"]["snaktype"] == "value"
    assert claim["mainsnak"]["datavalue"]["type"] == "string"
    assert claim["mainsnak"]["datavalue"]["value"] == "Goodbye world!"


def test_statement_ps_noop() -> None:
    triples = """
      wds:Q115569934-4874d203-4feb-def9-b19d-748313b1f9fc ps:P370 "Hello world!".
    """
    edits = list(process_graph(StringIO(triples)))
    assert len(edits) == 0


# def test_statement_novalue_change() -> None:
#     triples = """
#       wds:Q115569934-4874d203-4feb-def9-b19d-748313b1f9fc rdf:type wdno:P370.
#     """
#     edits = list(process_graph(StringIO(triples)))
#     assert len(edits) == 1


# def test_statement_somevalue_change() -> None:
#     triples = """
#       wds:Q115569934-4874d203-4feb-def9-b19d-748313b1f9fc ps:P1114 <http://www.wikidata.org/.well-known/genid/18b85823a28c78df421964c2e19009e1>.
#     """
#     edits = list(process_graph(StringIO(triples)))
#     assert len(edits) == 1


def test_statement_psv_change() -> None:
    triples = """
      wds:Q115569934-b40fcbdc-45c7-5aff-afd9-edafac78dfd4 psv:P1106 [
        a wikibase:QuantityValue ;
        wikibase:quantityAmount "+456"^^xsd:decimal ;
        wikibase:quantityUpperBound "+466"^^xsd:decimal ;
        wikibase:quantityLowerBound "+446"^^xsd:decimal ;
        wikibase:quantityUnit <http://www.wikidata.org/entity/Q199>
      ].
    """
    edits = list(process_graph(StringIO(triples)))
    assert len(edits) == 1
    (qid, _, claims, _) = edits[0]
    assert qid == "Q115569934"
    assert len(claims) == 1
    claim = claims[0]
    assert claim["id"] == "Q115569934$b40fcbdc-45c7-5aff-afd9-edafac78dfd4"
    assert claim["mainsnak"]["snaktype"] == "value"
    assert claim["mainsnak"]["property"] == "P1106"
    assert claim["mainsnak"]["datavalue"]["type"] == "quantity"
    assert claim["mainsnak"]["datavalue"]["value"]["amount"] == "+456"
    assert claim["mainsnak"]["datavalue"]["value"]["unit"] == "1"
    assert claim["mainsnak"]["datavalue"]["value"]["upperBound"] == "+466"
    assert claim["mainsnak"]["datavalue"]["value"]["lowerBound"] == "+446"


def test_statement_psv_noop() -> None:
    triples = """
      wds:Q115569934-b40fcbdc-45c7-5aff-afd9-edafac78dfd4 psv:P1106 [
        a wikibase:QuantityValue ;
        wikibase:quantityAmount "+123"^^xsd:decimal ;
        wikibase:quantityUpperBound "+133"^^xsd:decimal ;
        wikibase:quantityLowerBound "+113"^^xsd:decimal ;
        wikibase:quantityUnit <http://www.wikidata.org/entity/Q199>
      ].
    """
    edits = list(process_graph(StringIO(triples)))
    assert len(edits) == 0


def test_statement_pq_add() -> None:
    triples = """
      wds:q42-b88670f8-456b-3ecb-cf3d-2bca2cf7371e pq:P585 "1991-11-25T00:00:00Z"^^xsd:dateTime.
    """
    edits = list(process_graph(StringIO(triples)))
    assert len(edits) == 1
    (qid, _, claims, _) = edits[0]
    assert qid == "Q42"
    assert len(claims) == 1
    claim = claims[0]
    assert claim["id"] == "q42$b88670f8-456b-3ecb-cf3d-2bca2cf7371e"
    qualifier = claim["qualifiers"]["P585"][0]
    assert qualifier["snaktype"] == "value"
    assert qualifier["datavalue"]["type"] == "time"
    assert qualifier["datavalue"]["value"]["time"] == "+1991-11-25T00:00:00Z"
    assert qualifier["datavalue"]["value"]["precision"] == 11
    assert qualifier["datavalue"]["value"]["timezone"] == 0
    assert (
        qualifier["datavalue"]["value"]["calendarmodel"]
        == "http://www.wikidata.org/entity/Q1985727"
    )


def test_statement_pq_noop() -> None:
    triples = """
      wds:q42-b88670f8-456b-3ecb-cf3d-2bca2cf7371e pq:P580 "1991-11-25T00:00:00Z"^^xsd:dateTime.
    """
    edits = list(process_graph(StringIO(triples)))
    assert len(edits) == 0


def test_statement_pqv_add() -> None:
    triples = """
      wds:q42-b88670f8-456b-3ecb-cf3d-2bca2cf7371e pqv:P585 [
        a wikibase:TimeValue ;
        wikibase:timeValue "1991-11-25T00:00:00Z"^^xsd:dateTime ;
        wikibase:timePrecision "11"^^xsd:integer ;
        wikibase:timeTimezone "0"^^xsd:integer ;
        wikibase:timeCalendarModel <http://www.wikidata.org/entity/Q1985727>
      ].
    """
    edits = list(process_graph(StringIO(triples)))
    assert len(edits) == 1
    (qid, _, claims, _) = edits[0]
    assert qid == "Q42"
    assert len(claims) == 1
    claim = claims[0]
    assert claim["id"] == "q42$b88670f8-456b-3ecb-cf3d-2bca2cf7371e"
    qualifier = claim["qualifiers"]["P585"][0]
    assert qualifier["snaktype"] == "value"
    assert qualifier["datavalue"]["type"] == "time"
    assert qualifier["datavalue"]["value"]["time"] == "+1991-11-25T00:00:00Z"
    assert qualifier["datavalue"]["value"]["precision"] == 11
    assert qualifier["datavalue"]["value"]["timezone"] == 0
    assert (
        qualifier["datavalue"]["value"]["calendarmodel"]
        == "http://www.wikidata.org/entity/Q1985727"
    )


def test_statement_pqv_noop() -> None:
    triples = """
      wds:q42-b88670f8-456b-3ecb-cf3d-2bca2cf7371e pqv:P580 [
          a wikibase:TimeValue ;
          wikibase:timeValue "1991-11-25T00:00:00Z"^^xsd:dateTime ;
          wikibase:timePrecision "11"^^xsd:integer ;
          wikibase:timeTimezone "0"^^xsd:integer ;
          wikibase:timeCalendarModel <http://www.wikidata.org/entity/Q1985727>
      ].
    """
    edits = list(process_graph(StringIO(triples)))
    assert len(edits) == 0


def test_statement_pqe_add() -> None:
    triples = """
      wds:q42-b88670f8-456b-3ecb-cf3d-2bca2cf7371e pqe:P580 "1992-11-25T00:00:00Z"^^xsd:dateTime.
    """
    edits = list(process_graph(StringIO(triples)))
    assert len(edits) == 1
    (qid, _, claims, _) = edits[0]
    assert qid == "Q42"
    assert len(claims) == 1
    claim = claims[0]
    assert claim["id"] == "q42$b88670f8-456b-3ecb-cf3d-2bca2cf7371e"
    qualifier = claim["qualifiers"]["P580"][0]
    assert qualifier["snaktype"] == "value"
    assert qualifier["datavalue"]["type"] == "time"
    assert qualifier["datavalue"]["value"]["time"] == "+1992-11-25T00:00:00Z"
    assert qualifier["datavalue"]["value"]["precision"] == 11
    assert qualifier["datavalue"]["value"]["timezone"] == 0
    assert (
        qualifier["datavalue"]["value"]["calendarmodel"]
        == "http://www.wikidata.org/entity/Q1985727"
    )


def test_statement_pqe_noop() -> None:
    triples = """
      wds:q42-b88670f8-456b-3ecb-cf3d-2bca2cf7371e pqe:P580 "1991-11-25T00:00:00Z"^^xsd:dateTime.
    """
    edits = list(process_graph(StringIO(triples)))
    assert len(edits) == 0


def test_statement_pqve_update() -> None:
    triples = """
      wds:q42-b88670f8-456b-3ecb-cf3d-2bca2cf7371e pqve:P580 [
        a wikibase:TimeValue ;
        wikibase:timeValue "1992-11-25T00:00:00Z"^^xsd:dateTime ;
        wikibase:timePrecision "11"^^xsd:integer ;
        wikibase:timeTimezone "0"^^xsd:integer ;
        wikibase:timeCalendarModel <http://www.wikidata.org/entity/Q1985727>
      ].
    """
    edits = list(process_graph(StringIO(triples)))
    assert len(edits) == 1
    (qid, _, claims, _) = edits[0]
    assert qid == "Q42"
    assert len(claims) == 1
    claim = claims[0]
    assert claim["id"] == "q42$b88670f8-456b-3ecb-cf3d-2bca2cf7371e"
    qualifier = claim["qualifiers"]["P580"][0]
    assert qualifier["snaktype"] == "value"
    assert qualifier["datavalue"]["type"] == "time"
    assert qualifier["datavalue"]["value"]["time"] == "+1992-11-25T00:00:00Z"
    assert qualifier["datavalue"]["value"]["precision"] == 11
    assert qualifier["datavalue"]["value"]["timezone"] == 0
    assert (
        qualifier["datavalue"]["value"]["calendarmodel"]
        == "http://www.wikidata.org/entity/Q1985727"
    )


def test_statement_pqve_noop() -> None:
    triples = """
      wds:q42-b88670f8-456b-3ecb-cf3d-2bca2cf7371e pqve:P580 [
          a wikibase:TimeValue ;
          wikibase:timeValue "1991-11-25T00:00:00Z"^^xsd:dateTime ;
          wikibase:timePrecision "11"^^xsd:integer ;
          wikibase:timeTimezone "0"^^xsd:integer ;
          wikibase:timeCalendarModel <http://www.wikidata.org/entity/Q1985727>
      ].
    """
    edits = list(process_graph(StringIO(triples)))
    assert len(edits) == 0


def test_statement_pqe_remove() -> None:
    triples = """
      wds:q42-b88670f8-456b-3ecb-cf3d-2bca2cf7371e pqe:P580 [].
    """
    edits = list(process_graph(StringIO(triples)))
    assert len(edits) == 1
    (qid, _, claims, _) = edits[0]
    assert qid == "Q42"
    assert len(claims) == 1
    claim = claims[0]
    assert claim["id"] == "q42$b88670f8-456b-3ecb-cf3d-2bca2cf7371e"
    assert "P580" not in claim["qualifiers"]
    assert "P580" not in claim["qualifiers-order"]


def test_statement_prov_wasderivedfrom_add() -> None:
    triples = """
        wds:Q115569934-4874d203-4feb-def9-b19d-748313b1f9fc prov:wasDerivedFrom [
          pr:P854 "http://example.com";
          pr:P813 "2024-01-01"^^xsd:date
        ].
    """
    edits = list(process_graph(StringIO(triples)))
    assert len(edits) == 1
    (qid, _, claims, _) = edits[0]
    assert qid == "Q115569934"
    assert len(claims) == 1
    claim = claims[0]
    assert claim["id"] == "Q115569934$4874d203-4feb-def9-b19d-748313b1f9fc"
    assert "references" in claim
    reference = claim["references"][0]
    assert "hash" not in reference
    assert reference["snaks-order"] == ["P854", "P813"]
    assert reference["snaks"]["P854"][0]["snaktype"] == "value"
    assert reference["snaks"]["P854"][0]["datavalue"]["type"] == "string"
    assert reference["snaks"]["P854"][0]["datavalue"]["value"] == "http://example.com"
    assert reference["snaks"]["P813"][0]["snaktype"] == "value"
    assert reference["snaks"]["P813"][0]["datavalue"]["type"] == "time"
    assert (
        reference["snaks"]["P813"][0]["datavalue"]["value"]["time"]
        == "+2024-01-01T00:00:00Z"
    )


def test_statement_prov_wasderivedfrom_noop() -> None:
    triples = """
        wds:Q42-1d7d0ea9-412f-8b5b-ba8d-405ab9ecf026 prov:wasDerivedFrom [
            pr:P248 wd:Q36578 ;
            pr:P227 "119033364" ;
            pr:P407 wd:Q188 ;
            pr:P813 "2022-10-09T00:00:00Z"^^xsd:dateTime ;
        ].
    """
    edits = list(process_graph(StringIO(triples)))
    assert len(edits) == 0


def test_statement_prov_wasonlyderivedfrom_add() -> None:
    triples = """
        wds:Q115569934-4874d203-4feb-def9-b19d-748313b1f9fc prov:wasOnlyDerivedFrom [
          pr:P854 "http://example.com";
          pr:P813 "2024-01-01"^^xsd:date
        ].
    """
    edits = list(process_graph(StringIO(triples)))
    assert len(edits) == 1
    (qid, _, claims, _) = edits[0]
    assert qid == "Q115569934"
    assert len(claims) == 1
    claim = claims[0]
    assert claim["id"] == "Q115569934$4874d203-4feb-def9-b19d-748313b1f9fc"
    assert "references" in claim
    reference = claim["references"][0]
    assert "hash" not in reference
    assert reference["snaks-order"] == ["P854", "P813"]
    assert reference["snaks"]["P854"][0]["snaktype"] == "value"
    assert reference["snaks"]["P854"][0]["datavalue"]["type"] == "string"
    assert reference["snaks"]["P854"][0]["datavalue"]["value"] == "http://example.com"
    assert reference["snaks"]["P813"][0]["snaktype"] == "value"
    assert reference["snaks"]["P813"][0]["datavalue"]["type"] == "time"
    assert (
        reference["snaks"]["P813"][0]["datavalue"]["value"]["time"]
        == "+2024-01-01T00:00:00Z"
    )


def test_statement_prov_wasonlyderivedfrom_noop() -> None:
    triples = """
        wds:Q42-1d7d0ea9-412f-8b5b-ba8d-405ab9ecf026 prov:wasOnlyDerivedFrom [
            pr:P248 wd:Q36578 ;
            pr:P227 "119033364" ;
            pr:P407 wd:Q188 ;
            pr:P813 "2022-10-09T00:00:00Z"^^xsd:dateTime ;
        ].
    """
    edits = list(process_graph(StringIO(triples)))
    assert len(edits) == 0


def test_item_deleted_modification() -> None:
    triples = """
        wd:Q9964271 wdt:P31 wd:Q5.
    """
    edits = list(process_graph(StringIO(triples)))
    assert len(edits) == 0
