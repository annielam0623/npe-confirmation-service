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
