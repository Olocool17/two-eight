import curses
import datetime
import locale
import logging

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
        self.resize()
        self.input_loop()

    def resize(self):
        self.y, self.x = self.screen.getmaxyx()
        self.screen.clear()
        curses.resize_term(self.y, self.x)
        self.frames = [
            WeekFrame(
                self.screen, 0, 0, self.y - 1, min(self.x - 1, 50), WeekData.dummy(48)
            )
        ]
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
        pad.clipulx += self.uly + 1
        pad.clipbrx += self.uly + 1
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
        self.scroll = 0

    def refresh(self):
        self.pad.refresh(
            self.scroll,
            0,
            self.clipuly,
            self.clipulx,
            min(self.clipbry, self.clipuly + self.padheight - 1),
            self.clipbrx,
        )


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
        self.scroll = 0
        self.prescroll = self.clipheight // 4
        self.selected = [0, 0]

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
            if i > self.clipheight + self.scroll:
                self.scroll += self.clipheight
                self.refresh()
        self.select()

    def select(self):
        self.selected[0] %= self.weekdata.nr_timesegments
        self.selected[1] %= self.days
        select_scroll_delta_lower = self.selected[0] - self.prescroll
        select_scroll_delta_upper = self.selected[0] - self.clipheight + self.prescroll
        if select_scroll_delta_upper > self.scroll:
            self.scroll = select_scroll_delta_upper
        elif select_scroll_delta_lower < self.scroll:
            self.scroll = select_scroll_delta_lower
        self.scroll = max(0, min(self.padheight - self.clipheight, self.scroll))
        self.clear_select()
        self.pad.addstr(self.selected[0], 5 + self.selected[1] * 6, ">     <")
        self.refresh()

    def clear_select(self):
        self.pad.addch(self.selected[0], 5 + self.selected[1] * 6, " ")
        self.pad.addch(self.selected[0], 11 + self.selected[1] * 6, " ")

    def input_loop(self, c):
        if c == ord("w"):
            self.clear_select()
            self.selected[0] -= 1
            self.select()
        elif c == ord("s"):
            self.clear_select()
            self.selected[0] += 1
            self.select()
        elif c == ord("a"):
            self.clear_select()
            self.selected[1] -= 1
            self.select()
        elif c == ord("d"):
            self.clear_select()
            self.selected[1] += 1
            self.select()


class WeekHeaderPad(Pad):
    def __init__(self, screen, padwidth, clipuly, clipulx, clipbrx, weekdata):
        super().__init__(screen, 3, padwidth, clipuly, clipulx, clipuly + 2, clipbrx)
        self.weekdata = weekdata

    def draw_static(self):
        weekdate = self.weekdata.date
        month = weekdate.strftime("%b")
        self.pad.addstr(0, 5 - len(month), month)
        year = weekdate.strftime("%Y")
        self.pad.addstr(1, 5 - len(year), year)
        for i in range(7):
            self.pad.addstr(0, 6 + i * 6, weekdate.strftime("%d"))
            self.pad.addstr(1, 6 + i * 6, weekdate.strftime("%a"))
            weekdate += datetime.timedelta(days=1)


class WeekFrame(Frame):
    def __init__(self, screen, uly, ulx, bry, brx, weekdata):
        self.weekdata = weekdata
        super().__init__(
            screen,
            uly,
            ulx,
            bry,
            brx,
        )
        self.header = WeekHeaderPad(
            self.screen,
            self.width,
            0,
            0,
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


class ActivityPad(VertScrollPad):
    def __init__(
        self, screen, clipheight, clipwidth, clipuly, clipulx, activities: dict
    ):
        self.activities = activities
        super().__init__(
            screen,
            len(self.activities),
            clipwidth,
            clipheight,
            clipwidth,
            clipuly,
            clipulx,
        )


class Activity:
    def __init__(self, name: str, color, desc=""):
        self.name = name
        self.color = color
        self.desc = desc


class Timeslot:
    def __init__(self, plan: Activity, verify: Activity):
        self.plan = plan
        self.verify = verify

    @classmethod
    def from_strings(cls, plan: str, verify: str, activities: dict):
        try:
            plan = activities[plan]
        except KeyError:
            return
            # PH : Log warning here
        if verify == " ":
            return cls(plan, None)
        try:
            verify = activities[verify]
        except KeyError:
            return
            # PH : Log warning here
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
        self.activities = activities
        self.timetable = timetable
        if datetime.date != None:
            self.date = datetime.date.fromisocalendar(year, week, 1)
        self.date = date - datetime.timedelta(days=date.weekday())

    @staticmethod
    def from_file(parser, week: int, year: int):
        return parser.parse_week(week, year)

    @classmethod
    def dummy(cls, nr_timesegments):
        """Returns a week_data object with placeholder dummy data"""
        activities = {
            "dummy": Activity("dummy", 0),
            "dummy_verify": Activity("dummy_verify", 1),
        }
        return cls(
            nr_timesegments,
            activities,
            [
                [
                    Timeslot.from_strings("dummy", "dummy_verify", activities)
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
            name, color = self.parse_next_line(2)
            activities.update({name: Activity(name, color)})
        self.parse_next_line()
        return activities

    def parse_timetable(self, nr_timesegments: int, activities: dict) -> list:
        """Helper function for parse_week : parses the timetable of a week"""
        timetable = [[0] * 7 for _ in range(nr_timesegments)]
        for i in range(nr_timesegments):
            row = self.parse_next_line(14)
            for j in range(7):
                timetable[i][j] = Timeslot.from_strings(
                    *row[2 * j : 2 * j + 2], activities
                )
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
            log.warning(
                f"Expected {expected_el} elements but parsed {len(elements)} elements in file {self.dbfile_path} line {self.line}."
            )
            return None
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


class CleanExit(Exception):
    pass


def main(stdscr):
    TwoEight(stdscr)


if __name__ == "__main__":
    try:
        curses.wrapper(main)
    except CleanExit:
        exit()
