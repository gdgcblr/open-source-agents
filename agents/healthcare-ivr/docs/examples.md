# Examples

All outputs below come from genuine runs against the Sahyadri roster, on Saturday 24 October 2026 at 2:42 PM (Pune time).

## The receptionist's tools

During a call, the LLM calls these functions through Deepgram. Lines marked `[bridge]` show the backend scheduling a hang-up for after the receptionist's goodbye.

**Choosing a language.** The greeting asks "English or Hindi?". An answer that's neither is counted:
```
>> set_language {"language": "ta"}
{ "status": "not_supported", "message": "Only English and Hindi are available. Ask again: English or Hindi?" }

>> set_language {"language": "hi"}
{ "language": "hi", "message": "Reply in Hindi from now on. Write in Devanagari script." }
```

A different caller who never picks English or Hindi:
```
>> set_language {"language": "ta"}
{ "status": "not_supported", ... }
>> set_language {"language": "unknown"}
{ "status": "not_supported", ... }
>> set_language {"language": "fr"}
   [bridge] hang up after the goodbye: the caller didn't choose English or Hindi after 3 tries
{ "status": "ending_call", "message": "Say in one short sentence that you can only help in English or Hindi, and goodbye. The call ends after that." }
```

**Finding a time.** The caller has shoulder pain, so the receptionist suggested Orthopaedics and Dr. Amruta Khare (OPD Tuesday, Thursday and Saturday mornings). Her Saturday OPD is over, so the next free time is Tuesday:
```
>> find_slot {"doctor_name": "Amruta Khare"}
{ "doctor": "Dr. Amruta Khare", "department": "Orthopaedics", "date": "2026-10-27", "time": "10:00",
  "day": "Tuesday, 27 October 2026", "spoken_time": "10:00 AM" }

>> find_slot {"doctor_name": "Amruta Khare", "date": "2026-10-27", "time": "11:00"}
{ "doctor": "Dr. Amruta Khare", "department": "Orthopaedics", "date": "2026-10-27", "time": "11:00",
  "day": "Tuesday, 27 October 2026", "spoken_time": "11:00 AM", "requested_time_free": true }
```

A time beyond the 72-hour window ends the call:
```
>> find_slot {"doctor_name": "Amruta Khare", "date": "2026-10-31", "time": "10:00"}
   [bridge] hang up after the goodbye: no appointment with Dr. Amruta Khare within 72 hours
{ "status": "outside_booking_window", "message": "That time is more than 72 hours away. Appointments can only be booked within the next 72 hours. Apologise, explain that, and say goodbye in one short sentence. The call ends after that." }
```

**Booking** needs every patient detail, and each one is checked:
```
>> book_appointment {"doctor_name": "Dr. Amruta Khare", "date": "2026-10-27", "time": "11:00",
                     "patient_name": "Sunita Patil", "patient_age": 47, "patient_gender": "female",
                     "patient_phone": "+919822045678", "symptoms": "Right shoulder pain for two weeks",
                     "caller_confirmed": true}
{ "status": "booked", "reference": "9MGSBX", "doctor": "Dr. Amruta Khare", "department": "Orthopaedics",
  "day": "Tuesday, 27 October 2026", "time": "11:00 AM", "patient_name": "Sunita Patil",
  "patient_phone": "+919822045678", "message": "Tell the caller the reference character by character." }

>> book_appointment {... "time": "11:15", "patient_age": 470, ...}
{ "error": "Invalid arguments for book_appointment: patient_age: Input should be less than or equal to 120" }
```

On the call's timeline, this booking's age, gender, phone number and symptoms are stored as `[private]`. They're kept only on the appointment.

**Existing appointments** need the patient's name as well as a phone number or the reference:
```
>> find_appointments {"patient_name": "Sunita Patil", "patient_phone": "+919822045678"}
{ "appointments": [ { "reference": "9MGSBX", "doctor": "Dr. Amruta Khare", "department": "Orthopaedics",
                      "day": "Tuesday, 27 October 2026", "time": "11:00 AM", "patient_name": "Sunita Patil" } ] }

>> cancel_appointment {"reference": "9MGSBX", "patient_name": "Asha Patil", "caller_confirmed": true}
{ "error": "The patient's name doesn't match this booking. Ask for the name exactly as booked." }
```

## What a call costs

At the default rates, a 3-minute call costs about $0.49 in voice-agent time ($0.163 per minute with `claude-sonnet-5`) and $0.016 to transcribe ($0.0052 per minute for multilingual Nova-3). With `AGENT_LLM_MODEL=claude-haiku-4-5` and `VOICE_AGENT_USD_PER_MINUTE=0.075`, the voice-agent part drops to about $0.23. A call that reaches the default 15-minute limit costs about $2.45 in voice-agent time. These are estimates from Deepgram's list prices. Deepgram doesn't report LLM token counts for the models it runs, and Twilio's telephony charges aren't included.

## Diarizing an uploaded recording

The dashboard's **Upload recording** button sends a file to `POST /api/calls/upload`. Deepgram then splits it by speaker, and the call page shows the transcript with each speaker's lines.

<!-- TODO before opening the PR: add the utterances from a genuine run with a real Deepgram key,
     e.g. GET /api/calls/<id> → .utterances[:4] -->

`GET /api/calls/<id>` returns `"diarization_status": "completed"`, `utterances` (segments with `speaker`, `start`, `end`, `text` and `confidence`), the call's `events`, and `transcription_cost_usd`.
