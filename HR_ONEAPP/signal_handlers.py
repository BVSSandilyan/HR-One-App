"""
WebRTC Signaling via Flask-SocketIO.

Architecture: mesh topology — every participant opens a direct RTCPeerConnection
to every other participant in the same meeting room. This file is the signaling
relay: it forwards offer/answer/ICE between peers without touching the media itself.

Room naming: Socket.IO rooms are named "meeting_{id}" so signals are isolated
per meeting — participant A in meeting 1 never receives signals from meeting 2.

Session auth: we read Flask's server-side session via the `request.sid` context
so only authenticated users can join a signaling room. Unauthenticated socket
connections are immediately disconnected.
"""

from flask import request, session
from flask_socketio import emit, join_room, leave_room, disconnect
from app import socketio

# {meeting_id: {socket_id: {user_id, user_name}}}
_rooms: dict = {}


def _room_name(meeting_id):
    return f"meeting_{meeting_id}"


@socketio.on("connect")
def on_connect():
    # Flask session is available here because SocketIO shares the WSGI session
    if "user_id" not in session:
        disconnect()
        return False   # refuse the connection


@socketio.on("join_meeting")
def on_join(data):
    """Client emits this immediately after connecting, passing {meeting_id}."""
    mid  = str(data.get("meeting_id", ""))
    uid  = session.get("user_id")
    name = session.get("user_name", "Participant")
    room = _room_name(mid)

    join_room(room)
    _rooms.setdefault(mid, {})[request.sid] = {"user_id": uid, "name": name}

    # Tell the new joiner who else is already in the room so the client can
    # initiate peer connections to each of them (caller side).
    peers = [
        {"sid": sid, "user_id": info["user_id"], "name": info["name"]}
        for sid, info in _rooms[mid].items()
        if sid != request.sid
    ]
    emit("existing_peers", {"peers": peers})

    # Tell everyone already in the room about the new joiner (callee side).
    emit("peer_joined", {"sid": request.sid, "user_id": uid, "name": name},
         to=room, skip_sid=request.sid)


@socketio.on("offer")
def on_offer(data):
    """Relay: forward an SDP offer from caller → target peer only."""
    emit("offer", {
        "sdp":       data["sdp"],
        "from_sid":  request.sid,
        "from_name": session.get("user_name", "Participant")
    }, to=data["target_sid"])


@socketio.on("answer")
def on_answer(data):
    """Relay: forward an SDP answer from callee → original caller only."""
    emit("answer", {
        "sdp":      data["sdp"],
        "from_sid": request.sid
    }, to=data["target_sid"])


@socketio.on("ice_candidate")
def on_ice(data):
    """Relay: forward an ICE candidate between two specific peers."""
    emit("ice_candidate", {
        "candidate": data["candidate"],
        "from_sid":  request.sid
    }, to=data["target_sid"])


@socketio.on("media_state")
def on_media_state(data):
    """Broadcast this participant's mic/cam/screen state to the whole room."""
    mid  = str(data.get("meeting_id", ""))
    room = _room_name(mid)
    emit("peer_media_state", {
        "user_id":  session.get("user_id"),
        "sid":      request.sid,
        "mic":      data.get("mic", False),
        "cam":      data.get("cam", False),
        "screen":   data.get("screen", False),
        "name":     session.get("user_name", "Participant")
    }, to=room, skip_sid=request.sid)


@socketio.on("disconnect")
def on_disconnect():
    uid = session.get("user_id")
    for mid, sids in list(_rooms.items()):
        if request.sid in sids:
            del sids[request.sid]
            if not sids:
                del _rooms[mid]
            room = _room_name(mid)
            emit("peer_left", {"sid": request.sid, "user_id": uid},
                 to=room)
            leave_room(room)
            break
