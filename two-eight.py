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
        self.pads = [
            WeekPad(self.screen, self.y - 2, self.x - 2, 1, 1, WeekData.dummy(48))
        ]
        self.draw_frame()
        self.screen.refresh()
        for pad in self.pads:
            pad.refresh()

    def input_loop(self):
        while True:
            c = self.screen.getch()
            if c == curses.KEY_RESIZE:
                self.resize()
            elif c == 3:  # Crtl + C
                self.exit()
            else:
                for pad in self.pads:
                    pad.input_loop(c)

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
    def __init__(
        self,
        screen,
        padheight,
        padwidth,
        clipheight,
        clipwidth,
        clipuly,
        clipulx,
        bordered=False,
    ):
        self.screen = screen
        self.pad = curses.newpad(padheight, padwidth + 1)
        self.padheight, self.padwidth = padheight, padwidth
        self.clipheight, self.clipwidth = min(padheight, clipheight), min(
            padwidth, clipwidth
        )
        self.clipuly, self.clipulx = clipuly, clipulx
        self.pad.clear()
        if bordered:
            self.draw_cornerless_frame()

    def refresh(self):
        self.pad.refresh(
            0,
            0,
            self.clipuly,
            self.clipulx,
            self.clipuly + self.clipheight - 1,
            self.clipulx + self.clipwidth - 1,
        )

    def draw_cornerless_frame(self):
        # # is a placeholder corner character
        self.screen.addch(self.clipuly - 1, self.clipulx - 1, 35)  # #
        self.screen.addch(self.clipuly - 1, self.clipulx + self.clipwidth, 35)  # #
        self.screen.addch(self.clipuly + self.clipheight, self.clipulx - 1, 35)  # #
        self.screen.addch(
            self.clipuly + self.clipheight, self.clipulx + self.clipwidth, 35
        )  # #
        # left side
        for y in range(self.clipheight):
            coords = self.clipuly + y, self.clipulx - 1
            if self.screen.inch(*coords) & 0xFF == 35:
                continue
            painted_char = "│"
            self.screen.addch(*coords, painted_char)
        # right side
        for y in range(self.clipheight):
            coords = self.clipuly + y, self.clipulx + self.clipwidth
            if self.screen.inch(*coords) & 0xFF == 35:
                continue
            painted_char = "│"
            self.screen.addch(*coords, painted_char)
        # top side
        for x in range(self.clipwidth):
            coords = self.clipuly - 1, self.clipulx + x
            if self.screen.inch(*coords) & 0xFF == 35:
                continue
            painted_char = "─"
            self.screen.addch(*coords, painted_char)
        # bottom side
        for x in range(self.clipwidth):
            coords = self.clipuly + self.clipheight, self.clipulx + x
            if self.screen.inch(*coords) & 0xFF == 35:
                continue
            painted_char = "─"
            self.screen.addch(*coords, painted_char)


class VertScrollPad(Pad):
    def __init__(
        self,
        screen,
        padheight,
        padwidth,
        clipheight,
        clipwidth,
        clipuly,
        clipulx,
        bordered=False,
    ):
        super().__init__(
            screen,
            padheight,
            padwidth,
            clipheight,
            clipwidth,
            clipuly,
            clipulx,
            bordered,
        )
        self.scroll = 0

    def refresh(self):
        self.pad.refresh(
            self.scroll,
            0,
            self.clipuly,
            self.clipulx,
            self.clipuly + self.clipheight - 1,
            self.clipulx + self.clipwidth - 1,
        )

    def scroll_down(self, scrolldelta=4):
        self.scroll = min(self.scroll + scrolldelta, self.padheight - self.clipheight)
        self.refresh()

    def scroll_up(self, scrolldelta=4):
        self.scroll = max(self.scroll - scrolldelta, 0)
        self.refresh()


class TimetablePad(VertScrollPad):
    def __init__(
        self, screen, padwidth, clipheight, clipwidth, clipuly, clipulx, weekdata
    ):
        self.weekdata = weekdata
        self.days = 7
        super().__init__(
            screen,
            self.weekdata.nr_timesegments,
            padwidth,
            clipheight,
            clipwidth,
            clipuly,
            clipulx,
        )
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
        self.scroll = 0
        self.prescroll = self.clipheight // 4
        self.selected = [0, 0]
        self.pad.addstr(self.selected[0], 5 + self.selected[1] * 6, ">     <")

    def select(self):
        self.selected[0] %= self.weekdata.nr_timesegments
        self.selected[1] %= self.days
        select_scroll_delta_lower = self.selected[0] - self.prescroll
        select_scroll_delta_upper = self.selected[0] - self.clipheight + self.prescroll
        if select_scroll_delta_upper > self.scroll:
            self.scroll = select_scroll_delta_upper
        elif select_scroll_delta_lower < self.scroll:
            self.scroll = select_scroll_delta_lower
        self.scroll = min(self.padheight - self.clipheight, max(0, self.scroll))
        self.clear_select()
        self.pad.addstr(self.selected[0], 5 + self.selected[1] * 6, ">     <")
        self.refresh()

    def clear_select(self):
        for i in range(self.days + 1):
            for j in range(self.weekdata.nr_timesegments):
                self.pad.addch(j, 5 + i * 6, " ")

    def input_loop(self, c):
        if c == ord("w"):
            self.selected[0] -= 1
        elif c == ord("s"):
            self.selected[0] += 1
        elif c == ord("a"):
            self.selected[1] -= 1
        elif c == ord("d"):
            self.selected[1] += 1
        else:
            return
        self.select()


class WeekPad(Pad):
    def __init__(self, screen, clipheight, clipwidth, clipuly, clipulx, weekdata):
        self.weekdata = weekdata
        self.header_padheight = 3
        super().__init__(
            screen,
            self.weekdata.nr_timesegments + self.header_padheight,
            49,
            clipheight,
            clipwidth,
            clipuly,
            clipulx,
            bordered=True,
        )
        self.header_pad = Pad(
            self.screen,
            self.header_padheight,
            self.padwidth,
            self.header_padheight,
            self.clipwidth,
            self.clipuly,
            self.clipulx,
        )
        self.init_headerpad()
        self.timetable_pad = TimetablePad(
            self.screen,
            self.padwidth,
            self.clipheight - self.header_padheight,
            clipwidth,
            self.clipuly + self.header_padheight,
            self.clipulx,
            self.weekdata,
        )

    def init_headerpad(self):
        weekdate = self.weekdata.date
        month = weekdate.strftime("%b")
        self.header_pad.pad.addstr(0, 5 - len(month), month)
        year = weekdate.strftime("%Y")
        self.header_pad.pad.addstr(1, 5 - len(year), year)
        for i in range(7):
            self.header_pad.pad.addstr(0, 6 + i * 6, weekdate.strftime("%d"))
            self.header_pad.pad.addstr(1, 6 + i * 6, weekdate.strftime("%a"))
            weekdate += datetime.timedelta(days=1)

    def refresh(self):
        self.header_pad.refresh()
        self.timetable_pad.refresh()

    def input_loop(self, c):
        self.timetable_pad.input_loop(c)


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
        try:
            self.file = open(self.dbfile_path, mode="r", encoding="utf-8")
        except FileNotFoundError as e:
            log.warning(
                f'Could not find file with relative filepath "{self.dbfile_path}", original error: %s',
                exc_info=e,
            )
        self.line = 0

    def __del__(self):
        self.file.close()

    def parse_week(self, week: int, year: int) -> WeekData:
        """Searches the file for a week/year entry, then parses the contents of the week, returning a WeekData object."""
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
                f"Expected {expected_el} elements but parsed {len(elements)} elements in file {self.dbfile_path} line {self.line+1}."
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
