"""
NPE Confirmation Service — Database Models
Based on full analysis of WordPress PHP plugins:
  - tour-confirmation.php
  - morning-pickup.php
  - tickets-reminder.php
  - excel-parser.php
"""

from sqlalchemy import (
    Column, Integer, String, DateTime, Boolean, Text,
    Enum, ForeignKey, Date, LargeBinary, SmallInteger
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
import secrets
from sqlalchemy import Column, Integer, String, Text, DateTime, Date, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.database import Base


def _now_la():
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("America/Los_Angeles"))

# ─── Enums ────────────────────────────────────────────────────────────────────

class BookingType(str, enum.Enum):
    bus_tour   = "bus_tour"    # Tour Confirmation + Morning Reminder
    self_drive = "self_drive"  # Ticket Reminder only


class BookingSource(str, enum.Enum):
    manual   = "manual"
    rezdy    = "rezdy"
    tripguru = "tripguru"


class BookingStatus(str, enum.Enum):
    pending    = "pending"
    scheduled  = "scheduled"
    sent       = "sent"
    confirmed  = "confirmed"
    modify_req = "modify_req"
    cancelled  = "cancelled"


class NotificationChannel(str, enum.Enum):
    email = "email"
    sms   = "sms"


class NotificationType(str, enum.Enum):
    tour_confirmation = "tour_confirmation"
    morning_reminder  = "morning_reminder"
    ticket_reminder   = "ticket_reminder"


class NotificationStatus(str, enum.Enum):
    pending = "pending"
    sent    = "sent"
    failed  = "failed"


# ─── Pickup Locations ─────────────────────────────────────────────────────────

class PickupLocation(Base):
    __tablename__ = "pickup_locations"

    id           = Column(Integer, primary_key=True, index=True)
    hotel_name   = Column(String(200), unique=True, nullable=False)
    photo_url    = Column(String(500), default="")
    instruction  = Column(Text, nullable=True)
    last_fetched = Column(DateTime, nullable=True)
    created_at   = Column(DateTime, server_default=func.now())


# ─── Promotions ───────────────────────────────────────────────────────────────

class Promotion(Base):
    __tablename__ = "promotions"

    id          = Column(Integer, primary_key=True, index=True)
    code        = Column(String(20), unique=True, nullable=False)   # e.g. "MTLV"
    name        = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    email_notes = Column(Text, nullable=True)
    created_at  = Column(DateTime, server_default=func.now())

    tickets = relationship("BookingTicket", back_populates="promotion")


# ─── Manifests ────────────────────────────────────────────────────────────────

class Manifest(Base):
    """
    A manifest groups one or more Rezdy products into a named tour category.
    e.g. "Grand Canyon South" covers multiple GYG/Viator product variants.
    booking_type determines which send module applies.
    """
    __tablename__ = "manifests"

    id           = Column(Integer, primary_key=True, index=True)
    name         = Column(String(200), unique=True, nullable=False)
    booking_type = Column(String(20), nullable=False, default="bus_tour")
    is_active    = Column(Boolean, default=True)
    sort_order   = Column(Integer, default=0)
    created_at   = Column(DateTime, server_default=func.now())
    updated_at   = Column(DateTime, server_default=func.now(), onupdate=func.now())

    products = relationship("ManifestProduct", back_populates="manifest",
                            cascade="all, delete-orphan")


class ManifestProduct(Base):
    """
    Maps a Rezdy productCode to a Manifest.
    product_code is the stable Rezdy P-code (e.g. P60JMF).
    product_name is kept for display, auto-updated by webhook.
    """
    __tablename__ = "manifest_products"

    id           = Column(Integer, primary_key=True, index=True)
    manifest_id  = Column(Integer, ForeignKey("manifests.id"), nullable=False, index=True)
    product_code = Column(String(20), unique=True, nullable=False, index=True)
    product_name = Column(String(300), nullable=False, default="")
    created_at   = Column(DateTime, server_default=func.now())
    updated_at   = Column(DateTime, server_default=func.now(), onupdate=func.now())

    manifest = relationship("Manifest", back_populates="products")


# ─── Bookings ─────────────────────────────────────────────────────────────────

class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)

    # Type & Source
    booking_type = Column(String(20), nullable=False, default=BookingType.bus_tour.value)
    source       = Column(String(20), default=BookingSource.manual.value)
    status       = Column(String(20), default=BookingStatus.pending.value)

    # Identifiers
    confirm_token   = Column(String(64), unique=True, index=True,
                             default=lambda: secrets.token_urlsafe(32))
    order_number    = Column(String(50), index=True, nullable=False)
    rezdy_order_id  = Column(String(128), nullable=True, index=True)
    confirmation_no = Column(String(100), nullable=True)   # attraction confirmation#

    # Rezdy Product (v2)
    product_code = Column(String(20),  nullable=True, index=True)
    product_name = Column(String(300), nullable=True)
    tt_number    = Column(String(50),  nullable=True)   # financial ref, stored not displayed

    # Guest Info
    first_name     = Column(String(100), nullable=False)
    last_name      = Column(String(100), nullable=False, default="")
    customer_email = Column(String(200), nullable=False)
    phone          = Column(String(50), nullable=True)
    quantities     = Column(Integer, default=1)

    # Tour Info
    tour_type     = Column(String(80), nullable=True)
    tour_date     = Column(Date, nullable=True)
    tour_time     = Column(String(30), nullable=True)     # self_drive: tour slot time
    checkin_time  = Column(String(30), nullable=True)     # self_drive: check-in time
    tour_location = Column(String(200), nullable=True)    # self_drive: meeting location

    # Bus Tour Pickup
    pickup_time     = Column(String(20), nullable=True)
    pickup_location = Column(String(200), nullable=True)

    # Ops (filled by staff before Morning Reminder)
    driver       = Column(String(100), nullable=True)
    vehicle_no   = Column(String(50), nullable=True)
    driver_phone = Column(String(50), nullable=True)

    # Promotion
    has_promotion = Column(Boolean, default=False)
    promotion_id  = Column(Integer, ForeignKey("promotions.id"), nullable=True)
    mtlv_promo    = Column(String(10), nullable=True)     # "YES" / "Eligible" / null from Excel

    # MTLV (Madame Tussauds) — Eligible flow
    mtlv_eligible          = Column(Boolean, default=False)   # True when mtlv_promo == "Eligible"
    mtlv_qty               = Column(Integer, nullable=True)   # Guest-selected qty (null = not replied)
    mtlv_ticket_status     = Column(String(20), nullable=True)  # null / "pending_send" / "sent"
    mtlv_ticket_sent_by    = Column(String(100), nullable=True)  # display name of staff who sent
    mtlv_ticket_sent_at    = Column(DateTime, nullable=True)     # timestamp when sent

    # Lunch (bus_tour with lunch)
    lunch_turkey = Column(Integer, default=0)
    lunch_veggie = Column(Integer, default=0)
    lunch_beef   = Column(Integer, default=0)

    # Notes
    special_requirements = Column(Text, nullable=True)   # from Rezdy / Excel
    notes                = Column(Text, nullable=True)
    notes_history        = Column(Text, nullable=True)

    # Agent
    agent_name = Column(String(200), nullable=True)

    # Guest Confirmation
    confirmation     = Column(String(20), default="pending")
    reschedule_notes = Column(Text, nullable=True)
    submitted_at     = Column(DateTime, nullable=True)
    submission_count = Column(Integer, default=0)
    token_created    = Column(DateTime, nullable=True)

    # Send Status
    email_sent_at = Column(DateTime, nullable=True)
    email_status  = Column(String(200), default="")
    sms_sent_at   = Column(DateTime, nullable=True)
    sms_status    = Column(String(200), default="")

    # Take Action
    action_taken_by = Column(String(100), nullable=True)
    action_taken_at = Column(DateTime, nullable=True)
    notes_handler      = Column(String(100), nullable=True)
    notes_handled_at   = Column(DateTime(timezone=True), nullable=True)
    notes_action_taken = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    tickets           = relationship("BookingTicket", back_populates="booking")
    notification_logs = relationship("NotificationLog", back_populates="booking")
    promotion_rel     = relationship("Promotion", foreign_keys=[promotion_id])
    booking_notes     = relationship("BookingNote", back_populates="booking", cascade="all, delete-orphan", order_by="BookingNote.created_at")

    @property
    def guest_full_name(self):
        return f"{self.first_name} {self.last_name}".strip()


# ─── Dismissed Bookings ───────────────────────────────────────────────────────

class DismissedBooking(Base):
    """
    Records bookings dismissed from Action Required list.
    The booking row itself is NOT deleted — this is an audit trail.
    """
    __tablename__ = "dismissed_bookings"

    id           = Column(Integer, primary_key=True, index=True)
    booking_id   = Column(Integer, ForeignKey("bookings.id"), nullable=False,
                          unique=True, index=True)
    dismissed_by = Column(String(64), nullable=False, default="")
    reason       = Column(Text, nullable=True)
    dismissed_at = Column(DateTime, server_default=func.now())

    booking = relationship("Booking")


# ─── Settings ─────────────────────────────────────────────────────────────────

class Setting(Base):
    """Key-value store for ops configuration."""
    __tablename__ = "settings"

    id         = Column(Integer, primary_key=True, index=True)
    key        = Column(String(100), unique=True, nullable=False)
    value      = Column(Text, nullable=False, default="")
    label      = Column(String(200), nullable=False, default="")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


# ─── Booking Tickets ──────────────────────────────────────────────────────────

class BookingTicket(Base):
    """One PDF ticket per row. Auto-assigned by Quantities order on upload."""
    __tablename__ = "booking_tickets"

    id             = Column(Integer, primary_key=True, index=True)
    booking_id     = Column(Integer, ForeignKey("bookings.id"), nullable=False, index=True)
    promotion_id   = Column(Integer, ForeignKey("promotions.id"), nullable=False)

    batch_order_id = Column(String(50), nullable=False)   # "631251973" from filename
    ticket_index   = Column(Integer, nullable=False)       # [n] from filename
    filename       = Column(String(300), nullable=False)
    pdf_data       = Column(LargeBinary, nullable=False)

    created_at = Column(DateTime, server_default=func.now())

    booking   = relationship("Booking", back_populates="tickets")
    promotion = relationship("Promotion", back_populates="tickets")


# ─── Email Queue ──────────────────────────────────────────────────────────────

class EmailQueue(Base):
    """Scheduled send queue, processed every 5 minutes."""
    __tablename__ = "email_queue"

    id         = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=True)

    notification_type = Column(String(30), nullable=False)
    channel           = Column(String(10), nullable=False)

    scheduled_at = Column(DateTime, nullable=False, index=True)
    sent_at      = Column(DateTime, nullable=True)

    to_email = Column(String(200), nullable=True)
    to_phone = Column(String(50), nullable=True)
    to_name  = Column(String(200), nullable=True)

    subject  = Column(Text, nullable=True)
    body     = Column(Text, nullable=True)
    sms_body = Column(Text, nullable=True)

    status    = Column(String(20), default="pending", index=True)
    error_msg = Column(Text, nullable=True)
    attempts  = Column(SmallInteger, default=0)

    created_at = Column(DateTime, server_default=func.now())

    booking = relationship("Booking")


# ─── Notification Logs ────────────────────────────────────────────────────────

class NotificationLog(Base):
    __tablename__ = "notification_logs"

    id                = Column(Integer, primary_key=True, index=True)
    booking_id        = Column(Integer, ForeignKey("bookings.id"), nullable=True)
    notification_type = Column(String(30), nullable=False)
    channel           = Column(String(10), nullable=False)
    status            = Column(String(20), default=NotificationStatus.pending.value)
    recipient         = Column(String(256), nullable=True)
    external_id       = Column(String(256), nullable=True)
    error_message     = Column(Text, nullable=True)
    sent_at           = Column(DateTime, nullable=True)
    created_at        = Column(DateTime, server_default=func.now())

    booking = relationship("Booking", back_populates="notification_logs")


# ─── Admin Users ──────────────────────────────────────────────────────────────

class AdminUser(Base):
    __tablename__ = "admin_users"

    id              = Column(Integer, primary_key=True, index=True)
    username        = Column(String(64), unique=True, index=True)
    display_name    = Column(String(100), nullable=True)
    email           = Column(String(256), unique=True)
    hashed_password = Column(String(256))
    is_active       = Column(Boolean, default=True)
    role            = Column(String(20), nullable=False, default="staff")
    created_at      = Column(DateTime, server_default=func.now())

    # ── Invite fields (migrate_v9) ────────────────────────────────────────────
    invite_token    = Column(String(64),  nullable=True,  default=None)
    invite_used     = Column(Boolean,     nullable=False,  default=True)
    created_by      = Column(String(50),  nullable=True,  default=None)
    initials        = Column(String(10),  nullable=False,  default="")


# ─── Activity Log ─────────────────────────────────────────────────────────────

class ActivityLog(Base):
    __tablename__ = "activity_log"

    id           = Column(Integer, primary_key=True, index=True)
    order_number = Column(String(50), nullable=False, index=True)
    event_type   = Column(String(50), nullable=False)
    detail       = Column(Text, nullable=True)
    actor        = Column(String(100), nullable=True)
    actor_type   = Column(String(20), nullable=True)  # 'staff' / 'guest' / 'system'
    created_at   = Column(DateTime, server_default=func.now(), index=True)

# ─── Teams ────────────────────────────────────────────────────────────────────

class Team(Base):
    __tablename__ = "teams"

    id         = Column(Integer, primary_key=True, index=True)
    name       = Column(String(100), nullable=False)
    color      = Column(String(20),  nullable=False, default="#4285F4")
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


# ─── User-Team (many-to-many) ──────────────────────────────────────────────────

class UserTeam(Base):
    __tablename__ = "user_teams"

    user_id = Column(Integer, ForeignKey("admin_users.id", ondelete="CASCADE"), primary_key=True)
    team_id = Column(Integer, ForeignKey("teams.id",       ondelete="CASCADE"), primary_key=True)


# ─── Messages (team board) ─────────────────────────────────────────────────────

class Message(Base):
    __tablename__ = "messages"

    id         = Column(Integer, primary_key=True, index=True)
    author_id  = Column(Integer, ForeignKey("admin_users.id", ondelete="SET NULL"), nullable=True)
    team_id    = Column(Integer, ForeignKey("teams.id",       ondelete="SET NULL"), nullable=True)
    text       = Column(Text,    nullable=False)
    source     = Column(String(20), nullable=False, default="manual")   # manual | guest_note | staff_note
    booking_id = Column(Integer, ForeignKey("bookings.id",    ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), index=True)


# ─── Message Reads ─────────────────────────────────────────────────────────────

class MessageRead(Base):
    __tablename__ = "message_reads"

    user_id    = Column(Integer, ForeignKey("admin_users.id", ondelete="CASCADE"), primary_key=True)
    message_id = Column(Integer, ForeignKey("messages.id",    ondelete="CASCADE"), primary_key=True)
    read_at    = Column(DateTime, server_default=func.now())


# ── BookingNote ───────────────────────────────────────────────────────────────
class BookingNote(Base):
    __tablename__ = "booking_notes"

    id              = Column(Integer, primary_key=True, index=True)
    booking_id      = Column(Integer, ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False, index=True)
    author_username = Column(String(100), nullable=False)
    direction       = Column(String(20), nullable=False, default="staff_note")
    # 'staff_note' | 'sms_out' | 'email_out' | 'guest_reply'
    body            = Column(Text, nullable=False)
    sms_status      = Column(String(20), nullable=True)    # 'sent' | 'failed' | None
    email_status    = Column(String(20), nullable=True)    # 'sent' | 'failed' | None
    created_at      = Column(DateTime(timezone=True), nullable=False, default=_now_la)
    booking         = relationship("Booking", back_populates="booking_notes")


# ── BroadcastLog ─────────────────────────────────────────────────────────────
class BroadcastLog(Base):
    __tablename__ = "broadcast_log"

    id               = Column(Integer, primary_key=True, index=True)
    sent_by          = Column(String(100), nullable=False)
    module           = Column(String(30), nullable=False)   # 'tour' | 'morning' | 'tickets'
    group_filter     = Column(String(20), nullable=False)   # 'general' | 'mtlv'
    status_filter    = Column(String(20), nullable=False)   # 'all' | 'pending' | 'yes' | 'modify'
    tour_date        = Column(Date, nullable=False)
    template_name    = Column(String(100), nullable=True)
    message_body     = Column(Text, nullable=False)
    recipient_count  = Column(Integer, nullable=False, default=0)
    sms_sent         = Column(Integer, nullable=False, default=0)
    sms_failed       = Column(Integer, nullable=False, default=0)
    email_sent       = Column(Integer, nullable=False, default=0)
    email_failed     = Column(Integer, nullable=False, default=0)
    created_at       = Column(DateTime(timezone=True), nullable=False, default=_now_la)

    recipients       = relationship("BroadcastRecipient", back_populates="broadcast", cascade="all, delete-orphan")


# ── BroadcastRecipient ────────────────────────────────────────────────────────
class BroadcastRecipient(Base):
    __tablename__ = "broadcast_recipients"

    id              = Column(Integer, primary_key=True, index=True)
    broadcast_id    = Column(Integer, ForeignKey("broadcast_log.id", ondelete="CASCADE"), nullable=False, index=True)
    order_number    = Column(String(50), nullable=True)
    customer_name   = Column(String(200), nullable=True)
    phone           = Column(String(30), nullable=True)
    email           = Column(String(200), nullable=True)
    sms_status      = Column(String(20), nullable=True)   # 'sent' | 'failed' | 'skipped'
    email_status    = Column(String(20), nullable=True)
    created_at      = Column(DateTime(timezone=True), nullable=False, default=_now_la)

    broadcast       = relationship("BroadcastLog", back_populates="recipients")


