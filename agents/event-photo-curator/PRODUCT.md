# Product

## Project Pitch

Event Photo Curator is a local-first, privacy-focused app that helps organisers turn an overwhelming event gallery into a varied shortlist of memorable moments, and lets attendees find photos featuring themselves through opt-in face matching. Built for ease of use, it combines local Gemma 4 vision with OpenCV and ImageHash to assess photos, group similar shots, suggest captions, and preserve original-quality downloads—saving everyone time on the eternal “which one should I post?”

## Register

product

## Users

Event organizers and attendees testing a shared photo workflow on one laptop. The pilot collects credited uploads, finds possible matches from consenting reference photos, and helps an organizer choose event highlights.

## Product Purpose

Complete event photo curation locally: preserve originals, browse fast thumbnails, review every readable frame with local AI, and export a varied shortlist with optional attribution. The user plans a recorded video demonstration rather than a hosted deployment.

## Design Direction

The user requested dark mode and beui.dev. Photos are the primary content; controls support importing, reviewing, matching and downloading. The existing app uses system fonts, named form labels, keyboard focus, reduced-motion support, and responsive layouts.

## Design Principles

- Keep local processing and original preservation clear.
- Show AI decisions and technical hints without concealing rejected photos.
- Require permission for uploads and consent for face matching.
- Keep preview browsing lightweight and full-quality downloads explicit.
- Include both UI and backend in a reproducible local project; publish only when authorized.

## Current workflow

Attendees get a photo-first gallery and face search. Organizers import an explicitly supplied photo directory, see real processing progress through beUI TodoList, then use a floating beUI PromptInput to ask the local tool-calling agent for photos. Large introductory copy is omitted.
