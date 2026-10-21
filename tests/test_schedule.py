"""Daily schedules use wall-clock boundaries, not fixed 24-hour durations."""
from datetime import datetime, timezone
import unittest

from app import create_app
from lexi.schedule import daily_schedule, rollover_at, validate_time
from auth_support import signed_in_client


class ScheduleTests(unittest.TestCase):
    def test_before_and_at_the_selected_minute(self):
        before = daily_schedule(datetime(2026,10,19,1,59,59,tzinfo=timezone.utc),'Asia/Bishkek','08:00')
        after = daily_schedule(datetime(2026,10,19,2,0,tzinfo=timezone.utc),'Asia/Bishkek','08:00')
        self.assertEqual(before['calendarDate'],'2026-10-19')
        self.assertEqual(before['date'],'2026-10-18')
        self.assertEqual(after['date'],'2026-10-19')
        self.assertEqual(before['nextUpdateAt'],'2026-10-19T02:00:00+00:00')
        self.assertEqual(after['nextUpdateAt'],'2026-10-20T02:00:00+00:00')

    def test_midnight_and_quarter_hour_timezones(self):
        result = daily_schedule(datetime(2026,10,18,18,30,tzinfo=timezone.utc),'Asia/Kathmandu','00:15')
        self.assertEqual(result['date'],'2026-10-19')
        self.assertEqual(result['nextUpdateAt'],'2026-10-19T18:30:00+00:00')

    def test_spring_clock_gap_uses_first_valid_minute(self):
        self.assertEqual(rollover_at('2026-03-08','02:30','America/New_York'),datetime(2026,3,8,7,tzinfo=timezone.utc))
        self.assertEqual(daily_schedule(datetime(2026,3,8,6,59,tzinfo=timezone.utc),'America/New_York','02:30')['date'],'2026-03-07')
        self.assertEqual(daily_schedule(datetime(2026,3,8,7,0,tzinfo=timezone.utc),'America/New_York','02:30')['date'],'2026-03-08')

    def test_fall_repeated_hour_never_reverts_to_yesterday(self):
        self.assertEqual(rollover_at('2026-11-01','01:30','America/New_York'),datetime(2026,11,1,5,30,tzinfo=timezone.utc))
        # 06:10 UTC is the second 01:10. The first 01:30 already happened.
        for hour,minute in ((5,30),(5,59),(6,10),(6,30)):
            with self.subTest(hour=hour,minute=minute):
                self.assertEqual(daily_schedule(datetime(2026,11,1,hour,minute,tzinfo=timezone.utc),'America/New_York','01:30')['date'],'2026-11-01')

    def test_half_hour_daylight_saving_gap(self):
        self.assertEqual(rollover_at('2026-10-04','02:15','Australia/Lord_Howe'),datetime(2026,10,3,15,30,tzinfo=timezone.utc))

    def test_invalid_times_and_naive_clock_are_rejected(self):
        for value in ('8:00','24:00','00:60','noon','',None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_time(value)
        with self.assertRaises(ValueError):
            daily_schedule(datetime(2026,1,1),'UTC','08:00')

    def test_api_accepts_device_timezone_and_time(self):
        client = signed_in_client(create_app({'TESTING':True}))
        result = client.get('/api/daily?collections=ielts,science&timezone=Europe/London&update_time=09:15')
        self.assertEqual(result.status_code,200)
        data = result.get_json()
        self.assertEqual(data['timezone'],'Europe/London')
        self.assertEqual(data['updateTime'],'09:15')
        self.assertIn(data['word']['collectionId'],('ielts','science'))
        self.assertIn('nextUpdateAt',data)

    def test_api_rejects_invalid_timezone_or_time(self):
        client = signed_in_client(create_app({'TESTING':True}))
        for query in ('timezone=Not/A_Zone','update_time=24:00','update_time=8:00','timezone='):
            with self.subTest(query=query):
                self.assertEqual(client.get('/api/daily?'+query).status_code,400)


if __name__ == '__main__':
    unittest.main()
