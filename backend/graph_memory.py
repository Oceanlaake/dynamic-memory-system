"""Deterministic Graph Memory construction, export, and bounded multi-hop retrieval.

The graph is derived only from structured Memory and its source metadata.  It
never reads QA gold answers or evidence labels.  Structural hubs make explicit
the connections that used to be implicit in JSON fields:

Memory -> Subject / State Slot / Value / Session / Evidence Turn

Consecutive memories in one state slot receive ``NEXT_STATE`` edges, while
adjacent source turns receive ``NEXT_TURN`` edges.  Query expansion starts from
the ordinary Top-K candidates and performs a bounded best-first traversal.  The
result includes auditable paths and a compact subgraph for the Web UI.
"""

from __future__ import annotations

import argparse
import hashlib
import heapq
import json
import re
from collections import OrderedDict, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from backend.dynamic_state.question import is_collection_slot, supports_question
from backend.retrieval.text import tokenize
from backend.schemas import (
    CandidateMemory,
    GraphDocument,
    GraphEdge,
    GraphNode,
    GraphPath,
    GraphTrace,
    Memory,
    RetrievalResult,
)
from backend.store import MemoryStore

_TURN = re.compile(r"D(\d+):(\d+)$")
_SESSION = re.compile(r"(\d+)$")
_TEXT_DATE = re.compile(
    r"\b(\d{1,2})\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)"
    r",?\s+(\d{4})\b",
    re.IGNORECASE,
)
_CACHE: OrderedDict[tuple[str, str], "MemoryGraph"] = OrderedDict()
_CACHE_SIZE = 8

EDGE_WEIGHTS = {
    "NEXT_STATE": 1.00,
    "IN_SLOT": 0.95,
    "SUPPORTED_BY": 0.88,
    "NEXT_TURN": 0.78,
    "HAS_VALUE": 0.65,
    "ABOUT": 0.38,
    "OBSERVED_IN": 0.28,
}
MIN_GRAPH_CANDIDATE_SCORE = 0.30


@dataclass(frozen=True)
class _Link:
    neighbor: str
    relation: str
    weight: float


@dataclass(frozen=True)
class _Route:
    seed_id: str
    node_ids: tuple[str, ...]
    relations: tuple[str, ...]
    score: float

    @property
    def hops(self) -> int:
        return len(self.relations)


def _digest(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:14]


def _memory_node(memory_id: str) -> str:
    return f"memory:{memory_id}"


def _time_key(memory: Memory) -> tuple[int, str, int, str]:
    point = memory.time.effective_at or ""
    if not point and memory.time.date_time:
        match = _TEXT_DATE.search(memory.time.date_time)
        if match:
            try:
                point = datetime.strptime(" ".join(match.groups()), "%d %B %Y").date().isoformat()
            except ValueError:
                point = ""
    session = _SESSION.search(memory.time.session_id)
    return (0 if point else 1, point, int(session.group(1)) if session else 10**9, memory.memory_id)


def _turn_coordinate(node_id: str) -> tuple[int, int] | None:
    match = _TURN.search(node_id)
    return (int(match.group(1)), int(match.group(2))) if match else None


class MemoryGraph:
    """In-memory property graph with deterministic JSON serialization."""

    def __init__(self, sample_id: str, memories: Sequence[Memory]) -> None:
        self.sample_id = sample_id
        self.memories = {memory.memory_id: memory for memory in memories}
        self.nodes: dict[str, GraphNode] = {}
        self.edges: dict[tuple[str, str, str], GraphEdge] = {}
        self.adjacency: dict[str, list[_Link]] = defaultdict(list)
        self._build(memories)

    def _node(self, node_id: str, node_type: str, label: str, memory_id: str | None = None) -> None:
        self.nodes.setdefault(node_id, GraphNode(
            node_id=node_id, node_type=node_type, label=label, memory_id=memory_id,
        ))

    def _edge(self, source: str, target: str, relation: str) -> None:
        if source == target:
            return
        weight = EDGE_WEIGHTS[relation]
        key = (source, target, relation)
        if key in self.edges:
            return
        edge = GraphEdge(source=source, target=target, relation=relation, weight=weight)
        self.edges[key] = edge
        # Structural edges are directed when exported but traversable both ways.
        self.adjacency[source].append(_Link(target, relation, weight))
        self.adjacency[target].append(_Link(source, relation, weight))

    def _build(self, memories: Sequence[Memory]) -> None:
        slots: dict[tuple[str, str], list[Memory]] = defaultdict(list)
        turn_nodes: dict[tuple[int, int], str] = {}

        for memory in sorted(memories, key=lambda item: item.memory_id):
            memory_node = _memory_node(memory.memory_id)
            self._node(memory_node, "memory", memory.content, memory.memory_id)

            subject_label = memory.subject.strip()
            subject_node = f"subject:{_digest(subject_label.casefold())}"
            self._node(subject_node, "subject", subject_label)
            self._edge(memory_node, subject_node, "ABOUT")

            if memory.attribute:
                slot_key = (subject_label.casefold(), memory.attribute.strip().casefold())
                slot_node = f"slot:{_digest(chr(0).join(slot_key))}"
                self._node(slot_node, "slot", f"{memory.subject} / {memory.attribute}")
                self._edge(memory_node, slot_node, "IN_SLOT")
                slots[slot_key].append(memory)

            if memory.value:
                value_key = "\x00".join((subject_label.casefold(), memory.attribute or "", memory.value))
                value_node = f"value:{_digest(value_key)}"
                self._node(value_node, "value", memory.value)
                self._edge(memory_node, value_node, "HAS_VALUE")

            session_node = f"session:{memory.time.session_id}"
            self._node(session_node, "session", memory.time.session_id)
            self._edge(memory_node, session_node, "OBSERVED_IN")

            for ref in memory.evidence:
                turn_node = f"turn:{ref.session_id}/{ref.dia_id}"
                self._node(turn_node, "turn", f"{ref.session_id} / {ref.dia_id}")
                self._edge(memory_node, turn_node, "SUPPORTED_BY")
                coordinate = _turn_coordinate(turn_node)
                if coordinate is not None:
                    turn_nodes[coordinate] = turn_node

        for slot_memories in slots.values():
            ordered = sorted(slot_memories, key=_time_key)
            if is_collection_slot(ordered[0]):
                continue
            for older, newer in zip(ordered, ordered[1:]):
                self._edge(_memory_node(older.memory_id), _memory_node(newer.memory_id), "NEXT_STATE")

        for (session, turn), node_id in sorted(turn_nodes.items()):
            next_node = turn_nodes.get((session, turn + 1))
            if next_node:
                self._edge(node_id, next_node, "NEXT_TURN")

        for links in self.adjacency.values():
            links.sort(key=lambda link: (-link.weight, link.relation, link.neighbor))

    def document(self) -> GraphDocument:
        return GraphDocument(
            sample_id=self.sample_id,
            memory_count=len(self.memories),
            nodes=sorted(self.nodes.values(), key=lambda item: item.node_id),
            edges=sorted(self.edges.values(), key=lambda item: (item.source, item.target, item.relation)),
        )

    def routes(
        self, seed_memory_ids: Sequence[str], max_hops: int, *, question: str,
    ) -> tuple[dict[str, _Route], int]:
        """Return the strongest bounded route to each node."""
        best: dict[str, _Route] = {}
        queue: list[tuple[float, int, str, _Route]] = []
        serial = 0
        for memory_id in dict.fromkeys(seed_memory_ids):
            node_id = _memory_node(memory_id)
            if node_id not in self.nodes:
                continue
            route = _Route(memory_id, (node_id,), (), 1.0)
            best[node_id] = route
            heapq.heappush(queue, (-1.0, serial, node_id, route))
            serial += 1

        while queue:
            _, _, node_id, route = heapq.heappop(queue)
            current = best.get(node_id)
            if current != route or route.hops >= max_hops:
                continue
            for link in self.adjacency.get(node_id, ()):  # pragma: no branch - graph nodes may be leaves
                if link.neighbor in route.node_ids:
                    continue
                neighbor = self.nodes[link.neighbor]
                if neighbor.node_type == "memory" and neighbor.memory_id not in seed_memory_ids:
                    target = self.memories[neighbor.memory_id]
                    # Slot history is the graph's strongest explicit semantic
                    # connection. Subject/session/value/evidence hubs are much
                    # broader and may only return to a question-relevant Memory.
                    if link.relation not in {"NEXT_STATE", "IN_SLOT"} and not supports_question(
                        question, target,
                    ):
                        continue
                score = route.score * link.weight
                candidate = _Route(
                    route.seed_id,
                    (*route.node_ids, link.neighbor),
                    (*route.relations, link.relation),
                    score,
                )
                previous = best.get(link.neighbor)
                if previous is not None and (previous.score, -previous.hops) >= (score, -candidate.hops):
                    continue
                best[link.neighbor] = candidate
                heapq.heappush(queue, (-score, serial, link.neighbor, candidate))
                serial += 1
        return best, len(best)


def _fingerprint(memories: Sequence[Memory]) -> str:
    digest = hashlib.sha256()
    for memory in memories:
        digest.update(memory.memory_id.encode())
        digest.update(memory.subject.encode())
        digest.update(memory.type.encode())
        digest.update((memory.attribute or "").encode())
        digest.update((memory.value or "").encode())
        digest.update(memory.content.encode())
        digest.update(memory.time.session_id.encode())
        digest.update((memory.time.date_time or "").encode())
        digest.update((memory.time.effective_at or "").encode())
        for ref in memory.evidence:
            digest.update(f"{ref.session_id}/{ref.dia_id}".encode())
    return digest.hexdigest()


def graph_for(sample_id: str, memories: Sequence[Memory]) -> MemoryGraph:
    key = (sample_id, _fingerprint(memories))
    graph = _CACHE.get(key)
    if graph is not None:
        _CACHE.move_to_end(key)
        return graph
    graph = MemoryGraph(sample_id, memories)
    _CACHE[key] = graph
    while len(_CACHE) > _CACHE_SIZE:
        _CACHE.popitem(last=False)
    return graph


def _query_relevance(question: str, memory: Memory) -> float:
    query = set(tokenize(question))
    query -= set(tokenize(memory.subject))
    if not query:
        return 0.0
    text = " ".join(filter(None, (memory.attribute, memory.value, memory.content)))
    return len(query & set(tokenize(text))) / len(query)


def _route_is_relevant(question: str, memory: Memory, route: _Route) -> bool:
    relations = set(route.relations)
    if relations & {"NEXT_STATE", "IN_SLOT"}:
        return True
    lexical = _query_relevance(question, memory)
    if "NEXT_TURN" in relations:
        return lexical > 0 or supports_question(question, memory)
    if relations & {"HAS_VALUE", "ABOUT", "OBSERVED_IN"}:
        return lexical >= 0.25 and supports_question(question, memory)
    return False


def _compact_subgraph(graph: MemoryGraph, routes: Sequence[_Route]) -> tuple[list[GraphNode], list[GraphEdge]]:
    node_ids = {node_id for route in routes for node_id in route.node_ids}
    edge_keys = set()
    for route in routes:
        for source, target, relation in zip(route.node_ids, route.node_ids[1:], route.relations):
            direct = (source, target, relation)
            reverse = (target, source, relation)
            edge_keys.add(direct if direct in graph.edges else reverse)
    nodes = sorted((graph.nodes[node_id] for node_id in node_ids), key=lambda item: item.node_id)
    edges = sorted((graph.edges[key] for key in edge_keys), key=lambda item: (item.source, item.target, item.relation))
    return nodes, edges


def expand_graph_memories(
    retrieval: RetrievalResult,
    sample_memories: Sequence[Memory],
    *,
    enabled: bool = False,
    max_hops: int = 3,
    max_new_memories: int = 5,
) -> tuple[RetrievalResult, GraphTrace]:
    """Expand Top-K candidates through a bounded, auditable graph traversal."""
    if not 1 <= max_hops <= 4:
        raise ValueError("max_hops must be between 1 and 4")
    if not 1 <= max_new_memories <= 50:
        raise ValueError("max_new_memories must be between 1 and 50")
    seeds = [candidate.memory.memory_id for candidate in retrieval.candidates
             if candidate.candidate_source == "initial"]
    trace = GraphTrace(
        enabled=enabled,
        max_hops=max_hops,
        seed_memory_ids=list(dict.fromkeys(seeds)),
        stop_reason="disabled",
    )
    if not enabled:
        return retrieval, trace
    if retrieval.degraded or not seeds:
        trace.stop_reason = "no_seed"
        return retrieval, trace

    graph = graph_for(retrieval.sample_id, sample_memories)
    routes, visited = graph.routes(seeds, max_hops, question=retrieval.question)
    trace.visited_node_count = visited
    existing = {candidate.memory.memory_id for candidate in retrieval.candidates}
    ranked: list[tuple[float, int, str, Memory, _Route]] = []
    for node_id, route in routes.items():
        node = graph.nodes[node_id]
        if node.node_type != "memory" or not node.memory_id or node.memory_id in existing:
            continue
        memory = graph.memories[node.memory_id]
        if not _route_is_relevant(retrieval.question, memory, route):
            continue
        relevance = _query_relevance(retrieval.question, memory)
        score = route.score * (0.75 + 0.25 * relevance)
        # Subject and session hubs remain visible structural nodes but their
        # two-hop weights are intentionally below this threshold. They cannot
        # flood the answer context merely because a person or session matches.
        if score < MIN_GRAPH_CANDIDATE_SCORE:
            continue
        ranked.append((score, route.hops, memory.memory_id, memory, route))
    ranked.sort(key=lambda item: (-item[0], item[1], item[2]))
    trace.eligible_memory_count = len(ranked)
    trace.truncated = len(ranked) > max_new_memories

    candidates = [candidate.model_copy(update={"rank": index})
                  for index, candidate in enumerate(retrieval.candidates, start=1)]
    selected_routes: list[_Route] = []
    for _, _, _, memory, route in ranked[:max_new_memories]:
        candidates.append(CandidateMemory(
            memory=memory,
            score=0,
            rank=len(candidates) + 1,
            candidate_source="graph_expansion",
            expansion_reason="graph_path",
            graph_hops=route.hops,
            graph_path=list(route.node_ids),
        ))
        trace.added_memory_ids.append(memory.memory_id)
        trace.paths.append(GraphPath(
            memory_id=memory.memory_id,
            hops=route.hops,
            node_ids=list(route.node_ids),
            relations=list(route.relations),
        ))
        selected_routes.append(route)

    # Always expose seed nodes; selected paths add the intermediate graph.
    display_routes = selected_routes or [routes[_memory_node(seed)] for seed in seeds
                                          if _memory_node(seed) in routes]
    trace.nodes, trace.edges = _compact_subgraph(graph, display_routes)
    trace.stop_reason = (
        "candidate_limit" if trace.truncated else
        "expanded" if trace.added_memory_ids else "no_new_memory"
    )
    return retrieval.model_copy(update={"candidates": candidates}), trace


def export_graph(sample_id: str, memories: Sequence[Memory], path: Path) -> GraphDocument:
    document = graph_for(sample_id, memories).document()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(document.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return document


def main() -> None:
    parser = argparse.ArgumentParser(description="Build and export a deterministic Graph Memory JSON.")
    parser.add_argument("--sample-id", required=True)
    parser.add_argument("--memory-dir", type=Path, default=None)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    store = MemoryStore(args.memory_dir)
    memories = store.memories(args.sample_id)
    if memories is None:
        raise SystemExit(f"Unknown sample_id: {args.sample_id}")
    document = export_graph(args.sample_id, memories, args.out)
    print(json.dumps({
        "sample_id": document.sample_id,
        "memory_count": document.memory_count,
        "nodes": len(document.nodes),
        "edges": len(document.edges),
        "written": str(args.out),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
