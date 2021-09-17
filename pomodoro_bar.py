#!/usr/bin/env python3
"""
A simple pomodoro timer that supports pause, configuration, and statistics
With polybar and xmobar integrations.
"""
from functools import reduce
import argparse
import copy
from datetime import datetime, timedelta, date
from enum import Enum, auto
import json
from math import floor
from operator import itemgetter
import os
from pathlib import Path
from shutil import get_terminal_size, which
from statistics import mean
import sys
import termios
import textwrap
import time
import tty
from typing import Callable, Iterator, List, NamedTuple, Tuple, Union, Generator


class CustomHelpFormatter(argparse.ArgumentDefaultsHelpFormatter):
    def __init__(self, prog):
        super().__init__(prog, max_help_position=28, width=80)

    def _format_action_invocation(self, action):
        if action.option_strings and action.nargs != 0:
            default = self._get_default_metavar_for_optional(action)
            args_string = self._format_args(action, default)
            result = ', '.join(action.option_strings) + ' ' + args_string
        else:
            result = super()._format_action_invocation(action)
        return result + ' ' * (23 - len(result))

    def add_usage(self, usage, actions, groups, prefix='Usage: '):
        return super().add_usage(usage, actions, groups, prefix)


# -----------------------------------------------------------------------------
# types


class BarType(Enum):
    NONE = auto()
    POLYBAR = auto()
    XMOBAR = auto()

    def __repr__(self):
        return self.name.lower()

    @staticmethod
    def arg_parse_type(s):
        try:
            return BarType[s.upper()]
        except KeyError:
            return s


class NamedPipeStatus(Enum):
    VALID = auto()
    INVALID = auto()


class SessionType(Enum):
    WORK = auto()
    REST = auto()


class Session(NamedTuple):
    num: int
    command: str
    seconds: int
    type: SessionType


class TimerIdleStatus(Enum):
    TOBEGIN = auto()
    PAUSE = auto()


Record = dict[str, dict[str, int]]

# -----------------------------------------------------------------------------
# functions


def bar_create_label(s: Session) -> str:
    return "[" + str(s.num) + "]"


def bar_create_status(ts: TimerIdleStatus, s: Session) -> str:
    if ts == TimerIdleStatus.PAUSE:
        return "PAUSE"
    return "START" if s.type == SessionType.WORK else "BREAK"


def bar_update(bartype: BarType, working: bool, text: str) -> None:
    (path_w, path_i) = named_pipe_get_paths(bartype)
    if path_w == None or path_i == None:
        return
    else:
        (text_w, text_i) = ("", text) if working else (text, "")
        named_pipe_write(path_w, text_w)
        named_pipe_write(path_i, text_i)


def cli_create_progressbar(s: Session) -> str:
    bar = "w-b-w-b-w-b-w-l"
    i = 4 * ((s.num - 1) % 4) + (0 if s.type == SessionType.WORK else 2)
    return (bar[:i] + "[" + bar[i:i + 1] + "]" + bar[i + 1:])


def cli_get_echo_functions() -> Tuple[Callable[[], None], Callable[[], None]]:
    fd = sys.stdin.fileno()
    attr_old = termios.tcgetattr(fd)
    attr_new = termios.tcgetattr(fd)
    attr_new[3] = attr_new[3] & ~termios.ECHO  # lflags
    disable_echo = lambda: termios.tcsetattr(fd, termios.TCSADRAIN, attr_new)
    restore_echo = lambda: termios.tcsetattr(fd, termios.TCSADRAIN, attr_old)
    return disable_echo, restore_echo


def cli_hide_cursor() -> None:
    #     if os.name == 'posix':
    print("\x1b[?25l", end="")


def cli_show_cursor() -> None:
    #     if os.name == 'posix':
    print("\x1b[?25h", end="")


def cli_get_timer_keyhint(s: Session) -> str:
    if s.type == SessionType.WORK:
        return "CTRL+c to Pause"
    return "CTRL+c to Skip"


def cli_update(text: str) -> None:
    w = get_terminal_size().columns
    print("\r\033[2K" + text[:w], end='')


def date_get_monday(week_offset: int) -> date:
    today = datetime.now().date()
    return today - timedelta(days=(today.weekday() + week_offset * 7))


def display_create_hhmmss(sec: int) -> str:
    minute, second = divmod(sec, 60)
    hour, minute = divmod(minute, 60)
    hour_str = str(hour).zfill(2) + ":" if hour > 0 else ''
    return hour_str + str(minute).zfill(2) + ":" + str(second).zfill(2)


def display_sync_with_timer(s: Session, bartype: BarType) \
                            -> Generator[None, int, None]:
    bar_label = bar_create_label(s)
    keyhint = cli_get_timer_keyhint(s)
    progress_bar = cli_create_progressbar(s)
    working = s.type == SessionType.WORK
    while True:
        sec = (yield)
        if (sec >= 0):
            digit = display_create_hhmmss(sec)

            cli_update(text=progress_bar + " " + digit + " - " + keyhint)
            bar_update(bartype, working, text=bar_label + digit)


def get_user_choice(charset: List[str]) -> str:
    fd = sys.stdin.fileno()
    attr_old = termios.tcgetattr(fd)
    tty.setraw(fd, when=termios.TCSAFLUSH)

    ch = keep_asking_for_choice(charset)

    termios.tcsetattr(fd, termios.TCSADRAIN, attr_old)
    return ch


def keep_asking_for_choice(charset: List[str]) -> str:
    readchar = lambda: sys.stdin.buffer.read(1).decode(sys.stdin.encoding)
    while True:
        try:
            if (ch := readchar()) in charset:
                return ch
            else:
                pass
        except UnicodeError:
            pass


def named_pipe_ensure_exist(path: str) -> NamedPipeStatus:
    status = named_pipe_get_status(path)
    if status == NamedPipeStatus.INVALID:
        print(path + " is not a named pipe ...")
        Path(path).unlink(missing_ok=True)
        os.mkfifo(path)
        print("Created a named pipe at " + path)
    return status


def named_pipes_ensure_exist(bartype: BarType) -> None:
    path_i, path_w = named_pipe_get_paths(bartype)
    status_i = path_i != None and named_pipe_ensure_exist(path_i)
    status_w = path_w != None and named_pipe_ensure_exist(path_w)

    will_show_hint = status_i == NamedPipeStatus.INVALID \
        or status_w == NamedPipeStatus.INVALID
    named_pipe_show_recompile_hint(will_show_hint, bartype)


def named_pipe_get_paths(
        bartype: BarType) -> Tuple[Union[str, None], Union[str, None]]:
    idle_path, work_path = None, None
    if bartype == BarType.POLYBAR or bartype == BarType.XMOBAR:
        idle_path, work_path = "/tmp/.pomodoro-bar-i", "/tmp/.pomodoro-bar-w"
    return idle_path, work_path


def named_pipe_get_status(path: str) -> NamedPipeStatus:
    if Path(path).is_fifo():
        return NamedPipeStatus.VALID
    return NamedPipeStatus.INVALID


def named_pipe_show_recompile_hint(will_show: bool, bartype: BarType) -> None:
    if will_show:
        if bartype == BarType.XMOBAR:
            print("*** Please compile xmobar and rerun ***")
        if bartype == BarType.POLYBAR:
            print("*** Please rerun ***")
        sys.exit()


def named_pipe_write(path, text) -> None:
    Path(path).write_text(text + "\n")


def parser_create() -> argparse.ArgumentParser:
    type_err = lambda x: argparse.ArgumentTypeError(x)

    def check_command_type(s: str) -> str:
        if s == '""':
            return ""
        elif which(s.split(' ')[0]) == None:
            raise type_err("%s not found in PATH" % s)
        return s

    def check_posint_type(s: str) -> int:
        try:
            ival = int(s)
        except:
            raise type_err("%s must be positive integer" % s)
        else:
            if ival <= 0:
                raise type_err("%s must be positive integer" % s)
            return ival

    parser = argparse.ArgumentParser(add_help=False,
                                     formatter_class=CustomHelpFormatter,
                                     prog='pomodoro-bar.py')

    parser_timer = parser.add_argument_group("Timer options")
    parser_timer.add_argument(
        "-w",
        "--work",
        type=check_posint_type,
        default=25,
        metavar="MIN",
        help="Minutes per work session",
    )
    parser_timer.add_argument(
        "-b",
        "--break",
        type=check_posint_type,
        default=5,
        metavar="MIN",
        help="Minutes per break session",
    )
    parser_timer.add_argument(
        "-l",
        "--longbreak",
        type=check_posint_type,
        default=15,
        metavar="MIN",
        help="Minutes per long break session",
    )
    parser_timer.add_argument(
        "-s",
        "--session",
        type=check_posint_type,
        default=1,
        metavar="NUM",
        help="Session number on start",
    )
    parser_timer.add_argument(
        "--cmdwork",
        type=check_command_type,
        default='""',
        metavar="CMD",
        help="System command to execute when work session ends\
                (e.g. \"xset dpms force off\")",
    )
    parser_timer.add_argument(
        "--cmdbreak",
        type=check_command_type,
        default='""',
        metavar="CMD",
        help="Like --cmdwork but for unskipped break session",
    )
    parser_timer.add_argument(
        "--bartype",
        type=BarType.arg_parse_type,
        default=BarType.NONE,
        metavar="BAR",
        choices=list(BarType),
        help="Specify bar type from " + str(list(BarType)) + " to update.\
        May require additional settings",
    )

    parser_info = parser.add_argument_group("Information options")
    parser_info.add_argument(
        "--raw",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Show raw record in minutes",
    )
    parser_info.add_argument(
        "-r",
        "--record",
        action="store_true",
        default=argparse.SUPPRESS,
        help=
        "Show last 4 weeks summary (add -n option to adjust number of weeks and -w option to adjust session length)"
    ),
    parser_info.add_argument(
        "-n",
        type=check_posint_type,
        default=4,
        metavar="NUM",
        help=argparse.SUPPRESS,
    )
    parser_info.add_argument(
        "-v",
        "--version",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Show version",
    )
    parser_info.add_argument(
        "-h",
        "--help",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Show this help text",
    )
    return parser


def record_add_session(work_min: int) -> None:
    record_old = record_read(RECORD_PATH)
    this_monday = str(date_get_monday(0))
    today_letter = datetime.now().date().strftime("%a")
    new_record = record_create_updated(record_old, this_monday, today_letter,
                                       work_min)
    record_update(new_record)


def record_create_updated(old_record: Record, this_monday: str,
                          today_letter: str, minutes: int) -> Record:
    new_record = copy.deepcopy(old_record)
    if not this_monday in old_record:
        days_3_chars = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
        week_template = dict.fromkeys(days_3_chars, 0)
        new_record[this_monday] = week_template

    new_record[this_monday][today_letter] += minutes
    return new_record


def record_ensure_exist(path: str) -> None:
    Path(path).parents[0].mkdir(mode=0o755, parents=True, exist_ok=True)
    if not Path(path).is_file():
        Path(path).write_text("{}")


def record_get_existing_week_summary(week: List[int], num_day: int,
                                     work_min: int) -> List[str]:
    workload = [round(x / work_min, 1) for x in week[:num_day]]
    workload_str = [str(x) for x in workload] + ['' for _ in range(num_day, 7)]
    workload_avg_str = [str(round(mean(workload), 1))]
    return workload_str + workload_avg_str


def record_get_week_summary(record: Record, monday: str, num_day: int,
                            work_min: int) -> List[str]:
    if monday in record:
        week = list(record[monday].values())
        return record_get_existing_week_summary(week, num_day, work_min)
    else:
        return [""] * 8


def record_prettify_onerow(max_cols: List[int], l: List[str]) -> str:
    return '  '.join([y.rjust(x, ' ') for (x, y) in zip(max_cols, l)])


def record_print_pretty(max_cols: List[int], res: List[List[str]]) -> None:
    print(*[record_prettify_onerow(max_cols, x) for x in res], sep='\n')


def record_read(path: str) -> Record:
    try:
        result = json.loads(Path(path).read_text())
    except ValueError:
        print(path + " is not a valid JSON")
        sys.exit()
    return result


def record_update(updated_record: Record) -> None:
    Path(RECORD_PATH).write_text(json.dumps(updated_record))


def session_create(w: int, b: int, l: int, cmd_w: str, cmd_b: str,
                   n: int) -> Session:
    get_alternate = lambda choice1, choice2, n: [choice1, choice2][(n - 1) % 2]
    get_alternate_except_last = lambda choice1, choice2, last, n: \
        get_alternate(choice1, choice2, n) if n % 8 > 0 else last

    return Session(
        num=floor((n + 1) / 2),
        command=get_alternate(cmd_w, cmd_b, n),
        seconds=get_alternate_except_last(w, b, l, n),
        type=get_alternate(SessionType.WORK, SessionType.REST, n),
    )


def session_generator(w: int, b: int, l: int, cmd_w: str, cmd_b: str,
                      start_session_num) -> Iterator[Session]:
    sessions_per_session_num = 2
    num_past_sessions = (start_session_num - 1) * sessions_per_session_num
    n = num_past_sessions
    while True:
        n = n + 1
        yield session_create(w, b, l, cmd_w, cmd_b, n)


def session_loop(bartype: BarType, session: Iterator[Session]) -> None:
    while True:
        session_start(next(session), bartype, TimerIdleStatus.TOBEGIN, 0)


def session_start(s: Session, bartype: BarType, \
                        tmr_status: TimerIdleStatus, sec_left: int) -> None:
    tmr_len = sec_left if tmr_status == TimerIdleStatus.PAUSE else s.seconds
    digit = display_create_hhmmss(tmr_len)
    bar_text = bar_create_label(s) + bar_create_status(tmr_status, s)
    cli_text = cli_create_progressbar(s) + " " + digit + " - [s]tart or [q]uit"

    bar_update(bartype, working=False, text=bar_text)
    cli_update(cli_text)

    if get_user_choice(['q', 's']) == 's':
        sec_left_new = timer(s, bartype, tmr_len)
        timer_end_handler(s, sec_left_new)
        if will_repeat_session(s, sec_left_new):
            session_start(s, bartype, TimerIdleStatus.PAUSE, sec_left_new)
    else:
        cli_update("")  # clear line
        bar_update(bartype, working=False, text='POMODORO')
        sys.exit()


def show_help(parser: argparse.ArgumentParser) -> None:
    intro = "pomodoro-bar: A pausable and configurable Pomodoro Timer with \
stats.\nThe record file is stored at $XDG_DATA_HOME/pomodoro-bar\
/record.json, where XDG_DATA_HOME is " + XDG_DATA_HOME
    print(textwrap.fill(intro, width=80), end="\n\n")
    parser.print_help()


def show_record_raw() -> None:
    print(Path(RECORD_PATH).read_text())


def show_record_summary(record: Record, w_min: int, num_week: int) -> None:
    num_day_1st = datetime.now().date().weekday() + 1
    monday_1st = str(date_get_monday(0))
    monday_rest = [str(date_get_monday(x)) for x in list(range(1, num_week))]

    header = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun", "Avg"]
    header_sep = ["---"] * 8
    res_1st = record_get_week_summary(record, monday_1st, num_day_1st, w_min)
    res_rest = [
        record_get_week_summary(record, m, 7, w_min) for m in monday_rest
    ]
    res = [header] + [header_sep] + [res_1st] + res_rest

    print("Number of " + str(w_min) + "-minute sessions from this week (top)")
    lens = [list(map(len, x)) for x in res]
    max_cols = reduce(lambda a, b: list(map(max, a, b)), lens, [0] * 8)
    record_print_pretty(max_cols, res)


def show_version() -> None:
    print("pomodoro-bar-py, version 0.1.0\n\n\
License (SPDX): GPL-2.0-only\n\
Author: Theerawat Kiatdarakun")


def timer(s: Session, bartype: BarType, sec: int) -> int:
    display_update = display_sync_with_timer(s, bartype)
    next(display_update)
    try:
        while sec > 0:
            display_update.send(sec)
            time.sleep(1)
            sec = sec - 1
        return 0
    except KeyboardInterrupt:
        return sec
    finally:
        display_update.close()


def timer_end_handler(s: Session, sec_left: int) -> None:
    if sec_left == 0:
        if s.type == SessionType.WORK:
            record_add_session(work_min=int(s.seconds / 60))
        os.system(s.command)


def will_repeat_session(s: Session, sec_left: int) -> bool:
    return (sec_left != 0) and (s.type == SessionType.WORK)


# -----------------------------------------------------------------------------
try:
    import xdg.BaseDirectory as bd
    XDG_DATA_HOME = bd.xdg_data_home
except ImportError:
    #     if os.name == 'posix':
    XDG_DATA_HOME = str(Path.home() / ".local/share")

RECORD_PATH = XDG_DATA_HOME + "/pomodoro-bar/record.json"

if __name__ == "__main__":
    parser = parser_create()
    args = parser.parse_args()

    if 'help' in args and args.help:
        show_help(parser)
    elif 'version' in args and args.version:
        show_version()
    elif 'raw' in args and args.raw:
        show_record_raw()
    elif 'record' in args and args.record:
        show_record_summary(record_read(RECORD_PATH),
                            w_min=args.work,
                            num_week=args.n)
    else:
        w_min, b_min, l_min, start_session_num, cmd_w, cmd_b, bartype, = \
            itemgetter( 'work', 'break', 'longbreak', 'session', 'cmdwork',
                        'cmdbreak', 'bartype')(vars(args))

        record_ensure_exist(RECORD_PATH)
        named_pipes_ensure_exist(bartype)

        (w_sec, b_sec, l_sec) = map(lambda x: x * 60, (w_min, b_min, l_min))

        session = session_generator(w_sec, b_sec, l_sec, cmd_w, cmd_b,
                                    start_session_num)

        disable_keyboard_echo, restore_keyboard_echo = cli_get_echo_functions()
        try:
            disable_keyboard_echo()
            cli_hide_cursor()

            session_loop(bartype, session)
        finally:
            cli_show_cursor()
            restore_keyboard_echo()
