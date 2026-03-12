class EventBus:
    _listeners = {}

    @classmethod
    def subscribe(cls, event_type, callback):
        if event_type not in cls._listeners:
            cls._listeners[event_type] = []
        cls._listeners[event_type].append(callback)

    @classmethod
    def emit(cls, event_type, *args, **kwargs):
        if event_type in cls._listeners:
            for callback in cls._listeners[event_type]:
                try:
                    callback(*args, **kwargs)
                except Exception as e:
                    print(f"Error in event listener for {event_type}: {e}")

# Event Types
SALE_CREATED = "sale_created"
CUSTOMER_CREATED = "customer_created"
ITEM_UPDATED = "item_updated"
DATA_REFRESHED = "data_refreshed"
