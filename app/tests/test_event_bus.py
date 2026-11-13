import threading

from trainer.core.event_bus import EventBus
from trainer.core.events import Event, GameEvent, InputFrame


def test_publish_is_queued_until_dispatch():
    bus = EventBus()
    seen = []
    bus.subscribe(GameEvent, seen.append)
    bus.publish(GameEvent(kind="hit"))
    assert seen == []
    assert bus.dispatch() == 1
    assert seen[0].kind == "hit"


def test_base_class_subscription_receives_subclasses():
    bus = EventBus()
    seen = []
    bus.subscribe(Event, seen.append)
    bus.publish(InputFrame(tilt_x=0.1))
    bus.dispatch()
    assert isinstance(seen[0], InputFrame)


def test_bad_handler_does_not_stop_others():
    bus = EventBus()
    seen = []
    bus.subscribe(GameEvent, lambda e: 1 / 0)
    bus.subscribe(GameEvent, seen.append)
    bus.publish(GameEvent(kind="x"))
    bus.dispatch()
    assert len(seen) == 1


def test_publish_from_thread():
    bus = EventBus()
    seen = []
    bus.subscribe(GameEvent, seen.append)
    t = threading.Thread(target=lambda: [bus.publish(GameEvent(kind=str(i))) for i in range(100)])
    t.start()
    t.join()
    assert bus.dispatch() == 100
    assert len(seen) == 100
