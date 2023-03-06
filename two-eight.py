import curses
import datetime
import locale
import logging

from random import randrange, seed
from enum import Enum

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

    def on_any(self):
        return self.on_key(self, "*")

    def install(self, controller, fallback: tuple = (), screen=None):
        self.controller = controller
        self.fallback = fallback
        self.screen = screen

    def process(self, c):
        if self.controller is None:
            log.warning(f"Could not process input '{c}' for {self} because it does not have a controller installed.")
            return
        self.c = c
        if c not in self.controls:
            if "*" in self.controls:
                self.controls["*"](self.controller)
                return
            for e in self.fallback:
                try:
                    e.input
                except AttributeError:
                    log.warning(f"Could not process input '{c}' for {e.__class__.__name__} because it does not have an Input.")
                    continue
                e.input.process(c)

            return
        self.controls[c](self.controller)

    class InputBreak(Exception):
        pass

    def start_loop(self):
        if self.screen is None:
            log.warning(f"Could not start input loop for {self} because it does not have a screen installed.")
            return
        try:
            while True:
                self.process(self.screen.getch())
        except self.InputBreak:
            return

    def __enter__(self):
        self.fallback_store = self.fallback
        self.controls_store = self.controls.copy()
        self.fallback = ()
        return self

    def __exit__(self, *exc):
        self.fallback = self.fallback_store
        self.controls = self.controls_store
        self.fallback_store = None
        self.controls_store = None

    def __call__(self, func):
        for c in self.c:
            if c in self.controls.keys():
                log.warning(
                    f"Key '{c}' in '{self}' is already bound to function '{self.controls[c]}'. This will be overwritten with function '{func}'."
                )
            self.controls[c] = func
        return func

    def __str__(self):
        return f"Input for controller '{self.controller}' and fallback '{self.fallback}'"


class Pad:
    JUSTIFY = Enum("JUSTIFY", ["LEFT", "CENTER", "RIGHT"])

    height = 0
    width = 0
    # Dimensions of curses pad object

    uly = 0
    ulx = 0
    bry = 0
    brx = 0
    # Coordinates relative to frame origin

    justify_x = JUSTIFY.LEFT
    justify_y = JUSTIFY.LEFT
    # How does the pad justify itself within the space given by the parent?

    stretch_clipheight = False
    stretch_clipwidth = False
    # Determines if curses pad object should stretch to fit the clip and just dimensions provided by the parent frame

    min_height = 0
    min_width = 0
    # Minimum dimensions of curses pad object if stretch is enabled

    max_height = 0
    max_width = 0
    # Maximum dimensions of curses pad object if stretch is enabled

    floating = False
    # Determines if pad should be aligned with other pads by the parent frame or positioned absolutely (TODO)

    refreshable = False

    input = None

    def __init__(self, parent=None, init_pad=True):
        self.parent = parent
        self.init_pad = init_pad
        self.pad = None

    def resize(self):
        self.clipheight = self.bry - self.uly + 1
        self.clipwidth = self.brx - self.ulx + 1
        if self.clipheight <= 0 or self.clipwidth <= 0:
            log.warning(
                f"Cannot draw {self.__class__.__name__} with frame-relative upper left corner ({self.uly, self.ulx}) and frame-relative bottom right corner ({self.bry, self.brx}) because clip width or height is zero or negative.  "
            )
            self.refreshable = False
            return
        else:
            self.refreshable = True if self.parent is None else self.parent.refreshable

        # Perform pad stretching to clip dimensions
        if self.parent is not None:
            if self.stretch_clipheight:
                self.height = max(self.clipheight, self.min_height)
                if self.max_height > 0:
                    self.height = min(self.height, self.max_height)
            if self.stretch_clipwidth:
                self.width = max(self.clipwidth, self.min_width)
                if self.max_width > 0:
                    self.width = min(self.width, self.max_width)
        else:
            self.height = self.clipheight
            self.width = self.clipwidth

        if self.height <= 0 or self.width <= 0:
            log.warning(f"{self.__class__.__name__} has invalid pad height '{self.height}' and/or width '{self.width}'.")
            self.refreshable = False
            return

        # Calculate absolute coordinates used in refresh
        self.resize_abs()

        # (Re)create cursed pad object if height/width was changed
        if (not self.init_pad) or ((self.pad is not None) and (self.pad.getmaxyx() == (self.height + 1, self.width))):
            return

        self.pad = curses.newpad(self.height + 1, self.width)

        # (Re)draw static content of the pad
        self.draw_static()

    def resize_abs(self):
        # Calculate justification offset
        match self.justify_y:
            case Pad.JUSTIFY.LEFT:
                self.justy = 0
                self.absuly = self.uly
                self.absbry = min(self.uly + self.height - 1, self.bry)
            case Pad.JUSTIFY.CENTER:
                self.justy = max(self.height - self.clipheight, 0) // 2
                self.absuly = max(self.uly + (self.clipheight - self.height) // 2, self.uly)
                self.absbry = min(self.bry - (self.clipheight - self.height) // 2, self.bry)
            case Pad.JUSTIFY.RIGHT:
                self.justy = max(self.height - self.clipheight, 0)
                self.absuly = max(self.bry - self.height + 1, self.uly)
                self.absbry = self.bry

        match self.justify_x:
            case Pad.JUSTIFY.LEFT:
                self.justx = 0
                self.absulx = self.ulx
                self.absbrx = min(self.ulx + self.width - 1, self.brx)
            case Pad.JUSTIFY.CENTER:
                self.justx = max(self.width - self.clipwidth, 0) // 2
                self.absulx = max(self.ulx + (self.clipwidth - self.width) // 2, self.ulx)
                self.absbrx = min(self.brx - (self.clipwidth - self.width) // 2, self.brx)
            case Pad.JUSTIFY.RIGHT:
                self.justx = max(self.width - self.clipwidth, 0)
                self.absulx = max(self.brx - self.width + 1, self.ulx)
                self.absbrx = self.brx

        # Calculate absolute screen coordinates from frame-relative coordinates
        if self.parent is not None:
            self.justy = max(self.justy, self.parent.justy)
            self.justx = max(self.justx, self.parent.justx)

            self.absuly = min(self.absuly + self.parent.absuly, self.parent.absbry)
            self.absulx = min(self.absulx + self.parent.absulx, self.parent.absbrx)
            self.absbry = min(self.absbry + self.parent.absuly, self.parent.absbry)
            self.absbrx = min(self.absbrx + self.parent.absulx, self.parent.absbrx)

    def draw_static(self):
        pass

    def refresh(self):
        if self.refreshable:
            self.pad.refresh(
                self.justy,
                self.justx,
                self.absuly,
                self.absulx,
                self.absbry,
                self.absbrx,
            )

    def root(self):
        return self.parent.root() if self.parent is not None else self


class Frame(Pad):
    AXIS = Enum("AXIS", ["Y", "X"])
    SIZING = Enum("SIZING", ["FIT", "FILL", "FIXED"])
    ALIGNMENT = Enum("ALIGNMENT", ["SNUG", "EVEN"])
    JUSTIFY = Enum("JUSTIFY", ["LEFT", "CENTER", "RIGHT"])

    main_axis = AXIS.Y
    # Along which axis should the frame place its pads?

    sizing_y = SIZING.FILL
    sizing_x = SIZING.FILL
    # Determines how the frame should orchestrate its own height and width
    # FIT: Fit the frame around its children
    # FILL: Let the frame fill the space provided by the parent
    # FIXED: Keep the frame dimensions constant

    alignment = ALIGNMENT.SNUG
    # Determines how the frame should distribute main axis space among its children
    # SNUG: Give all leftover space to last and/or first added child
    # EVEN: Give all space evenly to each child

    alignment_justify = JUSTIFY.LEFT
    # Determines how the distributed main axis space should be justified

    bordered = False

    spawning = False

    def __init__(self, parent=None):
        if self.sizing_y == Frame.SIZING.FILL:
            self.stretch_clipheight = True
        if self.sizing_x == Frame.SIZING.FILL:
            self.stretch_clipwidth = True

        self.pads = []
        Pad.__init__(self, parent=parent, init_pad=self.bordered)

    def spawn(self, pad):
        if isinstance(pad, Frame):
            Frame.__init__(pad, parent=self)
            pad.spawner_wrapper()
        elif isinstance(pad, Pad):
            Pad.__init__(pad, parent=self)
        else:
            log.error(f"Could not spawn {pad} because it is not a valid Frame or Pad.")
            return
        self.pads.append(pad)
        if not self.spawning:
            self.fit_resize()
            self.resize()

        if pad.input is not None:
            pad.input.install(pad)

        return pad

    def spawner_wrapper(self):
        self.spawning = True
        self.spawner()
        self.spawning = False
        self.fit_resize()

    def spawner(self):
        pass

    def fit_resize(self):
        if self.sizing_y == Frame.SIZING.FIT:
            if self.main_axis == Frame.AXIS.X:
                self.height = max(child.height for child in self.pads) + 2 * self.bordered
            elif self.main_axis == Frame.AXIS.Y:
                self.height = sum(child.height for child in self.pads) + 2 * self.bordered
        if self.sizing_x == Frame.SIZING.FIT:
            if self.main_axis == Frame.AXIS.Y:
                self.width = max(child.width for child in self.pads) + 2 * self.bordered
            elif self.main_axis == Frame.AXIS.X:
                self.width = sum(child.width for child in self.pads) + 2 * self.bordered

    def resize(self):
        Pad.resize(self)

        if self.bordered:
            self.width -= 2
            self.height -= 2

        def child_resize_y(child, uly, bry):
            child.uly = max(min(uly, self.height), 0) + 1 * self.bordered
            child.bry = max(min(bry, self.height - 1), -1) + 1 * self.bordered

        def child_resize_x(child, ulx, brx):
            child.ulx = max(min(ulx, self.width), 0) + 1 * self.bordered
            child.brx = max(min(brx, self.width - 1), -1) + 1 * self.bordered

        if self.main_axis == Frame.AXIS.Y:
            child_resize_main = child_resize_y
            child_resize_off = child_resize_x
            main_length = lambda x: x.height
            off_length = self.width
        elif self.main_axis == Frame.AXIS.X:
            child_resize_main = child_resize_x
            child_resize_off = child_resize_y
            main_length = lambda x: x.width
            off_length = self.height

        clip_list = [0]
        match self.alignment:
            case Frame.ALIGNMENT.SNUG:
                match self.alignment_justify:
                    case Frame.JUSTIFY.LEFT:
                        coord = 0

                    case Frame.JUSTIFY.RIGHT:
                        coord = main_length(self) - sum(main_length(child) for child in self.pads)

                    case Frame.JUSTIFY.CENTER:
                        coord = (main_length(self) - sum(main_length(child) for child in self.pads)) // 2

                for child in self.pads[:-1]:
                    coord += main_length(child)
                    clip_list.append(coord)

            case Frame.ALIGNMENT.EVEN:
                coord = 0
                child_space = main_length(self) // len(self.pads)
                for child in self.pads[:-1]:
                    coord += child_space
                    clip_list.append(coord)

        clip_list.append(main_length(self))

        last_bordered = False
        for child, start_clip, end_clip in zip(self.pads, clip_list[:-1], clip_list[1:]):
            current_bordered = child.bordered if isinstance( child, Frame) else False
            child_resize_main(child, start_clip - 1*(last_bordered and current_bordered), end_clip - 1)
            child_resize_off(child, 0, off_length - 1)
            last_bordered = current_bordered

        if self.bordered:
            self.height += 2
            self.width += 2
        if not self.spawning:
            for child in self.pads:
                child.resize()

    def draw_static(self):
        if not self.bordered:
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

    def refresh(self):
        if not self.refreshable:
            return
        if self.bordered:
            Pad.refresh(self)
        for child in self.pads:
            child.refresh()


class RootFrame(Frame):
    input = Input()

    def __init__(self, stdscr):
        self.screen = stdscr
        Frame.__init__(self)
        self.spawner_wrapper()
        self.resize_term()

    @input.on_key(curses.KEY_RESIZE)
    def resize_term(self):
        termheight, termwidth = self.screen.getmaxyx()
        curses.resize_term(termheight, termwidth)
        self.screen.refresh()  # clear the screen
        self.uly, self.ulx = 0, 0
        self.bry, self.brx = termheight - 1, termwidth - 1
        self.resize()
        self.refresh()


class TwoEight(RootFrame):
    input = RootFrame.input

    def spawner(self):
        first_weekdata = WeekData.dummy(48)
        self.weekdatas = {(first_weekdata.year, first_weekdata.week): first_weekdata}
        self.header = self.spawn(HeaderPad(self))
        self.tabs = [self.spawn(WeekTab(first_weekdata))]
        self.current_tab = self.tabs[-1]
        self.input.install(self, fallback=(self.current_tab,), screen=self.screen)

    @input.on_key(ord("\t"))
    def switch_tab(self):
        self.current_tab = self.tabs[(self.tabs.index(self.current_tab) + 1) % len(self.tabs)]
        self.header.draw_static()
        self.input.install(self, fallback=(self.current_tab,), screen=self.screen)

    @input.on_key(3)  # Crtl + C
    def exit(self):
        log.info("Exiting two-eight. Goodnight, ladies and gentlemen.")
        raise CleanExit


class HeaderPad(Pad):
    height = 1
    width = 30

    def __init__(self, root):
        self.root = root

    def draw_static(self):
        self.pad.addstr(0, 0, "two-eight", curses.A_REVERSE)
        self.pad.addch("")
        if isinstance(self.root.current_tab, WeekTab):
            self.pad.addch(" ")
            self.pad.addstr(f"week {self.root.current_tab.weekdata.year}|{self.root.current_tab.weekdata.week}")


class WeekTab(Frame):
    main_axis = Frame.AXIS.X

    input = Input()

    def __init__(self, weekdata):
        self.weekdata = weekdata

    def spawner(self):
        self.timetableframe = self.spawn(TimetableFrame(self.weekdata))
        self.activityframe = self.spawn(ActivityFrame(self.weekdata))
        self.timetable = self.timetableframe.timetable
        self.activitytable = self.activityframe.activitytable

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
        self.activitytable.draw_activities_markers(*self.timetable.cursor_timeslot(), clear=True)
        self.timetable.cursor_y += d_y
        self.timetable.cursor_x += d_x
        self.timetable.select(shift=chr(self.input.c).isupper())
        self.activitytable.draw_activities_markers(*self.timetable.cursor_timeslot())
        self.activitytable.refresh()

    @input.on_key(ord("q"), ord("e"))
    def assign(self):
        verify = self.input.c == ord("e")
        activity = self.activitytable.cursor_activity()
        self.activitytable.draw_activities_markers(*self.timetable.cursor_timeslot(), clear=True)
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
        self.activitytable.refresh()

    @input.on_key(ord("o"))
    def activitytable_edit(self):
        self.activitytable.edit()


class VertScrollPad(Pad):
    scroll_variable = 0
    scrollpos = 0

    def refresh(self):
        if self.refreshable:
            self.pad.refresh(
                self.justy + self.scrollpos,
                self.justx,
                self.absuly,
                self.absulx,
                min(self.absbry, self.absuly + self.height - 1),
                self.absbrx,
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
    width = 48

    def __init__(self, weekdata):
        self.weekdata = weekdata
        self.height = weekdata.nr_timesegments
        self.cursor_y, self.cursor_x = 0, 0
        self.hold_cursor_y, self.hold_cursor_x = self.cursor_y, self.cursor_x
        self.selected = ((self.cursor_y, self.cursor_x),)

    def draw_static(self):
        for i in range(0, self.height):
            minutes = int(i * (24 / self.height) * 60)
            self.pad.addstr(i, 0, f"{minutes // 60:02d}:{minutes % 60:02d}", curses.A_DIM)
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
        self.pad.addch(self.cursor_y, timewidth + self.cursor_x * 6 + slotwidth + 1, "<")

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
    height = 3
    width = 48

    def __init__(self, weekdata):
        self.weekdata = weekdata

    def draw_static(self):
        weekdate = self.weekdata.date - datetime.timedelta(days=self.weekdata.date.weekday())
        month = weekdate.strftime("%b")
        self.pad.addstr(0, 5 - len(month), month)
        year = weekdate.strftime("%Y")
        self.pad.addstr(1, 5 - len(year), year)
        for i in range(7, self.width, 6):
            self.pad.addstr(0, i, weekdate.strftime("%d"))
            self.pad.addstr(1, i, weekdate.strftime("%a"))
            weekdate += datetime.timedelta(days=1)


class TimetableFrame(Frame):
    sizing_x = Frame.SIZING.FIT
    bordered = True

    def __init__(self, weekdata):
        self.weekdata = weekdata
        weekdata.timetableframe = self

    def spawner(self):
        self.header = self.spawn(TimetableHeaderPad(self.weekdata))
        self.timetable = self.spawn(TimetablePad(self.weekdata))


class ActivityTablePad(VertScrollPad):
    stretch_clipwidth = True
    min_width = 12

    input = Input()

    new_str = " + new"

    def __init__(self, weekdata):
        self.weekdata = weekdata
        self.height = len(weekdata.activities) + 1
        self.copy_activities()
        self.cursor = 0

    def copy_activities(self):
        self.activities_names = [e.name for e in self.weekdata.activities]
        self.activities_colors = [e.color() for e in self.weekdata.activities]

    def draw_static(self):
        self.namewidth = self.width - 12
        self.draw_activities()
        self.draw_cursor()

    def draw_activity(self, i):
        self.pad.move(i, 11)
        self.pad.clrtoeol()
        if self.namewidth > 0:
            self.pad.addstr(i, 11, self.activities_names[i][: self.namewidth])
        self.pad.chgat(i, 0, self.activities_colors[i] + curses.A_REVERSE)

    def draw_activities(self):
        if self.height != len(self.activities_names) + 1:
            self.height = len(self.activities_names) + 1
            self.resize()
        for i in range(len(self.activities_names)):
            self.draw_activity(i)
        self.pad.addstr(len(self.activities_names), 11, self.new_str)

    def draw_activities_markers(self, y, x, clear=False):
        cursor_timeslot = self.weekdata.timetable[y][x]
        char = "x" if not clear else " "
        for i in range(len(self.activities_names)):
            if self.weekdata.activities[i] == cursor_timeslot.plan:
                self.pad.addch(i, 2, char, self.activities_colors[i] + curses.A_REVERSE)
            if self.weekdata.activities[i] == cursor_timeslot.verify:
                self.pad.addch(i, 5, char, self.activities_colors[i] + curses.A_REVERSE)

    def draw_cursor(self, clear=False):
        char = ">" if not clear else " "
        if self.cursor < len(self.activities_names):
            self.pad.addch(
                self.cursor,
                8,
                char,
                self.activities_colors[self.cursor] + curses.A_REVERSE,
            )
        elif self.cursor == len(self.activities_names):
            self.pad.addch(self.cursor, 8, char)

    def select(self, d):
        self.draw_cursor(clear=True)
        self.cursor += d
        self.cursor %= self.height
        self.scroll(self.cursor)
        self.draw_cursor()
        self.refresh()

    def delete(self):
        if self.cursor == len(self.activities_names):
            return
        self.pad.move(len(self.activities_names), 0)
        self.pad.clrtoeol()
        self.refresh()
        self.weekdata.delete_activity(self.cursor_activity())
        self.copy_activities()
        self.draw_activities()
        self.select(0)

    def edit(self):
        is_new = self.cursor_activity() is None
        if is_new:
            activity = Activity("", 0, 0, 0) if is_new else self.cursor_activity()
            self.activities_names.append(activity.name)
            self.activities_colors.append(activity.color())
        else:
            activity = self.cursor_activity()
        activity_name = self.prompt_name(activity)
        if activity_name != "":
            r, g, b = self.prompt_colors(activity)
            self.draw_cursor(clear=True)
            if is_new:
                self.weekdata.add_activity(activity)
            self.weekdata.edit_activity(activity, activity_name, r, g, b)
            self.cursor = self.weekdata.activities.index(activity)
        self.copy_activities()
        self.draw_activities()
        self.select(0)

    def prompt_name(self, activity):
        self.activities_names[self.cursor] = activity.name
        self.draw_activity(self.cursor)
        self.refresh()
        with self.root().input as seizedinput:

            @seizedinput.on_key(curses.KEY_ENTER, 10, 13)  # new line, carriage return
            def confirm(_):
                raise seizedinput.InputBreak

            @seizedinput.on_key(curses.KEY_BACKSPACE, ord("\b"))
            def backspace(_):
                self.activities_names[self.cursor] = self.activities_names[self.cursor][:-1]
                if len(self.activities_names[self.cursor]) < self.namewidth:
                    self.pad.addch(
                        self.cursor,
                        11 + len(self.activities_names[self.cursor]),
                        " ",
                        self.activities_colors[self.cursor],
                    )
                self.draw_activity(self.cursor)
                self.refresh()

            @seizedinput.on_any()
            def type_char(_):
                self.activities_names[self.cursor] += chr(seizedinput.c)
                self.draw_activity(self.cursor)
                self.refresh()

            seizedinput.start_loop()
        return self.activities_names[self.cursor]

    def prompt_colors(self, activity):
        (
            r,
            g,
            b,
        ) = (activity.r, activity.g, activity.b)
        colors_str = [f"{r:03d}", f"{g:03d}", f"{b:03d}"]
        self.color_index = 0
        self.digit_index = 0
        self.activities_names[self.cursor] = f"R {colors_str[0]} | G {colors_str[1]} | B {colors_str[2]}"
        self.draw_activity(self.cursor)
        self.refresh()

        with self.root().input as seizedinput:

            @seizedinput.on_key(curses.KEY_ENTER, 10, 13)  # new line, carriage return
            def confirm(_):
                if self.color_index >= 2:
                    raise seizedinput.InputBreak
                self.color_index += 1
                self.digit_index = 0

            @seizedinput.on_key(*range(ord("0"), ord("9") + 1))
            def type_digit(_):
                colors_str[self.color_index] = (
                    colors_str[self.color_index][: self.digit_index] + chr(seizedinput.c) + colors_str[self.color_index][self.digit_index + 1 :]
                )
                self.digit_index += 1
                self.digit_index %= 3
                r, g, b = map(int, colors_str)
                activity.change_color(r, g, b)
                self.activities_colors[self.cursor] = activity.color()
                self.activities_names[self.cursor] = f"R {colors_str[0]} | G {colors_str[1]} | B {colors_str[2]}"
                self.draw_activity(self.cursor)
                self.refresh()

            seizedinput.start_loop()
        return r, g, b

    def cursor_activity(self):
        if self.cursor < len(self.activities_names):
            return self.weekdata.activities[self.cursor]
        return None


class ActivityHeaderPad(Pad):
    height = 2
    width = 20

    def draw_static(self):
        self.pad.addch(0, 2, "p")
        self.pad.addch(0, 5, "v")
        self.pad.addstr(0, 11, "name")


class ActivityFrame(Frame):
    bordered = True

    def __init__(self, weekdata):
        self.weekdata = weekdata

    def spawner(self):
        self.header = self.spawn(ActivityHeaderPad())
        self.activitytable = self.spawn(ActivityTablePad(self.weekdata))


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

        Activity.color_counter = Activity.color_counter + 1 if Activity.color_counter != curses.COLORS - 1 else 16
        Activity.color_pair_counter = Activity.color_pair_counter + 1 if Activity.color_pair_counter != curses.COLOR_PAIRS - 1 else 1

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
            log.error(f"Could not find an activity with name '{plan}' referenced in timeslot's planned activity.")
        if verify == "-":
            return cls(plan, None)
        try:
            verify = activities[verify]
        except KeyError:
            log.error(f"Could not find an activity with name '{verify}' referenced in timeslot's verify activity.")
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

    def change_timesegments(self, nr_timesegments):
        if self.nr_timesegments == nr_timesegments:
            return
        if nr_timesegments > self.nr_timesegments:
            ratio = nr_timesegments // self.nr_timesegments
            self.timetable = [self.timetable[i // ratio] for i in range(nr_timesegments)]
        else:
            ratio = self.nr_timesegments // nr_timesegments
            self.timetable = [self.timetable[i * ratio] for i in range(nr_timesegments)]

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
        return WeekData(nr_timesegments, list(activities.values()), timetable, week, year)

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
                    timetable[i][j] = Timeslot.from_strings(row[2 * j], row[2 * j + 1], activities)
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
            log.info(f"End of file reached in file {self.dbfile_path} line {self.line+1}")
            return None
        self.line += 1
        elements = line.replace("\n", "").split(self.delimiter)
        if expected_el != 0 and len(elements) != expected_el:
            log.error(f"Expected {expected_el} elements but parsed {len(elements)} elements in file {self.dbfile_path} line {self.line}.")
            raise ParseError
        return elements

    def seek_for(self, *args):
        """Seeks to a set of specific elements in a file"""
        el = self.parse_next_line()
        while el is not None and el != args:
            el = self.parse_next_line()
        log.error(f"Could not find seeking elements '{args}' in file {self.dbfile_path}")

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
    log.info(f"Terminal has extended color support: {curses.has_extended_color_support()}")
    log.info(f"Terminal can change colors: {curses.can_change_color()}")
    log.info(f"Amount of terminal colors: {curses.COLORS}")
    log.info(f"Amount of terminal color pairs: {curses.COLOR_PAIRS}")
    curses.use_default_colors()
    curses.curs_set(0)
    stdscr.leaveok(False)
    stdscr.refresh()  # refresh the stdscr window, otherwise this is implicitly called on first stdscr.getch()
    twoeight = TwoEight(stdscr)
    try:
        twoeight.input.start_loop()
    except CleanExit:
        stdscr.refresh()
        exit()


if __name__ == "__main__":
    curses.wrapper(main)
