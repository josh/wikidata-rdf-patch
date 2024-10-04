import datetime
import json
import logging
import re
import urllib.request
from collections import OrderedDict, defaultdict
from collections.abc import Iterator
from functools import cache
from typing import Any, TextIO, cast

import pywikibot  # type: ignore
from rdflib import XSD, Graph
from rdflib.namespace import Namespace, NamespaceManager
from rdflib.term import BNode, Literal, URIRef

from . import wikidata_typing

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


class WbSource:
    _source: OrderedDict[str, list[pywikibot.Claim]]

    def __init__(self) -> None:
        self._source = OrderedDict()

    def add_reference(self, pid: str, reference: pywikibot.Claim) -> None:
        assert pid.startswith("P"), pid
        if pid not in self._source:
            self._source[pid] = []
        self._source[pid].append(reference)


def _compute_qname(uri: URIRef) -> tuple[str, str]:
    prefix, _, name = NS_MANAGER.compute_qname(uri)
    return (prefix, name)


@cache
def get_item_page(qid: str) -> pywikibot.ItemPage:
    assert qid.startswith("Q"), qid
    return pywikibot.ItemPage(SITE, qid)


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


def _pywikibot_from_wikibase_datavalue(
    data: wikidata_typing.DataValue,
) -> (
    pywikibot.Coordinate
    | pywikibot.WbMonolingualText
    | pywikibot.WbQuantity
    | str
    | pywikibot.WbTime
    | pywikibot.ItemPage
    | pywikibot.PropertyPage
):
    if data["type"] == "globecoordinate":
        return pywikibot.Coordinate.fromWikibase(data=data["value"], site=SITE)
    elif data["type"] == "monolingualtext":
        return pywikibot.WbMonolingualText.fromWikibase(data=data["value"], site=SITE)
    elif data["type"] == "quantity":
        return pywikibot.WbQuantity.fromWikibase(data=data["value"], site=SITE)
    elif data["type"] == "string":
        return data["value"]
    elif data["type"] == "time":
        return pywikibot.WbTime.fromWikibase(data=data["value"], site=SITE)
    elif data["type"] == "wikibase-entityid":
        if data["value"]["entity-type"] == "item":
            return get_item_page(data["value"]["id"])
        elif data["value"]["entity-type"] == "property":
            return pywikibot.PropertyPage(SITE, data["value"]["id"])
        else:
            raise NotImplementedError(
                f"Unknown entity-type: {data['value']['entity-type']}"
            )
    else:
        raise NotImplementedError(f"Unknown data type: {data['type']}")


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


def _resolve_object(
    graph: Graph, object: AnyRDFObject
) -> wikidata_typing.DataValue | WbSource:
    if isinstance(object, URIRef):
        return _resolve_object_uriref(object)
    elif isinstance(object, BNode):
        return _resolve_object_bnode(graph, object)
    elif isinstance(object, Literal):
        return _resolve_object_literal(object)


def _resolve_object_target(
    graph: Graph, object: AnyRDFObject
) -> wikidata_typing.DataValue:
    obj = _resolve_object(graph, object)
    assert not isinstance(obj, WbSource)
    return obj


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
) -> wikidata_typing.QuantityDataValue | wikidata_typing.TimeDataValue | WbSource:
    if not rdf_type:
        rdf_type = graph.value(object, RDF.type)  # type: ignore
    assert rdf_type is None or isinstance(rdf_type, URIRef)

    if rdf_type == WIKIBASE.TimeValue:
        return _resolve_object_bnode_time_value(graph, object)
    elif rdf_type == WIKIBASE.QuantityValue:
        return _resolve_object_bnode_quantity_value(graph, object)
    elif rdf_type == WIKIBASE.Reference:
        return _resolve_object_bnode_reference(graph, object)
    else:
        raise NotImplementedError(f"Unknown bnode: {rdf_type}")


def _resolve_object_bnode_reference(graph: Graph, object: BNode) -> WbSource:
    source = WbSource()

    for pr_name, pr_object in _predicate_ns_objects(graph, object, PR):
        ref = pywikibot.PropertyPage(SITE, pr_name).newClaim(is_reference=True)
        target = _pywikibot_from_wikibase_datavalue(
            _resolve_object_target(graph, pr_object)
        )
        ref.setTarget(target)
        source.add_reference(pr_name, ref)

    for prv_name, prv_object in _predicate_ns_objects(graph, object, PRV):
        ref = pywikibot.PropertyPage(SITE, prv_name).newClaim(is_reference=True)
        target = _pywikibot_from_wikibase_datavalue(
            _resolve_object_target(graph, prv_object)
        )
        ref.setTarget(target)
        source.add_reference(prv_name, ref)

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
    property = pywikibot.PropertyPage(SITE, pid)

    if pid not in item.claims:
        item.claims[pid] = []
    claims = item.claims[pid]

    target_obj = _pywikibot_from_wikibase_datavalue(data=target)
    for claim in claims:
        if claim.target_equals(target_obj):
            return (False, claim)

    new_claim: pywikibot.Claim = property.newClaim()
    new_claim.setTarget(target_obj)
    item.claims[pid].append(new_claim)

    return (True, new_claim)


def _claim_append_qualifer(
    claim: pywikibot.Claim,
    pid: str,
    target: wikidata_typing.DataValue,
) -> bool:
    assert pid.startswith("P"), pid

    if pid not in claim.qualifiers:
        claim.qualifiers[pid] = []
    qualifiers = claim.qualifiers[pid]

    target_obj = _pywikibot_from_wikibase_datavalue(data=target)
    for qualifier in qualifiers:
        if qualifier.target_equals(target_obj):
            return False

    property = pywikibot.PropertyPage(SITE, pid)
    new_qualifier: pywikibot.Claim = property.newClaim(is_qualifier=True)
    new_qualifier.setTarget(target_obj)
    claim.qualifiers[pid].append(new_qualifier)

    return True


def _claim_set_qualifer(
    claim: pywikibot.Claim,
    pid: str,
    target: wikidata_typing.DataValue,
) -> bool:
    assert pid.startswith("P"), pid

    target_obj = _pywikibot_from_wikibase_datavalue(target)

    if pid in claim.qualifiers and len(claim.qualifiers[pid]) == 1:
        qualifier: pywikibot.Claim = claim.qualifiers[pid][0]
        if qualifier.target_equals(target_obj):
            return False

    property = pywikibot.PropertyPage(SITE, pid)
    new_qualifier: pywikibot.Claim = property.newClaim(is_qualifier=True)
    new_qualifier.setTarget(target_obj)
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


def process_graph(
    username: str,
    input: TextIO,
    blocked_qids: set[str] = set(),
) -> Iterator[tuple[pywikibot.ItemPage, list[wikidata_typing.Statement], str | None]]:
    graph = Graph()
    data = PREFIXES + input.read()
    graph.parse(data=data)

    changed_claims: dict[pywikibot.ItemPage, set[HashableClaim]] = defaultdict(set)
    edit_summaries: dict[pywikibot.ItemPage, str] = {}

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
            target = _resolve_object_target(graph, object)
            did_change, claim = _item_append_claim_target(
                item, predicate_local_name, target
            )
            if claim.rank == "deprecated":
                logger.warning("DeprecatedClaim <%s> already exists", _claim_uri(claim))
            mark_changed(item, claim, did_change)

        elif predicate_prefix == "p" and isinstance(object, BNode):
            p_property: pywikibot.PropertyPage = pywikibot.PropertyPage(
                SITE, predicate_local_name
            )

            property_claim: pywikibot.Claim = p_property.newClaim()
            if predicate_local_name not in item.claims:
                item.claims[predicate_local_name] = []
            item.claims[predicate_local_name].append(property_claim)
            mark_changed(item, property_claim)

            for predicate, p_object in _predicate_objects(graph, object):
                visit_wds_subject(item, property_claim, predicate, p_object)

        elif predicate == WIKIDATABOTS.editSummary:
            edit_summaries[item] = object.toPython()

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
            target2 = _resolve_object_target(graph, object)
            did_change = _claim_append_qualifer(claim, predicate_local_name, target2)
            mark_changed(item, claim, did_change)

        elif predicate_prefix == "pqe" or predicate_prefix == "pqve":
            if _graph_empty_node(graph, object):
                if predicate_local_name in claim.qualifiers:
                    del claim.qualifiers[predicate_local_name]
                    mark_changed(item, claim, True)
            else:
                target2 = _resolve_object_target(graph, object)
                did_change = _claim_set_qualifer(claim, predicate_local_name, target2)
                mark_changed(item, claim, did_change)

        elif predicate_prefix == "ps":
            target = _pywikibot_from_wikibase_datavalue(
                _resolve_object_target(graph, object)
            )
            assert claim.getID() == predicate_local_name

            if not claim.target_equals(target):
                claim.setTarget(target)
                mark_changed(item, claim)

        elif predicate_prefix == "psv":
            target = _pywikibot_from_wikibase_datavalue(
                _resolve_object_target(graph, object)
            )
            assert claim.getID() == predicate_local_name

            if not claim.target_equals(target):
                claim.setTarget(target)
                mark_changed(item, claim)

        elif predicate == WIKIBASE.rank:
            assert isinstance(object, URIRef)
            did_change = _claim_set_rank(claim, object)
            mark_changed(item, claim, did_change)

        elif predicate == PROV.wasDerivedFrom or predicate == PROV.wasOnlyDerivedFrom:
            assert isinstance(object, BNode)
            source = _resolve_object_bnode_reference(graph, object)
            prev_sources = claim.sources.copy()
            if predicate == PROV.wasOnlyDerivedFrom:
                claim.sources = [source._source]
            else:
                claim.sources.append(source._source)
            mark_changed(item, claim, claim.sources != prev_sources)

        elif predicate == WIKIDATABOTS.editSummary:
            edit_summaries[item] = object.toPython()

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
            for object in graph.objects(subject, WIKIDATABOTS.assertValue):  # type: ignore
                assert _resolve_object(graph, object)

        else:
            logger.error("NotImplemented: Unknown subject: %s", subject)

    for item, hclaims in changed_claims.items():
        if item.id in blocked_qids:
            logger.warning("Skipping edit, %s is blocked", item.id)
            continue

        summary: str | None = edit_summaries.get(item)
        logger.info("Edit %s: %s", item.id, summary or "(no summary)")

        statements: list[wikidata_typing.Statement] = [
            hclaim.claim.toJSON() for hclaim in hclaims
        ]
        for statement in statements:
            statement_id = statement["mainsnak"]["property"]
            statement_snak = statement.get("id", "(new claim)")
            logger.info(" ⮑ %s / %s", statement_id, statement_snak)

        assert len(statements) > 0, "No claims to save"
        yield (item, statements, summary)


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
