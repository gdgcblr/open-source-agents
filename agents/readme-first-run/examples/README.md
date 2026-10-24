# FirstRun sample projects

Three tiny Python projects, each broken on purpose in one way that a newcomer would hit on their
first run. They are written like real hackathon READMEs so you can watch FirstRun follow them
step by step.

| Sample | Broken on purpose | Expected FirstRun verdict |
| :--- | :--- | :--- |
| [`quote-of-the-day`](quote-of-the-day/) | `main.py` imports `dotenv`, but `requirements.txt` never lists `python-dotenv`. Install succeeds, `python main.py --day 3` crashes with `ModuleNotFoundError`. | **fixed**: adds `python-dotenv` to `requirements.txt`, the rerun prints the documented quote. |
| [`standup-notes`](standup-notes/) | The README says `python summarize.py notes.txt`, but the script lives at `src/summarize.py`. | **fixed**: corrects the command in the README, the rerun prints the documented standup. |
| [`gemini-haiku`](gemini-haiku/) | Nothing is wrong with the code. It needs a real `GEMINI_API_KEY`, and `.env.example` only has a placeholder. | **blocked: credentials required**. FirstRun stops and names the variable instead of pretending it worked. |

Try one from the project root:

```bash
python -m firstrun examples/quote-of-the-day
```

No Docker or no API key? Run FirstRun with the local sandbox and its offline rules:

```bash
python -m firstrun examples/quote-of-the-day --sandbox local --offline
```

The samples have no `.env` files, only `.env.example` placeholders.
