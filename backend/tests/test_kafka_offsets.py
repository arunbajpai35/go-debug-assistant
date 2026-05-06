from kafka.structs import TopicPartition

from backend.kafka_offsets import OffsetTracker

TOPIC = "debug.logs"


def tp(partition: int) -> TopicPartition:
    return TopicPartition(topic=TOPIC, partition=partition)


def test_complete_unknown_trace_returns_empty():
    t = OffsetTracker()
    assert t.complete("nope") == {}


def test_complete_single_partition_advances_to_high_water_plus_one_when_drained():
    t = OffsetTracker()
    t.add(TOPIC, 0, 5, "t1")
    t.add(TOPIC, 0, 6, "t1")
    t.add(TOPIC, 0, 7, "t1")

    commits = t.complete("t1")
    assert tp(0) in commits
    # all three offsets processed → next offset to consume = 8
    assert commits[tp(0)].offset == 8


def test_complete_does_not_advance_past_other_in_flight_traces():
    t = OffsetTracker()
    # interleaved t1 and t2 on the same partition
    t.add(TOPIC, 0, 10, "t1")
    t.add(TOPIC, 0, 11, "t2")
    t.add(TOPIC, 0, 12, "t1")
    t.add(TOPIC, 0, 13, "t2")

    # finishing t1 first must NOT advance past offset 11 because t2 still owns it
    commits = t.complete("t1")
    assert commits[tp(0)].offset == 11

    # now t2 finishes; everything drains → next offset is 14
    commits = t.complete("t2")
    assert commits[tp(0)].offset == 14


def test_complete_handles_multiple_partitions_independently():
    t = OffsetTracker()
    t.add(TOPIC, 0, 5, "t1")
    t.add(TOPIC, 1, 100, "t1")
    t.add(TOPIC, 1, 101, "t2")

    # finishing t1: partition 0 fully drained → 6, partition 1 still has t2's 101 → 101
    commits = t.complete("t1")
    assert commits[tp(0)].offset == 6
    assert commits[tp(1)].offset == 101


def test_complete_only_returns_partitions_that_changed():
    t = OffsetTracker()
    t.add(TOPIC, 0, 5, "t1")
    t.add(TOPIC, 1, 100, "t2")

    commits = t.complete("t1")
    # finishing t1 only affected partition 0; partition 1 is not in the dict
    assert tp(0) in commits
    assert tp(1) not in commits


def test_discard_trace_keeps_offsets_in_flight_for_retry():
    """when a bundle is re-buffered for retry, discard_trace clears trace bookkeeping but
    leaves the offsets in_flight so we don't commit past them."""
    t = OffsetTracker()
    t.add(TOPIC, 0, 5, "t1")
    t.add(TOPIC, 0, 6, "t2")

    t.discard_trace("t1")
    # t2 finishes; t1's offset 5 must still hold the watermark back to 5
    commits = t.complete("t2")
    assert commits[tp(0)].offset == 5


def test_complete_is_idempotent():
    t = OffsetTracker()
    t.add(TOPIC, 0, 5, "t1")
    first = t.complete("t1")
    second = t.complete("t1")
    assert tp(0) in first
    assert second == {}


def test_high_water_does_not_regress_with_out_of_order_arrivals():
    t = OffsetTracker()
    t.add(TOPIC, 0, 10, "t1")
    t.add(TOPIC, 0, 5, "t2")  # smaller offset arrives later (e.g. rebalance)
    commits = t.complete("t1")
    # min(in_flight) is 5 (t2's offset); we cannot commit past it
    assert commits[tp(0)].offset == 5
    commits = t.complete("t2")
    assert commits[tp(0)].offset == 11  # high_water (10) + 1
