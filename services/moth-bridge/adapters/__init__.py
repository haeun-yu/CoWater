from .base import ProtocolAdapter, ParsedReport, GeoPoint
from .nmea import NMEAAdapter
from .mavlink import MAVLinkAdapter
from .ros import ROSAdapter

ADAPTER_REGISTRY: dict[str, type[ProtocolAdapter]] = {
    "NMEAAdapter": NMEAAdapter,
    "MAVLinkAdapter": MAVLinkAdapter,
    "ROSAdapter": ROSAdapter,
}

__all__ = [
    "ProtocolAdapter",
    "ParsedReport",
    "GeoPoint",
    "NMEAAdapter",
    "MAVLinkAdapter",
    "ROSAdapter",
    "ADAPTER_REGISTRY",
]
