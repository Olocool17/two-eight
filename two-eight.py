import curses

class Two_eight:
    def __init__(self):
        curses.wrapper(self._init_window)
    def _init_window(self, stdscr):
        self.screen = stdscr
        curses.use_default_colors()
        self.resize()
        self.input_loop()

    def resize(self):
        self.y, self.x = self.screen.getmaxyx()
        self.screen.clear()
        curses.resize_term(self.y, self.x)
        self.draw_frame()
        self.screen.refresh()

        self.pads = [Week_pad(self.screen, self.y - 2, self.x - 2, 1, 1, 48)]

    def input_loop(self):
        while True:
            c = self.screen.getch()
            if  c == curses.KEY_RESIZE:
                self.resize()
            elif c == 3: #Crtl + C
                self.screen.clear()
                self.screen.refresh()
                raise KeyboardInterrupt()
            else:
                for pad in self.pads:
                    pad.input_loop(c)

    def draw_frame(self):
        self.screen.border(0,0,0,0,0,0,0,0)
        self.screen.addstr(0, (self.x // 2) - len("two-eight") // 2, "two-eight", curses.A_REVERSE)

class Scroll_vert_pad:
    def __init__(self, screen, padheight, padwidth, clipheight, clipwidth, clipuly, clipulx):
        self.screen = screen
        self.pad = curses.newpad(padheight, padwidth+1)
        self.padheight, self.padwidth = padheight, padwidth
        self.clipheight, self.clipwidth = min(padheight, clipheight), min(padwidth, clipwidth)
        self.clipuly, self.clipulx = clipuly, clipulx
        self.scroll = 0
        self.scrolldelta = 4
        self.pad.clear()
        self.refresh()
        
    def refresh(self):
        self.pad.refresh(self.scroll, 0, self.clipuly, self.clipulx, self.clipuly + self.clipheight - 1, self.clipulx + self.clipwidth - 1)
    
    def scroll_down(self):
        self.scroll = min(self.scroll + self.scrolldelta, self.padheight - self.clipheight)
        self.refresh()

    def scroll_up(self):
        self.scroll = max(self.scroll - self.scrolldelta, 0)
        self.refresh()

class Week_pad(Scroll_vert_pad):
    def  __init__(self, screen, clipheight, clipwidth, clipuly, clipulx, nr_timesegments):
        super().__init__(screen, nr_timesegments, 48, clipheight, clipwidth, clipuly, clipulx)
        if (nr_timesegments % 24 != 0 and 24 % nr_timesegments != 0):
            raise Exception()
        for i in range(nr_timesegments):
            minutes = int(i*(24 / nr_timesegments)*60)
            self.pad.addstr(i, 0,f"{minutes // 60:02d}:{minutes % 60:02d}", curses.A_DIM)
            if i > self.clipheight + self.scroll:
                self.scroll += self.clipheight
                self.refresh()
        self.scroll = 0

        self.days = 7
        self.segments = nr_timesegments #time segments per day

        self.selected = 0
        self.select()
 
    def select(self):
        self.selected = self.selected % (self.segments * self.days)
        self.scroll = min(self.padheight - self.clipheight, self.selected % self.segments)
        self.refresh()
        self.clear_select()
        self.pad.addstr(self.selected % self.segments, 5 + (self.selected // self.segments) * 6, ">     <")
        self.refresh()

    def clear_select(self):
        for i in range(self.days+1):
            for j in range(self.segments):
                self.pad.addch(j, 5 + i * 6, ' ')
    def input_loop(self, c):
        if c == ord('i'):
            self.selected -= 1
        elif c == ord('k'):
            self.selected += 1
        elif c == ord('j'):
            self.selected -= self.segments
        elif c == ord('l'):
            self.selected += self.segments
        else:
            return
        self.select()

class Week_data(): #Backend for week_pad class
    def __init__(self, nr_timesegments, activities, timetable):


class Parser():
    def __init__(self, dbfile_path = "data.te"):
        self.dbfile_path = dbfile_path
    def parse_week(self, week, year):
        with open(dbfile_path, mode='r', encoding='utf-8') as infile:
            while(infile.readline() != [str(year), str(week)] == e.replace('\n', '').split(' ')):
                nr_timesegments, nr_activities = infile.readline().replace('\n', '').split(' ')
                nr_timesegments, nr_activities = int(nr_timesegments), int(nr_activities)
                activities = []
                for _ in range(nr_activities):
                    try:
                        name, color = infile.readline().replace('\n', '').split(' ')
                    except ValueError():
                        #PH : Log warning here
                        return
                    activities.append(Activity(name, color))
                timetable = [[0 for j in range(nr_timesegments)]for i in range(7)]
                for i in range(nr_timesegments):
                    row = infile.readline().replace('\n', '').split(' ')
                    for j in range(7):
                        timetable[j,i] = row[j]

class Activity():
    def __init__(self, name, color):
        self.name = name
        self.color

class Timeslot():
    def __init(self, plan, verify):
        self.plan = plan
        self.verify = verify


def center_string(string, width):
    return (width // 2) - len(string) // 2, string

Two_eight()