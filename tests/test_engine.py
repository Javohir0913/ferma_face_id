from datetime import date, datetime, time

from davomat.engine import (
    IN, OUT, SHIFT_GUARD_DAY, SHIFT_GUARD_NIGHT, SHIFT_UNKNOWN,
    ST_CLOSED, ST_INCOMPLETE, ST_MANUAL, ST_OPEN, ST_UNCONFIRMED,
    Correction, Punch, RoleParams, compute, compute_with_roles, debounce,
)

STD = RoleParams(code="standart")
MILK = RoleParams(code="sog'uvchi", max_shift_hours=23)
GUARD = RoleParams(code="qorovul", mode="shift", max_shift_hours=14)
NOW = datetime(2026, 9, 30, 12, 0)


def P(s, d, src="faceid"):
    return Punch(datetime.strptime(s, "%Y-%m-%d %H:%M:%S"), d, src)


def test_debounce_keeps_first_in_and_last_out():
    ps = [
        P("2026-09-01 08:00:00", IN), P("2026-09-01 08:00:05", IN), P("2026-09-01 08:00:40", IN),
        P("2026-09-01 18:00:00", OUT), P("2026-09-01 18:00:20", OUT),
    ]
    kept, merged = debounce(ps, 60)
    assert [p.ts.strftime("%H:%M:%S") for p in kept] == ["08:00:00", "18:00:20"]
    assert len(merged) == 3


def test_debounce_does_not_merge_across_directions_or_long_gaps():
    ps = [P("2026-09-01 08:00:00", IN), P("2026-09-01 08:00:10", OUT), P("2026-09-01 08:02:00", OUT)]
    kept, merged = debounce(ps, 60)
    assert len(kept) == 3 and not merged


def test_simple_day_closed_with_break():
    ps = [
        P("2026-09-01 08:00:00", IN), P("2026-09-01 12:00:00", OUT),
        P("2026-09-01 13:00:00", IN), P("2026-09-01 18:00:00", OUT),
    ]
    [sh] = compute("1", ps, STD, NOW)
    assert sh.status == ST_CLOSED
    assert sh.span_sec == 10 * 3600
    assert sh.outside_sec == 3600
    assert sh.inside_sec == 9 * 3600


def test_consecutive_outs_do_not_cut_time_but_are_flagged():
    # 12:00 da chiqdi, qaytib kirganda kamera ushlamadi, 18:00 da yana chiqdi.
    ps = [P("2026-09-01 08:00:00", IN), P("2026-09-01 12:00:00", OUT), P("2026-09-01 18:00:00", OUT)]
    [sh] = compute("1", ps, STD, NOW)
    assert sh.status == ST_CLOSED
    assert sh.inside_sec == 10 * 3600
    assert "kirish qayd etilmagan" in sh.flags


def test_milker_midnight_crossing_goes_to_previous_day():
    ps = [
        P("2026-09-01 05:00:00", IN), P("2026-09-01 07:00:00", OUT),
        P("2026-09-01 18:00:00", IN), P("2026-09-02 01:00:00", OUT),
    ]
    shifts = compute("1", ps, MILK, NOW)
    assert len(shifts) == 1
    sh = shifts[0]
    assert sh.work_date == date(2026, 9, 1)
    assert sh.chiqish == datetime(2026, 9, 2, 1, 0)
    assert sh.inside_sec == 9 * 3600  # 2s + 7s
    assert sh.status == ST_CLOSED


def test_after_boundary_is_new_day():
    ps = [P("2026-09-02 03:30:00", IN), P("2026-09-02 12:00:00", OUT)]
    [sh] = compute("1", ps, MILK, NOW)
    assert sh.work_date == date(2026, 9, 2)


def test_unpaired_only_in_is_incomplete_when_past():
    [sh] = compute("1", [P("2026-09-01 08:00:00", IN)], STD, NOW)
    assert sh.status == ST_INCOMPLETE and sh.span_sec is None


def test_unpaired_only_out_is_incomplete():
    [sh] = compute("1", [P("2026-09-01 18:00:00", OUT)], STD, NOW)
    assert sh.status == ST_INCOMPLETE
    assert "kun chiqish bilan boshlangan" in sh.flags


def test_open_shift_today():
    [sh] = compute("1", [P("2026-09-30 08:00:00", IN)], STD, NOW)
    assert sh.status == ST_OPEN


def test_reentered_and_never_left_is_open_today_incomplete_later():
    ps = [P("2026-09-30 08:00:00", IN), P("2026-09-30 10:00:00", OUT), P("2026-09-30 11:00:00", IN)]
    [sh] = compute("1", ps, STD, NOW)
    assert sh.status == ST_OPEN
    ps_old = [P("2026-09-01 08:00:00", IN), P("2026-09-01 10:00:00", OUT), P("2026-09-01 11:00:00", IN)]
    [sh] = compute("1", ps_old, STD, NOW)
    assert sh.status == ST_INCOMPLETE


def test_guard_night_shift_assigned_to_start_date():
    ps = [
        P("2026-09-23 20:00:00", IN), P("2026-09-24 02:00:00", OUT), P("2026-09-24 02:20:00", IN),
        P("2026-09-24 08:05:00", OUT),
    ]
    [sh] = compute("1", ps, GUARD, NOW)
    assert sh.work_date == date(2026, 9, 23)
    assert sh.shift_type == SHIFT_GUARD_NIGHT
    assert sh.span_sec == 12 * 3600 + 5 * 60
    assert sh.inside_sec == 11 * 3600 + 45 * 60
    assert sh.status == ST_CLOSED


def test_guard_day_then_night_next_day_are_separate():
    ps = [
        P("2026-09-23 08:00:00", IN), P("2026-09-23 20:10:00", OUT),
        P("2026-09-24 19:55:00", IN), P("2026-09-25 08:00:00", OUT),
    ]
    shifts = compute("1", ps, GUARD, NOW)
    assert [s.shift_type for s in shifts] == [SHIFT_GUARD_DAY, SHIFT_GUARD_NIGHT]


def test_guard_unknown_shift_and_resolution():
    ps = [P("2026-09-23 14:00:00", IN), P("2026-09-23 23:00:00", OUT)]
    [sh] = compute("1", ps, GUARD, NOW)
    assert sh.shift_type == SHIFT_UNKNOWN
    assert "smena turi aniqlanmadi" in sh.flags
    res = {datetime(2026, 9, 23, 14, 0): (SHIFT_GUARD_DAY, False)}
    [sh] = compute("1", ps, GUARD, NOW, resolutions=res)
    assert sh.shift_type == SHIFT_GUARD_DAY and sh.status == ST_UNCONFIRMED
    res = {datetime(2026, 9, 23, 14, 0): (SHIFT_GUARD_DAY, True)}
    [sh] = compute("1", ps, GUARD, NOW, resolutions=res)
    assert sh.status == ST_CLOSED


def test_manual_correction():
    ps = [P("2026-09-01 08:00:00", IN)]
    corr = {date(2026, 9, 1): [Correction("chiqish", datetime(2026, 9, 1, 17, 0))]}
    [sh] = compute("1", ps, STD, NOW, corrections=corr)
    assert sh.status == ST_MANUAL
    assert sh.span_sec == 9 * 3600


def test_role_change_does_not_rewrite_old_days():
    ps = [
        # 1-sentabr: standart (kun chegarasi bo'yicha kunlik hisob)
        P("2026-09-01 08:00:00", IN), P("2026-09-01 18:00:00", OUT),
        # 10-sentabrdan qorovul (tungi smena)
        P("2026-09-10 20:00:00", IN), P("2026-09-11 08:00:00", OUT),
    ]

    def role_at(d):
        return GUARD if d >= date(2026, 9, 10) else STD

    shifts = compute_with_roles("1", ps, role_at, NOW)
    assert [(s.role, s.work_date) for s in shifts] == [("standart", date(2026, 9, 1)), ("qorovul", date(2026, 9, 10))]
    assert shifts[1].shift_type == SHIFT_GUARD_NIGHT and shifts[1].span_sec == 12 * 3600


def test_telegram_and_faceid_do_not_debounce_together():
    ps = [P("2026-09-01 08:00:00", IN, "telegram"), P("2026-09-01 08:00:30", IN, "faceid")]
    kept, _ = debounce(ps, 60)
    assert len(kept) == 2


def _guard_week(start_day):
    """Kunduzgi (09->21) va tungi (21->09) smenalar, orasida dam olish kunlari bilan."""
    from datetime import timedelta
    out = []
    plan = [("d", 0), ("n", 1), ("d", 4), ("n", 5), ("d", 8), ("n", 9), ("d", 12)]
    for kind, off in plan:
        d = datetime(2026, 9, start_day) + timedelta(days=off)
        if kind == "d":
            out += [Punch(d.replace(hour=9, minute=2), IN), Punch(d.replace(hour=21, minute=5), OUT)]
        else:
            out += [Punch(d.replace(hour=20, minute=55), IN), Punch((d + timedelta(days=1)).replace(hour=9, minute=3), OUT)]
    return out


def test_guard_pattern_detected():
    from davomat.engine import guard_shift_count
    n, days = guard_shift_count(_guard_week(1), time(9, 0), time(21, 0))
    assert n == 7 and n / days >= 0.4


def test_regular_worker_not_guard():
    from davomat.engine import guard_shift_count
    ps = []
    for dd in range(1, 21):
        ps += [P(f"2026-09-{dd:02d} 08:00:00", IN), P(f"2026-09-{dd:02d} 18:00:00", OUT)]
    n, _ = guard_shift_count(ps, time(9, 0), time(21, 0))
    assert n == 0


def test_milker_not_guard():
    from davomat.engine import guard_shift_count
    ps = []
    for dd in range(1, 21):
        ps += [P(f"2026-09-{dd:02d} 04:30:00", IN), P(f"2026-09-{dd:02d} 07:00:00", OUT),
               P(f"2026-09-{dd:02d} 18:30:00", IN), P(f"2026-09-{dd:02d} 23:50:00", OUT)]
    n, _ = guard_shift_count(ps, time(9, 0), time(21, 0))
    assert n == 0


def test_guard_09_21_shifts_with_new_windows():
    rp = RoleParams(code="qorovul", mode="shift", max_shift_hours=14, day_window=(7, 12), night_window=(19, 24))
    shifts = compute("1", _guard_week(1), rp, NOW)
    assert [s.shift_type for s in shifts] == ["kunduzgi", "tungi"] * 3 + ["kunduzgi"]
    assert all(s.status == ST_CLOSED for s in shifts)
    assert shifts[1].span_sec == 12 * 3600 + 8 * 60


def test_guard_back_to_back_night_then_day():
    rp = RoleParams(code="qorovul", mode="shift", max_shift_hours=14, day_window=(7, 12), night_window=(19, 24))
    ps = [P("2026-09-01 20:55:00", IN), P("2026-09-02 09:00:00", OUT),
          P("2026-09-02 09:05:00", IN), P("2026-09-02 21:03:00", OUT)]
    shifts = compute("1", ps, rp, NOW)
    assert [(s.shift_type, s.status) for s in shifts] == [("tungi", ST_CLOSED), ("kunduzgi", ST_CLOSED)]
    assert shifts[0].work_date == date(2026, 9, 1) and shifts[1].work_date == date(2026, 9, 2)


def test_guard_day_changes_at_noon():
    rp = RoleParams(code="qorovul", mode="shift", day_boundary=time(12, 0), max_shift_hours=14,
                    day_window=(6, 13), night_window=(17, 24))
    ps = [P("2026-09-23 21:00:00", IN), P("2026-09-24 09:00:00", OUT),   # tungi -> 23-sana
          P("2026-09-24 13:00:00", IN), P("2026-09-24 23:30:00", OUT),   # 12:00 dan keyin -> 24-sana
          P("2026-09-25 11:30:00", IN), P("2026-09-25 20:00:00", OUT)]   # 12:00 gacha -> 24-sana
    shifts = compute("1", ps, rp, NOW)
    assert [s.work_date for s in shifts] == [date(2026, 9, 23), date(2026, 9, 24), date(2026, 9, 24)]
    assert shifts[0].span_sec == 12 * 3600


def test_milker_day_changes_at_3am():
    ps = [P("2026-09-01 18:00:00", IN), P("2026-09-02 02:59:00", OUT), P("2026-09-02 03:01:00", IN)]
    shifts = compute("1", ps, MILK, NOW)
    assert [s.work_date for s in shifts] == [date(2026, 9, 1), date(2026, 9, 2)]


def test_report_sorted_least_worked_first():
    from davomat.engine import Shift
    from davomat.report import daily_html
    d = date(2026, 9, 1)
    mk = lambda emp, inside: Shift(employee_no=emp, work_date=d, role="standart", shift_type="kun", inside_sec=inside,
                                   span_sec=inside, kirish=datetime(2026, 9, 1, 8), chiqish=datetime(2026, 9, 1, 17),
                                   status="yopildi" if inside is not None else "to'liq emas")
    html = daily_html(d, [mk("A", 3600), mk("B", None), mk("C", 9 * 3600), mk("D", 5 * 3600)], lambda e: e, {})
    order = [html.index(f"<td>{e}") for e in ("A", "D", "C", "B")]
    assert order == sorted(order)
