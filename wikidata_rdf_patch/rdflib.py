import logging
from collections.abc import Iterator

from rdflib import Graph
from rdflib.term import BNode, Literal, URIRef

logger = logging.getLogger("rdflib")


GraphSubject = URIRef | BNode
GraphPredicate = URIRef
GraphObject = URIRef | BNode | Literal


def graph_subjects(graph: Graph) -> Iterator[GraphSubject]:
    for subject in graph.subjects(unique=True):
        assert isinstance(subject, URIRef) or isinstance(subject, BNode)
        yield subject


def graph_predicates(graph: Graph, subject: GraphSubject) -> Iterator[GraphPredicate]:
    for predicate in graph.predicates(subject=subject, unique=True):
        assert isinstance(predicate, URIRef)
        yield predicate


def graph_predicate_objects(
    graph: Graph, subject: GraphSubject
) -> Iterator[tuple[GraphPredicate, GraphObject]]:
    for predicate, object in graph.predicate_objects(subject, unique=True):
        assert isinstance(predicate, URIRef)
        assert (
            isinstance(object, URIRef)
            or isinstance(object, BNode)
            or isinstance(object, Literal)
        )
        yield predicate, object


def graph_objects(
    graph: Graph, subject: GraphSubject, predicate: GraphPredicate
) -> Iterator[GraphObject]:
    for object in graph.objects(subject, predicate, unique=True):
        assert (
            isinstance(object, URIRef)
            or isinstance(object, BNode)
            or isinstance(object, Literal)
        )
        yield object


def graph_value(
    graph: Graph, subject: GraphSubject, predicate: GraphPredicate
) -> GraphObject | None:
    objects = list(graph_objects(graph, subject, predicate))
    if len(objects) == 1:
        return objects[0]
    elif len(objects) > 1:
        logger.warning(f"multiple objects for {subject} {predicate}")
        return objects[0]
    else:
        return None


def graph_literal(
    graph: Graph, subject: GraphSubject, predicate: GraphPredicate
) -> Literal | None:
    value = graph_value(graph, subject, predicate)
    if value and isinstance(value, Literal):
        return value
    elif value and not isinstance(value, Literal):
        logger.warning(f"non-literal value for {subject} {predicate}: {value}")
        return None
    else:
        return None


def graph_urirefs(graph: Graph) -> Iterator[URIRef]:
    for subject in graph.subjects(unique=True):
        if isinstance(subject, URIRef):
            yield subject

    for predicate in graph.predicates(unique=True):
        if isinstance(predicate, URIRef):
            yield predicate

    for object in graph.objects(unique=True):
        if isinstance(object, URIRef):
            yield object


def graph_empty_node(graph: Graph, object: GraphObject) -> bool:
    return isinstance(object, BNode) and len(list(graph.predicate_objects(object))) == 0
