"""
app/services/tour_config.py
Tour types config — ported from PHP npe_tconf_tour_types()
Used by sendgrid.py, guest.py
"""

TOUR_TYPES: dict[str, dict] = {
    "upper_antelope": {
        "label": "Upper Antelope Canyon Bus Tour",
        "has_lunch": True, "has_beef": True, "has_park_fee": False,
        "booking_type": "bus_tour",
        "extra_reminders": [
            "To reduce dropoff time, tour will only drop off at: <strong>TREASURE ISLAND, PARK MGM, or EXCALIBUR</strong>. Subject to change due to road closures."
        ],
    },
    "lower_antelope": {
        "label": "Lower Antelope Canyon Bus Tour",
        "has_lunch": True, "has_beef": True, "has_park_fee": False,
        "booking_type": "bus_tour",
        "extra_reminders": [
            "To reduce dropoff time, tour will only drop off at: <strong>TREASURE ISLAND, PARK MGM, or EXCALIBUR</strong>. Subject to change due to road closures."
        ],
    },
    "antelope_x": {
        "label": "Antelope Canyon X Bus Tour",
        "has_lunch": True, "has_beef": True, "has_park_fee": False,
        "booking_type": "bus_tour",
        "extra_reminders": [
            "To reduce dropoff time, tour will only drop off at: <strong>TREASURE ISLAND, PARK MGM, or EXCALIBUR</strong>. Subject to change due to road closures."
        ],
    },
    "grand_canyon_south": {
        "label": "Grand Canyon South Rim Bus Tour",
        "has_lunch": True, "has_beef": False, "has_park_fee": True,
        "booking_type": "bus_tour",
        "extra_reminders": [
            "To reduce dropoff time, tour will only drop off at: <strong>TREASURE ISLAND, PARK MGM, or EXCALIBUR</strong>. Subject to change due to road closures.",
            'For your return trip, please meet in front of <a href="https://nationalparkexpress.com/grand-canyon-south-rim-pickup/">Bright Angel Lodge</a>.',
        ],
    },
    "grand_canyon_west": {
        "label": "Grand Canyon West Rim Bus Tour",
        "has_lunch": False, "has_beef": False, "has_park_fee": False,
        "booking_type": "bus_tour",
        "extra_reminders": [],
    },
    "bryce_zion": {
        "label": "Bryce Canyon & Zion National Park Bus Tour",
        "has_lunch": True, "has_beef": False, "has_park_fee": True,
        "booking_type": "bus_tour",
        "extra_reminders": [
            "To reduce dropoff time, tour will only drop off at: <strong>TREASURE ISLAND, PARK MGM, or EXCALIBUR</strong>. Subject to change due to road closures."
        ],
    },
    "valley_of_fire_full": {
        "label": "Valley of Fire Tour (Full Day)",
        "has_lunch": True, "has_beef": False, "has_park_fee": False,
        "booking_type": "bus_tour",
        "extra_reminders": [],
    },
    "valley_of_fire_half": {
        "label": "Valley of Fire Tour (Half Day)",
        "has_lunch": False, "has_beef": False, "has_park_fee": False,
        "booking_type": "bus_tour",
        "extra_reminders": [],
    },
    "hoover_dam": {
        "label": "Hoover Dam Tour",
        "has_lunch": False, "has_beef": False, "has_park_fee": False,
        "booking_type": "bus_tour",
        "extra_reminders": [],
    },
    # ── Self-drive / Ticket tours ─────────────────────────────────────────────
    "upper_antelope_self": {
        "label": "Upper Antelope Canyon (Self-Drive)",
        "has_lunch": False, "has_beef": False, "has_park_fee": False,
        "booking_type": "self_drive",
        "extra_reminders": [],
    },
    "lower_antelope_self": {
        "label": "Lower Antelope Canyon (Self-Drive)",
        "has_lunch": False, "has_beef": False, "has_park_fee": False,
        "booking_type": "self_drive",
        "extra_reminders": [],
    },
    "antelope_x_self": {
        "label": "Antelope Canyon X (Self-Drive)",
        "has_lunch": False, "has_beef": False, "has_park_fee": False,
        "booking_type": "self_drive",
        "extra_reminders": [],
    },
}
