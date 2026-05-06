"""per-(topic, partition) offset bookkeeping for the kafka worker.

problem: the previous worker called consumer.commit() with no args which advances all partition
cursors past every consumed offset, even messages still buffered for a different trace_id. that
loses messages on a hard kill mid-buffer.

OffsetTracker fixes this: when a message arrives, register its (topic, partition, offset, trace_id).
when a trace's bundle is flushed (success or dlq), call complete(trace_id) — it removes those
offsets from the in-flight set and returns the dict of commit positions per partition. those
positions are the earliest still-in-flight offset on each partition (or high_water + 1 if the
partition is fully drained).

semantics: commit position = next offset to consume after restart. messages strictly below it are
considered processed; the in-flight set guarantees we never advance past an unprocessed message."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from kafka.structs import OffsetAndMetadata, TopicPartition


@dataclass
class _PartitionState:
    high_water: int = -1
    in_flight: set[int] | None = None

    def __post_init__(self) -> None:
        if self.in_flight is None:
            self.in_flight = set()


class OffsetTracker:
    def __init__(self) -> None:
        self._partitions: dict[TopicPartition, _PartitionState] = defaultdict(_PartitionState)
        self._trace_offsets: dict[str, list[tuple[TopicPartition, int]]] = defaultdict(list)

    def add(self, topic: str, partition: int, offset: int, trace_id: str) -> None:
        tp = TopicPartition(topic=topic, partition=partition)
        st = self._partitions[tp]
        assert st.in_flight is not None
        st.in_flight.add(offset)
        if offset > st.high_water:
            st.high_water = offset
        self._trace_offsets[trace_id].append((tp, offset))

    def complete(self, trace_id: str) -> dict[TopicPartition, OffsetAndMetadata]:
        """remove the trace's offsets from the in-flight set and return a per-partition
        commit map. returns empty dict if the trace_id is unknown (idempotent)."""
        consumed = self._trace_offsets.pop(trace_id, [])
        affected: set[TopicPartition] = set()
        for tp, offset in consumed:
            st = self._partitions[tp]
            assert st.in_flight is not None
            st.in_flight.discard(offset)
            affected.add(tp)
        commits: dict[TopicPartition, OffsetAndMetadata] = {}
        for tp in affected:
            st = self._partitions[tp]
            assert st.in_flight is not None
            if st.in_flight:
                commits[tp] = OffsetAndMetadata(min(st.in_flight), "", -1)
            else:
                commits[tp] = OffsetAndMetadata(st.high_water + 1, "", -1)
        return commits

    def discard_trace(self, trace_id: str) -> None:
        """remove a trace from the bookkeeping without committing — used when a bundle is
        re-buffered for retry. the offsets stay in the in_flight set so we don't commit past
        them prematurely."""
        for tp, offset in self._trace_offsets.pop(trace_id, []):
            st = self._partitions[tp]
            assert st.in_flight is not None
            st.in_flight.add(offset)

    def reattach(self, trace_id: str, entries: list[tuple[str, int, int]]) -> None:
        """test/utility helper. (topic, partition, offset) triples for a single trace."""
        for topic, partition, offset in entries:
            self.add(topic, partition, offset, trace_id)
