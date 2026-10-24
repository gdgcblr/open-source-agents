# Note Summarizer

## Overview
This small agent reads a text file you point it at and returns a three bullet summary of it.

## Technical Stack
- Python with the requests library for the HTTP call to the summarizer service

## Architecture & Data Flow
The script reads the file, sends the text to the model endpoint, and prints the bullets it gets back.

## Example Input & Output
Input is a text file of meeting notes. Output is three short bullets with the main decisions.

## How to Test
Run the script on any text file and check that three bullets are printed.

## Known Limitations
Files larger than 10 MB are rejected. Summary quality is not verified.

## Security & Privacy Considerations
The file text is sent to the summarizer service. No credentials are stored by the script.
