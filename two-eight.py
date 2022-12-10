import curses
import datetime
import locale
import logging

from random import randrange, seed

seed()

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

timewidth = 5
slotwidth = 5


class Input:
    def __init__(self):
        self.controls = {}
        self.controller = None
        self.fallback = tuple()

    def on_key(self, *args):
        self.c = args
        return self

    def install(self, controller, fallback: tuple = ()):
        self.controller = controller
        self.fallback = fallback

    def process(self, c):
        if self.controller is None:
            log.warning(
                f"Could not process input '{c}' for {self} because it does not have a controller installed."
            )
            return
        try:
            self.c = c
            self.controls[c](self.controller)
        except KeyError:
            for e in self.fallback:
                try:
                    e.input.process(c)
                except AttributeError:
                    log.warning(
                        f"Could not process input '{c}' for {e.__class__.__name__} because it does not have an Input."
                    )
                    continue

    def seize(self, seized_input):
        """Temporarily sets the seized Input's fallback to this Input."""
        if not isinstance(seized_input, Input):
            log.error(
                f"Could not seize input from {seized_input} because it is not an Input."
            )
            return

        class InputSeize:
            input = self
            seized = seized_input

            def __enter__(self):
                self.fallback = self.seized.fallback
                self.seized.fallback = self

            def __exit__(self, *exc):
                self.seized.fallback = self.fallback

        return InputSeize()

    def __call__(self, func):
        for c in self.c:
            if c in self.controls.keys():
                log.warning(
                    f"Key '{c}' is already bound to function '{self.controls[c]}'. This will be overwritten with function '{func}'."
                )
            self.controls[c] = func
        return func

    def __str__(self):
        return (
            f"Input for controller '{self.controller}' and fallback '{self.fallback}'"
        )


class Pad:
    _height = 0
    _width = 0
    stretch_height = False
    stretch_width = False

    refreshable = False

    def __init__(self, uly, ulx, height=None, width=None, parent=None, init_pad=True):
        self.parent = parent
        self.uly, self.ulx = uly, ulx
        self.init_pad = init_pad
        self._height = height if height is not None else self._height
        self._width = width if width is not None else self._width
        self.pad = curses.newpad(self.height + 1, self.width) if init_pad else None
        Pad.resize(self)

    def resize(self):
        if self.parent is not None:
            if (
                self.stretch_height
            ):  # stretch the height of the pad to the parent's remaining height
                self.height = (
                    self.parent.height
                    - sum(e.height for e in self.parent.pads)
                    + (self.height if self in self.parent.pads else 0)
                    if isinstance(self.parent, VertFrame)
                    else self.parent.height
                ) - 2 * self.parent.bordered
            if (
                self.stretch_width
            ):  # stretch the width of the pad to the parent's remaining width
                self.width = (
                    (
                        self.parent.width
                        - sum(e.width for e in self.parent.pads)
                        + (self.width if self in self.parent.pads else 0)
                    )
                    if isinstance(self.parent, HorzFrame)
                    else self.parent.width
                ) - 2 * self.parent.bordered

            self.bry = min(
                self.uly + self.height - 1,
                self.parent.height - 1 - 1 * self.parent.bordered,
                *(e.uly - 1 for e in self.parent.pads if e.uly > self.uly),
            )
            self.brx = min(
                self.ulx + self.width - 1,
                self.parent.width - 1 - 1 * self.parent.bordered,
                *(e.ulx - 1 for e in self.parent.pads if e.ulx > self.ulx),
            )
            self.clipuly = self.uly + self.parent.clipuly
            self.clipulx = self.ulx + self.parent.clipulx
            self.clipbry = self.bry + self.parent.clipuly
            self.clipbrx = self.brx + self.parent.clipulx
        else:
            self.bry, self.brx = self.uly + self.height - 1, self.ulx + self.width - 1
            self.clipuly, self.clipulx = self.uly, self.ulx
            self.clipbry, self.clipbrx = self.bry, self.brx

        self.clipheight = self.clipbry - self.clipuly + 1
        self.clipwidth = self.clipbrx - self.clipulx + 1
        if self.height <= 0 or self.width <= 0:
            log.warning(
                f"{self.__class__.__name__} has no height '{self.height}' and/or width '{self.width}' set. This is most likely a mistake."
            )
        if self.clipheight <= 0 or self.clipwidth <= 0:
            log.warning(
                f"Cannot draw {self.__class__.__name__} with absolute upper left corner ({self.clipuly, self.clipulx}) and absolute bottom right corner ({self.clipbry, self.clipbrx}) because width or height is zero or negative.  "
            )
            self.refreshable = False
        else:
            self.refreshable = True

    @property
    def height(self):
        return self._height

    @height.setter
    def height(self, val):
        if self._height != val:
            self._height = val
            self.pad = (
                curses.newpad(self.height + 1, self.width) if self.init_pad else None
            )

    @property
    def width(self):
        return self._width

    @width.setter
    def width(self, val):
        if self._width != val:
            self._width = val
            self.pad = (
                curses.newpad(self.height + 1, self.width) if self.init_pad else None
            )

    def draw_static(self):
        pass

    def root(self):
        return self.parent.root() if self.parent is not None else self

    def refresh(self):
        if self.refreshable:
            self.pad.refresh(
                0,
                0,
                self.clipuly,
                self.clipulx,
                self.clipbry,
                self.clipbrx,
            )


class Frame(Pad):
    def __init__(self, uly, ulx, height=None, width=None, parent=None, bordered=False):
        # if not bordered, curses pad is not required
        self.pads = []
        self.bordered = bordered
        Pad.__init__(
            self, uly, ulx, height=height, width=width, parent=parent, init_pad=bordered
        )

    def create(
        self, cls, uly, ulx, *args, height=None, width=None, bordered=False, **kwargs
    ):
        if issubclass(cls, Frame):
            new_frame = object.__new__(cls, *args, **kwargs)
            Frame.__init__(
                new_frame,
                uly,
                ulx,
                parent=self,
                height=height,
                width=width,
                bordered=bordered,
            )
            if cls.__init__ is not Frame.__init__:
                cls.__init__(new_frame, *args, **kwargs)
            self.pads.append(new_frame)
            new_frame.draw_static()
            return new_frame
        elif issubclass(cls, Pad):
            new_pad = object.__new__(cls, *args, **kwargs)
            Pad.__init__(new_pad, uly, ulx, parent=self, height=height, width=width)
            if cls.__init__ is not Pad.__init__:
                cls.__init__(new_pad, *args, **kwargs)
            self.pads.append(new_pad)
            new_pad.draw_static()
            return new_pad
        log.error(
            f"Could not add '{cls.__name__}' to frame '{self.__class__.__name__}' because it is neither a {Frame.__name__} nor a {Pad.__name__}."
        )

    def draw_static(self):
        if self.bordered:
            self.draw_cornerless_frame()

    def refresh(self):
        if self.bordered:
            Pad.refresh(self)
        for child in self.pads:
            child.refresh()

    def resize(self):
        Pad.resize(self)
        for child in self.pads:
            child.resize()
        self.draw_static()

    def draw_cornerless_frame(self):
        if not self.bordered:
            return
        try:
            self.pad
        except AttributeError:
            log.error(
                f"Frame '{self.__class__.__name__} could not draw frame because it does not have a curses pad associated with it.'"
            )
            return
        # # is a placeholder corner character
        self.pad.addch(0, 0, 35)  # paint # in
        self.pad.addch(0, self.width - 1, 35)  # #
        self.pad.addch(self.height - 1, 0, 35)  # #
        self.pad.addch(self.height - 1, self.width - 1, 35)  # #
        # left/right side
        for y in range(1, self.height - 1):
            self.pad.addch(y, 0, "│")
            self.pad.addch(y, self.width - 1, "│")
        # top/bottom side
        for x in range(1, self.width - 1):
            self.pad.addch(0, x, "─")
            self.pad.addch(self.height - 1, x, "─")


class VertFrame(Frame):
    def create(self, cls, *args, height=None, width=None, bordered=False, **kwargs):
        return Frame.create(
            self,
            cls,
            self.pads[-1].bry + 1 if len(self.pads) > 0 else 1 * self.bordered,
            1 * self.bordered,
            *args,
            height=height,
            width=width,
            bordered=bordered,
            **kwargs,
        )


class HorzFrame(Frame):
    def create(self, cls, *args, height=None, width=None, bordered=False, **kwargs):
        return Frame.create(
            self,
            cls,
            1 * self.bordered,
            self.pads[-1].brx + 1 if len(self.pads) > 0 else 1 * self.bordered,
            *args,
            height=height,
            width=width,
            bordered=bordered,
            **kwargs,
        )


class TwoEight(VertFrame):
    input = Input()

    def __init__(self, screen):
        self.screen = screen
        first_weekdata = WeekData.dummy(48)
        self.weekdatas = {(first_weekdata.year, first_weekdata.week): first_weekdata}
        self.header = self.create(HeaderPad)
        self.tabs = [self.create(WeekTab, first_weekdata)]
        self.current_tab = self.tabs[-1]
        self.switch_tab()

    @input.on_key(ord("\t"))
    def switch_tab(self):
        self.current_tab = self.tabs[
            (self.tabs.index(self.current_tab) + 1) % len(self.tabs)
        ]
        self.header.draw_tab(self.current_tab)
        self.input.install(self, fallback=(self.current_tab,))

    @input.on_key(curses.KEY_RESIZE)
    def resize_term(self):
        resize_term(self)

    @input.on_key(3)  # Crtl + C
    def exit(self):
        log.info("Exiting two-eight. Goodnight, ladies and gentlemen.")
        raise CleanExit


class HeaderPad(Pad):
    _height = 1
    _width = 30

    def draw_static(self):
        self.pad.addstr(0, 0, "two-eight", curses.A_REVERSE)
        self.pad.addch("")

    def draw_tab(self, tab):
        if isinstance(tab, WeekTab):
            self.pad.addch(" ")
            self.pad.addstr(f"week {tab.weekdata.year}|{tab.weekdata.week}")


class WeekTab(HorzFrame):
    stretch_height = True
    stretch_width = True

    input = Input()

    def __init__(self, weekdata):
        self.weekdata = weekdata
        self.timetableframe = self.create(
            TimetableFrame, weekdata, width=50, bordered=True
        )
        self.activityframe = self.create(ActivityFrame, weekdata, bordered=True)
        self.timetable = self.timetableframe.timetable
        self.activitytable = self.activityframe.activitytable
        self.input.install(self)

    def draw_static(self):
        super().draw_static()
        self.activitytable.draw_activities_markers(*self.timetable.cursor_timeslot())

    @input.on_key(ord("w"), ord("W"))
    def timetable_up(self):
        self.timetable_select(-1, 0)

    @input.on_key(ord("s"), ord("S"))
    def timetable_down(self):
        self.timetable_select(1, 0)

    @input.on_key(ord("a"), ord("A"))
    def timetable_left(self):
        self.timetable_select(0, -1)

    @input.on_key(ord("d"), ord("D"))
    def timetable_right(self):
        self.timetable_select(0, 1)

    def timetable_select(self, d_y, d_x):
        self.activitytable.draw_activities_markers(
            *self.timetable.cursor_timeslot(), clear=True
        )
        self.timetable.cursor_y += d_y
        self.timetable.cursor_x += d_x
        self.timetable.select(shift=chr(self.input.c).isupper())
        self.activitytable.draw_activities_markers(*self.timetable.cursor_timeslot())
        self.activitytable.refresh()

    @input.on_key(ord("q"), ord("e"))
    def assign(self):
        verify = self.input.c == ord("e")
        activity = self.activitytable.cursor_activity()
        self.activitytable.draw_activities_markers(
            *self.timetable.cursor_timeslot(), clear=True
        )
        for y, x in self.timetable.selected:
            self.weekdata.assign(y, x, activity, verify=verify)
            self.timetable.draw_timeslot(y, x)
        self.timetable.refresh()
        self.activitytable.draw_activities_markers(*self.timetable.cursor_timeslot())
        self.activitytable.refresh()

    @input.on_key(ord("i"))
    def activitytable_up(self):
        self.activitytable.select(-1)

    @input.on_key(ord("k"))
    def activitytable_down(self):
        self.activitytable.select(1)

    @input.on_key(ord("u"))
    def activitytable_delete(self):
        activity = self.activitytable.cursor_activity()
        self.activitytable.draw_activities_markers(
            *self.timetable.cursor_timeslot(), clear=True
        )
        for i, y in enumerate(self.weekdata.timetable):
            for j, x in enumerate(y):
                if x.plan == activity:
                    x.plan = None
                    self.timetable.draw_timeslot(i, j)
                if x.verify == activity:
                    x.verify = None
                    self.timetable.draw_timeslot(i, j)
        self.timetable.refresh()
        self.activitytable.delete()
        self.activitytable.draw_activities_markers(*self.timetable.cursor_timeslot())
        self.activitytable.refresh()

    @input.on_key(ord("o"))
    def activitytable_edit(self):
        self.activitytable.edit()


class VertScrollPad(Pad):
    scroll_variable = 0
    scrollpos = 0

    def refresh(self):
        self.pad.refresh(
            self.scrollpos,
            0,
            self.clipuly,
            self.clipulx,
            min(self.clipbry, self.clipuly + self.height - 1),
            self.clipbrx,
        )

    def resize(self):
        Pad.resize(self)
        self.scroll(self.scroll_variable)

    def scroll(self, select):
        self.scroll_variable = select
        prescroll = self.clipheight // 4
        select_scroll_delta_lower = select - prescroll
        select_scroll_delta_upper = select - self.clipheight + prescroll + 1
        if select_scroll_delta_upper > self.scrollpos:
            self.scrollpos = select_scroll_delta_upper
        elif select_scroll_delta_lower < self.scrollpos:
            self.scrollpos = select_scroll_delta_lower
        self.scrollpos = max(0, min(self.height - self.clipheight, self.scrollpos))


class TimetablePad(VertScrollPad):
    stretch_width = True

    def __init__(self, weekdata):
        self.weekdata = weekdata
        self.cursor_y, self.cursor_x = 0, 0
        self.hold_cursor_y, self.hold_cursor_x = self.cursor_y, self.cursor_x
        self.selected = ((self.cursor_y, self.cursor_x),)

    def draw_static(self):
        for i in range(0, self.weekdata.nr_timesegments):
            minutes = int(i * (24 / self.weekdata.nr_timesegments) * 60)
            self.pad.addstr(
                i, 0, f"{minutes // 60:02d}:{minutes % 60:02d}", curses.A_DIM
            )
        self.draw_selected()
        for y in range(len(self.weekdata.timetable)):
            for x in range(len(self.weekdata.timetable[0])):
                self.draw_timeslot(y, x)

    def draw_timeslot(self, y, x):
        """Draw a timeslot by its y/x index"""
        timeslot = self.weekdata.timetable[y][x]
        begin_x = timewidth + (slotwidth + 1) * x + 1
        for x_paint in range(begin_x, begin_x + slotwidth):
            self.pad.addch(y, x_paint, " ")
        if timeslot.plan == timeslot.verify:
            char = "█"
        else:
            char = "░"
        if timeslot.verify is not None:
            for x_paint in range(begin_x, begin_x + slotwidth):
                self.pad.addch(y, x_paint, char, timeslot.verify.color())
        if timeslot.plan is not None:
            self.pad.addch(y, begin_x + slotwidth // 2, char, timeslot.plan.color())

    def draw_selected(self, clear=False):
        select_char = "+" if not clear else " "
        for y, x in self.selected:
            self.pad.addch(y, timewidth + x * 6, select_char)
            self.pad.addch(y, timewidth + x * 6 + slotwidth + 1, select_char)
        self.pad.addch(self.cursor_y, timewidth + self.cursor_x * 6, ">")
        self.pad.addch(
            self.cursor_y, timewidth + self.cursor_x * 6 + slotwidth + 1, "<"
        )

    def select(self, shift=False):
        self.cursor_y %= self.height
        self.cursor_x %= 7
        self.scroll(self.cursor_y)
        self.draw_selected(clear=True)
        if not shift:
            self.hold_cursor_y, self.hold_cursor_x = self.cursor_y, self.cursor_x
            self.selected = ((self.cursor_y, self.cursor_x),)
        else:
            self.selected = tuple(
                (y, x)
                for y in range(
                    min(self.cursor_y, self.hold_cursor_y),
                    max(self.cursor_y, self.hold_cursor_y) + 1,
                )
                for x in range(
                    min(self.cursor_x, self.hold_cursor_x),
                    max(self.cursor_x, self.hold_cursor_x) + 1,
                )
            )

        self.draw_selected()
        self.refresh()

    def cursor_timeslot(self):
        return self.cursor_y, self.cursor_x


class TimetableHeaderPad(Pad):
    _height = 3
    stretch_width = True

    def __init__(self, weekdata):
        self.weekdata = weekdata

    def draw_static(self):
        weekdate = self.weekdata.date - datetime.timedelta(
            days=self.weekdata.date.weekday()
        )
        month = weekdate.strftime("%b")
        self.pad.addstr(0, 5 - len(month), month)
        year = weekdate.strftime("%Y")
        self.pad.addstr(1, 5 - len(year), year)
        for i in range(7, self.width, 6):
            self.pad.addstr(0, i, weekdate.strftime("%d"))
            self.pad.addstr(1, i, weekdate.strftime("%a"))
            weekdate += datetime.timedelta(days=1)


class TimetableFrame(VertFrame):
    stretch_height = True

    def __init__(self, weekdata):
        self.weekdata = weekdata
        weekdata.timetableframe = self
        self.header = self.create(
            TimetableHeaderPad,
            self.weekdata,
        )
        self.timetable = self.create(
            TimetablePad,
            self.weekdata,
            height=self.weekdata.nr_timesegments,
        )


class ActivityTablePad(VertScrollPad):
    new_str = " + new"
    stretch_width = True

    def __init__(self, weekdata):
        self.weekdata = weekdata
        self.namewidth = self.width - 12
        self.cursor = 0

    def draw_static(self):
        self.draw_activities()
        self.draw_cursor()

    def draw_activities(self):
        self.height = len(self.weekdata.activities) + 1
        for i, activity in enumerate(self.weekdata.activities):
            self.pad.addstr(i, 11, activity.name[-self.namewidth :])
            self.pad.chgat(i, 0, activity.color() + curses.A_REVERSE)
        self.pad.addstr(len(self.weekdata.activities), 11, self.new_str)

    def draw_activities_markers(self, y, x, clear=False):
        cursor_timeslot = self.weekdata.timetable[y][x]
        char = "x" if not clear else " "
        for i, activity in enumerate(self.weekdata.activities):
            if activity == cursor_timeslot.plan:
                self.pad.addch(i, 2, char, activity.color() + curses.A_REVERSE)
            if activity == cursor_timeslot.verify:
                self.pad.addch(i, 5, char, activity.color() + curses.A_REVERSE)

    def draw_cursor(self, clear=False):
        char = ">" if not clear else " "
        if self.cursor < len(self.weekdata.activities):
            self.pad.addch(
                self.cursor,
                8,
                char,
                self.cursor_activity().color() + curses.A_REVERSE,
            )
        elif self.cursor == len(self.weekdata.activities):
            self.pad.addch(self.cursor, 8, char)

    def select(self, d):
        self.draw_cursor(clear=True)
        self.cursor += d
        self.cursor %= self.height
        self.scroll(self.cursor)
        self.draw_cursor()
        self.refresh()

    def delete(self):
        if self.cursor == len(self.weekdata.activities):
            return
        self.weekdata.delete_activity(self.cursor_activity())
        self.draw_activities()
        self.select(0)

    def edit(self):
        is_new = self.cursor_activity() is None
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
        self.select(0)

    def prompt_name(self, activity):
        activity_name = activity.name
        attr = activity.color() + curses.A_REVERSE
        self.pad.move(self.cursor, 11)
        self.pad.clrtoeol()
        self.pad.chgat(self.cursor, 0, attr)
        self.pad.addstr(self.cursor, 11, activity_name[-self.namewidth :], attr)
        self.refresh()

        c = self.root().screen.getch()
        while (
            c != curses.KEY_ENTER
            and c != 10  # also check for new line
            and c != 13  # and carriage return
        ):
            if c == curses.KEY_RESIZE:
                resize_term(self.root())
            else:
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
            c = self.root().screen.getch()
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
        c = self.root().screen.getch()
        while True:
            if c == curses.KEY_RESIZE:
                resize_term(self.root())
            else:
                if (
                    c == curses.KEY_ENTER or c == 10 or c == 13
                ):  # new line, carriage return
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
                    digit_index += 1
                    digit_index %= 3
            self.pad.addstr(
                self.cursor,
                11,
                f"R {colors_str[0]} | G {colors_str[1]} | B {colors_str[2]}",
                attr,
            )
            self.refresh()
            c = self.root().screen.getch()
        self.pad.move(self.cursor, 11)
        self.pad.clrtoeol()
        return r, g, b

    def cursor_activity(self):
        if self.cursor < len(self.weekdata.activities):
            return self.weekdata.activities[self.cursor]
        return None


class ActivityHeaderPad(Pad):
    _height = 2
    _width = 20

    def draw_static(self):
        self.pad.addch(0, 2, "p")
        self.pad.addch(0, 5, "v")
        self.pad.addstr(0, 11, "name")


class ActivityFrame(VertFrame):
    stretch_width = True
    stretch_height = True

    def __init__(self, weekdata):
        self.weekdata = weekdata
        weekdata.activityframe = self
        self.header = self.create(ActivityHeaderPad)
        self.activitytable = self.create(
            ActivityTablePad,
            self.weekdata,
            height=len(self.weekdata.activities) + 1,
        )


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
            randrange(0, 1000),
            randrange(0, 1000),
            randrange(0, 1000),
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

        self.date = date
        if date is None:
            self.date = datetime.date.fromisocalendar(year, week, 1)
            self.year, self.week = year, week
        else:
            self.date = date
            self.year, self.week, _ = date.isocalendar()

    def add_activity(self, activity: Activity):
        self.activities.append(activity)
        self.activities = sorted(self.activities, key=lambda x: x.name)

    def delete_activity(self, activity: Activity):
        self.activities.remove(activity)

    def edit_activity(self, activity, name, r, g, b):
        activity.name = name
        activity.r, activity.g, activity.b = r, g, b
        self.activities = sorted(self.activities, key=lambda x: x.name)

    def assign(self, y, x, activity, verify=False):
        "Assigns an activity to the timeslot with coordinates y, x."
        if not verify:
            self.timetable[y][x].plan = activity
        else:
            self.timetable[y][x].verify = activity

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
                        activities[randrange(0, nr_activities)],
                        activities[randrange(0, nr_activities)],
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
        if self.file is not None:
            self.file.close()

    @staticmethod
    def ensure_open(func):
        """Ensures the database file is loaded into the parser"""

        def decorated(self, *args, **kwargs):
            if self.file is None:
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
        while el is not None and el != args:
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
    curses.use_default_colors()
    curses.curs_set(0)
    stdscr.leaveok(False)

    term_height, term_width = stdscr.getmaxyx()
    curses.resize_term(term_height, term_width)
    twoeight = object.__new__(TwoEight)
    Frame.__init__(twoeight, 0, 0, height=term_height - 1, width=term_width)
    TwoEight.__init__(twoeight, stdscr)
    twoeight.refresh()
    while True:
        try:
            twoeight.input.process(stdscr.getch())
        except CleanExit:
            stdscr.clear()
            stdscr.refresh()
            exit()


def resize_term(root_frame):
    try:
        term_height, term_width = root_frame.screen.getmaxyx()
    except AttributeError:
        log.error(
            f"Root frame '{root_frame}' does not have a 'screen' attribute to be able to resize the terminal."
        )
        return
    curses.resize_term(term_height, term_width)
    root_frame.height = term_height - 1
    root_frame.width = term_width
    root_frame.resize()
    root_frame.refresh()


if __name__ == "__main__":
    curses.wrapper(main)
