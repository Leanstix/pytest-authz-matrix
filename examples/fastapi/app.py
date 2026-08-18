from __future__ import annotations

from fastapi import FastAPI, Header, HTTPException

app = FastAPI()

BOOKINGS = {
    1: {"id": 1, "owner": "owner", "status": "pending"},
    2: {"id": 2, "owner": "someone-else", "status": "pending"},
}


def _booking_for_actor(booking_id: int, actor: str | None) -> dict[str, object]:
    booking = BOOKINGS.get(booking_id)
    if booking is None or actor != booking["owner"]:
        raise HTTPException(status_code=404)
    return booking


@app.get("/bookings/{booking_id}", name="booking-detail")
def get_booking(booking_id: int, x_actor: str | None = Header(default=None)):
    return _booking_for_actor(booking_id, x_actor)


@app.patch("/bookings/{booking_id}", name="booking-update")
def update_booking(
    booking_id: int,
    payload: dict[str, str],
    x_actor: str | None = Header(default=None),
):
    booking = _booking_for_actor(booking_id, x_actor)
    booking["status"] = payload["status"]
    return booking
