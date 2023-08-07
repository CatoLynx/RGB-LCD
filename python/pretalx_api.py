"""
Copyright (C) 2023 Julian Metzler

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

import dateutil.parser
import requests


class APIError(Exception):
    pass


class PretalxAPI:
    def __init__(self, schedule_url):
        self.schedule_url = schedule_url
    
    def get_schedule(self):
        response = requests.get(self.schedule_url)
        if response.status_code != 200:
            raise APIError("Server returned HTTP status {code}".format(code=response.status_code))
        data = response.json()
        return data['schedule']
    
    def get_all_events(self):
        # Returns a list of all events sorted by time
        schedule = self.get_schedule()
        all_events = []
        for day in schedule['conference']['days']:
            for name, events in day['rooms'].items():
                all_events.extend(events)
        all_events.sort(key=lambda event: dateutil.parser.isoparse(event['date']))
        return all_events
