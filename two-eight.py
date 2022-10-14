import curses
import time

class TwoEight:
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

        self.pads = [WeekPad(self.screen, self.y - 2, self.x - 2, 1, 1, 48)]

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

class Pad:
    def __init__(self, screen, padheight, padwidth, clipheight, clipwidth, clipuly, clipulx):
        self.screen = screen
        self.pad = curses.newpad(padheight, padwidth+1)
        self.padheight, self.padwidth = padheight, padwidth
        self.clipheight, self.clipwidth = min(padheight, clipheight), min(padwidth, clipwidth)
        self.clipuly, self.clipulx = clipuly, clipulx     
    def refresh(self):
        self.pad.refresh(0, 0, self.clipuly, self.clipulx, self.clipuly + self.clipheight - 1, self.clipulx + self.clipwidth - 1)
    def subpad(self, padheight, padwidth, paduly, padulx):
        return self.pad.subpad(padheight, padwidth, paduly, padulx)

class VertScrollPad(Pad):
    def __init__(self, screen, padheight, padwidth, clipheight, clipwidth, clipuly, clipulx):
        super().__init__(screen, padheight, padwidth, clipheight, clipwidth, clipuly, clipulx)
        self.scroll = 0
        self.pad.clear()
        self.refresh()
        
    def refresh(self):
        self.pad.refresh(self.scroll, 0, self.clipuly, self.clipulx, self.clipuly + self.clipheight - 1, self.clipulx + self.clipwidth - 1)
    
    def scroll_down(self, scrolldelta = 4):
        self.scroll = min(self.scroll + scrolldelta, self.padheight - self.clipheight)
        self.refresh()

    def scroll_up(self, scrolldelta = 4):
        self.scroll = max(self.scroll - scrolldelta, 0)
        self.refresh()

class WeekPad(VertScrollPad):
    def  __init__(self, screen, clipheight, clipwidth, clipuly, clipulx, nr_timesegments):
        self.weekdata = WeekData.dummy(nr_timesegments)
        super().__init__(screen, nr_timesegments, 48, clipheight, clipwidth, clipuly, clipulx)
        if (nr_timesegments % 24 != 0 and 24 % nr_timesegments != 0):
            pass
            #PH : Log warning here
        for i in range(nr_timesegments):
            minutes = int(i*(24 / nr_timesegments)*60)
            self.pad.addstr(i, 0,f"{minutes // 60:02d}:{minutes % 60:02d}", curses.A_DIM)
            if i > self.clipheight + self.scroll:
                self.scroll += self.clipheight
                self.refresh()
        self.days = 7
        self.nr_timesegments = nr_timesegments #time segments per day

        self.selected = [0, 0]
        self.select()
 
    def select(self):
        self.selected[0] %= self.nr_timesegments
        self.selected[1] %= self.days
        self.scroll = min(self.padheight - self.clipheight, self.selected[0])
        self.refresh()
        self.clear_select()
        self.pad.addstr(self.selected[0], 5 + self.selected[1] * 6, ">     <")
        self.refresh()

    def clear_select(self):
        for i in range(self.days+1):
            for j in range(self.nr_timesegments):
                self.pad.addch(j, 5 + i * 6, ' ')
    def input_loop(self, c):
        if c == ord('i'):
            self.selected[0] -= 1
        elif c == ord('k'):
            self.selected[0] += 1
        elif c == ord('j'):
            self.selected[1] -= 1
        elif c == ord('l'):
            self.selected[1] += 1
        else:
            return
        self.select()

class Activity():
    def __init__(self, name: str, color, desc=''):
        self.name = name
        self.color = color
        self.desc = desc

class Activities():
    def  __init__(self, activities: set = {}):
        self.dict = {activity.name:activity for activity in activities}

    def add_activity(self, activity):
        self.dict.update({activity.name:activity})

class Timeslot():
    def __init__(self, plan: Activity, verify: Activity):
        self.plan = plan
        self.verify = verify

    @classmethod
    def from_strings(cls, plan: str, verify: str, activities: Activities):
        try:
            plan = activities.dict[plan]
        except KeyError:
            return
            #PH : Log warning here
        if verify == ' ':
            return cls(plan, None)
        try:
            verify = activities.dict[verify]
        except KeyError:
            return
            #PH : Log warning here
        return cls(plan, verify)

class WeekData(): #Backend for week_pad class
    def __init__(self, nr_timesegments : int, activities : Activities, timetable : list):
        self.nr_timesegments = nr_timesegments
        self.activities = activities
        self.timetable = timetable

    @staticmethod
    def from_file(parser, week: int, year: int):
        return parser.parse_week(week, year)
    #Returns a week_data object with placeholder data
    @classmethod
    def dummy(cls, nr_timesegments):
        activities = Activities({Activity('dummy', 0)})
        return cls(nr_timesegments, activities, [[Timeslot.from_strings('dummy', 'dummy', activities) for j in range(7)] for i in range(nr_timesegments)])

class Parser():
    delimiter = '\t'
    @classmethod
    def parse_next_line(cls, file):
        line = file.readline().replace('\n', '').split(cls.delimiter)
        return line
    def __init__(self, dbfile_path = "data.te"):
        #Check if filepath is valid
        try:
            file = open(dbfile_path, mode='r', encoding='utf-8')
            file.close()
        except FileNotFoundError:
            return
            #PH : Log warning here
        except:
            return
            #PH : Log warning here
        self.dbfile_path = dbfile_path

    def parse_week(self, week: int, year: int) -> WeekData:
        year, week = str(year), str(week)
        with open(self.dbfile_path, mode='r', encoding='utf-8') as infile:
            while(Parser.parse_next_line(infile) != [year, week]):
                pass
            nr_timesegments, nr_activities = Parser.parse_next_line(infile)
            nr_timesegments, nr_activities = int(nr_timesegments), int(nr_activities)
            activities = Parser.parse_activities(nr_activities, nr_timesegments, infile)
            timetable = Parser.parse_timetable(nr_timesegments, activities, infile)
            return WeekData(nr_timesegments, activities, timetable)

    @staticmethod
    def parse_activities(nr_activities: int, infile) -> Activities:
        activities = Activities()
        for _ in range(nr_activities):
            try:
                name, color = Parser.parse_next_line(infile)
            except ValueError():
                #PH : Log warning here
                return
            activities.add_activity(Activity(name, color))
        Parser.parse_next_line(infile)
        return activities

    @staticmethod
    def parse_timetable(nr_timesegments: int, activities: int, infile, verify : bool = True) -> list:
        timetable = [[0]*7 for _ in range(nr_timesegments)]
        for i in range(nr_timesegments):
            row = Parser.parse_next_line(infile)
            for j in range(7):
                timetable[i][j] = Timeslot.from_strings(*row[2*j:2*j+2], activities)
        return timetable


def main():
    TwoEight()

if __name__ == "__main__":
    main()