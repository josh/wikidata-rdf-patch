import datetime
import itertools
import logging
import re
import urllib.parse
import urllib.request
import uuid
from collections import defaultdict
from collections.abc import Iterable, Iterator
from copy import deepcopy
from typing import TextIO

from rdflib import XSD, Graph
from rdflib.namespace import Namespace, NamespaceManager
from rdflib.term import BNode, Literal, URIRef

from . import mediawiki_api, wikidata_typing
from .rdflib import (
    GraphObject,
    GraphSubject,
    graph_empty_node,
    graph_literal,
    graph_objects,
    graph_predicate_objects,
    graph_predicates,
    graph_subjects,
    graph_urirefs,
    graph_value,
)

logger = logging.getLogger("rdf_patch")

P = Namespace("http://www.wikidata.org/prop/")
PQ = Namespace("http://www.wikidata.org/prop/qualifier/")
PQE = Namespace("http://www.wikidata.org/prop/qualifier/exclusive/")
PQV = Namespace("http://www.wikidata.org/prop/qualifier/value/")
PQVE = Namespace("http://www.wikidata.org/prop/qualifier/value-exclusive/")
PR = Namespace("http://www.wikidata.org/prop/reference/")
PRV = Namespace("http://www.wikidata.org/prop/reference/value/")
PS = Namespace("http://www.wikidata.org/prop/statement/")
PSV = Namespace("http://www.wikidata.org/prop/statement/value/")
PROV = Namespace("http://www.w3.org/ns/prov#")
WD = Namespace("http://www.wikidata.org/entity/")
WDREF = Namespace("http://www.wikidata.org/reference/")
WDS = Namespace("http://www.wikidata.org/entity/statement/")
WDT = Namespace("http://www.wikidata.org/prop/direct/")
WDV = Namespace("http://www.wikidata.org/value/")
WDNO = Namespace("http://www.wikidata.org/prop/novalue/")
RDF = Namespace("http://www.w3.org/1999/02/22-rdf-syntax-ns#")
WIKIBASE = Namespace("http://wikiba.se/ontology#")
GEO = Namespace("http://www.opengis.net/ont/geosparql#")
COMMONS_MEDIA = Namespace("http://commons.wikimedia.org/wiki/Special:FilePath/")

WIKIDATABOTS = Namespace("https://github.com/josh/wikidatabots#")

NS_MANAGER = NamespaceManager(Graph())
NS_MANAGER.bind("wikibase", WIKIBASE)
NS_MANAGER.bind("wd", WD)
NS_MANAGER.bind("wds", WDS)
NS_MANAGER.bind("wdv", WDV)
NS_MANAGER.bind("wdref", WDREF)
NS_MANAGER.bind("wdt", WDT)
NS_MANAGER.bind("p", P)
NS_MANAGER.bind("wdno", WDNO)
NS_MANAGER.bind("ps", PS)
NS_MANAGER.bind("psv", PSV)
NS_MANAGER.bind("pq", PQ)
NS_MANAGER.bind("pqe", PQE)
NS_MANAGER.bind("pqv", PQV)
NS_MANAGER.bind("pqve", PQVE)
NS_MANAGER.bind("pr", PR)
NS_MANAGER.bind("prv", PRV)
NS_MANAGER.bind("geo", GEO)
NS_MANAGER.bind("commonsMedia", COMMONS_MEDIA)
NS_MANAGER.bind("wikidatabots", WIKIDATABOTS)

PREFIXES = """
PREFIX bd: <http://www.bigdata.com/rdf#>
PREFIX cc: <http://creativecommons.org/ns#>
PREFIX dct: <http://purl.org/dc/terms/>
PREFIX geo: <http://www.opengis.net/ont/geosparql#>
PREFIX hint: <http://www.bigdata.com/queryHints#>
PREFIX ontolex: <http://www.w3.org/ns/lemon/ontolex#>
PREFIX owl: <http://www.w3.org/2002/07/owl#>
PREFIX prov: <http://www.w3.org/ns/prov#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX schema: <http://schema.org/>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

PREFIX p: <http://www.wikidata.org/prop/>
PREFIX pq: <http://www.wikidata.org/prop/qualifier/>
PREFIX pqe: <http://www.wikidata.org/prop/qualifier/exclusive/>
PREFIX pqn: <http://www.wikidata.org/prop/qualifier/value-normalized/>
PREFIX pqv: <http://www.wikidata.org/prop/qualifier/value/>
PREFIX pqve: <http://www.wikidata.org/prop/qualifier/value-exclusive/>
PREFIX pr: <http://www.wikidata.org/prop/reference/>
PREFIX prn: <http://www.wikidata.org/prop/reference/value-normalized/>
PREFIX prv: <http://www.wikidata.org/prop/reference/value/>
PREFIX psv: <http://www.wikidata.org/prop/statement/value/>
PREFIX ps: <http://www.wikidata.org/prop/statement/>
PREFIX psn: <http://www.wikidata.org/prop/statement/value-normalized/>
PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdata: <http://www.wikidata.org/wiki/Special:EntityData/>
PREFIX wdno: <http://www.wikidata.org/prop/novalue/>
PREFIX wdref: <http://www.wikidata.org/reference/>
PREFIX wds: <http://www.wikidata.org/entity/statement/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX wdtn: <http://www.wikidata.org/prop/direct-normalized/>
PREFIX wdv: <http://www.wikidata.org/value/>
PREFIX wikibase: <http://wikiba.se/ontology#>

PREFIX wikidatabots: <https://github.com/josh/wikidatabots#>
PREFIX commonsMedia: <http://commons.wikimedia.org/wiki/Special:FilePath/>

"""


PropertyDatatypes = dict[str, wikidata_typing.DataType]


def _compute_qname(uri: URIRef) -> tuple[str, str]:
    try:
        prefix, _, name = NS_MANAGER.compute_qname(uri)
        return (prefix, name)
    except ValueError:
        return ("", str(uri))


def _resolve_object_uriref(
    object: URIRef,
) -> wikidata_typing.WikibaseEntityIdDataValue | wikidata_typing.StringDataValue:
    prefix, local_name = _compute_qname(object)

    if prefix == "wd" and local_name.startswith("Q"):
        return {
            "type": "wikibase-entityid",
            "value": {
                "entity-type": "item",
                "numeric-id": int(local_name[1:]),
                "id": local_name,
            },
        }
    elif prefix == "wd" and local_name.startswith("P"):
        return {
            "type": "wikibase-entityid",
            "value": {
                "entity-type": "property",
                "numeric-id": int(local_name[1:]),
                "id": local_name,
            },
        }
    elif prefix == "commonsMedia":
        return {
            "type": "string",
            "value": urllib.parse.unquote(local_name),
        }
    elif prefix == "":
        return {
            "type": "string",
            "value": local_name,
        }
    else:
        raise NotImplementedError(f"Unknown URI: {prefix}:{local_name} <{object}>")


def _resolve_object_bnode_time_value(
    graph: Graph, object: BNode
) -> wikidata_typing.TimeDataValue:
    if value := graph_literal(graph, object, WIKIBASE.timeValue):
        assert value.datatype is None or value.datatype == XSD.dateTime
    if precision := graph_literal(graph, object, WIKIBASE.timePrecision):
        assert precision.datatype == XSD.integer
        assert 0 <= precision.toPython() <= 14
    if timezone := graph_literal(graph, object, WIKIBASE.timeTimezone):
        assert timezone.datatype == XSD.integer
    if calendar_model := graph_value(graph, object, WIKIBASE.timeCalendarModel):
        assert isinstance(calendar_model, URIRef)

    data: wikidata_typing.TimeValue = {
        "time": "",
        "precision": 11,
        "after": 0,
        "before": 0,
        "timezone": 0,
        "calendarmodel": "https://www.wikidata.org/wiki/Q1985727",
    }
    if value:
        value_dt = value.toPython()
        if not isinstance(value_dt, datetime.datetime):
            value_dt = datetime.datetime.fromisoformat(value_dt)
        data["time"] = value_dt.strftime("+%Y-%m-%dT%H:%M:%SZ")
    if precision:
        data["precision"] = precision.toPython()
    if timezone:
        data["timezone"] = timezone.toPython()
    if calendar_model:
        data["calendarmodel"] = str(calendar_model)
    assert data["time"] != "", "missing time value"
    return {"type": "time", "value": data}


def _resolve_object_bnode_quantity_value(
    graph: Graph, object: BNode
) -> wikidata_typing.QuantityDataValue:
    if amount := graph_literal(graph, object, WIKIBASE.quantityAmount):
        assert amount.datatype == XSD.decimal
    if upper_bound := graph_literal(graph, object, WIKIBASE.quantityUpperBound):
        assert upper_bound.datatype == XSD.decimal
    if lower_bound := graph_literal(graph, object, WIKIBASE.quantityLowerBound):
        assert lower_bound.datatype == XSD.decimal
    if unit := graph_value(graph, object, WIKIBASE.quantityUnit):
        assert isinstance(unit, URIRef)

    data: wikidata_typing.QuantityValue = {
        "amount": "",
        "unit": "1",
    }
    if amount:
        data["amount"] = f"+{amount}"
    if upper_bound:
        data["upperBound"] = f"+{upper_bound}"
    if lower_bound:
        data["lowerBound"] = f"+{lower_bound}"
    if unit:
        data["unit"] = str(unit)
    assert data["amount"] != "", "missing amount value"
    return {"type": "quantity", "value": data}


def _resolve_object_bnode(
    graph: Graph, object: BNode, rdf_type: URIRef | None = None
) -> wikidata_typing.QuantityDataValue | wikidata_typing.TimeDataValue:
    bnode_type = rdf_type or graph_value(graph, object, RDF.type)
    if bnode_type == WIKIBASE.TimeValue:
        return _resolve_object_bnode_time_value(graph, object)
    elif bnode_type == WIKIBASE.QuantityValue:
        return _resolve_object_bnode_quantity_value(graph, object)
    else:
        raise NotImplementedError(f"Unknown bnode: {bnode_type}")


def _resolve_object_literal(
    object: Literal,
) -> (
    wikidata_typing.GlobecoordinateDataValue
    | wikidata_typing.MonolingualTextDataValue
    | wikidata_typing.QuantityDataValue
    | wikidata_typing.StringDataValue
    | wikidata_typing.TimeDataValue
):
    if object.language and object.datatype is None:
        return {
            "type": "monolingualtext",
            "value": {
                "language": object.language,
                "text": object.toPython(),
            },
        }

    elif object.datatype == XSD.decimal:
        return {
            "type": "quantity",
            "value": {
                "amount": f"+{object.toPython()}",
                "unit": "1",
            },
        }
    elif object.language is None and object.datatype is None:
        return {
            "type": "string",
            "value": object.toPython(),
        }
    elif object.datatype == XSD.dateTime or object.datatype == XSD.date:
        return {
            "type": "time",
            "value": {
                "time": object.toPython().strftime("+%Y-%m-%dT%H:%M:%SZ"),
                "precision": 11,
                "after": 0,
                "before": 0,
                "timezone": 0,
                "calendarmodel": "http://www.wikidata.org/entity/Q1985727",
            },
        }
    elif object.datatype == GEO.wktLiteral:
        match = re.match(r"Point\(([-0-9.]+) ([-0-9.]+)\)", object.toPython())
        assert match, f"invalid wktLiteral: {object.toPython()}"
        return {
            "type": "globecoordinate",
            "value": {
                "latitude": float(match.group(2)),
                "longitude": float(match.group(1)),
                "altitude": None,
                "precision": 0.0001,
                "globe": "http://www.wikidata.org/entity/Q2",
            },
        }
    else:
        raise NotImplementedError(f"not implemented datatype: {object.datatype}")


def _resolve_object(graph: Graph, object: GraphObject) -> wikidata_typing.DataValue:
    if isinstance(object, URIRef):
        return _resolve_object_uriref(object)
    elif isinstance(object, BNode):
        return _resolve_object_bnode(graph, object)
    elif isinstance(object, Literal):
        return _resolve_object_literal(object)


def _resolve_snak(
    graph: Graph,
    property_datatypes: PropertyDatatypes,
    pid: str,
    object: GraphObject,
) -> wikidata_typing.Snak:
    assert pid.startswith("P"), pid
    datatype = property_datatypes[pid]
    value = _resolve_object(graph, object)
    assert value["type"] == wikidata_typing.ALLOWED_DATA_TYPE_VALUE_TYPES[datatype]
    snak: wikidata_typing.SnakValue = {
        "snaktype": "value",
        "property": pid,
        "datatype": datatype,
        "datavalue": value,
    }
    return snak


def _resolve_reference_snaks_order(graph: Graph, subject: GraphSubject) -> list[str]:
    snaks_order: list[str] = []

    for predicate in graph_predicates(graph, subject):
        predicate_prefix, predicate_local_name = _compute_qname(predicate)
        if predicate_prefix.startswith("pr") and predicate_local_name.startswith("P"):
            if predicate_local_name not in snaks_order:
                snaks_order.append(predicate_local_name)

    return snaks_order


def _resolve_object_bnode_reference(
    graph: Graph, property_datatypes: PropertyDatatypes, object: BNode
) -> wikidata_typing.Reference:
    snaks_order = _resolve_reference_snaks_order(graph, object)
    snaks: dict[str, list[wikidata_typing.Snak]] = {}

    for pid in snaks_order:
        if pid not in snaks:
            snaks[pid] = []

        for pr_object in graph_objects(graph, object, PR[pid]):
            snak = _resolve_snak(graph, property_datatypes, pid, pr_object)
            snaks[pid].append(snak)

        for prv_object in graph_objects(graph, object, PRV[pid]):
            snak = _resolve_snak(graph, property_datatypes, pid, prv_object)
            snaks[pid].append(snak)

    assert len(snaks) > 0
    assert len(snaks_order) > 0

    reference: wikidata_typing.Reference = {
        "snaks": snaks,
        "snaks-order": snaks_order,
    }
    return reference


def _resolve_statement_references(
    graph: Graph, property_datatypes: PropertyDatatypes, subject: GraphSubject
) -> list[wikidata_typing.Reference]:
    references: list[wikidata_typing.Reference] = []
    for prov in graph_objects(graph, subject, PROV.wasDerivedFrom):
        assert isinstance(prov, BNode)
        reference = _resolve_object_bnode_reference(graph, property_datatypes, prov)
        references.append(reference)
    return references


def _resolve_statement_exclusive_references(
    graph: Graph, property_datatypes: PropertyDatatypes, subject: GraphSubject
) -> list[wikidata_typing.Reference]:
    for prov in graph_objects(graph, subject, PROV.wasOnlyDerivedFrom):
        assert isinstance(prov, BNode)
        reference = _resolve_object_bnode_reference(graph, property_datatypes, prov)
        return [reference]
    return []


def _resolve_statement_snak(
    graph: Graph,
    property_datatypes: PropertyDatatypes,
    subject: GraphSubject,
    pid: str,
) -> wikidata_typing.Snak | None:
    if psv_object := graph_value(graph, subject, PSV[pid]):
        return _resolve_snak(graph, property_datatypes, pid, psv_object)
    elif ps_object := graph_value(graph, subject, PS[pid]):
        return _resolve_snak(graph, property_datatypes, pid, ps_object)
    return None


_RANKS: dict[str, wikidata_typing.Rank] = {
    WIKIBASE.NormalRank: "normal",
    WIKIBASE.DeprecatedRank: "deprecated",
    WIKIBASE.PreferredRank: "preferred",
}


def _resolve_statement_rank(
    graph: Graph, subject: GraphSubject
) -> wikidata_typing.Rank | None:
    if rank_uri := graph_value(graph, subject, WIKIBASE.rank):
        assert isinstance(rank_uri, URIRef)
        return _RANKS[rank_uri]
    return None


def _resolve_statement_qualifiers_order(
    graph: Graph, subject: GraphSubject
) -> list[str]:
    order: list[str] = []
    for predicate in graph_predicates(graph, subject):
        predicate_prefix, predicate_local_name = _compute_qname(predicate)
        if predicate_prefix.startswith("pq"):
            order.append(predicate_local_name)
    return order


def _resolve_statement_qualifiers(
    graph: Graph,
    property_datatypes: PropertyDatatypes,
    subject: GraphSubject,
    pid: str,
) -> list[wikidata_typing.Snak]:
    assert pid.startswith("P"), pid
    qualifiers: list[wikidata_typing.Snak] = []

    for pqv_object in graph_objects(graph, subject, PQ[pid]):
        snak = _resolve_snak(graph, property_datatypes, pid, pqv_object)
        qualifiers.append(snak)

    for pqv_object in graph_objects(graph, subject, PQV[pid]):
        snak = _resolve_snak(graph, property_datatypes, pid, pqv_object)
        qualifiers.append(snak)

    if pqve_object := graph_value(graph, subject, PQE[pid]):
        snak = _resolve_snak(graph, property_datatypes, pid, pqve_object)
        qualifiers = [snak]

    if pqve_object := graph_value(graph, subject, PQVE[pid]):
        snak = _resolve_snak(graph, property_datatypes, pid, pqve_object)
        qualifiers = [snak]

    return qualifiers


def _qid(qid: str) -> str:
    assert qid.startswith("Q"), qid
    return qid


def _pid(pid: str) -> str:
    assert pid.startswith("P"), pid
    return pid


def _new_statement_id(qid: str) -> str:
    assert qid.startswith("Q"), qid
    return f"{qid}${uuid.uuid4()}"


def _item_property_claims(
    item: wikidata_typing.Item, pid: str
) -> list[wikidata_typing.Statement]:
    assert pid.startswith("P"), pid
    if "claims" not in item:
        item["claims"] = {}
    if pid not in item["claims"]:
        item["claims"][pid] = []
    return item["claims"][pid]


def _statement_property_qualifiers(
    statement: wikidata_typing.Statement, pid: str
) -> list[wikidata_typing.Snak]:
    assert pid.startswith("P"), pid
    if "qualifiers" not in statement:
        statement["qualifiers"] = {}
    if "qualifiers-order" not in statement:
        statement["qualifiers-order"] = []
    if pid not in statement["qualifiers"]:
        statement["qualifiers"][pid] = []
    if pid not in statement["qualifiers-order"]:
        statement["qualifiers-order"].append(pid)
    return statement["qualifiers"][pid]


def _delete_statement_property_qualifiers(
    statement: wikidata_typing.Statement, pid: str
) -> None:
    assert pid.startswith("P"), pid
    if "qualifiers" in statement and pid in statement["qualifiers"]:
        del statement["qualifiers"][pid]
    if "qualifiers-order" in statement:
        statement["qualifiers-order"].remove(pid)


def _statement_references(
    statement: wikidata_typing.Statement,
) -> list[wikidata_typing.Reference]:
    if "references" not in statement:
        statement["references"] = []
    return statement["references"]


def _item_statements(item: wikidata_typing.Item) -> Iterator[wikidata_typing.Statement]:
    for statements in item.get("claims", {}).values():
        yield from statements


def _datavalue_equals(
    a: wikidata_typing.DataValue, b: wikidata_typing.DataValue
) -> bool:
    if a["type"] == "wikibase-entityid" and b["type"] == "wikibase-entityid":
        if a["value"]["entity-type"] != b["value"]["entity-type"]:
            return False
        elif "numeric-id" in a["value"] and "numeric-id" in b["value"]:
            return a["value"]["numeric-id"] == b["value"]["numeric-id"]
        elif "id" in a["value"] and "id" in b["value"]:
            return a["value"]["id"] == b["value"]["id"]
        else:
            return False
    elif a["type"] == "quantity" and b["type"] == "quantity":
        a_unitless = (
            a["value"].get("unit") == "1"
            or a["value"].get("unit") == "https://www.wikidata.org/wiki/Q199"
        )
        b_unitless = (
            b["value"].get("unit") == "1"
            or b["value"].get("unit") == "https://www.wikidata.org/wiki/Q199"
        )
        if "upperBound" in a["value"] and "upperBound" not in b["value"]:
            return a["value"]["amount"] == b["value"]["amount"]
        elif a_unitless and b_unitless:
            return a["value"]["amount"] == b["value"]["amount"]
        else:
            return a == b
    else:
        return a == b


def _snak_equals(a: wikidata_typing.Snak, b: wikidata_typing.Snak) -> bool:
    if a["snaktype"] != b["snaktype"]:
        return False
    elif a["property"] != b["property"]:
        return False
    elif a["snaktype"] == "value" and b["snaktype"] == "value":
        return _datavalue_equals(a["datavalue"], b["datavalue"])
    else:
        return True


def _any_snak_equals(
    snaks: Iterable[wikidata_typing.Snak], snak: wikidata_typing.Snak
) -> bool:
    return any(_snak_equals(s, snak) for s in snaks)


def _only_snak_equals(
    snaks: Iterable[wikidata_typing.Snak], snak: wikidata_typing.Snak
) -> bool:
    snaks_lst = list(snaks)
    return len(snaks_lst) == 1 and _snak_equals(snaks_lst[0], snak)


def _statements_contains_snak(
    statements: Iterable[wikidata_typing.Statement], snak: wikidata_typing.Snak
) -> bool:
    return any(_snak_equals(statement["mainsnak"], snak) for statement in statements)


def _statements_contains_direct_snak(
    statements: Iterable[wikidata_typing.Statement], snak: wikidata_typing.Snak
) -> bool:
    return any(
        _snak_equals(statement["mainsnak"], snak)
        for statement in statements
        if statement["rank"] != "deprecated"
    )


def _snaks_equals(
    a: Iterable[wikidata_typing.Snak], b: Iterable[wikidata_typing.Snak]
) -> bool:
    a_lst = list(a)
    b_lst = list(b)
    return len(a_lst) == len(b_lst) and all(
        _snak_equals(a_lst[i], b_lst[i]) for i in range(len(a_lst))
    )


def _reference_equals(
    a: wikidata_typing.Reference, b: wikidata_typing.Reference
) -> bool:
    if a["snaks-order"] != b["snaks-order"]:
        return False
    for pid in a["snaks-order"]:
        if not _snaks_equals(a["snaks"][pid], b["snaks"][pid]):
            return False
    return True


def _references_contains(
    a: Iterable[wikidata_typing.Reference], b: wikidata_typing.Reference
) -> bool:
    return any(_reference_equals(r, b) for r in a)


def _find_claim_guid(
    items: dict[str, wikidata_typing.Item], guid: str
) -> tuple[str, wikidata_typing.Statement]:
    qid, hash = guid.split("-", 1)
    guid = f"{qid}${hash}"

    item = items[qid.upper()]

    for statements in item.get("claims", {}).values():
        for statement in statements:
            if guid == statement["id"]:
                return (qid.upper(), statement)

    assert False, f"Can't resolve statement GUID: {guid}"


def _new_statement(
    graph: Graph,
    property_datatypes: PropertyDatatypes,
    qid: str,
    pid: str,
    subject: BNode,
) -> tuple[wikidata_typing.Statement, str]:
    assert qid.startswith("Q"), qid
    assert pid.startswith("P"), pid

    edit_summary: str = ""

    snak = _resolve_statement_snak(graph, property_datatypes, subject, pid)
    assert snak, f"Can't resolve snak for {qid}/{pid}"

    rank = _resolve_statement_rank(graph, subject) or "normal"

    qualifiers_order = _resolve_statement_qualifiers_order(graph, subject)
    qualifiers: dict[str, list[wikidata_typing.Snak]] = {}
    for qualifier_pid in qualifiers_order:
        qualifiers[qualifier_pid] = _resolve_statement_qualifiers(
            graph, property_datatypes, subject, qualifier_pid
        )

    references = _resolve_statement_exclusive_references(
        graph, property_datatypes, subject
    ) or _resolve_statement_references(graph, property_datatypes, subject)

    if edit_summary_literal := graph_literal(graph, subject, WIKIDATABOTS.editSummary):
        edit_summary = edit_summary_literal.toPython()

    statement: wikidata_typing.Statement = {
        "id": _new_statement_id(qid),
        "type": "statement",
        "rank": rank,
        "mainsnak": snak,
    }

    if len(qualifiers_order) > 0:
        statement["qualifiers"] = qualifiers
        statement["qualifiers-order"] = qualifiers_order

    if len(references) > 0:
        statement["references"] = references

    return statement, edit_summary


def _detect_changed_claims(
    original_items: dict[str, wikidata_typing.Item],
    updated_items: dict[str, wikidata_typing.Item],
) -> Iterator[tuple[str, wikidata_typing.Statement]]:
    original_claims_by_guid: dict[str, wikidata_typing.Statement] = {}
    for item in original_items.values():
        for statement in _item_statements(item):
            guid = statement["id"]
            assert guid
            original_claims_by_guid[guid] = statement

    for item in updated_items.values():
        for statement in _item_statements(item):
            guid = statement.get("id", "")
            if not guid:
                yield item["id"], statement
            elif guid not in original_claims_by_guid:
                yield item["id"], statement
            elif statement != original_claims_by_guid[guid]:
                yield item["id"], statement


def _prefetch_items(
    graph: Graph, user_agent: str
) -> tuple[dict[str, wikidata_typing.Item], set[str]]:
    qids: set[str] = set()

    for uri in graph_urirefs(graph):
        _, local_name = _compute_qname(uri)
        if re.match(r"^Q\d+$", local_name):
            qids.add(local_name)
        elif m := re.match(r"^(Q\d+|q\d+)-", local_name):
            qids.add(m.group(1))

    if len(qids) == 0:
        logger.debug("No items prefetched")
        return {}, set()

    items: dict[str, wikidata_typing.Item] = {}
    missing_items: set[str] = set()

    for qid_batch in itertools.batched(qids, n=50):
        entities = mediawiki_api.wbgetentities(
            ids=list(qid_batch),
            user_agent=user_agent,
        )
        for qid, entity in entities.items():
            if "missing" in entity:
                logger.warning("%s missing", qid)
                missing_items.add(qid)
            else:
                assert entity["type"] == "item"
                items[qid] = entity

    logger.debug("Prefetched %d items", len(items))
    return items, missing_items


def _prefetch_property_datatypes(graph: Graph, user_agent: str) -> PropertyDatatypes:
    pids: set[str] = set()

    for uri in graph_urirefs(graph):
        _, local_name = _compute_qname(uri)
        if re.match(r"^P\d+$", local_name):
            pids.add(local_name)

    if len(pids) == 0:
        logger.debug("No properties prefetched")
        return {}

    entities = mediawiki_api.wbgetentities(
        ids=sorted(pids),
        user_agent=user_agent,
    )

    datatypes: PropertyDatatypes = {}
    for pid, entity in entities.items():
        assert entity["type"] == "property"
        datatypes[pid] = entity["datatype"]
    logger.debug("Prefetched %d property datatypes", len(datatypes))
    return datatypes


def _update_statement(
    graph: Graph,
    property_datatypes: PropertyDatatypes,
    qid: str,
    statement_subject: GraphSubject,
    statement: wikidata_typing.Statement,
    edit_summaries: set[str],
) -> None:
    assert qid.startswith("Q"), qid

    if rank := _resolve_statement_rank(graph, statement_subject):
        statement["rank"] = rank

    if snak := _resolve_statement_snak(
        graph,
        property_datatypes,
        statement_subject,
        statement["mainsnak"]["property"],
    ):
        if not _snak_equals(statement["mainsnak"], snak):
            statement["mainsnak"] = snak

    if new_references := _resolve_statement_references(
        graph, property_datatypes, statement_subject
    ):
        assert len(new_references) > 0
        existing_references = _statement_references(statement)
        for new_reference in new_references:
            if not _references_contains(existing_references, new_reference):
                existing_references.append(new_reference)

    if new_references := _resolve_statement_exclusive_references(
        graph, property_datatypes, statement_subject
    ):
        assert len(new_references) == 1
        existing_references = _statement_references(statement)
        if len(existing_references) != 1 or not _reference_equals(
            existing_references[0], new_references[0]
        ):
            statement["references"] = new_references

    for predicate, object in graph_predicate_objects(graph, statement_subject):
        predicate_prefix, predicate_local_name = _compute_qname(predicate)

        if predicate_prefix == "pq" or predicate_prefix == "pqv":
            pid = _pid(predicate_local_name)
            snak = _resolve_snak(graph, property_datatypes, pid, object)
            qualifiers = _statement_property_qualifiers(statement, pid)
            if not _any_snak_equals(qualifiers, snak):
                qualifiers.append(snak)

        elif predicate_prefix == "pqe" or predicate_prefix == "pqve":
            pid = _pid(predicate_local_name)
            if graph_empty_node(graph, object):
                _delete_statement_property_qualifiers(statement, pid)
            else:
                snak = _resolve_snak(graph, property_datatypes, pid, object)
                qualifiers = _statement_property_qualifiers(statement, pid)
                if not _only_snak_equals(qualifiers, snak):
                    qualifiers.clear()
                    qualifiers.append(snak)

    if edit_summary_literal := graph_literal(
        graph, statement_subject, WIKIDATABOTS.editSummary
    ):
        edit_summaries.add(edit_summary_literal.toPython())


def _update_item(
    graph: Graph,
    property_datatypes: PropertyDatatypes,
    item: wikidata_typing.Item,
    item_subject: GraphSubject,
    edit_summaries: set[str],
) -> None:
    qid = item["id"]

    if edit_summary_literal := graph_literal(
        graph, item_subject, WIKIDATABOTS.editSummary
    ):
        edit_summaries.add(edit_summary_literal.toPython())

    for predicate, object in graph_predicate_objects(graph, item_subject):
        predicate_prefix, predicate_local_name = _compute_qname(predicate)

        if predicate_prefix == "wdt":
            assert isinstance(object, URIRef) or isinstance(object, Literal)
            pid = _pid(predicate_local_name)
            snak = _resolve_snak(graph, property_datatypes, pid, object)
            claims = _item_property_claims(item, pid)
            if not _statements_contains_snak(claims, snak):
                statement: wikidata_typing.Statement = {
                    "id": _new_statement_id(qid),
                    "type": "statement",
                    "rank": "normal",
                    "mainsnak": snak,
                }
                claims.append(statement)
            elif not _statements_contains_direct_snak(claims, snak):
                # TODO: Maybe update rank
                logger.warning(
                    "snak for %s/%s %s exists, but is deprecated",
                    qid,
                    pid,
                    object.toPython(),
                )

        elif predicate_prefix == "p":
            assert isinstance(object, BNode)
            pid = _pid(predicate_local_name)
            statement, edit_summary = _new_statement(
                graph=graph,
                property_datatypes=property_datatypes,
                qid=qid,
                pid=pid,
                subject=object,
            )
            _item_property_claims(item, pid).append(statement)
            if edit_summary:
                edit_summaries.add(edit_summary)


def process_graph(
    input: TextIO,
    blocked_qids: set[str] = set(),
    user_agent: str = mediawiki_api.DEFAULT_USER_AGENT,
) -> Iterator[tuple[str, int, list[wikidata_typing.Statement], str | None]]:
    graph = Graph()
    data = PREFIXES + input.read()
    graph.parse(data=data)

    property_datatypes = _prefetch_property_datatypes(graph, user_agent)
    items, missing_items = _prefetch_items(graph, user_agent)
    original_items = deepcopy(items)

    edit_summaries: dict[str, set[str]] = defaultdict(lambda: set())

    for subject in graph_subjects(graph):
        if isinstance(subject, BNode):
            continue

        assert isinstance(subject, URIRef)
        prefix, local_name = _compute_qname(subject)

        if prefix == "wd":
            assert isinstance(subject, URIRef)
            qid = _qid(local_name)
            if qid in missing_items:
                logger.warning("%s deleted, skipping %s item", qid, subject)
                continue
            _update_item(
                graph=graph,
                property_datatypes=property_datatypes,
                item=items[qid],
                item_subject=subject,
                edit_summaries=edit_summaries[qid],
            )

        elif prefix == "wds":
            assert isinstance(subject, URIRef)
            qid_from_guid = local_name.split("-", 1)[0].upper()
            if qid_from_guid in missing_items:
                logger.warning(
                    "%s deleted, skipping %s statement",
                    qid_from_guid,
                    subject,
                )
                continue
            qid, claim = _find_claim_guid(items, local_name)
            _update_statement(
                graph=graph,
                property_datatypes=property_datatypes,
                qid=qid,
                statement_subject=subject,
                statement=claim,
                edit_summaries=edit_summaries[qid],
            )

    changed_statements: dict[str, list[wikidata_typing.Statement]] = {}
    for qid, statement in _detect_changed_claims(
        original_items=original_items,
        updated_items=items,
    ):
        if qid not in changed_statements:
            changed_statements[qid] = []
        changed_statements[qid].append(statement)

    for qid, statements in changed_statements.items():
        if qid in blocked_qids:
            logger.warning("Skipping edit, %s is blocked", qid)
            continue
        summary: str | None = None
        if summaries := edit_summaries[qid]:
            summary = ", ".join(sorted(summaries))
        assert summary != ""
        assert len(statements) > 0
        lastrevid = items[qid]["lastrevid"]
        yield qid, lastrevid, statements, summary
