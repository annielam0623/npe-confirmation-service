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

from app.database import Base


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


# ─── Bookings ─────────────────────────────────────────────────────────────────

class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)

    # Type & Source
    booking_type = Column(Enum(BookingType), nullable=False, default=BookingType.bus_tour)
    source       = Column(Enum(BookingSource), default=BookingSource.manual)
    status       = Column(Enum(BookingStatus), default=BookingStatus.pending)

    # Identifiers
    confirm_token   = Column(String(64), unique=True, index=True,
                             default=lambda: secrets.token_urlsafe(32))
    order_number    = Column(String(50), index=True, nullable=False)
    rezdy_order_id  = Column(String(128), nullable=True, index=True)
    confirmation_no = Column(String(100), nullable=True)   # self_drive attraction confirmation#

    # Guest Info
    first_name     = Column(String(100), nullable=False)
    last_name      = Column(String(100), nullable=False, default="")
    customer_email = Column(String(200), nullable=False)
    phone          = Column(String(50), nullable=True)
    quantities     = Column(Integer, default=1)

    # Tour Info
    tour_type    = Column(String(80), nullable=True)
    tour_date    = Column(Date, nullable=True)
    tour_time    = Column(String(30), nullable=True)      # self_drive: tour slot time
    checkin_time = Column(String(30), nullable=True)      # self_drive: check-in time
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
    mtlv_promo    = Column(String(10), nullable=True)     # "YES" or null from Excel

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

    # Timestamps
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    tickets           = relationship("BookingTicket", back_populates="booking")
    notification_logs = relationship("NotificationLog", back_populates="booking")
    promotion_rel     = relationship("Promotion", foreign_keys=[promotion_id])

    @property
    def guest_full_name(self):
        return f"{self.first_name} {self.last_name}".strip()


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

    notification_type = Column(Enum(NotificationType), nullable=False)
    channel           = Column(Enum(NotificationChannel), nullable=False)

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
    notification_type = Column(Enum(NotificationType), nullable=False)
    channel           = Column(Enum(NotificationChannel), nullable=False)
    status            = Column(Enum(NotificationStatus), default=NotificationStatus.pending)
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
    email           = Column(String(256), unique=True)
    hashed_password = Column(String(256))
    is_active       = Column(Boolean, default=True)
    created_at      = Column(DateTime, server_default=func.now())
