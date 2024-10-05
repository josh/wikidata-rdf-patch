import datetime
import json
import logging
import re
import urllib.request
from collections import OrderedDict, defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from functools import cache
from typing import Any, TextIO, cast

import pywikibot  # type: ignore
from rdflib import XSD, Graph
from rdflib.namespace import Namespace, NamespaceManager
from rdflib.term import BNode, Literal, URIRef

from . import mediawiki_api, wikidata_typing

logger = logging.getLogger("rdf_patch")

SITE = pywikibot.Site("wikidata", "wikidata")


class HashableClaim:
    def __init__(self, claim: pywikibot.Claim) -> None:
        self.claim = claim

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, HashableClaim):
            return False
        return cast(bool, self.claim == other.claim)

    def __hash__(self) -> int:
        return 0


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

"""


AnyRDFSubject = URIRef | BNode
AnyRDFPredicate = URIRef
AnyRDFObject = URIRef | BNode | Literal


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


def _compute_qname(uri: URIRef) -> tuple[str, str]:
    prefix, _, name = NS_MANAGER.compute_qname(uri)
    return (prefix, name)


@cache
def get_item_page(qid: str) -> pywikibot.ItemPage:
    assert qid.startswith("Q"), qid
    return pywikibot.ItemPage(SITE, qid)


@cache
def get_property_datatype(pid: str) -> wikidata_typing.DataType:
    assert pid.startswith("P"), pid
    entities = mediawiki_api.wbgetentities(
        # TODO: Would be better to prefetch all properties upfront
        ids=[pid],
        # TODO: Get user agent from cli somehow
        user_agent=mediawiki_api.DEFAULT_USER_AGENT,
    )
    entity = entities[pid]
    assert entity["type"] == "property"
    return entity["datatype"]


def _resolve_object_uriref(object: URIRef) -> wikidata_typing.WikibaseEntityIdDataValue:
    prefix, local_name = _compute_qname(object)
    assert prefix == "wd"
    if local_name.startswith("Q"):
        return {
            "type": "wikibase-entityid",
            "value": {
                "entity-type": "item",
                "numeric-id": int(local_name[1:]),
                "id": local_name,
            },
        }
    elif local_name.startswith("P"):
        return {
            "type": "wikibase-entityid",
            "value": {
                "entity-type": "property",
                "numeric-id": int(local_name[1:]),
                "id": local_name,
            },
        }
    else:
        raise NotImplementedError(f"Unknown item: {object}")


def _pywikibot_claim_to_json(claim: pywikibot.Claim) -> wikidata_typing.Statement:
    assert claim.isQualifier is False
    assert claim.isReference is False
    if claim.target is None:
        return {
            "id": "",
            "type": "statement",
            "rank": "normal",
            "mainsnak": {
                "snaktype": "novalue",
                "property": claim.getID(),
            },
        }
    return cast(wikidata_typing.Statement, claim.toJSON())


def _pywikibot_claim_from_json(snak: wikidata_typing.Snak) -> pywikibot.Claim:
    statement = {"type": "statement", "mainsnak": snak}
    claim = pywikibot.Claim.fromJSON(site=SITE, data=statement)
    assert claim.isQualifier is False
    assert claim.isReference is False
    return claim


def _pywikibot_qualifier_to_json(qualifier: pywikibot.Claim) -> wikidata_typing.Snak:
    assert qualifier.isQualifier is True
    assert qualifier.isReference is False
    return cast(wikidata_typing.Snak, qualifier.toJSON())


def _pywikibot_qualifier_from_json(snak: wikidata_typing.Snak) -> pywikibot.Claim:
    qualifier = pywikibot.Claim.fromJSON(site=SITE, data={"mainsnak": snak})
    qualifier.isQualifier = True
    assert qualifier.isQualifier is True
    assert qualifier.isReference is False
    return qualifier


def _pywikibot_reference_to_json(reference: pywikibot.Claim) -> wikidata_typing.Snak:
    assert reference.isQualifier is False
    assert reference.isReference is True
    return cast(wikidata_typing.Snak, reference.toJSON())


def _pywikibot_reference_from_json(snak: wikidata_typing.Snak) -> pywikibot.Claim:
    reference = pywikibot.Claim.fromJSON(site=SITE, data={"mainsnak": snak})
    reference.isReference = True
    assert reference.isQualifier is False
    assert reference.isReference is True
    return reference


def _resolve_object_literal(
    object: Literal,
) -> (
    wikidata_typing.MonolingualTextDataValue
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
    elif object.language is None and object.datatype is None:
        return {
            "type": "string",
            "value": object.toPython(),
        }
    elif object.datatype == XSD.dateTime or object.datatype == XSD.date:
        return {
            "type": "time",
            "value": {
                "time": object.toPython().strftime("%Y-%m-%dT%H:%M:%SZ"),
                "precision": 11,
                "after": 0,
                "before": 0,
                "timezone": 0,
                "calendarmodel": "http://www.wikidata.org/entity/Q1985727",
            },
        }
    else:
        raise NotImplementedError(f"not implemented datatype: {object.datatype}")


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
        data["time"] = value_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
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


def _resolve_object(graph: Graph, object: AnyRDFObject) -> wikidata_typing.DataValue:
    if isinstance(object, URIRef):
        return _resolve_object_uriref(object)
    elif isinstance(object, BNode):
        return _resolve_object_bnode(graph, object)
    elif isinstance(object, Literal):
        return _resolve_object_literal(object)


def _property_snakvalue(
    pid: str, value: wikidata_typing.DataValue
) -> wikidata_typing.SnakValue:
    assert pid.startswith("P"), pid
    return {
        "snaktype": "value",
        "property": pid,
        "datatype": get_property_datatype(pid),
        "datavalue": value,
    }


def _resolve_object_bnode_reference(
    graph: Graph, object: BNode
) -> OrderedDict[str, list[pywikibot.Claim]]:
    source: OrderedDict[str, list[pywikibot.Claim]] = OrderedDict()

    def add_reference(snak: wikidata_typing.Snak) -> None:
        pid = snak["property"]
        if pid not in source:
            source[pid] = []
        claim = _pywikibot_reference_from_json(snak)
        source[pid].append(claim)

    for pr_name, pr_object in _predicate_ns_objects(graph, object, PR):
        target = _resolve_object(graph, pr_object)
        add_reference(snak=_property_snakvalue(pid=pr_name, value=target))

    for prv_name, prv_object in _predicate_ns_objects(graph, object, PRV):
        target = _resolve_object(graph, prv_object)
        add_reference(snak=_property_snakvalue(pid=prv_name, value=target))

    return source


def _graph_empty_node(graph: Graph, object: AnyRDFObject) -> bool:
    return isinstance(object, BNode) and len(list(graph.predicate_objects(object))) == 0


@cache
def resolve_claim_guid(guid: str) -> pywikibot.Claim:
    qid, hash = guid.split("-", 1)
    snak = f"{qid}${hash}"

    item = get_item_page(qid.upper())

    for property in item.claims:
        for claim in item.claims[property]:
            if snak == claim.snak:
                return claim

    assert False, f"Can't resolve statement GUID: {guid}"


def _claim_uri(claim: pywikibot.Claim) -> str:
    snak: str = claim.snak
    guid = snak.replace("$", "-")
    return f"http://www.wikidata.org/entity/statement/{guid}"


def _item_append_claim_target(
    item: pywikibot.ItemPage,
    pid: str,
    target: wikidata_typing.DataValue,
) -> tuple[bool, pywikibot.Claim]:
    assert pid.startswith("P"), pid

    if pid not in item.claims:
        item.claims[pid] = []
    claims = item.claims[pid]

    for claim in claims:
        claim_json = _pywikibot_claim_to_json(claim)
        if (
            claim_json["mainsnak"]["snaktype"] == "value"
            and claim_json["mainsnak"]["datavalue"] == target
        ):
            return (False, claim)

    snak = _property_snakvalue(pid=pid, value=target)
    new_claim = _pywikibot_claim_from_json(snak)
    item.claims[pid].append(new_claim)

    return (True, new_claim)


def _datavalue_equals(
    a: wikidata_typing.DataValue,
    b: wikidata_typing.DataValue,
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
    else:
        return a == b


def _snak_equals(
    a: wikidata_typing.Snak,
    b: wikidata_typing.Snak,
) -> bool:
    if a["snaktype"] == "value" and b["snaktype"] == "value":
        return _datavalue_equals(a["datavalue"], b["datavalue"])
    else:
        return a == b


def _claim_set_target(
    claim: pywikibot.Claim,
    target: wikidata_typing.DataValue,
) -> bool:
    claim_json = _pywikibot_claim_to_json(claim)
    snak = _property_snakvalue(pid=claim.getID(), value=target)

    if _snak_equals(claim_json["mainsnak"], snak):
        return False

    new_claim = _pywikibot_claim_from_json(snak)
    claim.setTarget(new_claim.target)

    return True


def _claim_append_qualifer(
    claim: pywikibot.Claim,
    pid: str,
    target: wikidata_typing.DataValue,
) -> bool:
    assert pid.startswith("P"), pid

    if pid not in claim.qualifiers:
        claim.qualifiers[pid] = []
    qualifiers = claim.qualifiers[pid]

    snak = _property_snakvalue(pid=pid, value=target)

    for qualifier in qualifiers:
        qualifier_json = _pywikibot_qualifier_to_json(qualifier)
        if _snak_equals(qualifier_json, snak):
            return False

    new_qualifier = _pywikibot_qualifier_from_json(snak)
    claim.qualifiers[pid].append(new_qualifier)

    return True


def _claim_set_qualifer(
    claim: pywikibot.Claim,
    pid: str,
    target: wikidata_typing.DataValue,
) -> bool:
    assert pid.startswith("P"), pid

    snak = _property_snakvalue(pid=pid, value=target)

    if pid in claim.qualifiers and len(claim.qualifiers[pid]) == 1:
        qualifier: pywikibot.Claim = claim.qualifiers[pid][0]
        qualifier_json = _pywikibot_qualifier_to_json(qualifier)
        if _snak_equals(qualifier_json, snak):
            return False

    new_qualifier = pywikibot.Claim.fromJSON(site=SITE, data={"mainsnak": snak})
    new_qualifier.isQualifier = True
    claim.qualifiers[pid] = [new_qualifier]

    return True


_RANKS: dict[str, str] = {
    str(WIKIBASE.NormalRank): "normal",
    str(WIKIBASE.DeprecatedRank): "deprecated",
    str(WIKIBASE.PreferredRank): "preferred",
}


def _claim_set_rank(claim: pywikibot.Claim, rank: URIRef) -> bool:
    rank_str: str = _RANKS[str(rank)]
    if claim.rank == rank_str:
        return False
    claim.setRank(rank_str)
    return True


@dataclass
class ProcessState:
    edit_summaries: dict[str, str]


def process_graph(
    input: TextIO,
    blocked_qids: set[str] = set(),
) -> Iterator[tuple[wikidata_typing.Item, list[wikidata_typing.Statement], str | None]]:
    graph = Graph()
    data = PREFIXES + input.read()
    graph.parse(data=data)

    state = ProcessState(
        edit_summaries={},
    )

    changed_claims: dict[pywikibot.ItemPage, set[HashableClaim]] = defaultdict(set)

    def mark_changed(
        item: pywikibot.ItemPage, claim: pywikibot.Claim, did_change: bool = True
    ) -> None:
        if did_change:
            changed_claims[item].add(HashableClaim(claim))

    def visit_wd_subject(
        item: pywikibot.ItemPage, predicate: URIRef, object: AnyRDFObject
    ) -> None:
        predicate_prefix, predicate_local_name = _compute_qname(predicate)

        if predicate_prefix == "wdt":
            target = _resolve_object(graph, object)
            did_change, claim = _item_append_claim_target(
                item, predicate_local_name, target
            )
            if claim.rank == "deprecated":
                logger.warning("DeprecatedClaim <%s> already exists", _claim_uri(claim))
            mark_changed(item, claim, did_change)

        elif predicate_prefix == "p" and isinstance(object, BNode):
            property_claim = pywikibot.Claim(site=SITE, pid=predicate_local_name)
            if predicate_local_name not in item.claims:
                item.claims[predicate_local_name] = []
            item.claims[predicate_local_name].append(property_claim)
            mark_changed(item, property_claim)

            for predicate, p_object in _predicate_objects(graph, object):
                visit_wds_subject(item, property_claim, predicate, p_object)

        elif predicate == WIKIDATABOTS.editSummary:
            state.edit_summaries[item.id] = object.toPython()

        else:
            logger.error(
                "NotImplemented: Unknown wd triple: %s %s %s",
                subject,
                predicate,
                object,
            )

    def visit_wds_subject(
        item: pywikibot.ItemPage,
        claim: pywikibot.Claim,
        predicate: URIRef,
        object: AnyRDFObject,
    ) -> None:
        predicate_prefix, predicate_local_name = _compute_qname(predicate)

        if predicate_prefix == "pq" or predicate_prefix == "pqv":
            target = _resolve_object(graph, object)
            did_change = _claim_append_qualifer(claim, predicate_local_name, target)
            mark_changed(item, claim, did_change)

        elif predicate_prefix == "pqe" or predicate_prefix == "pqve":
            if _graph_empty_node(graph, object):
                if predicate_local_name in claim.qualifiers:
                    del claim.qualifiers[predicate_local_name]
                    mark_changed(item, claim, True)
            else:
                target = _resolve_object(graph, object)
                did_change = _claim_set_qualifer(claim, predicate_local_name, target)
                mark_changed(item, claim, did_change)

        elif predicate_prefix == "ps":
            target = _resolve_object(graph, object)
            assert claim.getID() == predicate_local_name
            did_change = _claim_set_target(claim, target)
            mark_changed(item, claim, did_change)

        elif predicate_prefix == "psv":
            target = _resolve_object(graph, object)
            assert claim.getID() == predicate_local_name
            did_change = _claim_set_target(claim, target)
            mark_changed(item, claim, did_change)

        elif predicate == WIKIBASE.rank:
            assert isinstance(object, URIRef)
            did_change = _claim_set_rank(claim, object)
            mark_changed(item, claim, did_change)

        elif predicate == PROV.wasDerivedFrom or predicate == PROV.wasOnlyDerivedFrom:
            assert isinstance(object, BNode)
            source = _resolve_object_bnode_reference(graph, object)
            prev_sources = claim.sources.copy()
            if predicate == PROV.wasOnlyDerivedFrom:
                claim.sources = [source]
            else:
                claim.sources.append(source)
            mark_changed(item, claim, claim.sources != prev_sources)

        elif predicate == WIKIDATABOTS.editSummary:
            state.edit_summaries[item.id] = object.toPython()

        else:
            logger.error("NotImplemented: Unknown wds triple: %s %s", predicate, object)

    for subject in _subjects(graph):
        if isinstance(subject, BNode):
            continue

        assert isinstance(subject, URIRef)
        prefix, local_name = _compute_qname(subject)

        if prefix == "wd":
            assert isinstance(subject, URIRef)
            item: pywikibot.ItemPage = get_item_page(local_name)
            for predicate, object in _predicate_objects(graph, subject):
                visit_wd_subject(item, predicate, object)

        elif prefix == "wds":
            assert isinstance(subject, URIRef)
            claim: pywikibot.Claim = resolve_claim_guid(local_name)
            claim_item: pywikibot.ItemPage | None = claim.on_item
            assert claim_item
            for predicate, object in _predicate_objects(graph, subject):
                visit_wds_subject(claim_item, claim, predicate, object)

        elif subject == WIKIDATABOTS.testSubject:
            assert isinstance(subject, URIRef)
            for rdf_object in graph.objects(subject, WIKIDATABOTS.assertValue):
                assert isinstance(rdf_object, AnyRDFObject)
                assert _resolve_object(graph, rdf_object)

        else:
            logger.error("NotImplemented: Unknown subject: %s", subject)

    for item, hclaims in changed_claims.items():
        if item.id in blocked_qids:
            logger.warning("Skipping edit, %s is blocked", item.id)
            continue

        summary: str | None = state.edit_summaries.get(item.id)
        logger.info("Edit %s: %s", item.id, summary or "(no summary)")

        statements = [_pywikibot_claim_to_json(hclaim.claim) for hclaim in hclaims]
        for statement in statements:
            statement_id = statement["mainsnak"]["property"]
            statement_snak = statement.get("id", "(new claim)")
            logger.info(" ⮑ %s / %s", statement_id, statement_snak)

        assert len(statements) > 0, "No claims to save"
        itemJSON: wikidata_typing.Item = item.toJSON()
        itemJSON["id"] = item.id
        itemJSON["lastrevid"] = item.latest_revision_id
        yield (itemJSON, statements, summary)


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
