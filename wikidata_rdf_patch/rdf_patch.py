import datetime
import itertools
import json
import logging
import re
import urllib.parse
import urllib.request
import uuid
from collections.abc import Iterable, Iterator
from copy import deepcopy
from dataclasses import dataclass
from typing import TextIO

from rdflib import XSD, Graph
from rdflib.namespace import Namespace, NamespaceManager
from rdflib.term import BNode, Literal, URIRef

from . import mediawiki_api, wikidata_typing

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

AnyRDFSubject = URIRef | BNode
AnyRDFPredicate = URIRef
AnyRDFObject = URIRef | BNode | Literal


def _graph_urirefs(graph: Graph) -> Iterator[URIRef]:
    for subject in graph.subjects(unique=True):
        if isinstance(subject, URIRef):
            yield subject

    for predicate in graph.predicates(unique=True):
        if isinstance(predicate, URIRef):
            yield predicate

    for object in graph.objects(unique=True):
        if isinstance(object, URIRef):
            yield object


def _subjects(graph: Graph) -> Iterator[AnyRDFSubject]:
    for subject in graph.subjects(unique=True):
        assert isinstance(subject, URIRef) or isinstance(subject, BNode)
        yield subject


def _predicate_objects(
    graph: Graph, subject: AnyRDFSubject
) -> Iterator[tuple[AnyRDFPredicate, AnyRDFObject]]:
    for predicate, object in graph.predicate_objects(subject, unique=True):
        assert isinstance(predicate, URIRef)
        assert (
            isinstance(object, URIRef)
            or isinstance(object, BNode)
            or isinstance(object, Literal)
        )
        yield predicate, object


def _predicate_ns_objects(
    graph: Graph, subject: AnyRDFSubject, predicate_ns: Namespace
) -> Iterator[tuple[str, AnyRDFObject]]:
    for predicate, object in _predicate_objects(graph, subject):
        _, ns, name = NS_MANAGER.compute_qname(predicate)
        if predicate_ns == ns:
            yield name, object


def _graph_empty_node(graph: Graph, object: AnyRDFObject) -> bool:
    return isinstance(object, BNode) and len(list(graph.predicate_objects(object))) == 0


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
    if value := graph.value(object, WIKIBASE.timeValue):
        assert isinstance(value, Literal)
        assert value.datatype is None or value.datatype == XSD.dateTime
    if precision := graph.value(object, WIKIBASE.timePrecision):
        assert isinstance(precision, Literal)
        assert precision.datatype == XSD.integer
        assert 0 <= precision.toPython() <= 14
    if timezone := graph.value(object, WIKIBASE.timeTimezone):
        assert isinstance(timezone, Literal)
        assert timezone.datatype == XSD.integer
    if calendar_model := graph.value(object, WIKIBASE.timeCalendarModel):
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
        value_dt = value.toPython()  # type: ignore
        if not isinstance(value_dt, datetime.datetime):
            value_dt = datetime.datetime.fromisoformat(value_dt)
        data["time"] = value_dt.strftime("+%Y-%m-%dT%H:%M:%SZ")
    if precision:
        data["precision"] = precision.toPython()  # type: ignore
    if timezone:
        data["timezone"] = timezone.toPython()  # type: ignore
    if calendar_model:
        data["calendarmodel"] = str(calendar_model)
    assert data["time"] != "", "missing time value"
    return {"type": "time", "value": data}


def _resolve_object_bnode_quantity_value(
    graph: Graph, object: BNode
) -> wikidata_typing.QuantityDataValue:
    if amount := graph.value(object, WIKIBASE.quantityAmount):
        assert isinstance(amount, Literal)
        assert amount.datatype == XSD.decimal
    if upper_bound := graph.value(object, WIKIBASE.quantityUpperBound):
        assert isinstance(upper_bound, Literal)
        assert upper_bound.datatype == XSD.decimal
    if lower_bound := graph.value(object, WIKIBASE.quantityLowerBound):
        assert isinstance(lower_bound, Literal)
        assert lower_bound.datatype == XSD.decimal
    if unit := graph.value(object, WIKIBASE.quantityUnit):
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
    if not rdf_type:
        rdf_type = graph.value(object, RDF.type)  # type: ignore
    assert rdf_type is None or isinstance(rdf_type, URIRef)

    if rdf_type == WIKIBASE.TimeValue:
        return _resolve_object_bnode_time_value(graph, object)
    elif rdf_type == WIKIBASE.QuantityValue:
        return _resolve_object_bnode_quantity_value(graph, object)
    else:
        raise NotImplementedError(f"Unknown bnode: {rdf_type}")


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


def _resolve_object(graph: Graph, object: AnyRDFObject) -> wikidata_typing.DataValue:
    if isinstance(object, URIRef):
        return _resolve_object_uriref(object)
    elif isinstance(object, BNode):
        return _resolve_object_bnode(graph, object)
    elif isinstance(object, Literal):
        return _resolve_object_literal(object)


def _qid(qid: str) -> str:
    assert qid.startswith("Q"), qid
    return qid


def _pid(pid: str) -> str:
    assert pid.startswith("P"), pid
    return pid


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


def _new_statement(
    qid: str,
    snak: wikidata_typing.Snak,
    rank: wikidata_typing.Rank = "normal",
) -> wikidata_typing.Statement:
    assert qid.startswith("Q"), qid
    return {
        "id": f"{qid}${uuid.uuid4()}",
        "type": "statement",
        "rank": rank,
        "mainsnak": snak,
    }


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


@dataclass
class ProcessState:
    graph: Graph
    edit_summaries: dict[str, str]
    property_datatypes: dict[str, wikidata_typing.DataType]
    original_items: dict[str, wikidata_typing.Item]
    items: dict[str, wikidata_typing.Item]


def _resolve_snak(
    state: ProcessState,
    pid: str,
    object: AnyRDFObject,
) -> wikidata_typing.Snak:
    assert pid.startswith("P"), pid
    datatype = state.property_datatypes[pid]
    value = _resolve_object(state.graph, object)
    assert value["type"] == wikidata_typing.ALLOWED_DATA_TYPE_VALUE_TYPES[datatype]
    # TODO: Support SnakSomeValue and SnakNoValue
    snak: wikidata_typing.SnakValue = {
        "snaktype": "value",
        "property": pid,
        "datatype": datatype,
        "datavalue": value,
    }
    return snak


def _resolve_object_bnode_reference(
    state: ProcessState, object: BNode
) -> wikidata_typing.Reference:
    reference: wikidata_typing.Reference = {
        "snaks": {},
        "snaks-order": [],
    }

    def add_reference(pid: str, object: AnyRDFObject) -> None:
        snak = _resolve_snak(state, pid, object)

        if pid not in reference["snaks"] and pid not in reference["snaks-order"]:
            reference["snaks"][pid] = []
            reference["snaks-order"].append(pid)

        assert pid == snak["property"]
        assert pid in reference["snaks"]
        assert pid in reference["snaks-order"]

        reference["snaks"][pid].append(snak)

    for pr_name, pr_object in _predicate_ns_objects(state.graph, object, PR):
        add_reference(pr_name, pr_object)

    for prv_name, prv_object in _predicate_ns_objects(state.graph, object, PRV):
        add_reference(prv_name, prv_object)

    assert len(reference["snaks"]) > 0
    assert len(reference["snaks-order"]) > 0

    return reference


def _prefetch_property_datatypes(
    graph: Graph, user_agent: str
) -> dict[str, wikidata_typing.DataType]:
    pids: set[str] = set()

    for uri in _graph_urirefs(graph):
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

    datatypes: dict[str, wikidata_typing.DataType] = {}
    for pid, entity in entities.items():
        assert entity["type"] == "property"
        datatypes[pid] = entity["datatype"]
    logger.debug("Prefetched %d property datatypes", len(datatypes))
    return datatypes


def _prefetch_items(graph: Graph, user_agent: str) -> dict[str, wikidata_typing.Item]:
    qids: set[str] = set()

    for uri in _graph_urirefs(graph):
        _, local_name = _compute_qname(uri)
        if re.match(r"^Q\d+$", local_name):
            qids.add(local_name)
        elif m := re.match(r"^(Q\d+|q\d+)-", local_name):
            qids.add(m.group(1))

    if len(qids) == 0:
        logger.debug("No items prefetched")
        return {}

    items: dict[str, wikidata_typing.Item] = {}

    for qid_batch in itertools.batched(qids, n=50):
        entities = mediawiki_api.wbgetentities(
            ids=list(qid_batch),
            user_agent=user_agent,
        )
        for qid, entity in entities.items():
            assert entity["type"] == "item"
            items[qid] = entity

    logger.debug("Prefetched %d items", len(items))
    return items


def _find_claim_guid(
    state: ProcessState, guid: str
) -> tuple[str, wikidata_typing.Statement]:
    qid, hash = guid.split("-", 1)
    guid = f"{qid}${hash}"

    item = state.items[qid.upper()]

    for statements in item.get("claims", {}).values():
        for statement in statements:
            if guid == statement["id"]:
                return (qid.upper(), statement)

    assert False, f"Can't resolve statement GUID: {guid}"


_RANKS: dict[str, wikidata_typing.Rank] = {
    str(WIKIBASE.NormalRank): "normal",
    str(WIKIBASE.DeprecatedRank): "deprecated",
    str(WIKIBASE.PreferredRank): "preferred",
}


def _item_statements(item: wikidata_typing.Item) -> Iterator[wikidata_typing.Statement]:
    for statements in item.get("claims", {}).values():
        yield from statements


def _detect_changed_claims(
    state: ProcessState,
) -> Iterator[tuple[wikidata_typing.Item, wikidata_typing.Statement]]:
    original_claims_by_guid: dict[str, wikidata_typing.Statement] = {}
    for item in state.original_items.values():
        for statement in _item_statements(item):
            guid = statement["id"]
            assert guid
            original_claims_by_guid[guid] = statement

    for item in state.items.values():
        for statement in _item_statements(item):
            guid = statement.get("id", "")
            if not guid:
                yield item, statement
            elif guid not in original_claims_by_guid:
                yield item, statement
            elif statement != original_claims_by_guid[guid]:
                yield item, statement


def _update_statement(
    state: ProcessState,
    qid: str,
    statement_subject: AnyRDFSubject,
    statement: wikidata_typing.Statement,
) -> None:
    assert qid.startswith("Q"), qid

    for predicate, object in _predicate_objects(state.graph, statement_subject):
        predicate_prefix, predicate_local_name = _compute_qname(predicate)

        if predicate_prefix == "pq" or predicate_prefix == "pqv":
            pid = _pid(predicate_local_name)
            snak = _resolve_snak(state, pid, object)
            qualifiers = _statement_property_qualifiers(statement, pid)
            if not _any_snak_equals(qualifiers, snak):
                qualifiers.append(snak)

        elif predicate_prefix == "pqe" or predicate_prefix == "pqve":
            pid = _pid(predicate_local_name)
            if _graph_empty_node(state.graph, object):
                _delete_statement_property_qualifiers(statement, pid)
            else:
                snak = _resolve_snak(state, pid, object)
                qualifiers = _statement_property_qualifiers(statement, pid)
                if not _only_snak_equals(qualifiers, snak):
                    qualifiers.clear()
                    qualifiers.append(snak)

        elif predicate_prefix == "ps" or predicate_prefix == "psv":
            pid = _pid(predicate_local_name)
            snak = _resolve_snak(state, pid, object)
            if not _snak_equals(statement["mainsnak"], snak):
                statement["mainsnak"] = snak

        elif predicate == WIKIBASE.rank:
            assert isinstance(object, URIRef)
            statement["rank"] = _RANKS[str(object)]

        elif predicate == PROV.wasDerivedFrom:
            assert isinstance(object, BNode)
            references = _statement_references(statement)
            reference = _resolve_object_bnode_reference(state, object)
            if not _references_contains(references, reference):
                references.append(reference)

        elif predicate == PROV.wasOnlyDerivedFrom:
            assert isinstance(object, BNode)
            references = _statement_references(statement)
            reference = _resolve_object_bnode_reference(state, object)
            if len(references) != 1 or not _reference_equals(references[0], reference):
                references.clear()
                references.append(reference)

        elif predicate == WIKIDATABOTS.editSummary:
            state.edit_summaries[qid] = object.toPython()

        else:
            logger.error("NotImplemented: Unknown wds triple: %s %s", predicate, object)


def _update_item(
    state: ProcessState,
    qid: str,
    item_subject: AnyRDFSubject,
) -> None:
    assert qid.startswith("Q"), qid
    item = state.items[qid]

    for predicate, object in _predicate_objects(state.graph, item_subject):
        predicate_prefix, predicate_local_name = _compute_qname(predicate)

        if predicate_prefix == "wdt":
            pid = _pid(predicate_local_name)
            snak = _resolve_snak(state, pid, object)
            claims = _item_property_claims(item, pid)
            if not _statements_contains_snak(claims, snak):
                claims.append(_new_statement(qid, snak))

        elif predicate_prefix == "p" and isinstance(object, BNode):
            pid = _pid(predicate_local_name)
            novalue_snak: wikidata_typing.SnakNoValue = {
                "snaktype": "novalue",
                "property": predicate_local_name,
            }
            statement = _new_statement(qid, novalue_snak)
            # TODO: Extract function to build new statement and append it here
            _item_property_claims(item, pid).append(statement)
            _update_statement(
                state=state,
                qid=qid,
                statement_subject=object,
                statement=statement,
            )
            assert statement["mainsnak"] != novalue_snak

        elif predicate == WIKIDATABOTS.editSummary:
            # TODO: Append to edit summary set
            state.edit_summaries[qid] = object.toPython()

        else:
            logger.error(
                "NotImplemented: Unknown wd triple: %s %s %s",
                item_subject,
                predicate,
                object,
            )


def process_graph(
    input: TextIO,
    blocked_qids: set[str] = set(),
    user_agent: str = mediawiki_api.DEFAULT_USER_AGENT,
) -> Iterator[tuple[wikidata_typing.Item, list[wikidata_typing.Statement], str | None]]:
    graph = Graph()
    data = PREFIXES + input.read()
    graph.parse(data=data)

    items = _prefetch_items(graph=graph, user_agent=user_agent)

    state = ProcessState(
        graph=graph,
        edit_summaries={},
        property_datatypes=_prefetch_property_datatypes(
            graph=graph, user_agent=user_agent
        ),
        original_items=deepcopy(items),
        items=items,
    )

    for subject in _subjects(graph):
        if isinstance(subject, BNode):
            continue

        assert isinstance(subject, URIRef)
        prefix, local_name = _compute_qname(subject)

        if prefix == "wd":
            assert isinstance(subject, URIRef)
            _update_item(state, _qid(local_name), subject)

        elif prefix == "wds":
            assert isinstance(subject, URIRef)
            qid, claim = _find_claim_guid(state, local_name)
            _update_statement(
                state=state,
                qid=qid,
                statement_subject=subject,
                statement=claim,
            )

        else:
            logger.error("NotImplemented: Unknown subject: %s", subject)

    changed_statements: dict[str, list[wikidata_typing.Statement]] = {}
    for item, statement in _detect_changed_claims(state):
        qid = item["id"]
        if qid not in changed_statements:
            changed_statements[qid] = []
        changed_statements[qid].append(statement)

    for qid, statements in changed_statements.items():
        if qid in blocked_qids:
            logger.warning("Skipping edit, %s is blocked", qid)
            continue
        summary: str | None = state.edit_summaries.get(qid)
        item = state.items[qid]
        yield item, statements, summary


def fetch_page_qids(title: str) -> set[str]:
    if not title:
        return set()
    assert not title.startswith("http"), "Expected title, not URL"

    query = urllib.parse.urlencode(
        {
            "action": "query",
            "format": "json",
            "titles": title,
            "prop": "extracts",
            "explaintext": "1",
        }
    )
    url = f"https://www.wikidata.org/w/api.php?{query}"

    with urllib.request.urlopen(url) as response:
        data = response.read()
        assert isinstance(data, bytes)
    data = json.loads(data)

    pages = data["query"]["pages"]
    assert len(pages) == 1, "Expected one page"
    page = next(iter(pages.values()))
    text = page["extract"]
    return set(re.findall(r"Q[0-9]+", text))
