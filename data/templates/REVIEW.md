# Template review sheet (drafted 2026-10-30)

Two templates, built from the transcripts only. Each line gives the value, the source timestamp(s), and
anything I had to decide. To approve a template, set `review.reviewed_by_user: true` in its YAML (or tell
Claude to). Check: `uv run python -m scripts.template_sources <video_id> --grep "<words>"`.

Sources: **40" Blueprint** = John Evans, *How to Get a 40" Vertical (Full Blueprint)* (Icml891MLHA, 2026-03-22).
**Knee Blueprint** = John Evans, *How To Get Rid Of Knee Pain (Full Blueprint)* (9X_j-oF2ZDg, 2026-10-16).

## 1. `long_conjugate_6mo` — six-month macrocycle

| Part | What the template says | Source | Decided / uncertain |
|---|---|---|---|
| Shape | 6-month macrocycle of 6 mesocycles; pattern lift–general–lift–general–lift, weekdays only an example ("if you're lifting Mon/Wed/Fri") | 40" 0:35, 1:45, 3:29 | Month 1 also says "train about 3 days a week" (2:54) — reads as 3 lift days, general days on top. **Confirm.** |
| Jump sessions | 40-min window: 35/5 → 30/10 → 25/15 → 20/20 (cap) warm-up/max-effort minutes, +5 max each month | 40" 13:12, 13:50 | Day of the week not stated. |
| M1 volume (4 wk) | Power clean 5×4; back squat 4–5 × 6–12 @ 65–70%; accessories 2–5 × 8–12 (to 14); varied general circuits; deload week 4 | 40" 2:21–3:29 | |
| M2 intensify (4 wk) | Clean pull 6 × 3–5 @ 90%; power clean 5–7 × 3 @ 75–85% (sets rise weekly); squat 6–8 reps; RDL & calf raise 4–6 reps to ~85%; general: bodybuilding circuits **incl. upper body** + tempo runs | 40" 4:04–5:20 | Length "a month" (5:20) → 4 weeks. |
| M3 absolute strength (3–4 wk) | Back squat 10×3 or 10×2; power clean %s pushed up (no number); clean pull 105–110% of power clean; eccentric accessories (Nordics, 2-up-1-down calves); general: sand jump circuits 20–30 s, harder tempo runs 30–45 s / ~3 min rest | 40" 5:20–7:07 | "About 3 weeks" (7:07) → 3–4 weeks. |
| M4 strength-speed | Power clean to maxes 2×/wk + clean-pull day; eccentric split squat 3 × 2–3 after 3 build-ups; accentuated eccentric belt squat 110–115% of max squat; elastic accessories 2 × 5–6 (high-velocity calf raise, drop RDL); general days more general, tempo and jump circuits removed | 40" 7:07–9:32 | Length not stated (called "month four") → left empty. **Set 4 weeks?** |
| M5 speed-strength | Power clean ~60%, power snatch ~50% of clean, hang power clean; squat primer 5-4-3 up to 85% then high-velocity squats ×5 @ 65–70%; med-ball throws, low-volume plyos; general = rest/regeneration (static flexibility, bodyweight circuits, **core work**, barefoot 100 m ×10), no jumping | 40" 9:32–11:21 | Length not stated → empty. **Set 4 weeks?** |
| M6 specificity | Either load-management (jump Mon/Thu, feel-good slow squats/calves/RDLs Tue/Fri) or shock loading Mon/Wed/Fri with heavy sprinting and the year's most plyo intensity/variety; accessories slow and general | 40" 11:21–12:34 | Two alternatives kept; the Planner picks one per athlete. Length not stated. |
| Taper (end) | 10–14 days; volume −50% (40") to −50–70% (taper video); intensity up, more max-effort jumping, 5-4-3-2-1 squats, daily max-velocity power clean; needs ≥ 12 weeks of loading first | 40" 12:34; taper video bFezqBUmWO4 1:08, 4:02; HWx9Q6gLxg8 0:43 | 12 weeks = "ideally at least 3 months" of loading. |
| Unload week | Volume × 0.4 (≈60% drop), intensity kept high | 28 Rules ZxzFvqBlzYw 0:38 | The proposal had ~0.7; the transcript says ~60% drop. |
| Gates | None yet | — | Jump-session barometer gates come in plan 2. |

"%" means different things by line (of 1RM, of power clean, of max squat); each line's note says which.

| Scheduling | Days follow your available days, not fixed weekdays; hard days (lift, jump) at least 2 days apart, no back-to-back hard days; a missed session is skipped, not made up ("training is cyclic") | START HERE Hhl7vONBAEs 8:56, 9:30; THP JoXfKavjn8g 9:03 | The missed-session rule is from a beginner video; missing a week or more is still open. |

## 2. `tendon_track` — patellar tendon track

The Knee Blueprint itself calls this a "four-step system" (16:25) with a reactive check first (0:42–2:05).
It matches the proposal's (Google Drive) version closely, but every value here is from the transcript.

| Stage | What the template says | Source | Decided / uncertain |
|---|---|---|---|
| Reactive check | Flare-up the day after / during a session that settles in 24–48 h: take 24–48 h off, then train as normal. Pain back 24–48 h after every elastic session = tendon disrepair → phase 1 | Knee 0:42, 1:23 | Added as a stage so a flare-up has somewhere to go. |
| Phase 1 isometrics | Isometric leg extension (machine best; manual or ~40 lb kettlebell) 3–5 × 45 s @ ~70% effort to 2–3/10 pain, 1 min rest, ≥ 2×/day (ideally every 6 h). All elastic loading cut. Exit: stairs pain-free | Knee 2:05–4:48, 6:42 | Length not stated. |
| Phase 2 heavy slow | Half squat (two-foot) / quarter squat (one-foot) 4 × 6–8, 4-1-4 tempo, 2–5/10 pain, Mon/Wed/Fri, +5–10 lb per session; worse at 48 h → −5–10 lb, slower. Exit: slow 225 lb quarter / 185 lb half squat pain-free. 2–4 weeks | Knee 6:05–9:20 | |
| Phase 3 elastic storage | 3-day cycle: (1) isometrics + 10–20 depth drops from 12 in, +6 in per session; (2) heavy slow 4×6 from where phase 2 ended, +5–10 lb last 2 sets; (3) isometrics only. Weekends isometrics | Knee 9:20–12:44 | No exit height or length stated. |
| Phase 4 return to jumping | Same 3-day cycle; only the elastic day progresses, 2 sessions per step: standing box jump to 24 in (10–20) → one-step box jump → 5 box jumps + 5 rim touches, approach effort rising. Heavy slow fixed. Then 1 jump + 1 drop session/week with 2 heavy-slow + 2 iso sessions until confident; back to the long conjugate sequence with lighter jumps, clean pulls not power cleans, slow main lift | Knee 12:44–18:15 | Starts ~8 weeks into rehab. |
| Scheduling | Repeating elastic → heavy slow → isometrics-only; the heavy slow day right after the elastic day is intended (the one allowed back-to-back pair); missed sessions skipped | Knee 6:05, 10:03, 11:26, 13:24; START HERE 9:30 | |
| Always | Isometrics for life (3 × 45 s before every session and ~6 h after); only one knee exercise; RDLs (not deadlifts), calf raises, band walks, adductors OK; flare-up → keep heavy slow + isos, step the elastic day back | Knee 4:48, 5:28, 15:11–17:00 | |

**Gates** (decisions code will apply in plan 2): stairs pain-free → progress; worse at 48 h after heavy slow → hold;
slow 225/185 pain-free → progress; next-day pain ~2–3/10 after elastic → progress; ≥ 6/10 → step back
(Knee 8:41–15:51). Morning pain test back to baseline → hold, clearly above → step back (THP VMSF8C25mxY 7:01–7:49,
ZN8wh4FFZuA 3:07). More than 2–3/10 while jumping → cut the session (THP 72YX7nkYmYE 2:22, ZShxHyeTsVk 1:15).

## 3. Open questions from the spec (§15)

1. **How the knee video divides its stages:** four phases in its own words, after a reactive check (above).
2. **Shortening for an event < 6 months away:** the 40" Blueprint (1:45) says a season can leave only 3–4 months,
   and the taper video says load ideally at least 3 months before a taper. Neither says which months to drop. So the
   Planner may shorten only down to 12 loading weeks + taper, and must say the transcripts don't specify which
   mesocycles to cut.
3. **Tendon track vs macrocycle:** while in phases 1–4, knee-loading work is only what the tendon stage prescribes
   (one knee exercise rule); RDLs, calves, band walks and adductors may stay. After phase 4 the athlete moves back
   into the macrocycle with lighter jump sessions and clean pulls instead of power cleans. Upper-body work during
   rehab is only mentioned inside the coaching sales pitch (18:52), so I did not add it.

## 4. Relevant to your direct-edit test cases

- **Upper body on general days:** month 2 general days already include upper-body bodybuilding circuits (40" 5:20).
- **Core at the end:** month 5 general days include core work (40" 11:21).

## 5. Review on 2026-11-06 (Claude, with your answers)

Checked: both files validate, all cites exist in `charsplit_matched`, every number found in its cited text
(except derived ones: month-3 jump minutes from the 5-minute rule, "100%" = "absolute maxes"), months 2–6 and
the tendon numbers read against the transcript.

| Item | Decision | Source |
|---|---|---|
| Months 4–6 | 4 weeks each (you). Macrocycle ≈ 23–24 weeks + taper. | — |
| Training days | "About" 3: 2–4 hard days by how you handle them — 3 lifts + jump when feeling good, 2 lifts + jump when beat up, busy or in season; ~4 hard days is THP's ceiling; general days optional extras (you + THP). | 40" 2:54; 3 vs 6 Days 9:16–20:32; How Many Days 3:04, 8:01 |
| Jump session | About once a week, after the last lift day (Fri lift → Sat jump allowed back to back). Fixes a bug: with Mon/Wed/Fri lifts the jump day had no legal slot. | At-Home Workout 13:00; Jump Without Lifting 5:40 |
| Unload | THP default: ~1 week every 3–4 weeks, volume −60%, intensity high; example week ("John Evans special") in defaults. By feel (you): beat up → unload now; fresh and progressing → unload at week 4, half unload (×0.5) OK; still thrashed after → another unload; low unload jump session → hold. Never skipped. | 28 Rules 0:38; Deload video 2:57–10:04; Eccentric vs Concentric 2:38; Box Squat vlog 3:09 (weaker: John's own training) |
| Event < 6 months | Shorten down to 12 loading weeks + taper (you; unlikely for you). | as §3 |
| Reactive stage | Kept (you). | Knee 0:42 |
| Exercises | Exact lists stay the default for now; slots later (you). | — |
| Small fixes | Month-4 partial-range note moved from belt squat to clean pull (it is about pulling from blocks); month-6 jump day gets its warm-up jumps; phase 3–4 isometrics cite the 70% MVC source. | 40" 8:21; Knee 2:45 |

Marked `reviewed_by_user: true` in both templates on 2026-11-06 (you approved).

## 6. Slot options for Month 1 (2026-11-08)

Month 1's `general lower-body accessory` now lists `options` (RDL, hip thrust, Nordic hamstring curl, lying hamstring curl, high box step-up, barbell lunge). Any option passes the fidelity check without a deviation; sets, reps and intensity stay the slot's. Each option cites the new-video chunks that name it (`SXjO279Oslw@137`, `I1baSIlV_pQ@408`, `OAsUemGRrpw@891`, `3vmd30VvzRA@855`). **Sumo deadlift dropped** (your call): THP does name it as general-phase work for two-foot jumpers (`Icml891MLHA@174`, `vdFI6b4M0P0@142`) but also says they rarely program it. Equipment names must match the profile's: `bench` and `hamstring curl machine` are not in the current profile, so those two options are filtered out for it. Months 2-6 are unchanged.
