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

    def resize(self):
        self.y, self.x = self.screen.getmaxyx()
        self.screen.clear()
        curses.resize_term(self.y, self.x)
        self.refresh()

    def refresh(self):
        self.frames = [
            TimetableFrame(self.screen, 1, 0, self.y - 2, 50, self.weekdata),
            ActivityFrame(self.screen, 1, 50, self.y - 2, self.x - 2, self.weekdata),
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
        self.screen.addstr(0, 0, "two-eight", curses.A_REVERSE)
        self.screen.addch("")

    def exit(self):
        self.screen.clear()
        self.screen.refresh()
        raise CleanExit


class Pad:
    def __init__(self, padheight, padwidth, clipuly, clipulx, clipbry, clipbrx):
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
        if pad.clipbry < pad.clipuly or pad.clipbrx < pad.clipbry:
            log.warning(
                f"Could not add pad {pad.__class__.__name__} with relative upper left corner ({pad.clipuly, pad.clipulx}) and relative bottom right corner ({pad.clipbry, pad.clipbrx}) because width or height is zero or negative.  "
            )
            return

        if pad.clipbry >= self.height or pad.clipbrx >= self.width:
            log.warning(
                f"Could not add pad {pad.__class__.__name__} with relative bottom right corner ({pad.clipbry, pad.clipbrx}) to frame with height {self.height} and width {self.width}"
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
    def __init__(self, padheight, padwidth, clipuly, clipulx, clipbry):
        super().__init__(padheight, padwidth, clipuly, clipulx, clipbry, padwidth - 1)

        self.scrollpos = 0
        self.prescroll = self.clipheight // 4

    def change_height(self, padheight):
        super().__init__(
            padheight,
            self.padwidth,
            self.clipuly,
            self.clipulx,
            self.clipbry,
            self.clipbrx,
        )

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
    def __init__(self, padwidth, clipuly, clipulx, clipbry, weekdata):
        self.weekdata = weekdata
        self.days = 7
        super().__init__(
            self.weekdata.nr_timesegments,
            padwidth,
            clipuly,
            clipulx,
            clipbry,
        )
        self.timewidth = 5
        self.slotwidth = 5
        self.cursor_y, self.cursor_x = 0, 0
        self.hold_cursor_y, self.hold_cursor_x = self.cursor_y, self.cursor_x
        self.selected = [(self.cursor_y, self.cursor_x)]

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
        begin_x = self.timewidth + (self.slotwidth + 1) * x + 1
        for x_paint in range(begin_x, begin_x + self.slotwidth):
            self.pad.addch(y, x_paint, " ")
        if timeslot.plan == timeslot.verify:
            char = "█"
        else:
            char = "░"
        if timeslot.verify != None:
            for x_paint in range(begin_x, begin_x + self.slotwidth):
                self.pad.addch(y, x_paint, char, timeslot.verify.color())
        if timeslot.plan != None:
            self.pad.addch(
                y, begin_x + self.slotwidth // 2, char, timeslot.plan.color()
            )

    def draw_cursor(self):
        self.pad.addch(self.cursor_y, self.timewidth + self.cursor_x * 6, ">")
        self.pad.addch(
            self.cursor_y, self.timewidth + self.cursor_x * 6 + self.slotwidth + 1, "<"
        )

    def select(self, shift=False):
        self.cursor_y %= self.padheight
        self.cursor_x %= self.days
        self.scroll(self.cursor_y)
        self.clear_select()
        if not shift:
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
        self.weekdata.change_cursor_timeslot(self.cursor_y, self.cursor_x)

    def clear_select(self):
        for y, x in self.selected:
            self.pad.addch(y, self.timewidth + x * 6, " ")
            self.pad.addch(y, 2 * self.timewidth + 1 + x * 6, " ")

    def assign(self, verify=False):
        for y, x in self.selected:
            self.weekdata.assign(y, x, verify=verify)
            self.draw_timeslot(y, x)
        self.refresh()
        self.weekdata.change_cursor_timeslot(self.cursor_y, self.cursor_x)

    def input_loop(self, c):
        if c == ord("w") or c == ord("W"):
            self.cursor_y -= 1
            self.select(shift=c == ord("W"))
        elif c == ord("s") or c == ord("S"):
            self.cursor_y += 1
            self.select(shift=c == ord("S"))
        elif c == ord("a") or c == ord("A"):
            self.cursor_x -= 1
            self.select(shift=c == ord("A"))
        elif c == ord("d") or c == ord("D"):
            self.cursor_x += 1
            self.select(shift=c == ord("D"))
        elif c == ord("q"):
            self.assign(verify=False)
        elif c == ord("e"):
            self.assign(verify=True)


class TimetableHeaderPad(Pad):
    def __init__(
        self, padheight, padwidth, clipuly, clipulx, clipbry, clipbrx, weekdata
    ):
        super().__init__(padheight, padwidth, clipuly, clipulx, clipbry, clipbrx)
        self.weekdata = weekdata

    def draw_static(self):
        weekdate = self.weekdata.date - datetime.timedelta(
            days=self.weekdata.date.weekday()
        )
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
            self.width,
            self.header.clipheight,
            0,
            self.height - 1,
            self.weekdata,
        )
        self.add_pad(self.timetable)

    def input_loop(self, c):
        self.timetable.input_loop(c)


class ActivityTablePad(VertScrollPad):
    new_str = " + new"

    def __init__(self, screen, padwidth, clipuly, clipulx, clipbry, weekdata):
        self.weekdata = weekdata
        self.screen = screen
        super().__init__(
            len(self.weekdata.activities) + 1,
            padwidth,
            clipuly,
            clipulx,
            clipbry,
        )
        self.namewidth = self.padwidth - 12
        self.cursor = 0

    def draw_static(self):
        self.draw_activities()
        self.draw_cursor()

    def draw_activities(self):
        if self.padheight != len(self.weekdata.activities) + 1:
            self.change_height(len(self.weekdata.activities) + 1)
        for i, activity in enumerate(self.weekdata.activities):
            self.pad.addstr(i, 11, activity.name[-self.namewidth :])
            self.pad.chgat(i, 0, activity.color() + curses.A_REVERSE)
        self.pad.addstr(len(self.weekdata.activities), 11, self.new_str)
        self.draw_activities_markers()

    def draw_activities_markers(self, clear=True):
        cursor_timeslot = self.weekdata.cursor_timeslot()
        if cursor_timeslot == None:
            return
        for i, activity in enumerate(self.weekdata.activities):
            if clear:
                self.pad.addch(i, 2, " ", activity.color() + curses.A_REVERSE)
                self.pad.addch(i, 5, " ", activity.color() + curses.A_REVERSE)
            if activity == cursor_timeslot.plan:
                self.pad.addch(i, 2, "x", activity.color() + curses.A_REVERSE)
            if activity == cursor_timeslot.verify:
                self.pad.addch(i, 5, "x", activity.color() + curses.A_REVERSE)
        self.refresh()

    def draw_cursor(self, clear=False):
        char = ">" if not clear else " "
        if self.cursor < self.padheight - 1:
            self.pad.addch(
                self.cursor,
                8,
                char,
                self.cursor_activity().color() + curses.A_REVERSE,
            )
        else:
            self.pad.addch(self.cursor, 8, char)

    def select(self):
        self.cursor %= self.padheight
        self.scroll(self.cursor)
        self.draw_cursor()
        self.refresh()

    def delete(self):
        if len(self.weekdata.activities) <= 0 or self.cursor == self.padheight - 1:
            return
        self.pad.move(self.cursor, 0)
        self.pad.clrtoeol()
        self.pad.move(self.padheight - 2, 0)
        self.pad.clrtoeol()
        self.pad.move(self.padheight - 1, 0)
        self.pad.clrtoeol()
        self.refresh()
        self.weekdata.delete_activity(self.cursor_activity())
        self.draw_activities()
        self.select()

    def edit(self):
        is_new = self.cursor_activity() == None
        activity = Activity("", 0, 0, 0) if is_new else self.cursor_activity()
        activity_name = self.prompt_name(activity)
        if activity_name != "":
            r, g, b = self.prompt_colors(activity)
            self.draw_cursor(clear=True)
            if is_new:
                self.weekdata.add_activity(activity)
            self.weekdata.edit_activity(activity, activity_name, r, g, b)
            self.cursor = self.weekdata.activities.index(activity)
        self.draw_activities()
        self.select()

    def prompt_name(self, activity):
        activity_name = activity.name
        attr = activity.color() + curses.A_REVERSE
        self.pad.move(self.cursor, 11)
        self.pad.clrtoeol()
        self.pad.chgat(self.cursor, 0, attr)
        self.pad.addstr(self.cursor, 11, activity_name[-self.namewidth :], attr)
        self.refresh()

        c = self.screen.getch()
        while (
            c != curses.KEY_ENTER
            and c != 10  # also check for new line
            and c != 13  # and carriage return
        ):
            if c == curses.KEY_RESIZE:
                twoeight.resize()
                c = self.screen.getch()
                continue
            activity_name += chr(c)
            if c == curses.KEY_BACKSPACE or c == ord("\b"):
                activity_name = activity_name[:-2]
                if len(activity_name) + 1 <= self.namewidth:
                    self.pad.addch(
                        self.cursor,
                        11 + len(activity_name),
                        " ",
                        attr,
                    )
            self.pad.addstr(
                self.cursor,
                11,
                activity_name[-self.namewidth :],
                attr,
            )
            self.refresh()
            c = self.screen.getch()
        self.pad.move(self.cursor, 11)
        self.pad.clrtoeol()
        return activity_name

    def prompt_colors(self, activity):
        (
            r,
            g,
            b,
        ) = (activity.r, activity.g, activity.b)
        colors_str = [f"{r:03d}", f"{g:03d}", f"{b:03d}"]
        attr = activity.color() + curses.A_REVERSE
        color_index = 0
        digit_index = 0
        self.pad.chgat(self.cursor, 0, attr)
        self.pad.addstr(
            self.cursor,
            11,
            f"R {colors_str[0]} | G {colors_str[1]} | B {colors_str[2]}",
            attr,
        )
        self.refresh()
        c = self.screen.getch()
        while True:
            if c == curses.KEY_RESIZE:
                twoeight.resize()
                c = self.screen.getch()
                continue
            if c == curses.KEY_ENTER or c == 10 or c == 13:  # new line, carriage return
                if color_index == 2:
                    break
                color_index += 1
                digit_index = 0
            if chr(c) in "0123456789":
                colors_str[color_index] = (
                    colors_str[color_index][:digit_index]
                    + chr(c)
                    + colors_str[color_index][digit_index + 1 :]
                )
                r, g, b = map(int, colors_str)
                activity.change_color(r, g, b)
                self.pad.addstr(
                    self.cursor,
                    11,
                    f"R {colors_str[0]} | G {colors_str[1]} | B {colors_str[2]}",
                    attr,
                )
                digit_index += 1
                digit_index %= 3
                self.refresh()
            c = self.screen.getch()
        self.pad.move(self.cursor, 11)
        self.pad.clrtoeol()
        return r, g, b

    def cursor_activity(self):
        if self.cursor < len(self.weekdata.activities):
            return self.weekdata.activities[self.cursor]
        return None

    def input_loop(self, c):
        if c == ord("i"):
            self.draw_cursor(clear=True)
            self.cursor -= 1
            self.select()
        elif c == ord("k"):
            self.draw_cursor(clear=True)
            self.cursor += 1
            self.select()
        elif c == ord("o"):
            self.edit()
        elif c == ord("u"):
            self.delete()


class ActivityHeaderPad(Pad):
    def __init__(self, padwidth, clipuly, clipulx, clipbry, clipbrx):
        super().__init__(2, padwidth, clipuly, clipulx, clipbry, clipbrx)

    def draw_static(self):
        self.pad.addch(0, 2, "p")
        self.pad.addch(0, 5, "v")
        self.pad.addstr(0, 11, "name")


class ActivityFrame(Frame):
    def __init__(self, screen, uly, ulx, bry, brx, weekdata):
        self.weekdata = weekdata
        super().__init__(screen, uly, ulx, bry, brx)
        self.header = ActivityHeaderPad(self.width, 0, 0, 1, self.width - 1)
        self.add_pad(self.header)
        self.activitytable = ActivityTablePad(
            self.screen,
            self.width,
            self.header.clipheight,
            0,
            self.height - 1,
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
        self.primary_color = Activity.color_counter
        curses.init_pair(Activity.color_counter, self.primary_color, 0)
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

    def change_color(self, r, g, b):
        curses.init_color(self.primary_color, r, g, b)

    def color(self):
        return curses.color_pair(self.color_pair)

    @classmethod
    def dummy(cls, name):
        return cls(
            name,
            random.randrange(0, 1000),
            random.randrange(0, 1000),
            random.randrange(0, 1000),
        )


class Timeslot:
    def __init__(self, plan: Activity, verify: Activity):
        self.plan = plan
        self.verify = verify

    @classmethod
    def from_strings(cls, plan: str, verify: str, activities: dict):
        """Given an activity dictionary, creates a Timeslot object from strings. Used by the parser."""
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
        activities: list,
        timetable: list,
        week: int = 1,
        year: int = 1,
        date: datetime.date = None,
    ):
        self.nr_timesegments = nr_timesegments
        self.activities = sorted(activities, key=lambda x: x.name)
        self.timetable = timetable

        self.activityframe = None
        self.timetableframe = None
        self.date = date
        if date == None:
            self.date = datetime.date.fromisocalendar(year, week, 1)

    def add_activity(self, activity: Activity):
        self.activities.append(activity)
        self.activities = sorted(self.activities, key=lambda x: x.name)

    def delete_activity(self, activity: Activity):
        for i, y in enumerate(self.timetable):
            for j, x in enumerate(y):
                if x.plan == activity:
                    x.plan = None
                    if self.timetableframe.timetable != None:
                        self.timetableframe.timetable.draw_timeslot(i, j)
                if x.verify == activity:
                    x.verify = None
                    if self.timetableframe.timetable != None:
                        self.timetableframe.timetable.draw_timeslot(i, j)
        if self.timetableframe.timetable != None:
            self.timetableframe.timetable.refresh()
        self.activities.remove(activity)

    def edit_activity(self, activity, name, r, g, b):
        activity.name = name
        activity.r, activity.g, activity.b = r, g, b
        self.activities = sorted(self.activities, key=lambda x: x.name)

    def add_frames(self, timetableframe: TimetableFrame, activityframe: ActivityFrame):
        self.timetableframe = timetableframe
        self.activityframe = activityframe

    def assign(self, y, x, verify=False):
        if self.activityframe == None:
            return
        activity = self.activityframe.activitytable.cursor_activity()
        if not verify:
            self.timetable[y][x].plan = activity
        else:
            self.timetable[y][x].verify = activity

    def cursor_timeslot(self):
        if self.timetableframe == None:
            return None
        return self.timetable[self.timetableframe.timetable.cursor_y][
            self.timetableframe.timetable.cursor_x
        ]

    def change_cursor_timeslot(self, y, x):
        self.activityframe.activitytable.draw_activities_markers()

    @classmethod
    def dummy(cls, nr_timesegments, nr_activities=10):
        """Returns a week_data object with placeholder dummy data"""
        activities = [Activity.dummy("dummy" + str(i)) for i in range(nr_activities)]
        return cls(
            nr_timesegments,
            activities,
            [
                [
                    Timeslot(
                        activities[random.randrange(0, nr_activities)],
                        activities[random.randrange(0, nr_activities)],
                    )
                    for j in range(7)
                ]
                for i in range(nr_timesegments)
            ],
            date=datetime.date.today(),
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
            self.file = open(self.dbfile_path, mode="r+", encoding="utf-8")
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
        return WeekData(
            nr_timesegments, list(activities.values()), timetable, week, year
        )

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
            el = self.parse_next_line()
        log.error(
            f"Could not find seeking elements '{args}' in file {self.dbfile_path}"
        )

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
    global twoeight
    twoeight = TwoEight(stdscr)
    twoeight.input_loop()


if __name__ == "__main__":
    try:
        curses.wrapper(main)
    except CleanExit:
        exit()
