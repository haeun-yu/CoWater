from .base import ProtocolAdapter, ParsedReport, ParsedStreamMessage, GeoPoint
from .device_stream import DeviceStreamAdapter
from .nmea import NMEAAdapter
from .mavlink import MAVLinkAdapter
from .ros import ROSAdapter

ADAPTER_REGISTRY: dict[str, type[ProtocolAdapter]] = {
    "DeviceStreamAdapter": DeviceStreamAdapter,
    "NMEAAdapter": NMEAAdapter,
    "MAVLinkAdapter": MAVLinkAdapter,
    "ROSAdapter": ROSAdapter,
}

__all__ = [
    "ProtocolAdapter",
    "ParsedReport",
    "ParsedStreamMessage",
    "GeoPoint",
    "DeviceStreamAdapter",
    "NMEAAdapter",
    "MAVLinkAdapter",
    "ROSAdapter",
    "ADAPTER_REGISTRY",
]
