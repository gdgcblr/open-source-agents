# Hospital data

## Where the default data comes from

The default hospital is **Sahyadri Super Speciality Hospital, Deccan Gymkhana (Pune)**, from `backend/knowledge/sahyadri-deccan/`.

- **From the official website** ([sahyadrihospital.com](https://sahyadrihospital.com/deccan), checked on 24 October 2026; its `robots.txt` allows these pages): name, address, the appointment and emergency number, enquiry email, fax, bed count and history, the specialities offered at Deccan, round-the-clock services, facilities, and health checkup packages with prices.
- **Synthetic sample data**: the doctors, their OPD days, hours and fees, the outpatient and visiting hours, and first-visit advice. The doctors are fictional. The website's doctor search couldn't be read reliably, and attaching made-up schedules to real doctors would mislead callers.

This project is not affiliated with Sahyadri Hospitals. **Don't connect this configuration to a public phone number**: callers would believe they had reached the real hospital and could be booked with doctors who don't exist.

`backend/knowledge/medcare-sample/` is a fully fictional hospital. To start from it, set `HOSPITAL_DIR=knowledge/medcare-sample` in `.env` before the first start, or run `make reset-db` first.

## Using your own hospital

`HOSPITAL_DIR` points to a folder (relative to `backend/`) containing:

- `hospital.md`: everything the receptionist may tell callers, starting with a `# Hospital name` heading
- `doctors.csv`: the columns `name`, `department`, `specialty`, `opd_days` (e.g. `Mon Wed Fri` or `Mon-Sat`), `opd_start` and `opd_end` (24-hour `HH:MM`), `slot_minutes` and `consultation_fee_inr`

The folder is loaded into the database on first start only. After that, edit the information and the doctors on the dashboard's **Hospital** page. Every save is validated, and edits apply from the next call. Changing `HOSPITAL_DIR` later doesn't overwrite your edits.

The whole prompt (rules, hospital information and doctors) must stay under Deepgram's 25,000-character limit, which every save checks.
