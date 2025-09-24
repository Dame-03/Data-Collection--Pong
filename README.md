# Marvel Pong

Fast-start guide, run instructions, and data logging spec for the assignment deliverable.

## Requirements
- Python 3.10+
- Dependencies listed in `requirements.txt`

## Install / Run
`bash`
- pip install -r `requirements.txt`
- `python "Cleaned Pong.py"`

## Output File Created During Gameplay
A CSV file is created with **one row per rally (point)**:
match_log_YYYYMMDD_HHMMSS.csv
- `YYYYMMDD_HHMMSS` = timestamp when the match starts.
- Saved in the **same directory** as the game script.

## Data Dictionary (Per Rally)
**CSV header (exact order):**
`rally_index, paddle_hits, end_ball_speed_px_per_frame, rally_duration_s, p1_ability_uses, p2_ability_uses, winner, p1_win_within_8s_after_ability, p2_win_within_8s_after_ability`

**Fields**
- `rally_index` *(int)* — 1-based counter of rallies within the match.  
- `paddle_hits` *(int)* — Total number of ball–paddle collisions during the rally.  
- `end_ball_speed_px_per_frame` *(float)* — Ball speed on the frame the rally ends, √(vx²+vy²), in pixels per frame.  
- `rally_duration_s` *(float)* — Duration from serve to point award, in seconds.  
- `p1_ability_uses` *(int)* — Number of times Player 1 used their ability during this rally.  
- `p2_ability_uses` *(int)* — Number of times Player 2 used their ability during this rally.  
- `winner` *(string)* — `"P1"` or `"P2"` indicating who won the point.  
- `p1_win_within_8s_after_ability` *(bool)* — `true` if P1 won and their most recent ability use occurred ≤ 8.0s before point end; else `false`.  
- `p2_win_within_8s_after_ability` *(bool)* — `true` if P2 won and their most recent ability use occurred ≤ 8.0s before point end; else `false`.  

## Strategy for Data Collection
- **Serve start:** begin a rally timer; reset `paddle_hits`, `p1_ability_uses`, `p2_ability_uses`, and last-ability timestamps.  
- **Paddle hit:** increment `paddle_hits`.  
- **Ability activation:** increment the activating player’s per-rally counter and record their last ability timestamp.  
- **Point end:** record `rally_duration_s`, compute `end_ball_speed_px_per_frame` from final velocity, set `winner`, evaluate the “win within 8s after ability” flags, then append **one CSV row** in the header order above.
