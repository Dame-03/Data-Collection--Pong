from os import environ
environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'

import math
import sys
import random
import pygame

import csv, time, os
LOG_FILENAME = f"match_log_{time.strftime('%Y%m%d_%H%M%S')}.csv"
if not os.path.exists(LOG_FILENAME):
    with open(LOG_FILENAME, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "rally_index",
            "paddle_hits",
            "end_ball_speed_px_per_frame",
            "rally_duration_s",
            "p1_ability_uses",
            "p2_ability_uses",
            "winner",
            "p1_win_within_8s_after_ability",
            "p2_win_within_8s_after_ability",
        ])

# --- per-rally tracking (vars + helpers) ---
# globals for one rally
rally_index = 0
rally_start_ms = 0
paddle_hits = 0
p1_ability_uses = 0
p2_ability_uses = 0
p1_last_ability_ms = None
p2_last_ability_ms = None

def begin_rally(now_ms: int):
    """Call this exactly when a new serve begins."""
    global rally_index, rally_start_ms, paddle_hits, p1_ability_uses, p2_ability_uses
    global p1_last_ability_ms, p2_last_ability_ms
    rally_index += 1
    rally_start_ms = now_ms
    paddle_hits = 0
    p1_ability_uses = 0
    p2_ability_uses = 0
    p1_last_ability_ms = None
    p2_last_ability_ms = None

def log_rally_row(winner: str, end_vx: float, end_vy: float, now_ms: int):
    """Append one CSV row for the rally that just ended."""
    import math
    duration_s = (now_ms - rally_start_ms) / 1000.0
    end_speed = math.hypot(end_vx, end_vy)  # pixels/frame
    p1_win_within_8s = (winner == "P1") and (p1_last_ability_ms is not None) and ((now_ms - p1_last_ability_ms) <= 8000)
    p2_win_within_8s = (winner == "P2") and (p2_last_ability_ms is not None) and ((now_ms - p2_last_ability_ms) <= 8000)
    with open(LOG_FILENAME, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            rally_index,
            paddle_hits,
            f"{end_speed:.3f}",
            f"{duration_s:.3f}",
            p1_ability_uses,
            p2_ability_uses,
            winner,
            str(bool(p1_win_within_8s)).lower(),
            str(bool(p2_win_within_8s)).lower(),
        ])

pygame.mixer.pre_init(44100, -16, 2, 512)

pygame.init()

# ----------------- GLOBALS / CONSTANTS -----------------
WIDTH, HEIGHT = 1200, 600
BLUE   = (0, 0, 255)
RED    = (255, 0, 0)
GREEN  = (0, 255, 0)
BLACK  = (0, 0, 0)
WHITE  = (255, 255, 255)
LIGHT_BLUE = (135, 206, 250)
YELLOW = (255, 215, 0)
HUD_BG = (20, 20, 20)
HUD_BORDER = (80, 80, 80)
JARVIS_COLOR = (80, 180, 255)

# Height of top HUD band (gameplay can't enter this area)
HUD_H = 80

# How close paddles may get to the midline when flying horizontally (px)
CENTER_MARGIN = 350  # smaller = can get closer to center

wn = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
pygame.display.set_caption("Pong")
clock = pygame.time.Clock()

# Fonts (cached once)
FONT_TITLE = pygame.font.SysFont('calibri', 64)
FONT_SUB   = pygame.font.SysFont('calibri', 26)
FONT_ITEM  = pygame.font.SysFont('calibri', 32)
FONT_DESC  = pygame.font.SysFont('calibri', 24)
FONT_NAME  = pygame.font.SysFont('calibri', 26, bold=True)
FONT_SMALL = pygame.font.SysFont('calibri', 22)
FONT_SCORE = pygame.font.SysFont('calibri', 28, bold=True)
FONT_WIN   = pygame.font.SysFont('calibri', 100)

# ----------------- BALL -----------------
radius = 10

def random_ball_velocity():
    # Random speed per-axis in 2.0–2.5 px/frame, random direction
    sx = random.uniform(2.0, 2.5) * (1 if random.random() < 0.5 else -1)
    sy = random.uniform(2.0, 2.5) * (1 if random.random() < 0.5 else -1)
    return sx, sy

# Ball state (center coords + velocity)
ball_x, ball_y = WIDTH / 2, HUD_H + (HEIGHT - HUD_H) / 2
ball_vel_x, ball_vel_y = 0.0, 0.0

# ----------------- PADDLES -----------------
paddle_width, paddle_height = 20, 120
left_x  = 60 - paddle_width / 2
left_y  = HUD_H + (HEIGHT - HUD_H - paddle_height) / 2
right_x = WIDTH - (60 + paddle_width / 2)
right_y = HUD_H + (HEIGHT - HUD_H - paddle_height) / 2

left_pad_vel  = 0.0
right_pad_vel = 0.0
PADDLE_SPEED  = 4.0  # px/frame

# ----------------- PHYSICS TUNING -----------------
MAX_DEFLECT_DEG = 60
SPEEDUP_PER_HIT = 1.20
MIN_SPEED       = 2.0
MAX_SPEED       = 50.0

# ----------------- GAME STATES -----------------
STATE_MENU  = "menu"
STATE_SERVE = "serve"
STATE_PLAY  = "play"

state   = STATE_MENU
server  = "left"
serve_vx, serve_vy = 0.0, 0.0

# ----------------- SCORE -----------------
score_left  = 0
score_right = 0
points_to_win = 5

# -------- IRON MAN CONFIG --------
IRON_X_NUDGE_SPEED = 3.0        # passive horizontal nudge speed
IRON_ABILITY_SPEED = 5.5        # absolute paddle speed during ability
IRON_ABILITY_MS    = 9000       # 9 seconds

# -------- QUICKSILVER CONFIG --------
QUICKSILVER_SPEED_BOOST = 3.5   # passive: px/frame over base paddle speed
QUICKSILVER_ABILITY_MS  = 18000  # 18 seconds
QUICKSILVER_FREEZE_MS   = 2000   # initial 2s freeze (enemy + real ball)
QUICKSILVER_HIT_FORCE   = 1.35   # extra hit force multiplier during ability
QUICKSILVER_MUSIC_PATH = r"assets/sweet_dreams_V1.ogg"

# Per-player horizontal offsets for passive (Iron Man only)
left_x_offset  = 0.0
right_x_offset = 0.0

# -------- INVISIBLE WOMAN CONFIG --------
INVIS_PASSIVE_MS = 750  # ~.75 s freeze
freeze_left_until_ms  = 0
freeze_right_until_ms = 0
p1_invis_passive_used = False
p2_invis_passive_used = False

p1_invis_hide_pending = False  # ability: next hit hides the ball
p2_invis_hide_pending = False
ball_invisible = False
last_ball_x = ball_x  # will be refreshed in reset_ball each rally

# -------- LOKI CONFIG --------
LOKI_RAND_MIN_DEG = 12   # min ball bounce degree range 
LOKI_RAND_MAX_DEG = 40   # max ball bounce degree range 
LOKI_MIN_SEP_DEG  = 10   # min separation between the two fake-ball angles
CLONE_SPAWN_GAP = 75             # Clone spawn gap (px) so it doesn’t overlap at spawn


# Per-player meters and timers (generic for all characters)
p1_meter = 0   # 0..8
p2_meter = 0   # 0..8
METER_MAX = 8

p1_ability_until_ms = 0
p2_ability_until_ms = 0

# Quicksilver ability timers + music flag
p1_qs_freeze_until_ms = 0  # LEFT side is frozen when RIGHT uses QS
p2_qs_freeze_until_ms = 0  # RIGHT side is frozen when LEFT uses QS
p1_qs_until_ms = 0
p2_qs_until_ms = 0
qs_music_on = False

# Loki "next hit will split ball" flags
p1_loki_split_pending = False
p2_loki_split_pending = False

# Loki hologram paddle active flags
holo_left_active  = False  # hologram on LEFT side (appears when RIGHT-as-Loki hits)
holo_right_active = False  # hologram on RIGHT side (appears when LEFT-as-Loki hits)

# Fake (illusory) balls list
# Each: {"x":float,"y":float,"vx":float,"vy":float}
fake_balls = []

# Double-press detection
last_key_press_time = {}
DOUBLE_PRESS_THRESHOLD = 250  # ms

# ----------------- POWER-UP MENU -----------------
POWERUPS = [
    {"name": "Iron Man",
     "desc": "(Passive) Rocket boosters: Use A/D or </> to move horizontally\n\n"
             "(Ability) Jarvis lock-in: Double-press 'D' or '<' to show ball trajectory only when it’s coming towards you. Also gain temporary speed boost. Ability lasts for 9 seconds"},
    {"name": "Loki",
     "desc": "(Passive) Doppelganger: When you hit the ball, an illusion of the enemy spawns on their side.\n\n"
             "(Ability) God of Mischief: Double-press 'D' or '<' to create illusions of the ball on your next hit. Total of 3 balls on the field"},
    {"name": "Invisible Woman",
     "desc": "(Passive) Force Field: Use 'A' or '>' to temporarily prevent enemy movement. One use per round. \n\n"
             "(Ability) Disappear: Double-press 'D' or '<' to turn the ball invisible on your next hit. Ball loses invisibility when crossing center of field"},
    {"name": "QuickSilver",
     "desc": "(Passive) Speedster: Gain speed boost\n\n"
             "(Ability) Sweet Dreams: Double-press 'D' or '<' to slow down the entire game. Slowness doesn't apply to you. Gain extra hit force on the ball. Ability last for 18 seconds"},
]

p1_idx = 0
p2_idx = 0
p1_ready = False
p2_ready = False
p1_power = None
p2_power = None

# Cached hologram paddle surfaces (built when match starts)
LEFT_GHOST_SURF = None  # shows LEFT player's skin ghost (drawn on left side)
RIGHT_GHOST_SURF = None # shows RIGHT player's skin ghost (drawn on right side)

# ----------------- HELPERS -----------------
def apply_resize(new_w, new_h):
    """Update globals and surface when the window is resized."""
    global WIDTH, HEIGHT, wn, right_x, ball_x, ball_y, left_y, right_y

    WIDTH, HEIGHT = int(new_w), int(new_h)
    wn = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)

    # Recompute right paddle base x (depends on WIDTH)
    right_x = WIDTH - (60 + paddle_width / 2)

    # Clamp paddles inside playfield (below HUD)
    if left_y < HUD_H: left_y = HUD_H
    if left_y + paddle_height > HEIGHT: left_y = HEIGHT - paddle_height
    if right_y < HUD_H: right_y = HUD_H
    if right_y + paddle_height > HEIGHT: right_y = HEIGHT - paddle_height

    # Keep ball inside new bounds (respect HUD top)
    if ball_x < radius: ball_x = radius
    if ball_x > WIDTH - radius: ball_x = WIDTH - radius
    if ball_y < HUD_H + radius: ball_y = HUD_H + radius
    if ball_y > HEIGHT - radius: ball_y = HEIGHT - radius


def draw_wrapped_text(surface, text, font, color, rect,
                      line_spacing_px=0,
                      paragraph_spacing_px=None,
                      first_line_indent_px=24,
                      subsequent_indent_px=0,
                      v_align='top'):
    """
    Paragraph-aware text drawing with optional vertical centering and first-line indents.
    Paragraphs split on '\n\n'.
    """
    paragraphs = [p.strip() for p in text.split("\n\n")]
    if not paragraphs:
        return rect.y

    if paragraph_spacing_px is None:
        paragraph_spacing_px = font.get_linesize()

    max_w = rect.w
    line_h = font.get_linesize()

    wrapped_lines = []
    for para in paragraphs:
        words = para.split()
        if not words:
            wrapped_lines.append(("", first_line_indent_px))
            wrapped_lines.append((None, paragraph_spacing_px))
            continue

        indent_first  = first_line_indent_px
        indent_follow = subsequent_indent_px

        line = ""
        indent = indent_first
        for w in words:
            candidate = (line + " " + w).strip()
            if font.size(candidate)[0] <= max_w - indent:
                line = candidate
            else:
                wrapped_lines.append((line, indent))
                line = w
                indent = indent_follow
        if line:
            wrapped_lines.append((line, indent))
        wrapped_lines.append((None, paragraph_spacing_px))

    if wrapped_lines and wrapped_lines[-1][0] is None:
        wrapped_lines.pop()

    total_height = 0
    for text_line, indent in wrapped_lines:
        if text_line is None:
            total_height += indent
        else:
            total_height += line_h + line_spacing_px

    if v_align == 'middle':
        y = rect.y + max(0, (rect.h - total_height) // 2)
    else:
        y = rect.y

    x0 = rect.x
    for text_line, indent in wrapped_lines:
        if text_line is None:
            y += indent
            continue
        surface.blit(font.render(text_line, True, color), (x0 + indent, y))
        y += line_h + line_spacing_px

    return y


# ---- game helpers ----
def get_paddle_rects():
    """Return (left_rect, right_rect) including current horizontal offsets."""
    lx = int(left_x  + left_x_offset)
    rx = int(right_x + right_x_offset)
    left_rect  = pygame.Rect(lx,  int(left_y),  int(paddle_width), int(paddle_height))
    right_rect = pygame.Rect(rx,  int(right_y), int(paddle_width), int(paddle_height))
    return left_rect, right_rect


def bounce_top_bottom(y, vy):
    """Bounce with damping against HUD ceiling and floor. Returns new (y, vy)."""
    if y - radius <= HUD_H:
        y = HUD_H + radius
        vy *= -0.8
    elif y + radius >= HEIGHT:
        y = HEIGHT - radius
        vy *= -0.8
    return y, vy

#----------------- IRON MAN HELPERS -----------------
def compute_trajectory_points(x, y, vx, vy, target_x, height, radius, max_bounces=12):
    """
    Predict piecewise-linear path with top/bottom bounces until reaching target_x.
    Uses HUD_H as the top wall. Only valid if vx is toward target_x.
    """
    pts = [(x, y)]
    if (target_x - x) * vx <= 0:
        return pts  # not moving toward target
    cx, cy = x, y
    sx, sy = vx, vy
    while len(pts) < max_bounces + 2:
        t_top    = float('inf') if sy >= 0 else ((HUD_H + radius - cy) / sy)
        t_bottom = float('inf') if sy <= 0 else (((height - radius) - cy) / sy)
        t_y = min(t_top, t_bottom)
        t_x = (target_x - cx) / sx
        if t_x <= t_y:
            hit_y = cy + sy * t_x
            pts.append((target_x, hit_y))
            break
        else:
            nx = cx + sx * t_y
            ny = cy + sy * t_y
            pts.append((nx, ny))
            sy = -sy
            ny = max(HUD_H + radius, min(height - radius, ny))
            cx, cy = nx, ny
    return pts


def draw_dotted_polyline(surface, points, color, dot_len=6, gap_len=6, width=2):
    """Draw dotted polyline along the given points list."""
    if len(points) < 2:
        return
    for i in range(len(points) - 1):
        x1, y1 = points[i]
        x2, y2 = points[i+1]
        dx, dy = x2 - x1, y2 - y1
        dist = math.hypot(dx, dy)
        if dist == 0:
            continue
        ux, uy = dx / dist, dy / dist
        t = 0.0
        while t < dist:
            seg_end = min(t + dot_len, dist)
            sx, sy = x1 + ux * t,       y1 + uy * t
            ex, ey = x1 + ux * seg_end, y1 + uy * seg_end
            pygame.draw.line(surface, color, (int(sx), int(sy)), (int(ex), int(ey)), width)
            t = seg_end + gap_len

def draw_jarvis_if_active():
    """Draw Iron Man dotted trajectory when active (both sides)."""
    now = pygame.time.get_ticks()
    if state != STATE_PLAY:
        return

    # Left Iron Man (incoming toward left)
    if (p1_power == "Iron Man" and now < p1_ability_until_ms and ball_vel_x < 0):
        target_x = (left_x + left_x_offset) + paddle_width
        pts = compute_trajectory_points(ball_x, ball_y, ball_vel_x, ball_vel_y,
                                        target_x, HEIGHT, radius)
        if len(pts) >= 2:
            draw_dotted_polyline(wn, pts, JARVIS_COLOR, dot_len=6, gap_len=6, width=2)

    # Right Iron Man (incoming toward right)
    if (p2_power == "Iron Man" and now < p2_ability_until_ms and ball_vel_x > 0):
        target_x = (right_x + right_x_offset)
        pts = compute_trajectory_points(ball_x, ball_y, ball_vel_x, ball_vel_y,
                                        target_x, HEIGHT, radius)
        if len(pts) >= 2:
            draw_dotted_polyline(wn, pts, JARVIS_COLOR, dot_len=6, gap_len=6, width=2)


#------------------- Quicksilver music helpers-------------------

def quicksilver_any_active(now_ms=None):
    now = pygame.time.get_ticks() if now_ms is None else now_ms
    return ((p1_power == "QuickSilver" and now < p1_qs_until_ms) or
            (p2_power == "QuickSilver" and now < p2_qs_until_ms))


def start_quicksilver_music():
    global qs_music_on
    if qs_music_on:
        return
    pygame.mixer.music.load(QUICKSILVER_MUSIC_PATH)
    pygame.mixer.music.set_volume(1)
    pygame.mixer.music.play(-1)
    qs_music_on = True


def update_quicksilver_music(now_ms):
    global qs_music_on
    if qs_music_on and not quicksilver_any_active(now_ms):
        pygame.mixer.music.stop()
        qs_music_on = False

# -------------------- Drawing helpers --------------------
def draw_paddle(surface, rect, power_name, side):
    """
    Draws a paddle with a character-specific skin.
    side: "left" or "right".
    """
    # default fallback coloring
    base = RED if side == "left" else GREEN

    if power_name == "Iron Man":
        # Red body
        pygame.draw.rect(surface, RED, rect)
        # Arc reactor: yellow ring + blue core, centered
        cx, cy = rect.center
        outer_r = max(6, rect.w // 2 - 2)
        inner_r = max(3, int(outer_r * 0.55))
        pygame.draw.circle(surface, YELLOW, (cx, cy), outer_r)
        pygame.draw.circle(surface, BLUE,   (cx, cy), inner_r)
        pygame.draw.rect(surface, WHITE, rect, 1)
        return

    if power_name == "Loki":
        # Dark green body
        body = (20, 90, 50)
        pygame.draw.rect(surface, body, rect)
    
        # Face line near the edge facing center
        face_edge_x = rect.right if side == "left" else rect.left
        line_x = face_edge_x - 3 if side == "left" else face_edge_x + 3
        pygame.draw.line(surface, YELLOW, (line_x, rect.top + 6), (line_x, rect.bottom - 6), 3)
    
        # Horns OUTSIDE the paddle, pointing toward the center
        horn_len = 14
        horn_th  = 7
        if side == "left":
            # center to the right → horns extend out to the right
            top_base = (rect.right, rect.top + 8)
            bot_base = (rect.right, rect.bottom - 8)
            tri_top = [
                (top_base[0] + horn_len, top_base[1]),  # tip toward center
                (top_base[0] + 2,        top_base[1] - horn_th),
                (top_base[0] + 2,        top_base[1] + horn_th),
            ]
            tri_bot = [
                (bot_base[0] + horn_len, bot_base[1]),
                (bot_base[0] + 2,        bot_base[1] - horn_th),
                (bot_base[0] + 2,        bot_base[1] + horn_th),
            ]
        else:
            # center to the left → horns extend out to the left
            top_base = (rect.left, rect.top + 8)
            bot_base = (rect.left, rect.bottom - 8)
            tri_top = [
                (top_base[0] - horn_len, top_base[1]),  # tip toward center
                (top_base[0] - 2,        top_base[1] - horn_th),
                (top_base[0] - 2,        top_base[1] + horn_th),
            ]
            tri_bot = [
                (bot_base[0] - horn_len, bot_base[1]),
                (bot_base[0] - 2,        bot_base[1] - horn_th),
                (bot_base[0] - 2,        bot_base[1] + horn_th),
            ]
    
        pygame.draw.polygon(surface, YELLOW, tri_top)
        pygame.draw.polygon(surface, YELLOW, tri_bot)
    
        pygame.draw.rect(surface, WHITE, rect, 1)
        return

    if power_name == "Invisible Woman":
        # Light blue body with a white "4" centered
        pygame.draw.rect(surface, LIGHT_BLUE, rect)
        # Draw a bold white "4" in the center (size depends on rect)
        fs = max(12, int(rect.h * 0.4))
        font4 = pygame.font.SysFont('calibri', fs, bold=True)
        t4 = font4.render("4", True, WHITE)
        surface.blit(t4, (rect.centerx - t4.get_width() // 2,
                          rect.centery - t4.get_height() // 2))
        pygame.draw.rect(surface, WHITE, rect, 1)
        return

    if power_name == "QuickSilver":
        # Light blue paddle with a whitish-gray lightning bolt
        pygame.draw.rect(surface, LIGHT_BLUE, rect)

        w, h = rect.w, rect.h
        x0, y0 = rect.x, rect.y
        bolt = [
            (x0 + int(0.22*w), y0 + int(0.06*h)),
            (x0 + int(0.58*w), y0 + int(0.06*h)),
            (x0 + int(0.42*w), y0 + int(0.46*h)),
            (x0 + int(0.76*w), y0 + int(0.46*h)),
            (x0 + int(0.30*w), y0 + int(0.94*h)),
            (x0 + int(0.46*w), y0 + int(0.54*h)),
            (x0 + int(0.22*w), y0 + int(0.54*h)),
        ]
        pygame.draw.polygon(surface, (150, 150, 150), bolt)  # whitish-gray
        pygame.draw.rect(surface, WHITE, rect, 1)
        return
    
    # Default (no skin yet)
    pygame.draw.rect(surface, base, rect)


# -------------------- Loki helpers --------------------
def draw_hologram_paddle_cached(surface, rect, side):
    """Draw hologram using the enemy's skin directly so Loki horns render outside the paddle bounds."""
    power = p1_power if side == "left" else p2_power
    # Draw directly onto the main surface so off-rect details (Loki horns) are not clipped
    draw_paddle(surface, rect, power, side)


def random_angle_vec(speed, toward_right, deg_min=LOKI_RAND_MIN_DEG, deg_max=LOKI_RAND_MAX_DEG):
    """Return (vx,vy) of length 'speed' with a random angle measured off the horizontal."""
    ang = math.radians(random.uniform(deg_min, deg_max))
    if random.random() < 0.5:
        ang = -ang
    base = 0.0 if toward_right else math.pi  # 0 = +x, pi = -x
    a = base + ang
    return speed * math.cos(a), speed * math.sin(a)


def spawn_loki_fake_balls(out_x, out_y, out_vx, out_vy):
    """Spawn two fake balls at independent random angles; both keep the real ball's speed."""
    s = math.hypot(out_vx, out_vy)
    if s < 1e-6:
        return

    toward_right = (out_vx > 0)

    # pick two distinct random angles (relative to horizontal), ensure separation
    def pick_angle_deg():
        d = random.uniform(LOKI_RAND_MIN_DEG, LOKI_RAND_MAX_DEG)
        return (+d if random.random() < 0.5 else -d)

    a1 = pick_angle_deg()
    while True:
        a2 = pick_angle_deg()
        if abs(a2 - a1) >= LOKI_MIN_SEP_DEG:
            break

    # convert to vectors
    base = 0.0 if toward_right else math.pi
    a1r = math.radians(a1) + base
    a2r = math.radians(a2) + base

    v1x, v1y = s * math.cos(a1r), s * math.sin(a1r)
    v2x, v2y = s * math.cos(a2r), s * math.sin(a2r)

    fake_balls.append({"x": out_x, "y": out_y, "vx": v1x, "vy": v1y})
    fake_balls.append({"x": out_x, "y": out_y, "vx": v2x, "vy": v2y})


# Hologram Y-follow logic (unchanged behavior)
holo_left_sign = 0
holo_right_sign = 0

def mirror_y_of(enemy_y, side):
    global holo_left_sign, holo_right_sign
    sign = holo_left_sign if side == "left" else holo_right_sign

    if sign == 0:
        above_ok = (enemy_y - (paddle_height + CLONE_SPAWN_GAP)) >= HUD_H
        below_ok = (enemy_y + paddle_height + CLONE_SPAWN_GAP + paddle_height) <= HEIGHT
        if above_ok and below_ok:
            sign = random.choice([-1, 1])
        elif above_ok:
            sign = -1
        elif below_ok:
            sign = +1
        else:
            space_above = enemy_y - HUD_H
            space_below = HEIGHT - (enemy_y + paddle_height)
            sign = -1 if space_above >= space_below else +1
        if side == "left":
            holo_left_sign = sign
        else:
            holo_right_sign = sign

    y = enemy_y + sign * (paddle_height + CLONE_SPAWN_GAP)
    y = max(HUD_H, min(HEIGHT - paddle_height, y))
    return y


# -------------------- Collisions  --------------------
def paddle_bounce_for_left(left_rect, ball_rect):
    global ball_x, ball_vel_x, ball_vel_y
    global p1_meter, holo_left_active, holo_right_active, p1_loki_split_pending
    global ball_invisible, last_ball_x, p1_invis_hide_pending
    global paddle_hits 

    if not (ball_rect.colliderect(left_rect) and ball_vel_x < 0):
        return

    # snap just outside paddle
    ball_x = left_rect.right + radius

    # Meter: left player hit +1
    p1_meter = min(METER_MAX, p1_meter + 1)
    paddle_hits += 1

    # normalized contact offset (-1..+1): top=-1, center=0, bottom=+1
    offset = (ball_y - (left_y + paddle_height / 2)) / (paddle_height / 2)

    # target angle
    max_angle = math.radians(MAX_DEFLECT_DEG)
    angle = offset * max_angle

    # keep current speed magnitude (at least MIN_SPEED)
    speed = max(MIN_SPEED, math.hypot(ball_vel_x, ball_vel_y))

    # outgoing to the right
    ball_vel_x =  speed * math.cos(angle)
    ball_vel_y =  speed * math.sin(angle)

    # speed up
    ball_vel_x *= SPEEDUP_PER_HIT
    ball_vel_y *= SPEEDUP_PER_HIT

    # Quicksilver extra hit force when ability active
    if p1_power == "QuickSilver" and pygame.time.get_ticks() < p1_qs_until_ms:
        ball_vel_x *= QUICKSILVER_HIT_FORCE
        ball_vel_y *= QUICKSILVER_HIT_FORCE

    # clamp to MAX_SPEED
    new_speed = math.hypot(ball_vel_x, ball_vel_y)
    if new_speed > MAX_SPEED:
        s = MAX_SPEED / new_speed
        ball_vel_x *= s
        ball_vel_y *= s

    if p1_power == "Invisible Woman" and p1_invis_hide_pending:
        ball_invisible = True
        last_ball_x = ball_x
        p1_invis_hide_pending = False
    
    # ---- Loki collision ----
    if p1_power == "Loki":
        holo_right_active = True  # appears now
    holo_left_active = False      # clear enemy's hologram on this side

    if p1_power == "Loki" and p1_loki_split_pending:
        spawn_loki_fake_balls(ball_x, ball_y, ball_vel_x, ball_vel_y)
        p1_loki_split_pending = False
        spd = math.hypot(ball_vel_x, ball_vel_y)
        ball_vel_x, ball_vel_y = random_angle_vec(spd, toward_right=True)


def paddle_bounce_for_right(right_rect, ball_rect):
    global ball_x, ball_vel_x, ball_vel_y
    global p2_meter, holo_left_active, holo_right_active, p2_loki_split_pending
    global ball_invisible, last_ball_x, p2_invis_hide_pending
    global paddle_hits 

    if not (ball_rect.colliderect(right_rect) and ball_vel_x > 0):
        return

    # snap just outside paddle
    ball_x = right_rect.left - radius

    # Meter: right player hit +1
    p2_meter = min(METER_MAX, p2_meter + 1)
    paddle_hits += 1

    # normalized contact offset (-1..+1): top=-1, center=0, bottom=+1
    offset = (ball_y - (right_y + paddle_height / 2)) / (paddle_height / 2)

    # target angle
    max_angle = math.radians(MAX_DEFLECT_DEG)
    angle = offset * max_angle

    # keep current speed magnitude (at least MIN_SPEED)
    speed = max(MIN_SPEED, math.hypot(ball_vel_x, ball_vel_y))

    # outgoing to the left
    ball_vel_x = -speed * math.cos(angle)
    ball_vel_y =  speed * math.sin(angle)

    # speed up
    ball_vel_x *= SPEEDUP_PER_HIT
    ball_vel_y *= SPEEDUP_PER_HIT

    # Quicksilver extra hit force when ability active
    if p2_power == "QuickSilver" and pygame.time.get_ticks() < p2_qs_until_ms:
        ball_vel_x *= QUICKSILVER_HIT_FORCE
        ball_vel_y *= QUICKSILVER_HIT_FORCE

    # clamp to MAX_SPEED
    new_speed = math.hypot(ball_vel_x, ball_vel_y)
    if new_speed > MAX_SPEED:
        s = MAX_SPEED / new_speed
        ball_vel_x *= s
        ball_vel_y *= s

    # ---- Character hooks ----
    if p2_power == "Invisible Woman" and p2_invis_hide_pending:
        ball_invisible = True
        last_ball_x = ball_x
        p2_invis_hide_pending = False
        
    if p2_power == "Loki":
        holo_left_active = True
    holo_right_active = False

    if p2_power == "Loki" and p2_loki_split_pending:
        spawn_loki_fake_balls(ball_x, ball_y, ball_vel_x, ball_vel_y)
        p2_loki_split_pending = False
        spd = math.hypot(ball_vel_x, ball_vel_y)
        ball_vel_x, ball_vel_y = random_angle_vec(spd, toward_right=False)


# ----------------- HUD DRAW -----------------
def draw_meter_bar(surface, x, y, value, maxv, seg_w=16, seg_h=18, gap=4,
                   fill_color=(255, 215, 0), empty_color=(70, 70, 40), border_color=(120,120,120)):
    """Draws a segmented meter bar (0..maxv)."""
    for i in range(maxv):
        r = pygame.Rect(x + i*(seg_w+gap), y, seg_w, seg_h)
        if i < value:
            pygame.draw.rect(surface, fill_color, r, border_radius=3)
        else:
            pygame.draw.rect(surface, empty_color, r, border_radius=3)
            pygame.draw.rect(surface, border_color, r, 1, border_radius=3)


def draw_hud():
    """Draw top HUD band with names, meters, scores, serve hint."""
    band = pygame.Rect(0, 0, WIDTH, HUD_H)
    pygame.draw.rect(wn, HUD_BG, band)
    pygame.draw.line(wn, HUD_BORDER, (0, HUD_H-1), (WIDTH, HUD_H-1), 2)

    left_name  = p1_power if p1_power else "P1"
    right_name = p2_power if p2_power else "P2"

    # layout
    left_pad_x = 20
    right_pad_x = WIDTH - 20
    center_x = WIDTH // 2

    ln = FONT_NAME.render(left_name, True, WHITE)
    rn = FONT_NAME.render(right_name, True, WHITE)
    wn.blit(ln, (left_pad_x, 12))
    wn.blit(rn, (right_pad_x - rn.get_width(), 12))

    draw_meter_bar(wn, left_pad_x, 44, p1_meter, METER_MAX)
    total_w = METER_MAX * (16 + 4) - 4
    draw_meter_bar(wn, right_pad_x - total_w, 44, p2_meter, METER_MAX)

    sc = FONT_SCORE.render(f"{score_left}  :  {score_right}", True, WHITE)
    wn.blit(sc, (center_x - sc.get_width()//2, 10))

    if state == STATE_SERVE:
        hint = "Player 1 serve — W/S" if server == "left" else "Player 2 serve — ↓/↑"
        hi = FONT_SMALL.render(hint, True, WHITE)
        wn.blit(hi, (center_x - hi.get_width()//2, 44))


# ----------------- MENU DRAW -----------------
def draw_menu():
    wn.fill(BLACK)

    title = FONT_TITLE.render("Marvel PONG — Pick Your Hero! Or villain...", True, WHITE)
    wn.blit(title, (WIDTH//2 - title.get_width()//2, 30))

    # Panels
    panel_w = WIDTH//2 - 40
    panel_h = 600
    p1_rect = pygame.Rect(30, 120, panel_w, panel_h)
    p2_rect = pygame.Rect(WIDTH - 30 - panel_w, 120, panel_w, panel_h)

    # Draw panels
    pygame.draw.rect(wn, (40,40,40), p1_rect, border_radius=16)
    pygame.draw.rect(wn, (40,40,40), p2_rect, border_radius=16)

    # Headers
    p1_hdr = FONT_SUB.render("P1 — Select with W/S---------Confirm with A/D", True, WHITE)
    p2_hdr = FONT_SUB.render("P2 — Select with ↓/↑-----Confirm with </>", True, WHITE)
    wn.blit(p1_hdr, (p1_rect.x + 16, p1_rect.y + 10))
    wn.blit(p2_hdr, (p2_rect.x + 16, p2_rect.y + 10))

    list_margin = 18
    gap_between = 18
    list_w_ratio = 0.45
    list_w = int(p1_rect.w * list_w_ratio)
    desc_w = p1_rect.w - list_w - gap_between - list_margin*2

    def draw_player_panel(rect, idx, ready):
        list_rect = pygame.Rect(rect.x + list_margin, rect.y + 50, list_w, rect.h - 70)
        desc_rect = pygame.Rect(list_rect.right + gap_between, rect.y + 50, desc_w, rect.h - 70)

        # List items
        y = list_rect.y
        for i, item in enumerate(POWERUPS):
            name = item["name"]
            is_selected = (i == idx)
            color = GREEN if (is_selected and ready) else (BLUE if is_selected else WHITE)
            prefix = "->" if is_selected else "   "
            text = FONT_ITEM.render(prefix + name, True, color)
            wn.blit(text, (list_rect.x, y))
            y += 36

        # Status tag
        status = "READY" if ready else "UNREADY"
        status_color = GREEN if ready else RED
        stat = FONT_SUB.render(status, True, status_color)
        wn.blit(stat, (rect.x + rect.w - stat.get_width() - 14, rect.y + rect.h - stat.get_height() - 12))

        # Description for selected hero
        sel = POWERUPS[idx]
        desc_title = FONT_ITEM.render(sel["name"], True, WHITE)
        wn.blit(desc_title, (desc_rect.x, desc_rect.y))

        desc_body_rect = pygame.Rect(desc_rect.x, desc_rect.y + 36, desc_rect.w, desc_rect.h - 36)
        draw_wrapped_text(
            wn,
            sel["desc"],
            FONT_DESC,
            WHITE,
            desc_body_rect,
            line_spacing_px=0,
            paragraph_spacing_px=None,
            first_line_indent_px=28,
            subsequent_indent_px=0,
            v_align='middle'
        )

    draw_player_panel(p1_rect, p1_idx, p1_ready)
    draw_player_panel(p2_rect, p2_idx, p2_ready)

    both_ready = p1_ready and p2_ready
    footer_msg = ("Both ready! Starting… (server will press paddle key to serve)"
                  if both_ready else "Both players READY up to start")
    info = FONT_SUB.render(footer_msg, True, WHITE)
    wn.blit(info, (WIDTH//2 - info.get_width()//2, HEIGHT - 46))


# ----------------- START GAME FROM MENU -----------------
def make_paddle_surface(power_name, side, alpha=None):
    """Build a paddle skin on its own Surface once; optionally translucent."""
    surf = pygame.Surface((paddle_width, paddle_height), pygame.SRCALPHA)
    rect = pygame.Rect(0, 0, paddle_width, paddle_height)
    draw_paddle(surf, rect, power_name, side)
    if alpha is not None:
        surf.set_alpha(alpha)
    return surf


def start_match_from_menu():
    global p1_power, p2_power, score_left, score_right
    global p1_meter, p2_meter, LEFT_GHOST_SURF, RIGHT_GHOST_SURF

    p1_power = POWERUPS[p1_idx]["name"]
    p2_power = POWERUPS[p2_idx]["name"]
    score_left = 0
    score_right = 0
    p1_meter = 0
    p2_meter = 0

    # Build ghost surfaces once per match (each is a copy of that side's real skin)
    LEFT_GHOST_SURF  = make_paddle_surface(p1_power, 'left')
    RIGHT_GHOST_SURF = make_paddle_surface(p2_power, 'right')

    reset_ball(right_scored=True)


# ----------------- STATE HELPERS -----------------
def reset_ball(right_scored: bool):
    """Enter SERVE after a point; center ball/paddles and set serve direction."""
    global ball_x, ball_y, ball_vel_x, ball_vel_y
    global state, server, serve_vx, serve_vy
    global left_y, right_y
    global left_x_offset, right_x_offset, p1_ability_until_ms, p2_ability_until_ms
    global holo_left_active, holo_right_active
    global holo_left_sign, holo_right_sign
    global p1_loki_split_pending, p2_loki_split_pending
    global freeze_left_until_ms, freeze_right_until_ms
    global p1_invis_passive_used, p2_invis_passive_used
    global p1_invis_hide_pending, p2_invis_hide_pending
    global ball_invisible, last_ball_x
    global p1_qs_until_ms, p2_qs_until_ms, p1_qs_freeze_until_ms, p2_qs_freeze_until_ms, qs_music_on

    # center ball & paddles in the playfield (not inside HUD)
    ball_x = WIDTH / 2
    ball_y = HUD_H + (HEIGHT - HUD_H) / 2
    left_y  = HUD_H + (HEIGHT - HUD_H - paddle_height) / 2
    right_y = HUD_H + (HEIGHT - HUD_H - paddle_height) / 2

    # who serves next (the one who got scored on)
    server = "left" if right_scored else "right"

    # random velocity; force it AWAY from the server
    vx, vy = random_ball_velocity()
    if server == "left":
        vx = abs(vx)   # serve to the right
    else:
        vx = -abs(vx)  # serve to the left

    serve_vx, serve_vy = vx, vy
    ball_vel_x, ball_vel_y = 0.0, 0.0

    # Reset Iron offsets and active ability timers (meters persist)
    left_x_offset = 0.0
    right_x_offset = 0.0
    p1_ability_until_ms = 0
    p2_ability_until_ms = 0

    # Loki state reset per rally
    holo_left_active = False
    holo_right_active = False
    fake_balls.clear()
    holo_left_sign = 0
    holo_right_sign = 0
    p1_loki_split_pending = False
    p2_loki_split_pending = False
    
    # Invisible Woman reset per rally
    freeze_left_until_ms = 0
    freeze_right_until_ms = 0
    p1_invis_passive_used = False
    p2_invis_passive_used = False
    p1_invis_hide_pending = False
    p2_invis_hide_pending = False
    ball_invisible = False
    last_ball_x = ball_x

    # Quick Silver reset per rally
    p1_qs_until_ms = 0
    p2_qs_until_ms = 0
    p1_qs_freeze_until_ms = 0
    p2_qs_freeze_until_ms = 0
    if qs_music_on:
        try:
            pygame.mixer.music.stop()
        except Exception:
            pass
        qs_music_on = False
    
    state = STATE_SERVE

begin_rally(pygame.time.get_ticks())

def begin_play_if_served(e_key: int):
    """Start rally when the server presses their paddle keys."""
    global ball_vel_x, ball_vel_y, state
    if state != STATE_SERVE:
        return
    if server == "left" and e_key in (pygame.K_w, pygame.K_s):
        ball_vel_x, ball_vel_y = serve_vx, serve_vy
        state = STATE_PLAY
    elif server == "right" and e_key in (pygame.K_UP, pygame.K_DOWN):
        ball_vel_x, ball_vel_y = serve_vx, serve_vy
        state = STATE_PLAY
    begin_rally(pygame.time.get_ticks())



def clamp_paddles_vertical():
    """Clamp paddles vertically to the playfield area below the HUD."""
    global left_y, right_y
    if left_y < HUD_H: left_y = HUD_H
    if left_y + paddle_height > HEIGHT: left_y = HEIGHT - paddle_height
    if right_y < HUD_H: right_y = HUD_H
    if right_y + paddle_height > HEIGHT: right_y = HEIGHT - paddle_height


def is_double_press(key):
    now = pygame.time.get_ticks()
    last = last_key_press_time.get(key, -10_000_000)
    last_key_press_time[key] = now
    return (now - last) <= DOUBLE_PRESS_THRESHOLD


# ----------------- MAIN LOOP -----------------
run = True
while run:

    # ---------- events ----------
    for e in pygame.event.get():
        if e.type == pygame.QUIT:
            run = False
            pygame.quit()
            sys.exit()

        elif e.type == pygame.VIDEORESIZE:
            apply_resize(e.w, e.h)

        elif e.type == pygame.KEYDOWN:
            if state == STATE_MENU:
                # Player 1 navigation
                if e.key == pygame.K_w:
                    p1_idx = (p1_idx - 1) % len(POWERUPS)
                elif e.key == pygame.K_s:
                    p1_idx = (p1_idx + 1) % len(POWERUPS)
                elif e.key == pygame.K_d:
                    p1_ready = True
                elif e.key == pygame.K_a:
                    p1_ready = False

                # Player 2 navigation
                if e.key == pygame.K_UP:
                    p2_idx = (p2_idx - 1) % len(POWERUPS)
                elif e.key == pygame.K_DOWN:
                    p2_idx = (p2_idx + 1) % len(POWERUPS)
                elif e.key == pygame.K_RIGHT:
                    p2_ready = True
                elif e.key == pygame.K_LEFT:
                    p2_ready = False

                if p1_ready and p2_ready:
                    start_match_from_menu()

            elif state == STATE_SERVE:
                begin_play_if_served(e.key)

            elif state == STATE_PLAY:
                pass

            # --- Ability activations (shared meter; per-character keys kept same) ---
            # Iron Man P1
            if p1_power == "Iron Man" and e.key == pygame.K_d and state != STATE_MENU:
                if is_double_press(e.key) and p1_meter >= METER_MAX:
                    p1_ability_uses += 1
                    p1_last_ability_ms = pygame.time.get_ticks()
                    p1_meter = 0
                    p1_ability_until_ms = pygame.time.get_ticks() + IRON_ABILITY_MS
            # Iron Man P2
            if p2_power == "Iron Man" and e.key == pygame.K_LEFT and state != STATE_MENU:
                if is_double_press(e.key) and p2_meter >= METER_MAX:
                    p2_ability_uses += 1
                    p2_last_ability_ms = pygame.time.get_ticks()
                    p2_meter = 0
                    p2_ability_until_ms = pygame.time.get_ticks() + IRON_ABILITY_MS

            # Loki P1: double-press D -> next hit will split ball
            if p1_power == "Loki" and e.key == pygame.K_d and state != STATE_MENU:
                if is_double_press(e.key) and p1_meter >= METER_MAX:
                    p1_ability_uses += 1
                    p1_last_ability_ms = pygame.time.get_ticks()
                    p1_meter = 0
                    p1_loki_split_pending = True
            # Loki P2: double-press Left Arrow
            if p2_power == "Loki" and e.key == pygame.K_LEFT and state != STATE_MENU:
                if is_double_press(e.key) and p2_meter >= METER_MAX:
                    p2_ability_uses += 1
                    p2_last_ability_ms = pygame.time.get_ticks()
                    p2_meter = 0
                    p2_loki_split_pending = True

            # Quicksilver P1 sweet dreams ability
            if p1_power == "QuickSilver" and e.key == pygame.K_d and state != STATE_MENU:
                if is_double_press(e.key) and p1_meter >= METER_MAX:
                    p1_ability_uses += 1
                    p1_last_ability_ms = pygame.time.get_ticks()
                    p1_meter = 0
                    p1_qs_until_ms = pygame.time.get_ticks() + QUICKSILVER_ABILITY_MS
                    p2_qs_freeze_until_ms = pygame.time.get_ticks() + QUICKSILVER_FREEZE_MS
                    start_quicksilver_music()

            # Quicksilver P2 ability
            if p2_power == "QuickSilver" and e.key == pygame.K_LEFT and state != STATE_MENU:
                if is_double_press(e.key) and p2_meter >= METER_MAX:
                    p2_ability_uses += 1
                    p2_last_ability_ms = pygame.time.get_ticks()
                    p2_meter = 0
                    p2_qs_until_ms = pygame.time.get_ticks() + QUICKSILVER_ABILITY_MS
                    p1_qs_freeze_until_ms = pygame.time.get_ticks() + QUICKSILVER_FREEZE_MS
                    start_quicksilver_music()

            now_ms = pygame.time.get_ticks()
            # Invisible Woman PASSIVE (freeze)
            if state == STATE_PLAY:
                if p1_power == "Invisible Woman" and e.key == pygame.K_a and not p1_invis_passive_used:
                    freeze_right_until_ms = now_ms + INVIS_PASSIVE_MS
                    p1_invis_passive_used = True
                if p2_power == "Invisible Woman" and e.key == pygame.K_RIGHT and not p2_invis_passive_used:
                    freeze_left_until_ms = now_ms + INVIS_PASSIVE_MS
                    p2_invis_passive_used = True

            # Invisible Woman ABILITY (double-press): P1 'D', P2 '<' (Left Arrow)
            if p1_power == "Invisible Woman" and e.key == pygame.K_d and state != STATE_MENU:
                if is_double_press(e.key) and p1_meter >= METER_MAX:
                    p1_ability_uses += 1
                    p1_last_ability_ms = pygame.time.get_ticks()
                    p1_meter = 0
                    p1_invis_hide_pending = True
            if p2_power == "Invisible Woman" and e.key == pygame.K_LEFT and state != STATE_MENU:
                if is_double_press(e.key) and p2_meter >= METER_MAX:
                    p2_ability_uses += 1
                    p2_last_ability_ms = pygame.time.get_ticks()
                    p2_meter = 0
                    p2_invis_hide_pending = True

    # ---------- RENDER / UPDATE PER STATE ----------
    if state == STATE_MENU:
        draw_menu()

    else:
        # GAME FIELD
        wn.fill(BLACK)

        # draw HUD (only in SERVE/PLAY)
        draw_hud()

        # continuous paddle input
        keys = pygame.key.get_pressed()

        now_ms = pygame.time.get_ticks()
        left_frozen  = (now_ms < freeze_left_until_ms)
        right_frozen = (now_ms < freeze_right_until_ms)

        # Update Quicksilver music (stop when no QS ability active)
        update_quicksilver_music(now_ms)
        
        # Quicksilver 2s freeze phase (enemy paddle + real ball)
        left_frozen  = left_frozen  or (now_ms < p1_qs_freeze_until_ms)
        right_frozen = right_frozen or (now_ms < p2_qs_freeze_until_ms)
        qs_ball_frozen = (now_ms < p1_qs_freeze_until_ms) or (now_ms < p2_qs_freeze_until_ms)

        # --- Iron Man passive: horizontal nudge  ---
        if p1_power == "Iron Man" and not left_frozen:
            if keys[pygame.K_d]:
                left_x_offset  += IRON_X_NUDGE_SPEED   # toward enemy (right)
            if keys[pygame.K_a]:
                left_x_offset  -= IRON_X_NUDGE_SPEED   # away (left)
        
        if p2_power == "Iron Man" and not right_frozen:
            if keys[pygame.K_LEFT]:
                right_x_offset -= IRON_X_NUDGE_SPEED   # toward enemy (left)
            if keys[pygame.K_RIGHT]:
                right_x_offset += IRON_X_NUDGE_SPEED   # away (right)

        # --- Absolute horizontal clamps ---
        LEFT_MIN_X = 0
        LEFT_MAX_X = WIDTH // 2 - paddle_width - CENTER_MARGIN
        new_left = left_x + left_x_offset
        if new_left < LEFT_MIN_X:
            new_left = LEFT_MIN_X
        elif new_left > LEFT_MAX_X:
            new_left = LEFT_MAX_X
        left_x_offset = new_left - left_x

        RIGHT_MIN_X = WIDTH // 2 + CENTER_MARGIN
        RIGHT_MAX_X = WIDTH - paddle_width
        new_right = right_x + right_x_offset
        if new_right < RIGHT_MIN_X:
            new_right = RIGHT_MIN_X
        elif new_right > RIGHT_MAX_X:
            new_right = RIGHT_MAX_X
        right_x_offset = new_right - right_x

        # standard vertical controls
        left_dir  = (-1 if keys[pygame.K_w]    else 0) + (1 if keys[pygame.K_s]    else 0)
        right_dir = (-1 if keys[pygame.K_UP]   else 0) + (1 if keys[pygame.K_DOWN] else 0)
        if left_frozen:  left_dir  = 0
        if right_frozen: right_dir = 0

        # ability-aware paddle speeds (Iron Man overrides; Quicksilver modifies base and enemy)
        left_base  = PADDLE_SPEED + (QUICKSILVER_SPEED_BOOST if p1_power == "QuickSilver" else 0)
        right_base = PADDLE_SPEED + (QUICKSILVER_SPEED_BOOST if p2_power == "QuickSilver" else 0)

        left_speed  = IRON_ABILITY_SPEED if (p1_power == "Iron Man" and now_ms < p1_ability_until_ms) else left_base
        right_speed = IRON_ABILITY_SPEED if (p2_power == "Iron Man" and now_ms < p2_ability_until_ms) else right_base

        # Quicksilver ability halves the ENEMY paddle speed
        if (p1_power == "QuickSilver" and now_ms < p1_qs_until_ms):
            right_speed *= 0.5
        if (p2_power == "QuickSilver" and now_ms < p2_qs_until_ms):
            left_speed *= 0.5
            
        # vertical velocities
        left_pad_vel  = left_dir  * left_speed
        right_pad_vel = right_dir * right_speed

        # paddles
        left_y  += left_pad_vel
        right_y += right_pad_vel
        clamp_paddles_vertical()

        #----------------State = PLAY -----------------
        if state == STATE_PLAY:
            # wall bounce dampens ball speed
            ball_y, ball_vel_y = bounce_top_bottom(ball_y, ball_vel_y)

            # hitboxes
            left_rect, right_rect = get_paddle_rects()
            ball_rect  = pygame.Rect(int(ball_x - radius), int(ball_y - radius), int(radius * 2), int(radius * 2))

            # paddle bounces
            paddle_bounce_for_left(left_rect, ball_rect)
            paddle_bounce_for_right(right_rect, ball_rect)

            # Quick Silver movement
            qs_ball_factor = 0.5 if ((p1_power == "QuickSilver" and now_ms < p1_qs_until_ms) or
                         (p2_power == "QuickSilver" and now_ms < p2_qs_until_ms)) else 1.0
            if not qs_ball_frozen:
                ball_x += ball_vel_x * qs_ball_factor
                ball_y += ball_vel_y * qs_ball_factor
            
            # Invisible woman invis-ball limits
            if ball_invisible:
                mid = WIDTH / 2
                if (last_ball_x - mid) * (ball_x - mid) <= 0:
                    ball_invisible = False

            #Loki Fake balls use same physics as real ball
            for fb in list(fake_balls):
                fb["y"], fb["vy"] = bounce_top_bottom(fb["y"], fb["vy"])
                fb["x"] += fb["vx"]
                fb["y"] += fb["vy"]
                if fb["x"] + radius < 0 or fb["x"] - radius > WIDTH:
                    fake_balls.remove(fb)

            # scoring -> go to SERVE
            if ball_x + radius < 0:
                # RIGHT scored
                score_right += 1
                p2_meter = min(METER_MAX, p2_meter + 1)
                p1_meter = min(METER_MAX, p1_meter + 2)
                now_ms = pygame.time.get_ticks()
                end_vx, end_vy = ball_vel_x, ball_vel_y  # capture BEFORE reset 
                winner = "P2"  
                log_rally_row(winner, end_vx, end_vy, now_ms)
                reset_ball(right_scored=True)

            elif ball_x - radius > WIDTH:
                # LEFT scored
                score_left += 1
                p1_meter = min(METER_MAX, p1_meter + 1)
                p2_meter = min(METER_MAX, p2_meter + 2)
                now_ms = pygame.time.get_ticks()
                end_vx, end_vy = ball_vel_x, ball_vel_y  # capture BEFORE reset
                winner = "P1" 
                log_rally_row(winner, end_vx, end_vy, now_ms)
                reset_ball(right_scored=False)

        else:
            # SERVE state: build hitboxes just for drawing consistency
            left_rect, right_rect = get_paddle_rects()

        # --------- DRAW ORDER ---------
        # 1) Dotted trajectory (under paddles)
        draw_jarvis_if_active()

        # 3) Real paddles and real ball
        if not ball_invisible:
            pygame.draw.circle(wn, BLUE, (int(ball_x), int(ball_y)), radius)
        draw_paddle(wn, left_rect,  p1_power, side="left")
        draw_paddle(wn, right_rect, p2_power, side="right")

        # 2) Hologram paddles (Loki passive)
        if state == STATE_PLAY:
            if holo_right_active:
                # follow enemy right paddle X; Y offset decided in mirror_y_of
                hx = int(right_x + right_x_offset)
                hy = int(mirror_y_of(right_y, "right"))
                holo_right_rect = pygame.Rect(hx, hy, paddle_width, paddle_height)
                draw_hologram_paddle_cached(wn, holo_right_rect, side="right")
            if holo_left_active:
                hx = int(left_x + left_x_offset)
                hy = int(mirror_y_of(left_y, "left"))
                holo_left_rect = pygame.Rect(hx, hy, paddle_width, paddle_height)
                draw_hologram_paddle_cached(wn, holo_left_rect, side="left")

        # 4) Fake balls (Loki ability)  
        if state == STATE_PLAY and fake_balls:
            for fb in fake_balls:
                pygame.draw.circle(wn, BLUE, (int(fb["x"]), int(fb["y"])), radius)

        # win check → brief screen → return to MENU
        if score_right >= points_to_win:
            wn.fill(BLACK)
            draw_hud()
            game_over = FONT_WIN.render("Player 2 Wins!", True, WHITE)
            wn.blit(game_over, (WIDTH//2 - game_over.get_width()//2, HUD_H + (HEIGHT - HUD_H)//2 - 50))
            pygame.display.update()
            pygame.time.delay(1800)
            p1_ready = p2_ready = False
            state = STATE_MENU
            continue

        elif score_left >= points_to_win:
            wn.fill(BLACK)
            draw_hud()
            game_over = FONT_WIN.render("Player 1 Wins!", True, WHITE)
            wn.blit(game_over, (WIDTH//2 - game_over.get_width()//2, HUD_H + (HEIGHT - HUD_H)//2 - 50))
            pygame.display.update()
            pygame.time.delay(1800)
            p1_ready = p2_ready = False
            state = STATE_MENU
            continue

    pygame.display.update()
    clock.tick(120)