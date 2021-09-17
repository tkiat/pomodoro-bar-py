#!/usr/bin/env python3
import unittest
import pomodoro_bar as app
from datetime import datetime


class TestDisplay(unittest.TestCase):
    def test_hhmmss(self):
        t = lambda a: app.display_create_hhmmss(a)
        self.assertEqual(t(1), '00:01')
        self.assertEqual(t(111), '01:51')
        self.assertEqual(t(3611), '01:00:11')


class TestRecord(unittest.TestCase):
    def setUp(self):
        self.w_min = 25
        self.workload = [25, 50, 75, 100, 75, 50, 25]
        self.this_monday = str(app.date_get_monday(0))
        self.today_letter = datetime.now().date().strftime("%a")
        self.num_days = 7
        self.record = {
            self.this_monday: {
                "Mon": self.workload[0],
                "Tue": self.workload[1],
                "Wed": self.workload[2],
                "Thu": self.workload[3],
                "Fri": self.workload[4],
                "Sat": self.workload[5],
                "Sun": self.workload[6],
            }
        }

    def test_record_create_updated(self):
        update = lambda rec: app.record_create_updated(
            rec, self.this_monday, self.today_letter, self.w_min)
        sum_thisweek = lambda rec: sum(rec[self.this_monday].values())

        sum_old = sum_thisweek(self.record)

        updated_once = update(self.record)
        self.assertEqual(sum_thisweek(updated_once), sum_old + 25)

        updated_twice = update(updated_once)
        self.assertEqual(sum_thisweek(updated_twice), sum_old + 50)
#

    def test_record_get_week_summary(self):
        t = lambda week_offset: app.record_get_week_summary(
            self.record, str(app.date_get_monday(week_offset)), self.num_days,
            self.w_min)
        self.assertEqual(
            ['1.0', '2.0', '3.0', '4.0', '3.0', '2.0', '1.0', '2.3'], t(0))
        self.assertEqual(['', '', '', '', '', '', '', ''], t(1))


# -----------------------------------------------------------------------------
# Test session

# def helper_test_alternate(self, a: Iterator[app.Session], f):
#     n = lambda: getattr(next(a), f)
#     (a1, a2, a3) = (n(), n(), n())
#     for _ in range(0, 9):
#         self.assertEqual(a1, a3)
#         self.assertNotEqual(a1, a2)
#         (a1, a2, a3) = (a2, a3, getattr(next(a), f))
#
#
# def helper_test_alternate_except_last(self, a: Iterator[app.Session], f):
#     n = lambda: getattr(next(a), f)
#     (a1, a2, a3) = (n(), n(), n())
#     for i in range(0, 9):
#         self.assertNotEqual(a1, a2)
#         if i in range(0, 5):
#             self.assertEqual(a1, a3)
#         else:
#             self.assertNotEqual(a2, a3)
#         (a1, a2, a3) = (a2, a3, n())


class TestSession(unittest.TestCase):
    def setUp(self):
        self.w_sec = 25 * 60
        self.b_sec = 5 * 60
        self.l_sec = 15 * 60
        self.cmd_w = 'cmd_w'
        self.cmd_b = 'cmd_b'
        start_session_num = 1
        self.session_iter = app.session_generator(self.w_sec, self.b_sec,
                                                  self.l_sec, self.cmd_w,
                                                  self.cmd_b,
                                                  start_session_num)

    def test_session_num(self):
        a = next(self.session_iter).num
        b = next(self.session_iter).num
        c = next(self.session_iter).num
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)

    def test_session_command(self):
        a = next(self.session_iter).command
        b = next(self.session_iter).command
        c = next(self.session_iter).command
        self.assertNotEqual(a, b)
        self.assertEqual(a, c)

    def test_session_progress_bar(self):
        progress_bar = app.cli_create_progressbar(next(self.session_iter))
        self.assertEqual(progress_bar, "[w]-b-w-b-w-b-w-l")

        progress_bar = app.cli_create_progressbar(next(self.session_iter))
        self.assertEqual(progress_bar, "w-[b]-w-b-w-b-w-l")

        progress_bar = app.cli_create_progressbar(next(self.session_iter))
        self.assertEqual(progress_bar, "w-b-[w]-b-w-b-w-l")

    def test_session_seconds(self):
        self.assertEqual(next(self.session_iter).seconds, self.w_sec)
        self.assertEqual(next(self.session_iter).seconds, self.b_sec)
        self.assertEqual(next(self.session_iter).seconds, self.w_sec)
        self.assertEqual(next(self.session_iter).seconds, self.b_sec)
        self.assertEqual(next(self.session_iter).seconds, self.w_sec)
        self.assertEqual(next(self.session_iter).seconds, self.b_sec)
        self.assertEqual(next(self.session_iter).seconds, self.w_sec)
        self.assertEqual(next(self.session_iter).seconds, self.l_sec)

    def test_session_type(self):
        a = next(self.session_iter).type
        b = next(self.session_iter).type
        c = next(self.session_iter).type
        self.assertNotEqual(a, b)
        self.assertEqual(a, c)


if __name__ == '__main__':
    unittest.main()
