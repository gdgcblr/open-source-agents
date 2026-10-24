"""Generate original SVG illustrations; no external image service or assets."""
from pathlib import Path

out = Path(__file__).resolve().parent.parent / "frontend/public/art"
out.mkdir(parents=True, exist_ok=True)
palette = {
    "temples": ("#dbc0a4", "#d1a082", "#5d7565"),
    "palace": ("#e1c39f", "#c79877", "#738a7f"),
    "coast": ("#b9c9c2", "#94b3ab", "#3d7379"),
    "mountain": ("#cfcec0", "#a8b49f", "#536f61"),
    "city": ("#c1bcc5", "#a99aab", "#586a70"),
}
for scene, (sky, horizon, dark) in palette.items():
    shapes = ""
    if scene == "temples":
        shapes = '''<path d="M0 245Q90 130 180 220T400 180T700 205V420H0Z" fill="#6f8070"/>
        <path d="M0 295Q150 220 300 290T700 240V420H0Z" fill="#4d665b"/>
        <g fill="#514e40" stroke="#514e40"><path d="M365 140h130v180H365Z"/><path d="m340 160 90-47 90 47-20-2H360Z"/><path d="m350 197 80-38 80 38Z"/><path d="m350 237 80-35 80 35Z"/><path d="M425 85h10v35h-10Z"/></g>
        <g fill="#e0c091"><path d="M380 168h100v14H380ZM380 207h100v17H380ZM380 248h100v20H380Z"/></g>
        <path d="M450 420Q260 330 335 275" stroke="#b7a184" stroke-width="47" fill="none"/>
        <path d="M110 420 147 180" stroke="#544b40" stroke-width="14"/><path d="M143 240 65 185M145 216l76-60" stroke="#544b40" stroke-width="7"/>
        <g fill="#d29f9b"><ellipse cx="85" cy="171" rx="75" ry="39"/><ellipse cx="186" cy="148" rx="78" ry="44"/><ellipse cx="138" cy="121" rx="80" ry="38"/></g>'''
    elif scene == "palace":
        shapes = '''<path d="M0 300Q180 265 350 300T700 285V420H0Z" fill="#8fa8a0"/>
        <g fill="#d4ab7e" stroke="#9a7759" stroke-width="2"><path d="M140 135h410v165H140Z"/><path d="M125 165h65v135h-65ZM500 165h65v135h-65Z"/><path d="M155 145V90M532 145V90"/><path d="m123 133 34-35 35 35ZM498 133l34-35 35 35Z"/><path d="M300 125V85q45-68 90 0v40Z"/></g>
        <g fill="#7b6857"><path d="M310 300V215q35-55 70 0v85Z"/>
        <path d="M215 190v-22q13-24 26 0v22ZM260 190v-22q13-24 26 0v22ZM405 190v-22q13-24 26 0v22ZM450 190v-22q13-24 26 0v22Z"/></g>
        <g opacity=".3" stroke="#cfddc9" stroke-width="3"><path d="M100 335h470M170 355h390M80 380h520"/></g>
        <path d="M0 420V280l80-30 70 170Z" fill="#536b5a"/>'''
    elif scene == "coast":
        shapes = '''<path d="M0 220Q200 200 700 210V420H0Z" fill="#6c9fa0"/>
        <path d="M0 200 120 120l150 110 100-36 150 226H0Z" fill="#6c8172"/>
        <g stroke="#8c7967" stroke-width="1"><path d="M105 220V140h57v80Z" fill="#e4c9a0"/><path d="M168 250V175h62v75Z" fill="#d0a591"/><path d="M215 288v-90h68v90Z" fill="#e0cbae"/><path d="M274 300v-69h55v69Z" fill="#bfa39a"/><path d="M65 190v-60h43v60Z" fill="#bfae8c"/></g>
        <g fill="#506967"><path d="M115 156h12v21h-12ZM139 156h12v21h-12ZM181 191h12v22h-12ZM202 191h12v22h-12ZM236 216h12v25h-12ZM262 216h12v25h-12ZM290 250h11v22h-11Z"/></g>
        <path d="M0 320Q200 345 348 420H0Z" fill="#3d665b"/><path d="M365 282h180M430 305h180M520 342h160" stroke="#d4e0cf" stroke-width="2" opacity=".5"/>
        <path d="m520 255 40 1-8 10h-24Z" fill="#ebe0c2"/><path d="M540 255v-30" stroke="#6d7468" stroke-width="2"/>'''
    elif scene == "mountain":
        shapes = '''<path d="m0 285 180-200 130 140L440 60l260 250v110H0Z" fill="#91a392"/>
        <path d="m135 135 45-50 50 88-50-18-25 22Z" fill="#e3e0cc"/><path d="m385 118 55-58 73 90-54-16-19 22-22-20Z" fill="#e3e0cc"/>
        <path d="M0 290Q190 160 350 300T700 260V420H0Z" fill="#6e8c72"/>
        <path d="M0 340Q210 235 400 340T700 320V420H0Z" fill="#466e5b"/>
        <g stroke="#a9bb8a" stroke-width="3" fill="none" opacity=".55"><path d="M0 350q190-100 400 10M0 370q190-100 430 10M0 395q190-100 460 8"/></g>
        <path d="M530 420 560 200l25 220Z" fill="#314e44"/><path d="m500 285 60-105 60 105ZM510 325l50-95 55 95Z" fill="#45624d"/>'''
    else:
        shapes = '''<g stroke="#706b6e" stroke-width="1"><path d="M0 250V180h95v190H0Z" fill="#969699"/><path d="M90 200v-65h85v230H90Z" fill="#c5b4a4"/><path d="M510 200v-70h85v235h-85Z" fill="#b7a799"/><path d="M590 250V180h110v185H590Z" fill="#8e9190"/></g>
        <path d="M150 420q200-125 410 0Z" fill="#b2a394"/><path d="M0 340h700v80H0Z" fill="#7b8b86"/>
        <g stroke="#585d59" fill="none"><path d="M350 75q-5 150-85 260h170Q355 225 350 75Z" stroke-width="9"/><path d="M325 180h50M305 245h90M280 305h140M350 60v30" stroke-width="6"/><path d="m310 245 83 60m-3-60-84 60" stroke-width="3"/></g>
        <path d="M0 355q180-30 290 65H0ZM700 355q-180-30-290 65h290Z" fill="#4a645b"/>
        <g fill="#696a63"><path d="M112 155h15v24h-15ZM143 155h15v24h-15ZM534 153h16v25h-16ZM563 153h16v25h-16Z"/></g>'''
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="700" height="420" viewBox="0 0 700 420" role="img" aria-label="Original stylized travel illustration">
    <defs><linearGradient id="sky" x2="0" y2="1"><stop stop-color="{sky}"/><stop offset="1" stop-color="{horizon}"/></linearGradient><filter id="grain"><feTurbulence baseFrequency=".65" numOctaves="3" stitchTiles="stitch"/><feColorMatrix type="saturate" values="0"/><feComponentTransfer><feFuncA type="linear" slope=".07"/></feComponentTransfer></filter></defs>
    <rect width="700" height="420" fill="url(#sky)"/><circle cx="535" cy="100" r="43" fill="#f5e4ba" opacity=".8"/>
    <path d="M0 200Q150 90 310 200T700 170V420H0Z" fill="{dark}" opacity=".15"/>{shapes}<rect width="700" height="420" filter="url(#grain)" opacity=".55"/></svg>'''
    (out / f"{scene}.svg").write_text(svg)
print(f"Generated {len(palette)} original vector illustrations.")
