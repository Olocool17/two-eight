from calendar import week
import curses
import random
import datetime
import locale
import logging

random.seed()

locale.setlocale(locale.LC_ALL, "")

logformat = "[%(asctime)s] %(name)-8s %(levelname)-8s %(message)-s"
logging.basicConfig(
    filename="two-eight.log",
    filemode="w",
    format=logformat,
    encoding="utf-8",
    level=logging.DEBUG,
)
log = logging.getLogger()
log.info("Logger initialised")


class TwoEight:
    def __init__(self, stdscr):
        self.screen = stdscr
        curses.use_default_colors()
        curses.curs_set(0)
        self.screen.leaveok(False)
        self.weekdata = WeekData.dummy(48)
        self.resize()
        self.input_loop()

    def resize(self):
        self.y, self.x = self.screen.getmaxyx()
        self.screen.clear()
        curses.resize_term(self.y, self.x)
        self.refresh()

    def refresh(self):
        self.frames = [
            TimetableFrame(self.screen, 0, 0, self.y - 1, 50, self.weekdata),
            ActivityFrame(self.screen, 0, 50, self.y - 1, self.x - 2, self.weekdata),
        ]
        self.weekdata.add_frames(*self.frames)
        self.draw_frame()
        self.screen.refresh()
        for frame in self.frames:
            frame.refresh()

    def input_loop(self):
        while True:
            c = self.screen.getch()
            if c == curses.KEY_RESIZE:
                self.resize()
            elif c == 3:  # Crtl + C
                self.exit()
            else:
                for frame in self.frames:
                    frame.input_loop(c)

    def draw_frame(self):
        self.screen.border(0, 0, 0, 0, 0, 0, 0, 0)
        self.screen.addstr(
            0, (self.x // 2) - len("two-eight") // 2, "two-eight", curses.A_REVERSE
        )

    def exit(self):
        self.screen.clear()
        self.screen.refresh()
        raise CleanExit


class Pad:
    def __init__(self, screen, padheight, padwidth, clipuly, clipulx, clipbry, clipbrx):
        self.screen = screen
        self.pad = curses.newpad(padheight, padwidth)
        self.padheight, self.padwidth = padheight, padwidth
        self.clipuly, self.clipulx = clipuly, clipulx
        self.clipbry, self.clipbrx = clipbry, clipbrx
        self.clipheight = self.clipbry - self.clipuly + 1
        self.clipwidth = self.clipbrx - self.clipulx + 1
        self.pad.clear()

    def draw_static(self):
        pass

    def refresh(self):
        self.pad.refresh(
            0,
            0,
            self.clipuly,
            self.clipulx,
            self.clipbry,
            self.clipbrx,
        )


class Frame:
    def __init__(self, screen, uly, ulx, bry, brx):
        self.screen = screen
        self.pads = []
        self.uly, self.ulx = uly, ulx
        self.bry, self.brx = bry, brx
        self.height = self.bry - self.uly - 1  # amount of enclosed rows
        self.width = self.brx - self.ulx - 1  # amount of enclosed columns
        self.draw_cornerless_frame()

    def refresh(self):
        for pad in self.pads:
            pad.refresh()

    def add_pad(self, pad: Pad):
        """Adds a pad to this frame, interpreting its 'clip' coordinates as relative to the frame"""
        if pad.clipbry >= self.height or pad.clipbrx >= self.width:
            log.warning(
                f"Could not add pad with relative right corner ({pad.clipbry, pad.clipbrx}) to frame with height {self.height} and width {self.width}"
            )
            return
        pad.clipuly += self.uly + 1
        pad.clipbry += self.uly + 1
        pad.clipulx += self.ulx + 1
        pad.clipbrx += self.ulx + 1
        self.pads.append(pad)
        pad.draw_static()

    def draw_cornerless_frame(self):
        # # is a placeholder corner character
        self.screen.addch(self.uly, self.ulx, 35)  # #
        self.screen.addch(self.uly, self.brx, 35)  # #
        self.screen.addch(self.bry, self.ulx, 35)  # #
        self.screen.addch(self.bry, self.brx, 35)  # #
        # left side
        for y in range(1, self.height + 1):
            coords = self.uly + y, self.ulx
            if self.screen.inch(*coords) & 0xFF == 35:
                continue
            painted_char = "│"
            self.screen.addch(*coords, painted_char)
        # right side
        for y in range(1, self.height + 1):
            coords = self.uly + y, self.brx
            if self.screen.inch(*coords) & 0xFF == 35:
                continue
            painted_char = "│"
            self.screen.addch(*coords, painted_char)
        # top side
        for x in range(1, self.width + 1):
            coords = self.uly, self.ulx + x
            if self.screen.inch(*coords) & 0xFF == 35:
                continue
            painted_char = "─"
            self.screen.addch(*coords, painted_char)
        # bottom side
        for x in range(1, self.width + 1):
            coords = self.bry, self.ulx + x
            if self.screen.inch(*coords) & 0xFF == 35:
                continue
            painted_char = "─"
            self.screen.addch(*coords, painted_char)


class VertScrollPad(Pad):
    def __init__(self, screen, padheight, padwidth, clipuly, clipulx, clipbry, clipbrx):
        super().__init__(
            screen, padheight, padwidth, clipuly, clipulx, clipbry, clipbrx
        )
        self.scrollpos = 0
        self.prescroll = self.clipheight // 4

    def refresh(self):
        self.pad.refresh(
            self.scrollpos,
            0,
            self.clipuly,
            self.clipulx,
            min(self.clipbry, self.clipuly + self.padheight - 1),
            self.clipbrx,
        )

    def scroll(self, select):
        select_scroll_delta_lower = select - self.prescroll
        select_scroll_delta_upper = select - self.clipheight + self.prescroll
        if select_scroll_delta_upper > self.scrollpos:
            self.scrollpos = select_scroll_delta_upper
        elif select_scroll_delta_lower < self.scrollpos:
            self.scrollpos = select_scroll_delta_lower
        self.scrollpos = max(0, min(self.padheight - self.clipheight, self.scrollpos))


class TimetablePad(VertScrollPad):
    def __init__(self, screen, padwidth, clipuly, clipulx, clipbry, clipbrx, weekdata):
        self.weekdata = weekdata
        self.days = 7
        super().__init__(
            screen,
            self.weekdata.nr_timesegments,
            padwidth,
            clipuly,
            clipulx,
            clipbry,
            clipbrx,
        )
        self.timewidth = 5
        self.slotwidth = 5
        self.selected = [(0, 0)]  # list of selected timeslots by indices
        self.cursor_x, self.cursor_y = 0, 0
        self.hold_cursor_x, self.hold_cursor_y = 0, 0
        self.weekdata.selected_timeslot = self.weekdata.timetable[self.cursor_y][
            self.cursor_x
        ]

    def draw_static(self):
        if (
            self.weekdata.nr_timesegments % 24 != 0
            and 24 % self.weekdata.nr_timesegments != 0
        ):
            pass
            # PH : Log warning here
        for i in range(0, self.weekdata.nr_timesegments):
            minutes = int(i * (24 / self.weekdata.nr_timesegments) * 60)
            self.pad.addstr(
                i, 0, f"{minutes // 60:02d}:{minutes % 60:02d}", curses.A_DIM
            )
        self.scrollpos = 0
        self.draw_cursor()
        for x in range(self.days):
            for y in range(self.padheight):
                self.draw_timeslot(y, x)

    def draw_timeslot(self, y, x):
        """Draw a timeslot by its y/x index"""
        timeslot = self.weekdata.timetable[y][x]
        center_x = self.timewidth + (self.slotwidth + 1) * x + 1
        if timeslot.plan == timeslot.verify:
            char = "█"
        else:
            char = "░"
        if timeslot.verify != None:
            for x_paint in range(center_x, center_x + self.slotwidth):
                self.pad.addch(
                    y, x_paint, char, curses.color_pair(timeslot.verify.color_pair)
                )
        if timeslot.plan != None:
            self.pad.addch(
                y,
                center_x + self.slotwidth // 2,
                char,
                curses.color_pair(timeslot.plan.color_pair),
            )

    def draw_cursor(self):
        self.pad.addch(self.cursor_y, self.timewidth + self.cursor_x * 6, ">")
        self.pad.addch(
            self.cursor_y, self.timewidth + self.cursor_x * 6 + self.slotwidth + 1, "<"
        )

    def select(self, individ=True):
        self.cursor_y %= self.padheight
        self.cursor_x %= self.days
        self.weekdata.change_timeslot(self.cursor_y, self.cursor_x)
        self.scroll(self.cursor_y)
        self.clear_select()
        if individ:
            self.hold_cursor_y, self.hold_cursor_x = self.cursor_y, self.cursor_x
            self.selected = [(self.cursor_y, self.cursor_x)]
        else:
            self.selected = [
                (y, x)
                for y in range(
                    min(self.cursor_y, self.hold_cursor_y),
                    max(self.cursor_y, self.hold_cursor_y) + 1,
                )
                for x in range(
                    min(self.cursor_x, self.hold_cursor_x),
                    max(self.cursor_x, self.hold_cursor_x) + 1,
                )
            ]

        for y, x in self.selected:
            self.pad.addch(y, self.timewidth + x * 6, "+")
            self.pad.addch(y, self.timewidth + x * 6 + self.slotwidth + 1, "+")
        self.draw_cursor()
        self.refresh()

    def clear_select(self):
        for y, x in self.selected:
            self.pad.addch(y, 5 + x * 6, " ")
            self.pad.addch(y, 11 + x * 6, " ")

    def input_loop(self, c):
        if c == ord("w") or c == ord("W"):
            self.cursor_y -= 1
            self.select(individ=bool(c - ord("W")))
        elif c == ord("s") or c == ord("S"):
            self.cursor_y += 1
            self.select(individ=bool(c - ord("S")))
        elif c == ord("a") or c == ord("A"):
            self.cursor_x -= 1
            self.select(individ=bool(c - ord("A")))
        elif c == ord("d") or c == ord("D"):
            self.cursor_x += 1
            self.select(individ=bool(c - ord("D")))


class TimetableHeaderPad(Pad):
    def __init__(
        self, screen, padheight, padwidth, clipuly, clipulx, clipbry, clipbrx, weekdata
    ):
        super().__init__(
            screen, padheight, padwidth, clipuly, clipulx, clipbry, clipbrx
        )
        self.weekdata = weekdata

    def draw_static(self):
        weekdate = self.weekdata.date
        month = weekdate.strftime("%b")
        self.pad.addstr(0, 5 - len(month), month)
        year = weekdate.strftime("%Y")
        self.pad.addstr(1, 5 - len(year), year)
        for i in range(7, self.padwidth, 6):
            self.pad.addstr(0, i, weekdate.strftime("%d"))
            self.pad.addstr(1, i, weekdate.strftime("%a"))
            weekdate += datetime.timedelta(days=1)


class TimetableFrame(Frame):
    def __init__(self, screen, uly, ulx, bry, brx, weekdata):
        self.weekdata = weekdata
        super().__init__(
            screen,
            uly,
            ulx,
            bry,
            brx,
        )
        self.header = TimetableHeaderPad(
            self.screen,
            3,
            self.width,
            0,
            0,
            2,
            self.width - 1,
            weekdata,
        )
        self.add_pad(self.header)
        self.timetable = TimetablePad(
            self.screen,
            self.width,
            self.header.clipheight,
            0,
            self.height - 1,
            self.width - 1,
            self.weekdata,
        )
        self.add_pad(self.timetable)

    def input_loop(self, c):
        self.timetable.input_loop(c)


class ActivityTablePad(VertScrollPad):
    def __init__(
        self, screen, padheight, padwidth, clipuly, clipulx, clipbry, clipbrx, weekdata
    ):
        self.weekdata = weekdata
        super().__init__(
            screen,
            padheight,
            padwidth,
            clipuly,
            clipulx,
            clipbry,
            clipbrx,
        )
        self.cursor = 0
        self.activities_list = []
        self.update_activities()
        self.draw_cursor()

    def update_activities(self):
        self.activities_list = []
        for i, activity in enumerate(self.weekdata.activities.values()):
            self.activities_list.append(activity)
            self.pad.addstr(i, 11, activity.name)
            self.pad.chgat(i, 0, curses.color_pair(activity.color) + curses.A_REVERSE)

        self.update_activities_markers()

    def update_activities_markers(self):
        for i, activity in enumerate(self.activities_list):
            if activity == self.weekdata.selected_timeslot.plan:
                self.pad.addch(
                    i, 2, "x", curses.color_pair(activity.color) + curses.A_REVERSE
                )
            if activity == self.weekdata.selected_timeslot.verify:
                self.pad.addch(
                    i, 5, "x", curses.color_pair(activity.color) + curses.A_REVERSE
                )
        self.refresh()

    def clear_activities_markers(self):
        for i, activity in enumerate(self.activities_list):
            if activity == self.weekdata.selected_timeslot.plan:
                self.pad.addch(
                    i, 2, " ", curses.color_pair(activity.color) + curses.A_REVERSE
                )
            if activity == self.weekdata.selected_timeslot.verify:
                self.pad.addch(
                    i, 5, " ", curses.color_pair(activity.color) + curses.A_REVERSE
                )

    def clear_cursor(self):
        self.pad.addch(
            self.cursor,
            8,
            " ",
            curses.color_pair(self.activities_list[self.cursor].color)
            + curses.A_REVERSE,
        )

    def draw_cursor(self):
        self.pad.addch(
            self.cursor,
            8,
            ">",
            curses.color_pair(self.activities_list[self.cursor].color)
            + curses.A_REVERSE,
        )

    def select(self):
        self.cursor %= len(self.weekdata.activities)
        self.scroll(self.cursor)
        self.draw_cursor()
        self.refresh()

    def input_loop(self, c):
        if c == ord("k"):
            self.clear_cursor()
            self.cursor -= 1
            self.select()
        elif c == ord("j"):
            self.clear_cursor()
            self.cursor += 1
            self.select()


class ActivityHeaderPad(Pad):
    def __init__(self, screen, padwidth, clipuly, clipulx, clipbry, clipbrx):
        super().__init__(screen, 2, padwidth, clipuly, clipulx, clipbry, clipbrx)

    def draw_static(self):
        self.pad.addch(0, 2, "p")
        self.pad.addch(0, 5, "v")
        self.pad.addstr(0, 11, "name")


class ActivityFrame(Frame):
    def __init__(self, screen, uly, ulx, bry, brx, weekdata):
        self.weekdata = weekdata
        super().__init__(screen, uly, ulx, bry, brx)
        self.header = ActivityHeaderPad(
            self.screen, self.width, 0, 0, 1, self.width - 1
        )
        self.add_pad(self.header)
        self.activitytable = ActivityTablePad(
            self.screen,
            len(self.weekdata.activities),
            self.width,
            self.header.clipheight,
            0,
            self.height - 1,
            self.width - 1,
            self.weekdata,
        )
        self.add_pad(self.activitytable)

    def input_loop(self, c):
        self.activitytable.input_loop(c)


class Activity:
    color_counter = 16
    color_pair_counter = 16

    def __init__(self, name: str, r, g, b, desc=""):
        self.name = name
        self.r = r
        self.g = g
        self.b = b
        self.desc = desc

        curses.init_color(Activity.color_counter, r, g, b)
        self.color = Activity.color_counter
        curses.init_pair(Activity.color_counter, self.color, 0)
        self.color_pair = Activity.color_pair_counter

        Activity.color_counter = (
            Activity.color_counter + 1
            if Activity.color_counter != curses.COLORS - 1
            else 16
        )
        Activity.color_pair_counter = (
            Activity.color_pair_counter + 1
            if Activity.color_pair_counter != curses.COLOR_PAIRS - 1
            else 1
        )

    @classmethod
    def dummy(cls, name):
        return cls(
            name,
            random.randrange(0, 1001),
            random.randrange(0, 1001),
            random.randrange(0, 1001),
        )


class Timeslot:
    def __init__(self, plan: Activity, verify: Activity):
        self.plan = plan
        self.verify = verify

    @classmethod
    def from_strings(cls, plan: str, verify: str, activities: dict):
        try:
            plan = activities[plan]
        except KeyError:
            log.error(
                f"Could not find an activity with name '{plan}' referenced in timeslot's planned activity."
            )
        if verify == "-":
            return cls(plan, None)
        try:
            verify = activities[verify]
        except KeyError:
            log.error(
                f"Could not find an activity with name '{verify}' referenced in timeslot's verify activity."
            )
        return cls(plan, verify)


class WeekData:
    """Backend for week_pad class"""

    def __init__(
        self,
        nr_timesegments: int,
        activities: dict,
        timetable: list,
        week: int = 1,
        year: int = 1,
        date: datetime.date = None,
    ):
        self.nr_timesegments = nr_timesegments
        self.activities = dict(sorted(activities.items()))
        self.selected_activity = None
        self.timetable = timetable
        self.selected_timeslot = None
        self.activityframe = None
        self.timetableframe = None
        if datetime.date != None:
            self.date = datetime.date.fromisocalendar(year, week, 1)
        self.date = date - datetime.timedelta(days=date.weekday())

    def add_activity(self, activity: Activity):
        self.activities.update({activity.name: activity})
        self.activities = dict(sorted(self.activities.items()))

    def add_frames(self, timetableframe: TimetableFrame, activityframe: ActivityFrame):
        self.timetableframe = timetableframe
        self.activityframe = activityframe

    def change_timeslot(self, y, x):
        self.activityframe.activitytable.clear_activities_markers()
        self.selected_timeslot = self.timetable[y][x]
        self.activityframe.activitytable.update_activities_markers()

    @staticmethod
    def from_file(parser, week: int, year: int):
        return parser.parse_week(week, year)

    @classmethod
    def dummy(cls, nr_timesegments, nr_activities=10):
        """Returns a week_data object with placeholder dummy data"""
        activities = {
            "dummy" + str(i): Activity.dummy("dummy" + str(i))
            for i in range(nr_activities)
        }
        return cls(
            nr_timesegments,
            activities,
            [
                [
                    Timeslot.from_strings(
                        "dummy" + str(random.randrange(0, nr_activities)),
                        "dummy" + str(random.randrange(0, nr_activities)),
                        activities,
                    )
                    for j in range(7)
                ]
                for i in range(nr_timesegments)
            ],
            date=datetime.date(2022, 10, 31),
        )


class Parser:
    """Manages reading and writing from/to a database file"""

    delimiter = "\t"

    def __init__(self, dbfile_path="data.te"):
        self.dbfile_path = dbfile_path
        self.file = None
        self.open()

    def __del__(self):
        self.file.close()

    def open(self):
        """Tries to load the database file"""
        try:
            self.file = open(self.dbfile_path, mode="r", encoding="utf-8")
        except FileNotFoundError as e:
            log.warning(
                f'Could not find file with relative filepath "{self.dbfile_path}", original error: %s',
                exc_info=e,
            )
        self.line = 0

    def close(self):
        """Closes the database file"""
        if self.file != None:
            self.file.close()

    @staticmethod
    def ensure_open(func):
        """Ensures the database file is loaded into the parser"""

        def decorated(self, *args, **kwargs):
            if self.file == None:
                self.open()
            return func(self, *args, **kwargs)

        return decorated

    @ensure_open
    def parse_week(self, week: int, year: int) -> WeekData:
        """Searches the file for a week/year entry, then parses the contents of the week, returning a WeekData object"""
        self.seek_for(str(year), str(week))
        nr_timesegments, nr_activities = self.parse_next_line(2)
        nr_timesegments, nr_activities = int(nr_timesegments), int(nr_activities)
        activities = self.parse_activities(nr_activities)
        timetable = self.parse_timetable(nr_timesegments, activities)
        self.reset_seek()
        return WeekData(nr_timesegments, activities, timetable, week, year)

    def parse_activities(self, nr_activities: int) -> dict:
        """Helper function for parse_week : parses the activities of a week"""
        activities = dict()
        for _ in range(nr_activities):
            name, r, g, b = self.parse_next_line(4)
            activities.update({name: Activity(name, r, g, b)})
        self.parse_next_line()
        return activities

    def parse_timetable(self, nr_timesegments: int, activities: dict) -> list:
        """Helper function for parse_week : parses the timetable of a week"""
        timetable = [[0] * 7 for _ in range(nr_timesegments)]
        for i in range(nr_timesegments):
            row = self.parse_next_line(14)
            for j in range(7):
                try:
                    timetable[i][j] = Timeslot.from_strings(
                        row[2 * j], row[2 * j + 1], activities
                    )
                except ParseError:
                    log.error(
                        f"Could not parse timeslot in file {self.dbfile_path} line {self.line} column {j} from '{row[2 * j]}' and '{row[2 * j + 1]}'"
                    )
                    timetable[i][j] = Timeslot(None, None)
        return timetable

    def parse_next_line(self, expected_el: int = 0) -> list:
        """Parses the next line from the file, returning a list of strings split by the delimiter."""
        line = self.file.readline()
        if line == "":
            log.info(
                f"End of file reached in file {self.dbfile_path} line {self.line+1}"
            )
            return None
        self.line += 1
        elements = line.replace("\n", "").split(self.delimiter)
        if expected_el != 0 and len(elements) != expected_el:
            log.error(
                f"Expected {expected_el} elements but parsed {len(elements)} elements in file {self.dbfile_path} line {self.line}."
            )
            raise ParseError
        return elements

    def seek_for(self, *args):
        """Seeks to a set of specific elements in a file"""
        el = self.parse_next_line()
        while el != None and el != args:
            pass

    def reset_seek(self):
        """Resets file seeker to the beginning of the file"""
        self.file.seek(0, 0)
        self.line = 0


class ParseError(Exception):
    pass


class CleanExit(Exception):
    pass


def main(stdscr):
    log.info(f"Terminal has color support: {curses.has_colors()}")
    log.info(
        f"Terminal has extended color support: {curses.has_extended_color_support()}"
    )
    log.info(f"Terminal can change colors: {curses.can_change_color()}")
    log.info(f"Amount of terminal colors: {curses.COLORS}")
    log.info(f"Amount of terminal color pairs: {curses.COLOR_PAIRS}")

    TwoEight(stdscr)


if __name__ == "__main__":
    try:
        curses.wrapper(main)
    except CleanExit:
        exit()
