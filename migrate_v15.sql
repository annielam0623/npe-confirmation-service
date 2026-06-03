-- migrate_v15.sql
-- Template Copy: seed all editable text defaults into settings table
-- key format:  tmpl__{scope}__{field}
--   scope = 'global' for shared text, or '{module}__{tour_type}' for per-product text
--   module: tc = Tour Confirmation, tix = Tickets Reminder, mp = Morning Pickup

-- ─────────────────────────────────────────────────────────────────────────────
-- GLOBAL — shared across all modules / pages
-- ─────────────────────────────────────────────────────────────────────────────

INSERT INTO settings (key, value, label) VALUES

-- Guest confirmation page: global blocks
('tmpl__global__guest_sms_notice',
 'You will receive a morning reminder SMS with check-in link and real-time vehicle tracking on the day of your tour.',
 '[Guest Page] Morning SMS notice (📱 row)'),

('tmpl__global__guest_depart_warning',
 '* Departs promptly — vehicle cannot wait for late arrivals.',
 '[Guest Page] Departure warning (red text)'),

('tmpl__global__guest_phone_confirm',
 'To ensure a smooth pick-up process, check-in and Bus Track information will be sent to your mobile phone prior to departure.\nPlease confirm that the following phone number is correct: {phone}\nIf this number is incorrect, kindly provide the correct number in the Notes section below.',
 '[Guest Page] Phone confirmation box (blue box) — use {phone} as placeholder'),

('tmpl__global__guest_confirm_instructions',
 'Confirm Your Tour|Click YES to confirm, then select lunch and click Submit Confirmation.\nRequest a Date Change|If you would like to change your tour date, click Modify — you do not need to click YES first. Choose your preferred new date and click Submit Confirmation. Our reservations team will contact you as soon as possible to confirm availability.\nImportant|Your reservation is only finalized after you click Submit Confirmation.',
 '[Guest Page] Confirm/Modify instructions (deep blue box) — format: Title|Body per line'),

('tmpl__global__guest_thanks_text',
 'Your confirmation has been received. We look forward to seeing you on your tour!',
 '[Guest Page] Thank you page body text'),

('tmpl__global__guest_expired_text',
 'This confirmation link has expired or is invalid. Please contact us at reservations@nationalparkexpress.com or call 702-948-4190.',
 '[Guest Page] Expired link page text'),

-- Tour Confirmation email: global
('tmpl__global__tc_email_greeting',
 'Greetings from National Park Express!',
 '[TC Email] Opening greeting line'),

('tmpl__global__tc_email_intro',
 'As your local tour operator for the {label}, we''re excited to welcome you on {date}.',
 '[TC Email] Intro line — use {label} for tour name, {date} for tour date'),

('tmpl__global__tc_email_review',
 'Please review your tour details below and reconfirm your participation so we can ensure everything is ready for your visit.',
 '[TC Email] Review/reconfirm line'),

('tmpl__global__tc_email_closing',
 'Thank you for choosing National Park Express. We are honored to be part of your adventure and are committed to making your experience smooth, enjoyable and filled with lasting memories.',
 '[TC Email] Closing paragraph'),

('tmpl__global__tc_email_link_expiry',
 'Link expires at 6:00 PM PST the day before your tour',
 '[TC Email] Link expiry notice (below CTA button)'),

('tmpl__global__tc_email_footer_contact',
 'Questions? We''re here to help!\n+1 (702) 948-4190 | reservations@nationalparkexpress.com\nnationalparkexpress.com',
 '[TC Email] Footer contact block'),

-- Tour Confirmation SMS: global template
('tmpl__global__tc_sms_with_lunch',
 'Hi {name}, This is National Park Express, your local tour operator for {label} on {date}. Please reconfirm your tour and select your lunch option here: {url}. Thank you',
 '[TC SMS] SMS body for tours WITH lunch — variables: {name} {label} {date} {url}'),

('tmpl__global__tc_sms_no_lunch',
 'Hi {name}, This is National Park Express, your local tour operator for {label} on {date}. Please reconfirm your tour here: {url}. Thank you',
 '[TC SMS] SMS body for tours WITHOUT lunch — variables: {name} {label} {date} {url}'),

-- Tickets Reminder email: global
('tmpl__global__tix_email_intro',
 'This is a reminder for your upcoming Antelope Canyon tour. Please reconfirm your attendance using the button below.',
 '[Tickets Email] Intro paragraph'),

('tmpl__global__tix_email_warning',
 '★ Late check-in is subject to forfeiting your tour entry.\n★ All times are based on the Arizona (AZ) time zone.',
 '[Tickets Email] Warning box (red box, one item per line)'),

('tmpl__global__tix_email_cta_desc',
 'Please click the "Reconfirm My Tour & Continue" button below to review important information about your tour. This may include the check-in procedure, supplier rules, age requirements, local regulations, and other important notes to help you prepare for your trip.',
 '[Tickets Email] Paragraph above CTA button'),

('tmpl__global__tix_email_link_expiry',
 'Link expires the day after your tour',
 '[Tickets Email] Link expiry notice (below CTA button)'),

('tmpl__global__tix_email_footer',
 'National Park Express — Thank you for choosing us! 🏞️',
 '[Tickets Email] Footer text'),

-- Morning Pickup SMS: global
('tmpl__global__mp_sms_body',
 'Good morning, {name}.\nThis is a reminder that your pickup time for today''s tour is {pickup_time}.\nPlease use the link below to check in when you arrive at your pickup location and to track your vehicle in real time:\n{url}\nIf you need assistance, please call {phone}.',
 '[Morning SMS] Full SMS body — variables: {name} {pickup_time} {url} {phone}'),

-- Morning Pickup email: global
('tmpl__global__mp_email_body',
 'This is a reminder that your pickup time for today''s tour is {pickup_time}.\nPlease use the link below to check in when you arrive at your pickup location and to track your vehicle in real time:',
 '[Morning Email] Body paragraphs — variables: {pickup_time}'),

('tmpl__global__mp_email_cta',
 'Check In & Track Vehicle',
 '[Morning Email] CTA button text'),

('tmpl__global__mp_email_footer',
 'National Park Express — Have a great tour! 🏞️',
 '[Morning Email] Footer text')

ON CONFLICT (key) DO NOTHING;


-- ─────────────────────────────────────────────────────────────────────────────
-- PER TOUR TYPE — Tour Confirmation (tc)
-- ─────────────────────────────────────────────────────────────────────────────

INSERT INTO settings (key, value, label) VALUES

-- upper_antelope
('tmpl__tc__upper_antelope__reminders',
 'Please dress appropriately for the weather and stay hydrated throughout your tour.\nAll vehicles are air-conditioned. During periods of extreme heat, it may take a few minutes for the vehicle to cool down after boarding. You are welcome to bring small personal comfort items, such as handheld fans, cooling towels, or ice packs.\nTo help ensure a pleasant experience for everyone on board, we kindly ask guests to refrain from wearing strong fragrances, including perfumes, colognes, and heavily scented products.\nIf you have any special needs or concerns, please contact us prior to your tour so we can better assist you.',
 '[TC Guest Page] Important Reminders — Upper Antelope Canyon Bus Tour (one item per line)'),

('tmpl__tc__upper_antelope__extra_reminders',
 'To reduce dropoff time, tour will only drop off at: TREASURE ISLAND, PARK MGM, or EXCALIBUR. Subject to change due to road closures.',
 '[TC Guest Page] Extra reminders — Upper Antelope Canyon (one item per line)'),

-- lower_antelope
('tmpl__tc__lower_antelope__reminders',
 'Please dress appropriately for the weather and stay hydrated throughout your tour.\nAll vehicles are air-conditioned. During periods of extreme heat, it may take a few minutes for the vehicle to cool down after boarding. You are welcome to bring small personal comfort items, such as handheld fans, cooling towels, or ice packs.\nTo help ensure a pleasant experience for everyone on board, we kindly ask guests to refrain from wearing strong fragrances, including perfumes, colognes, and heavily scented products.\nIf you have any special needs or concerns, please contact us prior to your tour so we can better assist you.',
 '[TC Guest Page] Important Reminders — Lower Antelope Canyon Bus Tour (one item per line)'),

('tmpl__tc__lower_antelope__extra_reminders',
 'To reduce dropoff time, tour will only drop off at: TREASURE ISLAND, PARK MGM, or EXCALIBUR. Subject to change due to road closures.',
 '[TC Guest Page] Extra reminders — Lower Antelope Canyon (one item per line)'),

-- antelop_X
('tmpl__tc__antelop_X__reminders',
 'Please dress appropriately for the weather and stay hydrated throughout your tour.\nAll vehicles are air-conditioned. During periods of extreme heat, it may take a few minutes for the vehicle to cool down after boarding. You are welcome to bring small personal comfort items, such as handheld fans, cooling towels, or ice packs.\nTo help ensure a pleasant experience for everyone on board, we kindly ask guests to refrain from wearing strong fragrances, including perfumes, colognes, and heavily scented products.\nIf you have any special needs or concerns, please contact us prior to your tour so we can better assist you.',
 '[TC Guest Page] Important Reminders — Antelope Canyon X Bus Tour (one item per line)'),

('tmpl__tc__antelop_X__extra_reminders',
 'To reduce dropoff time, tour will only drop off at: TREASURE ISLAND, PARK MGM, or EXCALIBUR. Subject to change due to road closures.',
 '[TC Guest Page] Extra reminders — Antelope Canyon X (one item per line)'),

-- grand_canyon_south
('tmpl__tc__grand_canyon_south__reminders',
 'Please dress appropriately for the weather and stay hydrated throughout your tour.\nAll vehicles are air-conditioned. During periods of extreme heat, it may take a few minutes for the vehicle to cool down after boarding. You are welcome to bring small personal comfort items, such as handheld fans, cooling towels, or ice packs.\nTo help ensure a pleasant experience for everyone on board, we kindly ask guests to refrain from wearing strong fragrances, including perfumes, colognes, and heavily scented products.\nIf you have any special needs or concerns, please contact us prior to your tour so we can better assist you.',
 '[TC Guest Page] Important Reminders — Grand Canyon South Rim Bus Tour (one item per line)'),

('tmpl__tc__grand_canyon_south__extra_reminders',
 'To reduce dropoff time, tour will only drop off at: TREASURE ISLAND, PARK MGM, or EXCALIBUR. Subject to change due to road closures.\nFor your return trip, please meet in front of Bright Angel Lodge.',
 '[TC Guest Page] Extra reminders — Grand Canyon South Rim (one item per line)'),

('tmpl__tc__grand_canyon_south__park_fee_nonresident',
 'Non-U.S. Residents fee (ages 16+): $100/person or $250 America the Beautiful Annual Pass (up to 4 people).',
 '[TC Guest Page + Email] Park fee — non-US residents (Grand Canyon South)'),

('tmpl__tc__grand_canyon_south__park_fee_resident',
 'Legal U.S. residents: Present valid government-issued ID to waive the $100 fee.',
 '[TC Guest Page + Email] Park fee — US residents (Grand Canyon South)'),

-- grand_canyon_west
('tmpl__tc__grand_canyon_west__reminders',
 'Please dress appropriately for the weather and stay hydrated throughout your tour.\nAll vehicles are air-conditioned. During periods of extreme heat, it may take a few minutes for the vehicle to cool down after boarding. You are welcome to bring small personal comfort items, such as handheld fans, cooling towels, or ice packs.\nTo help ensure a pleasant experience for everyone on board, we kindly ask guests to refrain from wearing strong fragrances, including perfumes, colognes, and heavily scented products.\nIf you have any special needs or concerns, please contact us prior to your tour so we can better assist you.',
 '[TC Guest Page] Important Reminders — Grand Canyon West Rim Bus Tour (one item per line)'),

('tmpl__tc__grand_canyon_west__extra_reminders',
 '',
 '[TC Guest Page] Extra reminders — Grand Canyon West Rim (one item per line)'),

-- bryce_zion
('tmpl__tc__bryce_zion__reminders',
 'Please dress appropriately for the weather and stay hydrated throughout your tour.\nAll vehicles are air-conditioned. During periods of extreme heat, it may take a few minutes for the vehicle to cool down after boarding. You are welcome to bring small personal comfort items, such as handheld fans, cooling towels, or ice packs.\nTo help ensure a pleasant experience for everyone on board, we kindly ask guests to refrain from wearing strong fragrances, including perfumes, colognes, and heavily scented products.\nIf you have any special needs or concerns, please contact us prior to your tour so we can better assist you.',
 '[TC Guest Page] Important Reminders — Bryce Canyon & Zion Bus Tour (one item per line)'),

('tmpl__tc__bryce_zion__extra_reminders',
 'To reduce dropoff time, tour will only drop off at: TREASURE ISLAND, PARK MGM, or EXCALIBUR. Subject to change due to road closures.',
 '[TC Guest Page] Extra reminders — Bryce Canyon & Zion (one item per line)'),

('tmpl__tc__bryce_zion__park_fee_nonresident',
 'Non-U.S. Residents fee (ages 16+): $100/person or $250 America the Beautiful Annual Pass (up to 4 people).',
 '[TC Guest Page + Email] Park fee — non-US residents (Bryce & Zion)'),

('tmpl__tc__bryce_zion__park_fee_resident',
 'Legal U.S. residents: Present valid government-issued ID to waive the $100 fee.',
 '[TC Guest Page + Email] Park fee — US residents (Bryce & Zion)'),

-- valley_of_fire_full
('tmpl__tc__valley_of_fire_full__reminders',
 'Please dress appropriately for the weather and stay hydrated throughout your tour.\nAll vehicles are air-conditioned. During periods of extreme heat, it may take a few minutes for the vehicle to cool down after boarding. You are welcome to bring small personal comfort items, such as handheld fans, cooling towels, or ice packs.\nTo help ensure a pleasant experience for everyone on board, we kindly ask guests to refrain from wearing strong fragrances, including perfumes, colognes, and heavily scented products.\nIf you have any special needs or concerns, please contact us prior to your tour so we can better assist you.',
 '[TC Guest Page] Important Reminders — Valley of Fire Full Day (one item per line)'),

('tmpl__tc__valley_of_fire_full__extra_reminders',
 '',
 '[TC Guest Page] Extra reminders — Valley of Fire Full Day (one item per line)'),

-- valley_of_fire_half
('tmpl__tc__valley_of_fire_half__reminders',
 'Please dress appropriately for the weather and stay hydrated throughout your tour.\nAll vehicles are air-conditioned. During periods of extreme heat, it may take a few minutes for the vehicle to cool down after boarding. You are welcome to bring small personal comfort items, such as handheld fans, cooling towels, or ice packs.\nTo help ensure a pleasant experience for everyone on board, we kindly ask guests to refrain from wearing strong fragrances, including perfumes, colognes, and heavily scented products.\nIf you have any special needs or concerns, please contact us prior to your tour so we can better assist you.',
 '[TC Guest Page] Important Reminders — Valley of Fire Half Day (one item per line)'),

('tmpl__tc__valley_of_fire_half__extra_reminders',
 '',
 '[TC Guest Page] Extra reminders — Valley of Fire Half Day (one item per line)'),

-- hoover_dam
('tmpl__tc__hoover_dam__reminders',
 'Please dress appropriately for the weather and stay hydrated throughout your tour.\nAll vehicles are air-conditioned. During periods of extreme heat, it may take a few minutes for the vehicle to cool down after boarding. You are welcome to bring small personal comfort items, such as handheld fans, cooling towels, or ice packs.\nTo help ensure a pleasant experience for everyone on board, we kindly ask guests to refrain from wearing strong fragrances, including perfumes, colognes, and heavily scented products.\nIf you have any special needs or concerns, please contact us prior to your tour so we can better assist you.',
 '[TC Guest Page] Important Reminders — Hoover Dam Tour (one item per line)'),

('tmpl__tc__hoover_dam__extra_reminders',
 '',
 '[TC Guest Page] Extra reminders — Hoover Dam Tour (one item per line)')

ON CONFLICT (key) DO NOTHING;


-- ─────────────────────────────────────────────────────────────────────────────
-- PER TOUR TYPE — Tickets Reminder (tix)
-- ─────────────────────────────────────────────────────────────────────────────

INSERT INTO settings (key, value, label) VALUES

('tmpl__tix__upper_antelope_tsosie__extra_notes',
 '★ No children, toddlers or infants (ages 0–5) are permitted due to safety concerns.\nThe general guidelines for visiting Antelope Canyon:\n1. Bottled water is allowed.\n2. No bags are allowed on the walking tour. Please leave all bags in your vehicle.\n3. Phones and standard cameras are allowed.\n4. Tripods, monopods, large camera equipment, and flash/light equipment are generally NOT permitted.\nPlease note that rules may vary slightly depending on the canyon and tour operator. Final instructions will be provided by the guide on site.',
 '[Tickets Guest Page] Notes — Upper Antelope (Chief Tsosie) (one item per line)'),

('tmpl__tix__upper_antelope_brenda__extra_notes',
 'Car seats are required for children under 4. Visitors must provide their own car seat or booster seat.\nThe general guidelines for visiting Antelope Canyon:\n1. Bottled water is allowed.\n2. No bags are allowed on the walking tour. Please leave all bags in your vehicle.\n3. Phones and standard cameras are allowed.\n4. Tripods, monopods, large camera equipment, and flash/light equipment are generally NOT permitted.\nPlease note that rules may vary slightly depending on the canyon and tour operator. Final instructions will be provided by the guide on site.',
 '[Tickets Guest Page] Notes — Upper Antelope (Brenda) (one item per line)'),

('tmpl__tix__upper_antelope_brenda_no_fee__extra_notes',
 'Car seats are required for children under 4. Visitors must provide their own car seat or booster seat.\nThe general guidelines for visiting Antelope Canyon:\n1. Bottled water is allowed.\n2. No bags are allowed on the walking tour. Please leave all bags in your vehicle.\n3. Phones and standard cameras are allowed.\n4. Tripods, monopods, large camera equipment, and flash/light equipment are generally NOT permitted.\nPlease note that rules may vary slightly depending on the canyon and tour operator. Final instructions will be provided by the guide on site.',
 '[Tickets Guest Page] Notes — Upper Antelope (Brenda, no fee) (one item per line)'),

('tmpl__tix__upper_antelope_aact__extra_notes',
 '★ Minimum age 8. Guests must be at least 8 years of age to join the walking tour.\n★ Pregnant guests are not permitted to participate due to safety concerns.\nThe general guidelines for visiting Antelope Canyon:\n1. Bottled water is allowed.\n2. No bags are allowed on the walking tour. Please leave all bags in your vehicle.\n3. Phones and standard cameras are allowed.\n4. Tripods, monopods, large camera equipment, and flash/light equipment are generally NOT permitted.\nPlease note that rules may vary slightly depending on the canyon and tour operator. Final instructions will be provided by the guide on site.',
 '[Tickets Guest Page] Notes — Upper Antelope (AACT) (one item per line)'),

('tmpl__tix__upper_antelope_hogan_transport__extra_notes',
 'Car seats are required for children under 8. Visitors must provide their own car seat.\n★ These entry reservations are non-refundable.\nAntelope Canyon does not allow any bags on the walking tour. Please leave them in your vehicle.\nIf you can''t find the check-in location, call: 928-693-9293',
 '[Tickets Guest Page] Notes — Upper Antelope (Hogan with Transport) (one item per line)'),

('tmpl__tix__upper_antelope_hogan_hiking__extra_notes',
 '★ Minimum age 8. Guests must be at least 8 years of age to join the hiking tour.\n★ Pregnant guests are not permitted to participate due to safety concerns.\n★ These entry reservations are non-refundable.\nPrepare for a 2-mile round-trip hike. Bring plenty of water.\nThe general guidelines for visiting Antelope Canyon:\n1. Bottled water is allowed.\n2. No bags are allowed on the walking tour. Please leave all bags in your vehicle.\n3. Phones and standard cameras are allowed.\n4. Tripods, monopods, large camera equipment, and flash/light equipment are generally NOT permitted.\nIf you can''t find the check-in location, call: 928-693-9293',
 '[Tickets Guest Page] Notes — Upper Antelope (Hogan Hiking) (one item per line)'),

('tmpl__tix__lower_antelope_kens__extra_notes',
 '★ These entry reservations are non-refundable.\nThe general guidelines for visiting Antelope Canyon:\n1. Bottled water is allowed.\n2. No bags are allowed on the walking tour. Please leave all bags in your vehicle.\n3. Phones and standard cameras are allowed.\n4. Tripods, monopods, large camera equipment, and flash/light equipment are generally NOT permitted.\nPlease note that rules may vary slightly depending on the canyon and tour operator. Final instructions will be provided by the guide on site.',
 '[Tickets Guest Page] Notes — Lower Antelope (Ken''s Tours) (one item per line)'),

('tmpl__tix__lower_antelope_dixie__extra_notes',
 'The general guidelines for visiting Antelope Canyon:\n1. Bottled water is allowed.\n2. No bags are allowed on the walking tour. Please leave all bags in your vehicle.\n3. Phones and standard cameras are allowed.\n4. Tripods, monopods, large camera equipment, and flash/light equipment are generally NOT permitted.\nPlease note that rules may vary slightly depending on the canyon and tour operator. Final instructions will be provided by the guide on site.',
 '[Tickets Guest Page] Notes — Lower Antelope (Dixie''s Tours) (one item per line)'),

('tmpl__tix__canyon_x__extra_notes',
 'The general guidelines for visiting Antelope Canyon:\n1. Bottled water is allowed.\n2. No bags are allowed on the walking tour. Please leave all bags in your vehicle.\n3. Phones and standard cameras are allowed.\n4. Tripods, monopods, large camera equipment, and flash/light equipment are generally NOT permitted.\nPlease note that rules may vary slightly depending on the canyon and tour operator. Final instructions will be provided by the guide on site.',
 '[Tickets Guest Page] Notes — Canyon X (one item per line)')

ON CONFLICT (key) DO NOTHING;

-- Fix: convert literal \n to real newlines in all template values
UPDATE settings
SET value = replace(value, '\n', chr(10))
WHERE key LIKE 'tmpl__%'
  AND value LIKE '%\n%';

-- ─────────────────────────────────────────────────────────────────────────────
-- PER TOUR TYPE — Tickets Reminder (tix)
-- ─────────────────────────────────────────────────────────────────────────────

INSERT INTO settings (key, value, label) VALUES

('tmpl__tix__upper_antelope_tsosie__extra_notes',
 '★ No children, toddlers or infants (ages 0–5) are permitted due to safety concerns.\nThe general guidelines for visiting Antelope Canyon:\n1. Bottled water is allowed.\n2. No bags are allowed on the walking tour. Please leave all bags in your vehicle.\n3. Phones and standard cameras are allowed.\n4. Tripods, monopods, large camera equipment, and flash/light equipment are generally NOT permitted.\nPlease note that rules may vary slightly depending on the canyon and tour operator. Final instructions will be provided by the guide on site.',
 '[Tickets Guest Page] Notes — Upper Antelope (Chief Tsosie) (one item per line)'),

('tmpl__tix__upper_antelope_brenda__extra_notes',
 'Car seats are required for children under 4. Visitors must provide their own car seat or booster seat.\nThe general guidelines for visiting Antelope Canyon:\n1. Bottled water is allowed.\n2. No bags are allowed on the walking tour. Please leave all bags in your vehicle.\n3. Phones and standard cameras are allowed.\n4. Tripods, monopods, large camera equipment, and flash/light equipment are generally NOT permitted.\nPlease note that rules may vary slightly depending on the canyon and tour operator. Final instructions will be provided by the guide on site.',
 '[Tickets Guest Page] Notes — Upper Antelope (Brenda) (one item per line)'),

('tmpl__tix__upper_antelope_brenda_no_fee__extra_notes',
 'Car seats are required for children under 4. Visitors must provide their own car seat or booster seat.\nThe general guidelines for visiting Antelope Canyon:\n1. Bottled water is allowed.\n2. No bags are allowed on the walking tour. Please leave all bags in your vehicle.\n3. Phones and standard cameras are allowed.\n4. Tripods, monopods, large camera equipment, and flash/light equipment are generally NOT permitted.\nPlease note that rules may vary slightly depending on the canyon and tour operator. Final instructions will be provided by the guide on site.',
 '[Tickets Guest Page] Notes — Upper Antelope (Brenda, no fee) (one item per line)'),

('tmpl__tix__upper_antelope_aact__extra_notes',
 '★ Minimum age 8. Guests must be at least 8 years of age to join the walking tour.\n★ Pregnant guests are not permitted to participate due to safety concerns.\nThe general guidelines for visiting Antelope Canyon:\n1. Bottled water is allowed.\n2. No bags are allowed on the walking tour. Please leave all bags in your vehicle.\n3. Phones and standard cameras are allowed.\n4. Tripods, monopods, large camera equipment, and flash/light equipment are generally NOT permitted.\nPlease note that rules may vary slightly depending on the canyon and tour operator. Final instructions will be provided by the guide on site.',
 '[Tickets Guest Page] Notes — Upper Antelope (AACT) (one item per line)'),

('tmpl__tix__upper_antelope_hogan_transport__extra_notes',
 'Car seats are required for children under 8. Visitors must provide their own car seat.\n★ These entry reservations are non-refundable.\nAntelope Canyon does not allow any bags on the walking tour. Please leave them in your vehicle.\nIf you can''t find the check-in location, call: 928-693-9293',
 '[Tickets Guest Page] Notes — Upper Antelope (Hogan with Transport) (one item per line)'),

('tmpl__tix__upper_antelope_hogan_hiking__extra_notes',
 '★ Minimum age 8. Guests must be at least 8 years of age to join the hiking tour.\n★ Pregnant guests are not permitted to participate due to safety concerns.\n★ These entry reservations are non-refundable.\nPrepare for a 2-mile round-trip hike. Bring plenty of water.\nThe general guidelines for visiting Antelope Canyon:\n1. Bottled water is allowed.\n2. No bags are allowed on the walking tour. Please leave all bags in your vehicle.\n3. Phones and standard cameras are allowed.\n4. Tripods, monopods, large camera equipment, and flash/light equipment are generally NOT permitted.\nIf you can''t find the check-in location, call: 928-693-9293',
 '[Tickets Guest Page] Notes — Upper Antelope (Hogan Hiking) (one item per line)'),

('tmpl__tix__lower_antelope_kens__extra_notes',
 '★ These entry reservations are non-refundable.\nThe general guidelines for visiting Antelope Canyon:\n1. Bottled water is allowed.\n2. No bags are allowed on the walking tour. Please leave all bags in your vehicle.\n3. Phones and standard cameras are allowed.\n4. Tripods, monopods, large camera equipment, and flash/light equipment are generally NOT permitted.\nPlease note that rules may vary slightly depending on the canyon and tour operator. Final instructions will be provided by the guide on site.',
 '[Tickets Guest Page] Notes — Lower Antelope (Ken''s Tours) (one item per line)'),

('tmpl__tix__lower_antelope_dixie__extra_notes',
 'The general guidelines for visiting Antelope Canyon:\n1. Bottled water is allowed.\n2. No bags are allowed on the walking tour. Please leave all bags in your vehicle.\n3. Phones and standard cameras are allowed.\n4. Tripods, monopods, large camera equipment, and flash/light equipment are generally NOT permitted.\nPlease note that rules may vary slightly depending on the canyon and tour operator. Final instructions will be provided by the guide on site.',
 '[Tickets Guest Page] Notes — Lower Antelope (Dixie''s Tours) (one item per line)'),

('tmpl__tix__canyon_x__extra_notes',
 'The general guidelines for visiting Antelope Canyon:\n1. Bottled water is allowed.\n2. No bags are allowed on the walking tour. Please leave all bags in your vehicle.\n3. Phones and standard cameras are allowed.\n4. Tripods, monopods, large camera equipment, and flash/light equipment are generally NOT permitted.\nPlease note that rules may vary slightly depending on the canyon and tour operator. Final instructions will be provided by the guide on site.',
 '[Tickets Guest Page] Notes — Canyon X (one item per line)')

ON CONFLICT (key) DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────────────
-- PER TOUR TYPE — Tickets Reminder: checkin_location, maps_url, location_photo,
--                                   prepare_steps (up to 3)
-- ─────────────────────────────────────────────────────────────────────────────

INSERT INTO settings (key, value, label) VALUES

-- upper_antelope_tsosie
('tmpl__tix__upper_antelope_tsosie__checkin_location','Antelope Slot Canyon Tours, 148 6th Ave, Page, AZ 86040','[Tickets] Check-in location — Upper Antelope (Tsosie)'),
('tmpl__tix__upper_antelope_tsosie__maps_url','https://goo.gl/maps/t8e9E9uioEWG9zHn7','[Tickets] Maps URL — Upper Antelope (Tsosie)'),
('tmpl__tix__upper_antelope_tsosie__location_photo','https://maps.app.goo.gl/DiwJPosKMWNXzrH3A','[Tickets] Location photo URL — Upper Antelope (Tsosie)'),
('tmpl__tix__upper_antelope_tsosie__prep_1_label','','[Tickets] Prepare step 1 label — Upper Antelope (Tsosie)'),
('tmpl__tix__upper_antelope_tsosie__prep_1_url','','[Tickets] Prepare step 1 URL — Upper Antelope (Tsosie)'),
('tmpl__tix__upper_antelope_tsosie__prep_1_note','','[Tickets] Prepare step 1 note — Upper Antelope (Tsosie)'),
('tmpl__tix__upper_antelope_tsosie__prep_2_label','','[Tickets] Prepare step 2 label — Upper Antelope (Tsosie)'),
('tmpl__tix__upper_antelope_tsosie__prep_2_url','','[Tickets] Prepare step 2 URL — Upper Antelope (Tsosie)'),
('tmpl__tix__upper_antelope_tsosie__prep_2_note','','[Tickets] Prepare step 2 note — Upper Antelope (Tsosie)'),
('tmpl__tix__upper_antelope_tsosie__prep_3_label','','[Tickets] Prepare step 3 label — Upper Antelope (Tsosie)'),
('tmpl__tix__upper_antelope_tsosie__prep_3_url','','[Tickets] Prepare step 3 URL — Upper Antelope (Tsosie)'),
('tmpl__tix__upper_antelope_tsosie__prep_3_note','','[Tickets] Prepare step 3 note — Upper Antelope (Tsosie)'),

-- upper_antelope_brenda
('tmpl__tix__upper_antelope_brenda__checkin_location','Tse Bighanilini Tours, Highway 98, Milepost 299.8, Page, AZ 86040 (Between 299 and 300)','[Tickets] Check-in location — Upper Antelope (Brenda)'),
('tmpl__tix__upper_antelope_brenda__maps_url','https://maps.app.goo.gl/kcixg7Hee9WMMt3h8','[Tickets] Maps URL — Upper Antelope (Brenda)'),
('tmpl__tix__upper_antelope_brenda__location_photo','https://maps.app.goo.gl/3meJhQqfCAAt9Ayp7','[Tickets] Location photo URL — Upper Antelope (Brenda)'),
('tmpl__tix__upper_antelope_brenda__prep_1_label','Sign the required waiver form','[Tickets] Prepare step 1 label — Upper Antelope (Brenda)'),
('tmpl__tix__upper_antelope_brenda__prep_1_url','https://fareharbor.com/waivers?shortname=tsebighanilini&bookingUuid=4487ab4e-7d05-4cea-860b-b7da6ab47df6&source=copy-link','[Tickets] Prepare step 1 URL — Upper Antelope (Brenda)'),
('tmpl__tix__upper_antelope_brenda__prep_1_note','','[Tickets] Prepare step 1 note — Upper Antelope (Brenda)'),
('tmpl__tix__upper_antelope_brenda__prep_2_label','Pay the permit fee using the provided payment link','[Tickets] Prepare step 2 label — Upper Antelope (Brenda)'),
('tmpl__tix__upper_antelope_brenda__prep_2_url','https://fareharbor.com/embeds/book/navajonationparks/items/691331/calendar/2026/01/','[Tickets] Prepare step 2 URL — Upper Antelope (Brenda)'),
('tmpl__tix__upper_antelope_brenda__prep_2_note','For all guests, please keep your payment receipt for check-in. Same-day Lower Antelope or Canyon X receipts can waive the Upper Antelope permit fee. If we supplied your tickets, we can provide the receipt — just let us know.','[Tickets] Prepare step 2 note — Upper Antelope (Brenda)'),
('tmpl__tix__upper_antelope_brenda__prep_3_label','','[Tickets] Prepare step 3 label — Upper Antelope (Brenda)'),
('tmpl__tix__upper_antelope_brenda__prep_3_url','','[Tickets] Prepare step 3 URL — Upper Antelope (Brenda)'),
('tmpl__tix__upper_antelope_brenda__prep_3_note','','[Tickets] Prepare step 3 note — Upper Antelope (Brenda)'),

-- upper_antelope_brenda_no_fee
('tmpl__tix__upper_antelope_brenda_no_fee__checkin_location','Tse Bighanilini Tours, Highway 98, Milepost 299.8, Page, AZ 86040 (Between 299 and 300)','[Tickets] Check-in location — Upper Antelope (Brenda, no fee)'),
('tmpl__tix__upper_antelope_brenda_no_fee__maps_url','https://maps.app.goo.gl/kcixg7Hee9WMMt3h8','[Tickets] Maps URL — Upper Antelope (Brenda, no fee)'),
('tmpl__tix__upper_antelope_brenda_no_fee__location_photo','https://maps.app.goo.gl/3meJhQqfCAAt9Ayp7','[Tickets] Location photo URL — Upper Antelope (Brenda, no fee)'),
('tmpl__tix__upper_antelope_brenda_no_fee__prep_1_label','Sign the required waiver form','[Tickets] Prepare step 1 label — Upper Antelope (Brenda, no fee)'),
('tmpl__tix__upper_antelope_brenda_no_fee__prep_1_url','https://fareharbor.com/waivers?shortname=tsebighanilini&bookingUuid=4487ab4e-7d05-4cea-860b-b7da6ab47df6&source=copy-link','[Tickets] Prepare step 1 URL — Upper Antelope (Brenda, no fee)'),
('tmpl__tix__upper_antelope_brenda_no_fee__prep_1_note','','[Tickets] Prepare step 1 note — Upper Antelope (Brenda, no fee)'),
('tmpl__tix__upper_antelope_brenda_no_fee__prep_2_label','','[Tickets] Prepare step 2 label — Upper Antelope (Brenda, no fee)'),
('tmpl__tix__upper_antelope_brenda_no_fee__prep_2_url','','[Tickets] Prepare step 2 URL — Upper Antelope (Brenda, no fee)'),
('tmpl__tix__upper_antelope_brenda_no_fee__prep_2_note','','[Tickets] Prepare step 2 note — Upper Antelope (Brenda, no fee)'),
('tmpl__tix__upper_antelope_brenda_no_fee__prep_3_label','','[Tickets] Prepare step 3 label — Upper Antelope (Brenda, no fee)'),
('tmpl__tix__upper_antelope_brenda_no_fee__prep_3_url','','[Tickets] Prepare step 3 URL — Upper Antelope (Brenda, no fee)'),
('tmpl__tix__upper_antelope_brenda_no_fee__prep_3_note','','[Tickets] Prepare step 3 note — Upper Antelope (Brenda, no fee)'),

-- upper_antelope_aact
('tmpl__tix__upper_antelope_aact__checkin_location','Adventurous Antelope Canyon, Highway 98 Road & Milepost 302, Page, AZ 86040','[Tickets] Check-in location — Upper Antelope (AACT)'),
('tmpl__tix__upper_antelope_aact__maps_url','https://maps.app.goo.gl/hWXU2JSLSphMda529','[Tickets] Maps URL — Upper Antelope (AACT)'),
('tmpl__tix__upper_antelope_aact__location_photo','https://maps.app.goo.gl/tZttDC6G3jctLC8E7','[Tickets] Location photo URL — Upper Antelope (AACT)'),
('tmpl__tix__upper_antelope_aact__prep_1_label','','[Tickets] Prepare step 1 label — Upper Antelope (AACT)'),
('tmpl__tix__upper_antelope_aact__prep_1_url','','[Tickets] Prepare step 1 URL — Upper Antelope (AACT)'),
('tmpl__tix__upper_antelope_aact__prep_1_note','','[Tickets] Prepare step 1 note — Upper Antelope (AACT)'),
('tmpl__tix__upper_antelope_aact__prep_2_label','','[Tickets] Prepare step 2 label — Upper Antelope (AACT)'),
('tmpl__tix__upper_antelope_aact__prep_2_url','','[Tickets] Prepare step 2 URL — Upper Antelope (AACT)'),
('tmpl__tix__upper_antelope_aact__prep_2_note','','[Tickets] Prepare step 2 note — Upper Antelope (AACT)'),
('tmpl__tix__upper_antelope_aact__prep_3_label','','[Tickets] Prepare step 3 label — Upper Antelope (AACT)'),
('tmpl__tix__upper_antelope_aact__prep_3_url','','[Tickets] Prepare step 3 URL — Upper Antelope (AACT)'),
('tmpl__tix__upper_antelope_aact__prep_3_note','','[Tickets] Prepare step 3 note — Upper Antelope (AACT)'),

-- upper_antelope_hogan_transport
('tmpl__tix__upper_antelope_hogan_transport__checkin_location','Antelope Hogan Canyon Tours, LLC, 302 SR-98 (7 miles east of Page), Page, AZ 86040','[Tickets] Check-in location — Upper Antelope (Hogan Transport)'),
('tmpl__tix__upper_antelope_hogan_transport__maps_url','https://maps.app.goo.gl/DgmwCEepZbNLRn7A6','[Tickets] Maps URL — Upper Antelope (Hogan Transport)'),
('tmpl__tix__upper_antelope_hogan_transport__location_photo','https://maps.app.goo.gl/DztGqAk8b9pUp8EV7','[Tickets] Location photo URL — Upper Antelope (Hogan Transport)'),
('tmpl__tix__upper_antelope_hogan_transport__prep_1_label','','[Tickets] Prepare step 1 label — Upper Antelope (Hogan Transport)'),
('tmpl__tix__upper_antelope_hogan_transport__prep_1_url','','[Tickets] Prepare step 1 URL — Upper Antelope (Hogan Transport)'),
('tmpl__tix__upper_antelope_hogan_transport__prep_1_note','','[Tickets] Prepare step 1 note — Upper Antelope (Hogan Transport)'),
('tmpl__tix__upper_antelope_hogan_transport__prep_2_label','','[Tickets] Prepare step 2 label — Upper Antelope (Hogan Transport)'),
('tmpl__tix__upper_antelope_hogan_transport__prep_2_url','','[Tickets] Prepare step 2 URL — Upper Antelope (Hogan Transport)'),
('tmpl__tix__upper_antelope_hogan_transport__prep_2_note','','[Tickets] Prepare step 2 note — Upper Antelope (Hogan Transport)'),
('tmpl__tix__upper_antelope_hogan_transport__prep_3_label','','[Tickets] Prepare step 3 label — Upper Antelope (Hogan Transport)'),
('tmpl__tix__upper_antelope_hogan_transport__prep_3_url','','[Tickets] Prepare step 3 URL — Upper Antelope (Hogan Transport)'),
('tmpl__tix__upper_antelope_hogan_transport__prep_3_note','','[Tickets] Prepare step 3 note — Upper Antelope (Hogan Transport)'),

-- upper_antelope_hogan_hiking
('tmpl__tix__upper_antelope_hogan_hiking__checkin_location','Antelope Hogan Canyon Tours, LLC, 302 SR-98 (7 miles east of Page), Page, AZ 86040','[Tickets] Check-in location — Upper Antelope (Hogan Hiking)'),
('tmpl__tix__upper_antelope_hogan_hiking__maps_url','https://maps.app.goo.gl/DgmwCEepZbNLRn7A6','[Tickets] Maps URL — Upper Antelope (Hogan Hiking)'),
('tmpl__tix__upper_antelope_hogan_hiking__location_photo','https://maps.app.goo.gl/DztGqAk8b9pUp8EV7','[Tickets] Location photo URL — Upper Antelope (Hogan Hiking)'),
('tmpl__tix__upper_antelope_hogan_hiking__prep_1_label','','[Tickets] Prepare step 1 label — Upper Antelope (Hogan Hiking)'),
('tmpl__tix__upper_antelope_hogan_hiking__prep_1_url','','[Tickets] Prepare step 1 URL — Upper Antelope (Hogan Hiking)'),
('tmpl__tix__upper_antelope_hogan_hiking__prep_1_note','','[Tickets] Prepare step 1 note — Upper Antelope (Hogan Hiking)'),
('tmpl__tix__upper_antelope_hogan_hiking__prep_2_label','','[Tickets] Prepare step 2 label — Upper Antelope (Hogan Hiking)'),
('tmpl__tix__upper_antelope_hogan_hiking__prep_2_url','','[Tickets] Prepare step 2 URL — Upper Antelope (Hogan Hiking)'),
('tmpl__tix__upper_antelope_hogan_hiking__prep_2_note','','[Tickets] Prepare step 2 note — Upper Antelope (Hogan Hiking)'),
('tmpl__tix__upper_antelope_hogan_hiking__prep_3_label','','[Tickets] Prepare step 3 label — Upper Antelope (Hogan Hiking)'),
('tmpl__tix__upper_antelope_hogan_hiking__prep_3_url','','[Tickets] Prepare step 3 URL — Upper Antelope (Hogan Hiking)'),
('tmpl__tix__upper_antelope_hogan_hiking__prep_3_note','','[Tickets] Prepare step 3 note — Upper Antelope (Hogan Hiking)'),

-- lower_antelope_kens
('tmpl__tix__lower_antelope_kens__checkin_location','Ken''s Tours, 22 S Lake Powell Blvd, Page, AZ 86040','[Tickets] Check-in location — Lower Antelope (Ken''s)'),
('tmpl__tix__lower_antelope_kens__maps_url','','[Tickets] Maps URL — Lower Antelope (Ken''s)'),
('tmpl__tix__lower_antelope_kens__location_photo','','[Tickets] Location photo URL — Lower Antelope (Ken''s)'),
('tmpl__tix__lower_antelope_kens__prep_1_label','','[Tickets] Prepare step 1 label — Lower Antelope (Ken''s)'),
('tmpl__tix__lower_antelope_kens__prep_1_url','','[Tickets] Prepare step 1 URL — Lower Antelope (Ken''s)'),
('tmpl__tix__lower_antelope_kens__prep_1_note','','[Tickets] Prepare step 1 note — Lower Antelope (Ken''s)'),
('tmpl__tix__lower_antelope_kens__prep_2_label','','[Tickets] Prepare step 2 label — Lower Antelope (Ken''s)'),
('tmpl__tix__lower_antelope_kens__prep_2_url','','[Tickets] Prepare step 2 URL — Lower Antelope (Ken''s)'),
('tmpl__tix__lower_antelope_kens__prep_2_note','','[Tickets] Prepare step 2 note — Lower Antelope (Ken''s)'),
('tmpl__tix__lower_antelope_kens__prep_3_label','','[Tickets] Prepare step 3 label — Lower Antelope (Ken''s)'),
('tmpl__tix__lower_antelope_kens__prep_3_url','','[Tickets] Prepare step 3 URL — Lower Antelope (Ken''s)'),
('tmpl__tix__lower_antelope_kens__prep_3_note','','[Tickets] Prepare step 3 note — Lower Antelope (Ken''s)'),

-- lower_antelope_dixie
('tmpl__tix__lower_antelope_dixie__checkin_location','Dixie''s Tours, 29 S Lake Powell Blvd, Page, AZ 86040','[Tickets] Check-in location — Lower Antelope (Dixie''s)'),
('tmpl__tix__lower_antelope_dixie__maps_url','','[Tickets] Maps URL — Lower Antelope (Dixie''s)'),
('tmpl__tix__lower_antelope_dixie__location_photo','','[Tickets] Location photo URL — Lower Antelope (Dixie''s)'),
('tmpl__tix__lower_antelope_dixie__prep_1_label','','[Tickets] Prepare step 1 label — Lower Antelope (Dixie''s)'),
('tmpl__tix__lower_antelope_dixie__prep_1_url','','[Tickets] Prepare step 1 URL — Lower Antelope (Dixie''s)'),
('tmpl__tix__lower_antelope_dixie__prep_1_note','','[Tickets] Prepare step 1 note — Lower Antelope (Dixie''s)'),
('tmpl__tix__lower_antelope_dixie__prep_2_label','','[Tickets] Prepare step 2 label — Lower Antelope (Dixie''s)'),
('tmpl__tix__lower_antelope_dixie__prep_2_url','','[Tickets] Prepare step 2 URL — Lower Antelope (Dixie''s)'),
('tmpl__tix__lower_antelope_dixie__prep_2_note','','[Tickets] Prepare step 2 note — Lower Antelope (Dixie''s)'),
('tmpl__tix__lower_antelope_dixie__prep_3_label','','[Tickets] Prepare step 3 label — Lower Antelope (Dixie''s)'),
('tmpl__tix__lower_antelope_dixie__prep_3_url','','[Tickets] Prepare step 3 URL — Lower Antelope (Dixie''s)'),
('tmpl__tix__lower_antelope_dixie__prep_3_note','','[Tickets] Prepare step 3 note — Lower Antelope (Dixie''s)'),

-- canyon_x
('tmpl__tix__canyon_x__checkin_location','Canyon X Tours, Page, AZ 86040','[Tickets] Check-in location — Canyon X'),
('tmpl__tix__canyon_x__maps_url','','[Tickets] Maps URL — Canyon X'),
('tmpl__tix__canyon_x__location_photo','','[Tickets] Location photo URL — Canyon X'),
('tmpl__tix__canyon_x__prep_1_label','','[Tickets] Prepare step 1 label — Canyon X'),
('tmpl__tix__canyon_x__prep_1_url','','[Tickets] Prepare step 1 URL — Canyon X'),
('tmpl__tix__canyon_x__prep_1_note','','[Tickets] Prepare step 1 note — Canyon X'),
('tmpl__tix__canyon_x__prep_2_label','','[Tickets] Prepare step 2 label — Canyon X'),
('tmpl__tix__canyon_x__prep_2_url','','[Tickets] Prepare step 2 URL — Canyon X'),
('tmpl__tix__canyon_x__prep_2_note','','[Tickets] Prepare step 2 note — Canyon X'),
('tmpl__tix__canyon_x__prep_3_label','','[Tickets] Prepare step 3 label — Canyon X'),
('tmpl__tix__canyon_x__prep_3_url','','[Tickets] Prepare step 3 URL — Canyon X'),
('tmpl__tix__canyon_x__prep_3_note','','[Tickets] Prepare step 3 note — Canyon X')

ON CONFLICT (key) DO NOTHING;

-- Fix newlines (run again safely)
UPDATE settings
SET value = replace(value, '\n', chr(10))
WHERE key LIKE 'tmpl__%'
  AND value LIKE '%\n%';

-- Tickets SMS global
INSERT INTO settings (key, value, label) VALUES
('tmpl__global__tix_sms_body','Dear {name}, reminder for your {sms_label} on {date}. Check-in: {checkin}, Tour: {tour_time}. Please use the link below to review important information and reconfirm your booking: {url} Questions? Call 702-948-4190.','[Tickets SMS] Full SMS body — variables: {name} {sms_label} {date} {checkin} {tour_time} {url}')
ON CONFLICT (key) DO NOTHING;

-- Tickets Reminder: missing global guest page fields
INSERT INTO settings (key, value, label) VALUES
('tmpl__global__tix_guest_cfm_note',
 'Please present this number to the check-in staff upon arrival.',
 '[Tickets Guest Page] Confirmation# note'),
('tmpl__global__tix_guest_already_info',
 'If you have any questions, please leave a message in the Notes section below and click Submit to update. Our customer service team will contact you as soon as possible.',
 '[Tickets Guest Page] Info box (green) when already submitted'),
('tmpl__global__tix_guest_checkbox_text',
 'I have read the information above and confirm my tour reservation.',
 '[Tickets Guest Page] Checkbox / confirmation statement'),
('tmpl__global__tix_guest_submit_btn',
 'Submit',
 '[Tickets Guest Page] Submit button text'),
('tmpl__global__tix_guest_thanks_small',
 'Thank you for choosing National Park Express! 🏞️',
 '[Tickets Guest Page] Footer thank you text')
ON CONFLICT (key) DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────────────
-- TC Global: Guest Page — missing fields (migrate_v15 supplement)
-- ─────────────────────────────────────────────────────────────────────────────
INSERT INTO settings (key, value, label) VALUES

-- Pickup box
('tmpl__global__tc_guest_pickup_box_title',
 '🚌 Your Pick-up Process',
 '[TC Guest Page] Pickup box section title'),

('tmpl__global__tc_guest_pu_sms_head',
 'Morning of your tour — SMS reminder',
 '[TC Guest Page] Pickup step: SMS head'),
('tmpl__global__tc_guest_pu_sms_text',
 'We''ll send you an SMS with your check-in link and live vehicle tracking before departure.',
 '[TC Guest Page] Pickup step: SMS body text'),
('tmpl__global__tc_guest_pu_wrong_number',
 'Wrong number? Let us know in the Notes section below.',
 '[TC Guest Page] Pickup step: wrong number hint'),

('tmpl__global__tc_guest_pu_head_head',
 'Head to your pickup location',
 '[TC Guest Page] Pickup step: head to location title'),
('tmpl__global__tc_guest_pu_depart_warn',
 '⚠ We depart promptly — the vehicle cannot wait for late arrivals.',
 '[TC Guest Page] Pickup step: departure warning (red)'),

('tmpl__global__tc_guest_pu_checkin_head',
 'Check in when you arrive',
 '[TC Guest Page] Pickup step: check in title'),
('tmpl__global__tc_guest_pu_checkin_text',
 'Use the link in your SMS to check in on the spot. Your guide will be looking out for you!',
 '[TC Guest Page] Pickup step: check in body text'),

('tmpl__global__tc_guest_pu_notsure_head',
 'Not sure where to go?',
 '[TC Guest Page] Pickup step: not sure where to go title'),

-- Already submitted info box
('tmpl__global__tc_guest_already_submitted',
 'Response already submitted. You can update it below.',
 '[TC Guest Page] Already submitted green info box'),

-- Lunch section
('tmpl__global__tc_guest_lunch_title',
 '🥪 Lunch Selection',
 '[TC Guest Page] Lunch section title'),
('tmpl__global__tc_guest_lunch_hint',
 'Select for all {qty} guest(s). Total must equal your party size.',
 '[TC Guest Page] Lunch section hint — use {qty} for party size'),
('tmpl__global__tc_guest_lunch_default',
 'Default is Turkey Sandwich if no selection received.',
 '[TC Guest Page] Lunch default note'),
('tmpl__global__tc_guest_lunch_note_main',
 'For tours including lunch, you will choose your lunch option after clicking the Reconfirm My Spot button.',
 '[TC Guest Page + Email] Lunch note — main line'),
('tmpl__global__tc_guest_lunch_note_disclaimer',
 'This does not apply to Hoover Dam tours, tours without meals, or voucher bookings.',
 '[TC Guest Page + Email] Lunch note — disclaimer (orange)'),

-- MTLV
('tmpl__global__tc_guest_mtlv_title',
 '🏛️ Madame Tussauds Las Vegas Ticket',
 '[TC Guest Page] MTLV section title'),
('tmpl__global__tc_guest_mtlv_hint',
 'As a special bonus for this trip, you are eligible to receive complimentary Madame Tussauds Las Vegas tickets. Please select the number of tickets you would like to receive for your party (0–{qty}). No action is required for this section if you do not wish to receive the tickets.',
 '[TC Guest Page] MTLV hint paragraph — use {qty} for party size'),
('tmpl__global__tc_guest_mtlv_bullet_1',
 'If you plan to visit Madame Tussauds Las Vegas, please check the attraction''s operating hours, available dates, and any admission requirements before your visit: https://www.madametussauds.com/las-vegas.',
 '[TC Guest Page] MTLV bullet 1'),
('tmpl__global__tc_guest_mtlv_bullet_2',
 'Please note that attraction operating hours, closures, capacity restrictions, and admission policies are determined solely by Madame Tussauds Las Vegas and may change without notice. National Park Express is not responsible for attraction availability, operating schedules, or admission decisions made by the attraction.',
 '[TC Guest Page] MTLV bullet 2'),
('tmpl__global__tc_guest_mtlv_locked_cancelled',
 'Your Madame Tussauds ticket selection has been cancelled.',
 '[TC Guest Page] MTLV locked — cancelled message'),
('tmpl__global__tc_guest_mtlv_locked_confirmed',
 'Your Madame Tussauds ticket selection has been confirmed and can no longer be changed.',
 '[TC Guest Page] MTLV locked — confirmed message'),

-- Notes section
('tmpl__global__tc_guest_notes_title',
 '📝 Notes',
 '[TC Guest Page] Notes section title'),
('tmpl__global__tc_guest_notes_placeholder',
 'Special requests, dietary notes...',
 '[TC Guest Page] Notes textarea placeholder'),
('tmpl__global__tc_guest_last_update_label',
 '📝 Your last update',
 '[TC Guest Page] Last update display label'),

-- Submit / footer
('tmpl__global__tc_guest_submit_btn',
 'Submit Confirmation',
 '[TC Guest Page] Submit button text'),
('tmpl__global__tc_guest_footer_thanks',
 'Thank you for choosing National Park Express — we look forward to your adventure! 🏞️',
 '[TC Guest Page] Footer thank you text'),

-- Date modal
('tmpl__global__tc_guest_date_modal_title',
 '📅 Select New Tour Date',
 '[TC Guest Page] Date change modal title'),
('tmpl__global__tc_guest_date_modal_desc',
 'Please select your requested new date below.',
 '[TC Guest Page] Date change modal description'),

-- ── TC Last Minute Email ──────────────────────────────────────────────────────
('tmpl__global__tc_lm_email_intro_with_lunch',
 'Please review your tour details below and select your lunch option using the button below to help ensure a smooth and hassle-free departure.',
 '[TC Last Minute Email] Intro — tours with lunch'),
('tmpl__global__tc_lm_email_intro_no_lunch',
 'Please review your tour details below and confirm your pickup information to help ensure a smooth and hassle-free departure.',
 '[TC Last Minute Email] Intro — tours without lunch'),
('tmpl__global__tc_lm_email_closing',
 'We look forward to seeing you soon.',
 '[TC Last Minute Email] Closing line'),
('tmpl__global__tc_lm_email_btn_lunch',
 '🍽 SELECT MY LUNCH OPTION',
 '[TC Last Minute Email] CTA button — tours with lunch'),
('tmpl__global__tc_lm_email_btn_no_lunch',
 '✓ I''VE READ THIS MESSAGE',
 '[TC Last Minute Email] CTA button — tours without lunch')

ON CONFLICT (key) DO NOTHING;
