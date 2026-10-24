# Writing narration

Narration is spoken aloud by a text-to-speech engine and heard once, by someone
who has never seen the app. That constrains it far more than written copy.

## The rules

**Write for the ear, not the page.** Short sentences. One idea each. No
parentheses, no semicolons, no bullet lists read aloud as prose. If you would
not say it out loud to a colleague, do not write it.

**22 to 30 words a beat.** That is about eight to eleven seconds of speech — one
scene. Longer and the viewer loses the thread; shorter and the cut feels nervous.

**Say what is on screen, as it happens.** The viewer is watching a pointer move.
Narration that describes something else is disorienting. "Selecting any pipe
opens the inspector" works because the pointer is selecting a pipe.

**Never claim a capability you did not see.** If the snapshot showed no export
button, there is no export feature, whatever the marketing page says. An
invented feature is the single worst failure mode of a generated demo: it is
confident, plausible, and wrong, and nobody catches it until a customer asks.

**No marketing adjectives.** Cut "powerful", "seamless", "intuitive",
"cutting-edge", "robust", "revolutionary". They carry no information and make a
demo sound like an ad. Describe what it does; the viewer will judge it.

**Spell acronyms the way they are said.** TTS reads letter strings as words.

| Write | Not |
|---|---|
| `B W S S B` | `BWSSB` |
| `E PANET` | `EPANET` |
| `G I S` | `GIS` |
| `control K` | `Ctrl+K` |
| `A P I` | `API` |

**Write numbers as a person says them.** `two lakh forty-eight thousand`, not
`248,000`. `fourteen thousand kilometres`, not `14,000 km`. `ninety-five per
cent`, not `95%`. A TTS engine will read `2.48L` as "two point four eight ell".

**Dashes and quotes.** Use a plain hyphen or restructure the sentence. Curly
quotes and em-dashes are usually fine but vary by engine; if a clip sounds
wrong, that is the first thing to check.

## Structure across scenes

A demo is an argument, not a tour. Order the scenes so each one earns the next.

1. **Open with what it is and who it is for** — one title card, two sentences.
   Not the tech stack, not the team.
2. **Show the thing the product is actually about**, early. If the viewer stops
   watching after ninety seconds, they should already have seen the point.
3. **Build.** Each scene should depend on the last: show the data, then query
   it, then act on the result. Do not shuffle through tabs in menu order.
4. **End on the strongest capability**, not on settings.

Avoid the two standard failure shapes: the *menu tour* ("here is the Dashboard
tab, here is the Reports tab…"), which has no argument; and the *feature list
read aloud*, which has no pictures.

## Examples

**Weak — marketing, vague, nothing on screen:**
> Our powerful, intuitive dashboard gives you seamless visibility into all your
> key metrics in real time, empowering your team to make data-driven decisions.

**Better — concrete, matches the picture, 29 words:**
> The dashboard opens on the work in flight. Each row shows the owner and what
> is blocking it, so the standup is reading a screen instead of going round the
> table.

**Weak — unreadable by TTS:**
> The GIS import handles 248,000+ pipe segments via the EPANET solver (~95%
> coverage).

**Better:**
> The G I S import handles more than two lakh forty-eight thousand pipe
> segments, solved with E PANET, covering about ninety-five per cent of the
> network.

## Before you render

Read every scene's narration aloud, in order, at a normal speaking pace. If you
run out of breath, trip over a phrase, or cannot tell where one scene ends and
the next begins, fix it before spending the render. Then show the full script to
the user for approval — always, every time.
