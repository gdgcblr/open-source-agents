import math
from PIL import Image, ImageDraw, ImageFont

WIDTH = 920
HEIGHT = 520

# Fonts
try:
    font_mono_lg = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 16)
    font_mono_md = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 13)
    font_mono_sm = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 11)
    font_sans_lg = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 22)
    font_sans_md = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 15)
    font_sans_sm = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 12)
    font_sans_bold = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 17)
except Exception:
    font_mono_lg = font_mono_md = font_mono_sm = ImageFont.load_default()
    font_sans_lg = font_sans_md = font_sans_sm = font_sans_bold = ImageFont.load_default()

def draw_window_chrome(draw, title, scene_num, total_scenes=5):
    # Background
    draw.rectangle([0, 0, WIDTH, HEIGHT], fill=(8, 10, 18))
    
    # Outer Card Window
    draw.rounded_rectangle([25, 20, WIDTH - 25, HEIGHT - 20], radius=14, fill=(13, 17, 30), outline=(36, 46, 74), width=1)
    
    # Title bar
    draw.rectangle([26, 21, WIDTH - 26, 62], fill=(18, 24, 42))
    draw.line([26, 62, WIDTH - 26, 62], fill=(36, 46, 74), width=1)
    
    # Window traffic lights
    draw.ellipse([42, 36, 54, 48], fill=(255, 95, 86))
    draw.ellipse([62, 36, 74, 48], fill=(255, 189, 46))
    draw.ellipse([82, 36, 94, 48], fill=(39, 201, 63))
    
    # Window Title
    draw.text((120, 35), "IntentGuard — Autonomous Intent Verification", fill=(200, 210, 230), font=font_sans_md)
    
    # Scene indicator on right
    scene_str = f"Scene {scene_num}/{total_scenes}: {title}"
    draw.text((WIDTH - 360, 36), scene_str, fill=(96, 165, 250), font=font_sans_sm)

def draw_bottom_bar(draw, active_scene):
    # Scrubber background
    draw.rectangle([45, HEIGHT - 55, WIDTH - 45, HEIGHT - 35], fill=(18, 22, 36))
    pct = (active_scene / 5.0)
    fill_w = int(45 + pct * (WIDTH - 90))
    draw.rectangle([45, HEIGHT - 52, fill_w, HEIGHT - 38], fill=(99, 102, 241))
    
    # Badges
    scenes = ["1. Spec Void", "2. Silent Drift", "3. AST Scan", "4. Verdict", "5. FastMCP"]
    spacing = (WIDTH - 120) // 5
    for i, s in enumerate(scenes):
        color = (255, 255, 255) if (i + 1) == active_scene else (100, 116, 139)
        draw.text((55 + i * spacing, HEIGHT - 30), s, fill=color, font=font_sans_sm)

frames = []

# --- SCENE 1: The Intent-to-Implementation Void (4 frames) ---
for sub in range(4):
    img = Image.new("RGB", (WIDTH, HEIGHT), (8, 10, 18))
    d = ImageDraw.Draw(img)
    draw_window_chrome(d, "The Intent-to-Implementation Void", 1)
    
    # Left: JIRA Spec
    d.rounded_rectangle([45, 80, 440, HEIGHT - 70], radius=8, fill=(16, 22, 38), outline=(40, 52, 82), width=1)
    d.text((65, 95), "PRODUCT SPEC / JIRA-104", fill=(56, 189, 248), font=font_sans_bold)
    d.text((65, 125), "• REQ-1: Route POST /api/v1/auth/login", fill=(226, 232, 240), font=font_mono_md)
    d.text((65, 155), "• REQ-2: Sign JWT using RS256 RSA Key", fill=(226, 232, 240), font=font_mono_md)
    d.text((65, 185), "• REQ-3: Hash password with bcrypt(rounds=12)", fill=(226, 232, 240), font=font_mono_md)
    d.text((65, 215), "• REQ-4: Rate limit 5 req/15min on failure", fill=(226, 232, 240), font=font_mono_md)
    d.text((65, 255), "Input: Prompt fed into AI coding assistant", fill=(148, 163, 184), font=font_sans_sm)

    # Right: AI Assistant output
    d.rounded_rectangle([465, 80, WIDTH - 45, HEIGHT - 70], radius=8, fill=(12, 16, 28), outline=(40, 52, 82), width=1)
    d.text((485, 95), "CURSOR / COPILOT GENERATING...", fill=(168, 85, 247), font=font_sans_bold)
    
    files = [
        ("app/auth/router.py", (148, 163, 184)),
        ("app/auth/security.py", (148, 163, 184)),
        ("app/db/models.py", (148, 163, 184)),
        ("app/admin/override.py (UNREQUESTED)", (239, 68, 68)),
    ]
    for idx, (f, c) in enumerate(files[:sub + 1]):
        d.text((485, 135 + idx * 32), f"+ {f}", fill=c, font=font_mono_md)
        
    d.rounded_rectangle([485, 300, WIDTH - 65, 360], radius=6, fill=(30, 27, 75), outline=(99, 102, 241), width=1)
    d.text((505, 315), "Does this generated code match intent?", fill=(199, 210, 254), font=font_sans_bold)
    d.text((505, 335), "Reviewers glance and assume it does.", fill=(148, 163, 184), font=font_sans_sm)

    draw_bottom_bar(d, 1)
    frames.append((img, 700))

# --- SCENE 2: Zooming In on Dangerous Silent Drift (4 frames) ---
for sub in range(4):
    img = Image.new("RGB", (WIDTH, HEIGHT), (8, 10, 18))
    d = ImageDraw.Draw(img)
    draw_window_chrome(d, "Zoom: 3 Critical Misinterpretations", 2)
    
    # Zoomed box
    d.rounded_rectangle([45, 80, WIDTH - 45, HEIGHT - 70], radius=8, fill=(15, 18, 30), outline=(239, 68, 68), width=2)
    d.text((65, 95), "SILENT DRIFT & VULNERABILITIES FOUND IN DIFF", fill=(248, 113, 113), font=font_sans_bold)
    
    flaws = [
        ("❌ FLAW 1: Cryptographic Downgrade", "- password_hash = hashlib.sha256(pw)", "+ REQUIREMENT: bcrypt.hashpw(pw, rounds=12)", (239, 68, 68)),
        ("❌ FLAW 2: Token Algorithm Downgrade", "- jwt.encode(payload, key, algorithm='HS256')", "+ REQUIREMENT: RS256 RSA Private Key", (245, 158, 11)),
        ("🚨 FLAW 3: Dangerous Scope Creep", "@app.post('/admin/reset-password-override')", "Unrequested endpoint allows unauthenticated resets!", (168, 85, 247)),
    ]
    
    y = 130
    for idx, (title_flaw, bad, good, col) in enumerate(flaws):
        d.rounded_rectangle([65, y, WIDTH - 65, y + 68], radius=6, fill=(24, 20, 35), outline=col, width=1)
        d.text((80, y + 8), title_flaw, fill=col, font=font_mono_md)
        d.text((80, y + 28), bad, fill=(252, 165, 165), font=font_mono_sm)
        d.text((80, y + 46), good, fill=(110, 231, 183), font=font_mono_sm)
        y += 78

    draw_bottom_bar(d, 2)
    frames.append((img, 800))

# --- SCENE 3: IntentGuard Neural & AST Laser Sweep (8 frames) ---
for sub in range(8):
    img = Image.new("RGB", (WIDTH, HEIGHT), (8, 10, 18))
    d = ImageDraw.Draw(img)
    draw_window_chrome(d, "2-Pass Neural Sweep & Deterministic AST", 3)
    
    # Split view
    d.rounded_rectangle([45, 80, 440, HEIGHT - 70], radius=8, fill=(16, 22, 38), outline=(56, 189, 248), width=1)
    d.text((65, 95), "PASS 1: Requirement Extraction", fill=(56, 189, 248), font=font_sans_bold)
    
    req_items = [
        ("REQ-1: /api/v1/auth/login", "EXTRACTED ✓", (52, 211, 153)),
        ("REQ-2: RS256 Keypair", "EXTRACTED ✓", (52, 211, 153)),
        ("REQ-3: bcrypt rounds=12", "EXTRACTED ✓", (52, 211, 153)),
        ("REQ-4: 5 req/15min Limit", "EXTRACTED ✓", (52, 211, 153)),
    ]
    for idx, (req_title, stat, c) in enumerate(req_items):
        d.text((65, 135 + idx * 36), req_title, fill=(226, 232, 240), font=font_mono_md)
        d.text((320, 135 + idx * 36), stat, fill=c, font=font_mono_md)

    # Right: AST & Diff
    d.rounded_rectangle([465, 80, WIDTH - 45, HEIGHT - 70], radius=8, fill=(16, 20, 36), outline=(99, 102, 241), width=1)
    d.text((485, 95), "PASS 2: AST Static Cross-Reference", fill=(129, 140, 248), font=font_sans_bold)
    
    ast_items = [
        ("check_python_syntax()", "AST VALID ✓", (52, 211, 153)),
        ("parse_diff_metadata()", "14 Files / 280 lines", (148, 163, 184)),
        ("AST Hash Call", "MISMATCH: SHA-256 ✗", (239, 68, 68)),
        ("AST JWT Call", "MISMATCH: HS256 ✗", (245, 158, 11)),
        ("Ingress Route Check", "SCOPE CREEP ! ", (168, 85, 247)),
    ]
    for idx, (ast_title, stat, c) in enumerate(ast_items):
        d.text((485, 135 + idx * 32), ast_title, fill=(226, 232, 240), font=font_mono_sm)
        d.text((700, 135 + idx * 32), stat, fill=c, font=font_mono_sm)

    # Cyan Laser Scan Beam sweeping top to bottom
    scan_y = int(90 + (sub / 7.0) * (HEIGHT - 170))
    d.rectangle([45, scan_y - 2, WIDTH - 45, scan_y + 2], fill=(0, 240, 255))
    d.rectangle([45, scan_y - 8, WIDTH - 45, scan_y + 8], fill=(0, 240, 255, 60))

    draw_bottom_bar(d, 3)
    frames.append((img, 300))

# --- SCENE 4: Compliance Scorecard Verdict (4 frames) ---
for sub in range(4):
    img = Image.new("RGB", (WIDTH, HEIGHT), (8, 10, 18))
    d = ImageDraw.Draw(img)
    draw_window_chrome(d, "Executive Audit Scorecard (FAIL)", 4)
    
    # Verdict Card
    d.rounded_rectangle([45, 80, WIDTH - 45, 135], radius=8, fill=(40, 18, 28), outline=(239, 68, 68), width=2)
    d.rounded_rectangle([65, 92, 200, 122], radius=6, fill=(239, 68, 68))
    d.text((80, 98), "VERDICT: FAIL", fill=(255, 255, 255), font=font_sans_bold)
    d.text((220, 98), "Confidence: 1.00  •  Violations Quarantined Before Merge", fill=(252, 165, 165), font=font_sans_md)
    
    # Matrix Table
    d.rounded_rectangle([45, 150, WIDTH - 45, HEIGHT - 70], radius=8, fill=(14, 18, 32), outline=(40, 52, 82), width=1)
    d.text((65, 165), "ID       REQUIREMENT               STATUS          EVIDENCE", fill=(148, 163, 184), font=font_mono_md)
    d.line([65, 185, WIDTH - 65, 185], fill=(40, 52, 82), width=1)
    
    table = [
        ("REQ-1", "POST /api/v1/auth/login", "✅ Implemented", "router.py:46", (52, 211, 153)),
        ("REQ-2", "RS256 JWT Signing", "🔄 Misinterpreted", "Found HS256", (245, 158, 11)),
        ("REQ-3", "bcrypt Password Hashing", "❌ Missing", "Found sha256", (239, 68, 68)),
        ("CREEP", "/admin/reset-password", "🚨 Scope Creep", "override.py", (168, 85, 247)),
    ]
    for idx, (rid, req, stat, ev, col) in enumerate(table):
        y = 200 + idx * 30
        d.text((65, y), rid, fill=(96, 165, 250), font=font_mono_md)
        d.text((150, y), req, fill=(226, 232, 240), font=font_mono_md)
        d.text((420, y), stat, fill=col, font=font_mono_md)
        d.text((620, y), ev, fill=(148, 163, 184), font=font_mono_md)

    draw_bottom_bar(d, 4)
    frames.append((img, 800))

# --- SCENE 5: In-Editor FastMCP Integration (4 frames) ---
for sub in range(4):
    img = Image.new("RGB", (WIDTH, HEIGHT), (8, 10, 18))
    d = ImageDraw.Draw(img)
    draw_window_chrome(d, "FastMCP: Cursor & Antigravity In-Editor", 5)
    
    # Editor mock
    d.rounded_rectangle([45, 80, WIDTH - 45, HEIGHT - 70], radius=8, fill=(14, 18, 32), outline=(99, 102, 241), width=1)
    
    # Cursor Command Palette
    d.rounded_rectangle([180, 100, WIDTH - 180, 145], radius=8, fill=(30, 41, 59), outline=(96, 165, 250), width=2)
    d.text((200, 112), "> IntentGuard: Audit Staged Changes against PRD", fill=(255, 255, 255), font=font_mono_md)
    
    # Result overlay inside editor
    d.rounded_rectangle([100, 165, WIDTH - 100, HEIGHT - 90], radius=8, fill=(10, 14, 26), outline=(52, 211, 153), width=1)
    d.text((120, 185), "⚡ FAST-MCP AUDIT COMPLETE (2.4s)", fill=(52, 211, 153), font=font_sans_bold)
    d.text((120, 215), "• Staged Diff: 2 files, 46 additions, 2 deletions", fill=(203, 213, 225), font=font_mono_sm)
    d.text((120, 240), "• Security Guardrails: Prompt injection scan PASS (0 threats)", fill=(52, 211, 153), font=font_mono_sm)
    d.text((120, 265), "• Intent Drift Detected: 2 violations require revision before commit", fill=(248, 113, 113), font=font_mono_sm)
    d.text((120, 290), "• Generated Markdown scorecard written to INTENTGUARD_REPORT.md", fill=(148, 163, 184), font=font_mono_sm)

    draw_bottom_bar(d, 5)
    frames.append((img, 800))

# Save animated GIF
images = [f[0] for f in frames]
durations = [f[1] for f in frames]

output_path = "/Users/apoorv/Documents/open-source-agents/agents/intent-guard/demo.gif"
images[0].save(
    output_path,
    save_all=True,
    append_images=images[1:],
    optimize=True,
    duration=durations,
    loop=0
)
print(f"Animated demo GIF successfully saved to {output_path}")
