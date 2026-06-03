from __future__ import annotations

import asyncio

import pytest

from rangkai.event_bus import Event, EventBus


@pytest.mark.asyncio
async def test_publish_delivers_event_to_active_subscriber():
    bus = EventBus()
    event = Event(type="issues_updated", data={"count": 5})

    received = []
    async with bus.subscribe() as sub:
        await bus.publish(event)
        received.append(await asyncio.wait_for(sub.__anext__(), timeout=1.0))

    assert received == [event]


@pytest.mark.asyncio
async def test_multiple_subscribers_receive_independently():
    bus = EventBus()
    event = Event(type="runs_updated", data={"issue": 42})

    received_1 = []
    received_2 = []
    
    async with bus.subscribe() as sub1, bus.subscribe() as sub2:
        await bus.publish(event)
        received_1.append(await asyncio.wait_for(sub1.__anext__(), timeout=1.0))
        received_2.append(await asyncio.wait_for(sub2.__anext__(), timeout=1.0))

    assert received_1 == [event]
    assert received_2 == [event]


@pytest.mark.asyncio
async def test_unsubscribed_consumer_stops_receiving():
    bus = EventBus()
    event1 = Event(type="log_append", data={"issue": 1, "line": "first"})
    event2 = Event(type="log_append", data={"issue": 1, "line": "second"})

    received = []
    
    async with bus.subscribe() as sub:
        await bus.publish(event1)
        received.append(await asyncio.wait_for(sub.__anext__(), timeout=1.0))
    
    # After exiting the context, subscriber should be cleaned up
    await bus.publish(event2)
    
    assert received == [event1]
    assert len(bus._subscribers) == 0


@pytest.mark.asyncio
async def test_slow_consumer_drops_events_without_blocking():
    bus = EventBus()

    async with bus.subscribe() as sub:
        # Fill the queue beyond capacity (100)
        for i in range(120):
            await bus.publish(Event(type="issues_updated", data={"i": i}))

        # Should receive exactly 100 (the queue capacity)
        received = []
        for _ in range(100):
            received.append(await asyncio.wait_for(sub.__anext__(), timeout=1.0))

        # The 20 overflow events were dropped
        assert len(received) == 100
        assert received[0].data["i"] == 0
        assert received[99].data["i"] == 99

        # Queue is now empty; reading again should time out
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(sub.__anext__(), timeout=0.05)


@pytest.mark.asyncio
async def test_concurrent_publish_and_subscribe_are_safe():
    bus = EventBus()
    num_events = 50
    num_subscribers = 3

    async def publisher():
        for i in range(num_events):
            await bus.publish(Event(type="runs_updated", data={"i": i}))

    async def subscriber():
        count = 0
        async with bus.subscribe() as sub:
            for _ in range(num_events):
                try:
                    await asyncio.wait_for(sub.__anext__(), timeout=1.0)
                    count += 1
                except asyncio.TimeoutError:
                    break
        return count

    # Start publishers and subscribers concurrently
    tasks = [asyncio.create_task(publisher()) for _ in range(2)]
    tasks.extend([asyncio.create_task(subscriber()) for _ in range(num_subscribers)])

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # No exceptions should occur
    for result in results:
        assert not isinstance(result, Exception), f"Task failed: {result}"
