### Prompt A/B: original vs enhanced on haiku (claude-code, 3 answers per version)

| Group | Cases | Win / loss / tie | Checks passed (original → enhanced) |
| :-- | --: | :-- | :-- |
| answered | 5 | 5 / 0 / 0 | 24% → 100% |
| restructured | 10 | 0 / 1 / 9 | 99% → 97% |

| Case | Group | Outcome | Original | Enhanced | Failed checks (original → enhanced) |
| :-- | :-- | :-- | --: | --: | :-- |
| `auto-summary-limits` | restructured | loss | 5/6 | 4/6 | under 50 words → under 50 words |
| `auto-long-context-bullets` | restructured | tie | 6/6 | 6/6 | none → none |
| `auto-banned-words` | restructured | tie | 9/9 | 9/9 | none → none |
| `auto-numbered-list` | restructured | tie | 6/6 | 6/6 | none → none |
| `auto-json-only` | restructured | tie | 9/9 | 9/9 | none → none |
| `auto-no-code` | restructured | tie | 9/9 | 9/9 | none → none |
| `auto-tweet` | restructured | tie | 9/9 | 9/9 | none → none |
| `auto-haiku` | restructured | tie | 3/3 | 3/3 | none → none |
| `auto-injection` | restructured | tie | 9/9 | 9/9 | none → none |
| `auto-no-names` | restructured | tie | 6/6 | 6/6 | none → none |
| `answered-json-fields` | answered | win | 4/9 | 9/9 | agreed keys, valid json → none |
| `answered-format` | answered | win | 0/6 | 6/6 | 4 bullets, short → none |
| `answered-language` | answered | win | 4/6 | 6/6 | has tests → none |
| `answered-audience` | answered | win | 0/6 | 6/6 | no jargon, under 120 words → none |
| `answered-scope` | answered | win | 0/6 | 6/6 | in scope (India), under 200 words → none |

_Check pass rates on a small sample; sampling noise can exceed the difference. Re-run with more trials before drawing conclusions._