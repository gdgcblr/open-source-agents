"""Create the synthetic text-based PDF used in the README example."""

from pathlib import Path

import pymupdf


OUTPUT = Path(__file__).with_name("sample_form.generated.pdf")
FORM_TEXT = """Community Workshop Registration

Full name (required): ______________________________
Email address (required): ___________________________

Experience level (select one):
[ ] Beginner
[ ] Intermediate
[ ] Advanced

May we email you workshop updates?  [ ] Yes  [ ] No
"""


def main() -> None:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_textbox(pymupdf.Rect(72, 72, 540, 760), FORM_TEXT, fontsize=12)
    document.save(OUTPUT)
    document.close()
    print(f"Created {OUTPUT}")


if __name__ == "__main__":
    main()

