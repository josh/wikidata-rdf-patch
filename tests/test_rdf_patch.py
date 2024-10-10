from io import StringIO

import wikidata_rdf_patch.actions_logging as actions_logging
from wikidata_rdf_patch.rdf_patch import process_graph

actions_logging.setup()


def test_item_wdt_add_monolingualtext() -> None:
    triples = """
        wd:Q115569934 wdt:P1450 "hello"@en.
    """
    edits = list(process_graph(StringIO(triples)))
    assert len(edits) == 1
    (item, claims, _) = edits[0]
    assert item["id"] == "Q115569934"
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
    (item, claims, _) = edits[0]
    assert item["id"] == "Q115569934"
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
    (item, claims, _) = edits[0]
    assert item["id"] == "Q115569934"
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
    (item, claims, _) = edits[0]
    assert item["id"] == "Q115569934"
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
    (item, claims, _) = edits[0]
    assert item["id"] == "Q115569934"
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
    (item, claims, _) = edits[0]
    assert item["id"] == "Q115569934"
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
    (item, claims, _) = edits[0]
    assert item["id"] == "Q115569934"
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
    (item, claims, _) = edits[0]
    assert item["id"] == "Q115569934"
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
    (item, claims, _) = edits[0]
    assert item["id"] == "Q115569934"
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


def test_item_p_add_string() -> None:
    triples = """
        wd:Q115569934 p:P370 [ ps:P370 "Hello world!" ].
    """
    edits = list(process_graph(StringIO(triples)))
    assert len(edits) == 1
    (item, claims, _) = edits[0]
    assert item["id"] == "Q115569934"
    assert len(claims) == 1
    claim = claims[0]
    assert claim["id"].startswith("Q115569934$")
    assert claim["id"] != "Q115569934$4874d203-4feb-def9-b19d-748313b1f9fc"
    assert claim["rank"] == "normal"
    assert claim["mainsnak"]["snaktype"] == "value"
    assert claim["mainsnak"]["property"] == "P370"
    assert claim["mainsnak"]["datavalue"]["type"] == "string"
    assert claim["mainsnak"]["datavalue"]["value"] == "Hello world!"


def test_item_p_add_preferred_string() -> None:
    triples = """
        wd:Q115569934 p:P370 [ wikibase:rank wikibase:PreferredRank ; ps:P370 "Hello world!" ].
    """
    edits = list(process_graph(StringIO(triples)))
    assert len(edits) == 1
    (item, claims, _) = edits[0]
    assert item["id"] == "Q115569934"
    assert len(claims) == 1
    claim = claims[0]
    assert claim["id"].startswith("Q115569934$")
    assert claim["id"] != "Q115569934$4874d203-4feb-def9-b19d-748313b1f9fc"
    assert claim["rank"] == "preferred"
    assert claim["mainsnak"]["snaktype"] == "value"
    assert claim["mainsnak"]["property"] == "P370"
    assert claim["mainsnak"]["datavalue"]["type"] == "string"
    assert claim["mainsnak"]["datavalue"]["value"] == "Hello world!"


def test_statement_rank_change() -> None:
    triples = """
      wds:Q172241-6B571F20-7732-47E1-86B2-1DFA6D0A15F5 wikibase:rank wikibase:DeprecatedRank;
        wikidatabots:editSummary "Changed rank".
    """
    edits = list(process_graph(StringIO(triples)))
    assert len(edits) == 1
    (item, claims, summary) = edits[0]
    assert item["id"] == "Q172241"
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
      wds:Q115569934-4874d203-4feb-def9-b19d-748313b1f9fc ps:P370 "Goodbye world!".
    """
    edits = list(process_graph(StringIO(triples)))
    assert len(edits) == 1
    (item, claims, _) = edits[0]
    assert item["id"] == "Q115569934"
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
    (item, claims, _) = edits[0]
    assert item["id"] == "Q115569934"
    assert len(claims) == 1
    claim = claims[0]
    assert claim["id"] == "Q115569934$b40fcbdc-45c7-5aff-afd9-edafac78dfd4"
    assert claim["mainsnak"]["snaktype"] == "value"
    assert claim["mainsnak"]["property"] == "P1106"
    assert claim["mainsnak"]["datavalue"]["type"] == "quantity"
    assert claim["mainsnak"]["datavalue"]["value"]["amount"] == "+456"
    assert (
        claim["mainsnak"]["datavalue"]["value"]["unit"]
        == "http://www.wikidata.org/entity/Q199"
    )
    assert claim["mainsnak"]["datavalue"]["value"]["upperBound"] == "+466"
    assert claim["mainsnak"]["datavalue"]["value"]["lowerBound"] == "+446"


def test_statement_psv_noop() -> None:
    triples = """
      wds:Q115569934-b40fcbdc-45c7-5aff-afd9-edafac78dfd4 psv:P1106 [
        a wikibase:QuantityValue ;
        wikibase:quantityAmount "+123"^^xsd:decimal ;
        wikibase:quantityUpperBound "+133"^^xsd:decimal ;
        wikibase:quantityLowerBound "+113"^^xsd:decimal ;
        wikibase:quantityUnit <https://www.wikidata.org/wiki/Q199>
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
    (item, claims, _) = edits[0]
    assert item["id"] == "Q42"
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
    (item, claims, _) = edits[0]
    assert item["id"] == "Q42"
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
    (item, claims, _) = edits[0]
    assert item["id"] == "Q42"
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
    (item, claims, _) = edits[0]
    assert item["id"] == "Q42"
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
    (item, claims, _) = edits[0]
    assert item["id"] == "Q42"
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
    (item, claims, _) = edits[0]
    assert item["id"] == "Q115569934"
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
    (item, claims, _) = edits[0]
    assert item["id"] == "Q115569934"
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
