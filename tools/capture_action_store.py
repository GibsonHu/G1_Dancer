"""Temporary passive capture tool for documenting the official UniStore protocol."""
import os
import time

from cyclonedds.sub import DataReader
from cyclonedds.topic import Topic
from unitree_sdk2py.core.channel import ChannelFactory, ChannelFactoryInitialize
from unitree_sdk2py.idl.std_msgs.msg.dds_ import String_
from unitree_sdk2py.idl.unitree_api.msg.dds_ import Request_, Response_


ChannelFactoryInitialize(0, "enP8p1s0")
participant = ChannelFactory._ChannelFactory__participant
topics = (("event", "rt/event/action_store", String_),
          ("webrtc", "rt/webrtcreq", String_),
          ("webrtc", "rt/xfk_webrtcreq", String_),
          ("request", "rt/api/action_store/request", Request_),
          ("response", "rt/api/action_store/response", Response_),
          # UniStore packages can hand control to any of these robot services.
          ("request", "rt/api/sport/request", Request_),
          ("response", "rt/api/sport/response", Response_),
          ("request", "rt/api/arm/request", Request_),
          ("response", "rt/api/arm/response", Response_),
          ("request", "rt/api/motion_switcher/request", Request_),
          ("response", "rt/api/motion_switcher/response", Response_))
readers = [(label, DataReader(participant, Topic(participant, topic, message)))
           for label, topic, message in topics]
path = os.environ.get("ACTION_STORE_CAPTURE", "/tmp/g1-action-store-capture.log")
with open(path, "a", encoding="utf-8") as log:
    log.write("READY\n")
    log.flush()
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        for label, reader in readers:
            for sample in reader.take(50):
                log.write(f"{label.upper()} {sample!r}\n")
                log.flush()
        time.sleep(.1)
