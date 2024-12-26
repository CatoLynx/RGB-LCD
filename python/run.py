"""
Copyright (C) 2023-2024 Julian Metzler

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

import datetime
import dateutil.parser
import hashlib
import json
import os
import random
import time
import traceback

from pretalx_api import PretalxAPI, ongoing_or_future_filter, max_duration_filter
from deutschebahn import DBInfoscreen
from deutschebahn.utils import timeout

from PIL import Image
from pprint import pprint
from pyfis.aegmis import MIS1MatrixDisplay
from pyfis.aegmis.exceptions import CommunicationError
from requests.exceptions import ConnectionError

from _config import *
from text_renderer import TextRenderer
from gcm_controller import GCMController


DISPLAY_MODES = [
    "db-departures",
    "hackertours",
    "pretalx",
    "images",
]

TRACK_CODES = {
    "Hardware & Making": "HW",
    "Art & Beauty": "AB",
    "Ethics, Society & Politics": "EP",
    "CCC": "C",
    "Entertainment": "E",
    "Science": "S",
    "Security": "SE"
}

ROOM_ABBREVIATIONS = {
    "Saal GLITCH": "GLITCH",
    "Saal ZIGZAG": "ZIGZAG"
}

TRACK_COLORS = {
    "HW": 0x6b5ea1,
    "AB": 0xf9b000,
    "EP": 0xe40429,
    "C":  0xf2f006,
    "E":  0x80807f,
    "S":  0x00ff88,
    "SE": 0x0463fb
}

GENERIC_PALETTE = [
    0xff0000,
    0x00ff00,
    0x0000ff,
    0xff0000,
    0x00ffff,
    0xff00ff,
    0xffffff
]


@timeout(30)
def get_trains(dbi, station):
    return dbi.get_trains(station)


# Pride flag image parser
def _flag_to_sectors(flag):
    # Takes the middle vertical column of pixels from the image
    # and converts it into a list of 32 colors
    if not isinstance(flag, Image.Image):
        flag = Image.open(flag)
    flag = flag.convert('RGB')
    pixels = flag.load()
    width, height = flag.size
    x = width // 2
    
    # Get colors and height per color
    colors = []
    current_color = pixels[x, 0]
    current_color_height = 0
    for y in range(height):
        color = pixels[x, y]
        current_color_height += 1
        if (color != current_color) or (y == height - 1):
            # Discard color artefacts that are too narrow
            if current_color_height / height > 0.05:
                hex_color = (current_color[0] << 16) | (current_color[1] << 8) | current_color[2]
                colors.append([hex_color, current_color_height])
            current_color = color
            current_color_height = 0
    
    # Limit to 32 colors max.
    colors = colors[:32]
    
    # Adapt heights to 32 sectors
    total_height = sum([color[1] for color in colors])
    for i, (color, height) in enumerate(colors):
        colors[i][1] = round(32 * height / total_height)
    
    # If new heights don't add up to 32, adapt last one
    if sum([color[1] for color in colors]) != 32:
        colors[-1][1] = 32 - sum([color[1] for color in colors[:-1]])
    
    # Turn color list into sector list of 32 colors
    sectors = []
    for color, height in colors:
        sectors.extend([color] * height)
    return sectors
    


def main():
    try:
        mode_index = 0
        mode = DISPLAY_MODES[mode_index]
        page = 1
        secondary_page = 2
        display_width = 3 * 96
        display_height = 64
        page_interval = 10 # Page switch interval in seconds (roughly)
        
        hackertours_boarding_duration = 10 # How long (in minutes) the boarding screen should stay
        
        dbi_stations = [("ADF", "Dammtor")]
        dbi_num_trains = 3
        dbi_cur_station = 0
        
        pretalx = PretalxAPI("https://fahrplan.events.ccc.de/congress/2024/fahrplan/schedule/export/schedule.json")
        dbi = DBInfoscreen("trains.xatlabs.com")
        renderer = TextRenderer("../fonts")
        display = MIS1MatrixDisplay(CONFIG_LCD_PORT, baudrate=115200, use_rts=False, debug=False)
        gcm = GCMController(CONFIG_GCM_PORT, debug=False)
        time.sleep(3)
        gcm.set_high_current(True)
        
        try:
            display.reset()
        except CommunicationError:
            pass
        time.sleep(1)
        display.set_config(
            lcd_module=0,
            num_lcds=3,
            x=0,
            y=0,
            id=1,
            board_timeout=600,
            fr_freq=0,
            fps=0,
            is_master=False,
            protocol_timeout=600,
            response_delay=0
        )
        display.become_master()
        
        last_page_update = 0
        hackertours_boarding = False
        hackertours_last_blink_update = 0
        hackertours_blink_state = False
        while True:
            utcnow = datetime.datetime.utcnow()
            now = datetime.datetime.now()
            
            # Handle all background calculations and data operations
            # Handle green alternating flashing on hackertours boarding
            if hackertours_boarding:
                now_time = time.time()
                if now_time - hackertours_last_blink_update >= 1.0:
                    hackertours_blink_state = not hackertours_blink_state
                    gcm.clear()
                    if hackertours_blink_state:
                        for i in range(10):
                            gcm.set_sector(i, 0x000000)
                        for i in range(10):
                            gcm.set_sector(i+22, 0x00FF00)
                    else:
                        for i in range(10):
                            gcm.set_sector(i, 0x00FF00)
                        for i in range(10):
                            gcm.set_sector(i+22, 0x000000)
                    gcm.update()
                    hackertours_last_blink_update = now_time
            
            if (time.time() - last_page_update) < page_interval:
                time.sleep(0.1)
                continue
            
            display.delete_page(secondary_page)
            gcm.clear()
            page, secondary_page = secondary_page, page
            print("Handling mode: " + mode)
            
            # Handle displaying the required content
            hackertours_boarding = False
            skip_current_mode = False
            try:
                if mode == "hackertours":
                    # Load tours from file
                    with open("/tmp/hackertours.txt", 'r') as f:
                        lines = f.readlines()
                    
                    tours = []
                    for line in lines:
                        timestamp = " ".join(line.split()[:2])
                        code = line.split()[2]
                        destination = " ".join(line.split()[3:])
                        start = datetime.datetime.strptime(timestamp, "%d.%m.%Y %H:%M")
                        if start >= (now - datetime.timedelta(minutes=hackertours_boarding_duration)):
                            tours.append({'start': start, 'code': code, 'destination': destination})
                    
                    for tour in tours:
                        if now >= tour['start'] and now <= (tour['start'] + datetime.timedelta(minutes=hackertours_boarding_duration)):
                            # This tour is boarding now
                            display.fill_area(page, x=0, y=0, width=24, height=64, state=1)
                            boarding_img = renderer.render_multiline_text(width=display_width-24, height=display_height, pad_left=0, pad_top=0, font="21_DBLCD", size=0, halign='center', valign='middle', inverted=True, h_spacing=1, v_spacing=3, char_width=None, text="Now boarding:\n" + tour['destination'], auto_wrap=True, break_words=False)
                            display.image(page, 24, 0, boarding_img)
                            hackertours_boarding = True
                    
                    if not hackertours_boarding:
                        header_image = renderer.render_text(width=256, height=12, pad_left=0, pad_top=0, font="12_DBLCD", size=0, halign='left', valign='top', inverted=True, spacing=1, char_width=None, text="Hackertours")
                        display.image(page, 32, 0, header_image)
                        display.fill_area(page, x=0, y=14, width=288, height=1, state=1)
                        display.fill_area(page, x=0, y=0, width=24, height=14, state=1)
                        gcm.set_sector(0, 0xFF0000)
                        gcm.set_sector(1, 0xFF7F00)
                        gcm.set_sector(2, 0xFFFF00)
                        gcm.set_sector(3, 0x00FF00)
                        gcm.set_sector(4, 0x0000FF)
                        gcm.set_sector(5, 0x4B0082)
                        gcm.set_sector(6, 0x8F00FF)
                        
                        if tours:
                            items = sorted(tours, key=lambda t: t['start'])[:3]
                            for i, tour in enumerate(items):
                                dep_str = tour['start'].strftime("%a %H:%M")
                                y_base = (i + 1) * 16
                                line = tour['code']
                                # Crudely make lines have repeatable distinct colors
                                color_index = sum(hashlib.md5(line.encode('utf8')).digest()) % len(GENERIC_PALETTE)
                                for sector in range(8):
                                    gcm.set_sector(y_base // 2 + sector, GENERIC_PALETTE[color_index])
                                line_image = renderer.render_text(width=24, height=16, pad_left=0, pad_top=0, font="10S_DBLCD", size=0, halign='center', valign='middle', inverted=False, spacing=1, char_width=None, text=line)
                                display.image(page, 0, y_base, line_image)
                                dest_image = renderer.render_text(width=180, height=16, pad_left=0, pad_top=0, font="10S_DBLCD", size=0, halign='left', valign='middle', inverted=True, spacing=1, char_width=None, text=tour['destination'])
                                display.image(page, 32, y_base, dest_image)
                                dep_image = renderer.render_text(width=72, height=16, pad_left=0, pad_top=0, font="10S_DBLCD", size=0, halign='right', valign='middle', inverted=True, spacing=1, char_width=None, text=dep_str)
                                display.image(page, 216, y_base, dep_image)
                        else:
                            no_dep_img = renderer.render_text(width=display_width-24, height=48, pad_left=0, pad_top=0, font="12_DBLCD", size=0, halign='center', valign='middle', inverted=True, spacing=2, char_width=None, text="No Hackertours :(")
                            display.image(page, 24, 16, no_dep_img)
                elif mode == "pretalx":
                    # Display header
                    track_image = renderer.render_text(width=28, height=7, pad_left=0, pad_top=0, font="7_DBLCD", size=0, halign='left', valign='top', inverted=True, spacing=1, char_width=None, text="Trck")
                    location_image = renderer.render_text(width=70, height=7, pad_left=0, pad_top=0, font="7_DBLCD", size=0, halign='left', valign='top', inverted=True, spacing=1, char_width=None, text="Location")
                    title_image = renderer.render_text(width=32, height=7, pad_left=0, pad_top=0, font="7_DBLCD", size=0, halign='left', valign='top', inverted=True, spacing=1, char_width=None, text="Title")
                    time_image = renderer.render_text(width=50, height=7, pad_left=0, pad_top=0, font="7_DBLCD", size=0, halign='right', valign='top', inverted=True, spacing=1, char_width=None, text="Starts in")
                    display.image(page, 0, 0, track_image)
                    display.image(page, 26, 0, location_image)
                    display.image(page, 96, 0, title_image)
                    display.image(page, 238, 0, time_image)
                    display.fill_area(page, x=0, y=8, width=288, height=1, state=1)
                    for i in range(5):
                        gcm.set_sector(i, 0xffffff)

                    # Get schedule from pretalx
                    events = pretalx.get_all_events()

                    #tracks = list(set([event['track'] for event in events]))
                    #pprint(tracks)
                    
                    # Filter out all events longer then 2 hours
                    events = filter(lambda event: max_duration_filter(event, 2, 0), events)
                    
                    # Filter out all events that are finished
                    events = filter(lambda event: ongoing_or_future_filter(event, max_ongoing=9), events)
                    events = list(events)

                    if events:
                        for i, event in enumerate(events[:3]):
                            start = dateutil.parser.isoparse(event['date']).replace(tzinfo=None)
                            delta = start - now
                            seconds = round(delta.total_seconds())
                            if seconds < 0:
                                time_text = "{}m ago".format(round(-seconds / 60))
                            elif seconds >= 3600:
                                time_text = "{}h{}m".format(seconds // 3600, round((seconds % 3600) / 60))
                            else:
                                time_text = "{}m".format(round((seconds % 3600) / 60))

                            track_code = TRACK_CODES.get(event['track'], (event['track'] or "/").upper()[:2])
                            track_color = TRACK_COLORS.get(track_code, 0xffffff)

                            y_base = 12 + i * 16
                            for r in range(8):
                                gcm.set_sector(y_base // 2 + r, track_color)

                            track_image = renderer.render_text(width=24, height=16, pad_left=0, pad_top=0, font="10S_DBLCD", size=0, halign='center', valign='middle', inverted=False, spacing=1, char_width=None, text=track_code)
                            room_image = renderer.render_text(width=68, height=16, pad_left=0, pad_top=3, font="7_DBLCD", size=0, halign='left', valign='top', inverted=True, spacing=1, char_width=None, text=ROOM_ABBREVIATIONS.get(event['room'], event['room']))
                            title_image = renderer.render_text(width=1000, height=16, pad_left=0, pad_top=0, font="10_DBLCD", size=0, halign='left', valign='top', inverted=True, spacing=1, char_width=None, text=event['title'])
                            time_image = renderer.render_text(width=50, height=16, pad_left=0, pad_top=0, font="10S_DBLCD", size=0, halign='right', valign='top', inverted=True, spacing=1, char_width=None, text=time_text)
                            
                            room_bbox = room_image.getbbox()
                            room_image = room_image.crop((0, 0, room_bbox[2], room_bbox[3]))
                            title_bbox = title_image.getbbox()
                            title_image = title_image.crop((0, 0, title_bbox[2], title_bbox[3]))
                            
                            display.image(page, 0, y_base, track_image)
                            display.image(page, 26, y_base+1, room_image)
                            if title_image.size[0] > 140:
                                display.scroll_image(i*2+1, page, 96, y_base+3, 140, title_image, extra_whitespace=50)
                            else:
                                display.image(page, 96, y_base+3, title_image)
                            display.image(page, 238, y_base+3, time_image)
                    else:
                        no_evt_img = renderer.render_text(width=display_width-24, height=48, pad_left=0, pad_top=0, font="12_DBLCD", size=0, halign='center', valign='middle', inverted=True, spacing=2, char_width=None, text="No Events :(")
                        display.image(page, 24, 16, no_evt_img)
                elif mode == "pride":
                    display.fill_area(page, x=0, y=0, width=24, height=64, state=1)
                    flags = [file for file in os.listdir("../flags") if not file.endswith("json")]
                    flag = random.choice(flags)
                    flag_path = os.path.join("../flags", flag)
                    info_path = os.path.join("../flags", os.path.splitext(flag)[0] + ".json")
                    print("Displaying flag:", flag)
                    sectors = _flag_to_sectors(flag_path)
                    with open(info_path, 'r') as f:
                        info = json.load(f)
                    for i, color in enumerate(sectors):
                        gcm.set_sector(i, color)
                    name_image = renderer.render_text(width=256, height=24, pad_left=0, pad_top=0, font="14S_DBLCD", size=0, halign='left', valign='middle', inverted=True, spacing=2, char_width=None, text="Pride Flags: " + info['name'])
                    display.image(page, 32, 0, name_image)
                    #info_image = renderer.render_multiline_text(width=256, height=40, pad_left=0, pad_top=0, font="10S_DBLCD", size=0, halign='left', valign='bottom', inverted=True, h_spacing=1, v_spacing=3, char_width=None, text=info['info'], auto_wrap=True, break_words=False)
                    #display.image(page, 32, 24, info_image)
                elif mode == "images":
                    images = [file for file in os.listdir("../images")]
                    image = random.choice(images)
                    image_path = os.path.join("../images", image)
                    print("Displaying image:", image)
                    display.image(page, 24, 0, image_path)
                elif mode == "db-departures":
                    station = dbi_stations[dbi_cur_station][0]
                    station_name = dbi_stations[dbi_cur_station][1]
                    trains = dbi.calc_real_times(get_trains(dbi, station))
                    trains.sort(key=dbi.time_sort)

                    header_image = renderer.render_text(width=256, height=12, pad_left=0, pad_top=0, font="12_DBLCD", size=0, halign='left', valign='top', inverted=True, spacing=1, char_width=None, text=f"Abfahrten in {station_name}")
                    display.image(page, 32, 0, header_image)
                    display.fill_area(page, x=0, y=14, width=288, height=1, state=1)
                    display.fill_area(page, x=0, y=0, width=24, height=14, state=1)
                    gcm.set_sector(0, 0xFF0000)
                    gcm.set_sector(1, 0xFF7F00)
                    gcm.set_sector(2, 0xFFFF00)
                    gcm.set_sector(3, 0x00FF00)
                    gcm.set_sector(4, 0x0000FF)
                    gcm.set_sector(5, 0x4B0082)
                    gcm.set_sector(6, 0x8F00FF)
                    
                    if trains:
                        items = [t for t in trains if 'scheduledDeparture' in t][:dbi_num_trains]
                        for i, train in enumerate(items):
                            dep_str = train['scheduledDeparture']
                            delay_str = f"+{train['delayDeparture']}" if train['delayDeparture'] >= 0 else f"{train['delayDeparture']}"
                            y_base = (i + 1) * 16
                            line = "EV" if train['train'] == "Bus EV" else "".join([l for l in train['train'] if l.isdigit()])
                            # Crudely make lines have repeatable distinct colors
                            color_index = sum(hashlib.md5(line.encode('utf8')).digest()) % len(GENERIC_PALETTE)
                            for sector in range(8):
                                gcm.set_sector(y_base // 2 + sector, GENERIC_PALETTE[color_index])
                            line_image = renderer.render_text(width=24, height=16, pad_left=0, pad_top=0, font="10S_DBLCD", size=0, halign='center', valign='middle', inverted=False, spacing=1, char_width=None, text=line)
                            display.image(page, 0, y_base, line_image)
                            dest_image = renderer.render_text(width=180, height=16, pad_left=0, pad_top=0, font="10S_DBLCD", size=0, halign='left', valign='middle', inverted=True, spacing=1, char_width=None, text=train['destination'])
                            display.image(page, 32, y_base, dest_image)
                            dep_image = renderer.render_text(width=38, height=16, pad_left=0, pad_top=0, font="10S_DBLCD", size=0, halign='left', valign='middle', inverted=True, spacing=1, char_width=None, text=dep_str)
                            display.image(page, 218, y_base, dep_image)
                            delay_image = renderer.render_text(width=30, height=16, pad_left=0, pad_top=0, font="10S_DBLCD", size=0, halign='left', valign='middle', inverted=True, spacing=1, char_width=None, text=delay_str)
                            display.image(page, 258, y_base, delay_image)
                    else:
                        no_dep_img = renderer.render_text(width=display_width-24, height=48, pad_left=0, pad_top=0, font="12_DBLCD", size=0, halign='center', valign='middle', inverted=True, spacing=2, char_width=None, text="Keine Abfahrten")
                        display.image(page, 24, 16, no_dep_img)
                    
                    dbi_cur_station += 1
                    dbi_cur_station %= len(dbi_stations)
            except KeyboardInterrupt:
                raise
            except ConnectionError:
                traceback.print_exc()
                # Force shorter delay
                skip_current_mode = True
            
            # Process any messages from the display and check for errors
            while True:
                response = display.send_tx_request()
                if response[0] == 0x15:
                    break
                display.check_error(response)
            
            display.set_page(page)
            time.sleep(0.4) # LCD update delay
            gcm.update()
            if not hackertours_boarding:
                # HT boarding stays until the flag is reset, so prevent mode switching
                mode_index += 1
            if mode_index >= len(DISPLAY_MODES):
                mode_index = 0
            mode = DISPLAY_MODES[mode_index]
            if skip_current_mode:
                # Force 1 second until next mode
                last_page_update = time.time() - (page_interval - 1)
            else:
                last_page_update = time.time()
    except KeyboardInterrupt:
        raise
    except:
        try:
            display.port.close()
        except:
            pass
        try:
            gcm.port.close()
        except:
            pass
        raise


if __name__ == "__main__":
    while True:
        try:
            main()
        except KeyboardInterrupt:
            break
        except:
            traceback.print_exc()
            print("Restarting in 10 seconds")
            time.sleep(10)
