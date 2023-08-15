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

import datetime
import dateutil.parser
import hashlib
import json
import os
import random
import time
import traceback

from c3toc import C3TOCAPI
from pretalx_api import PretalxAPI, ongoing_or_future_filter, max_duration_filter

from PIL import Image
from pprint import pprint
from pyfis.aegmis import MIS1MatrixDisplay
from pyfis.aegmis.exceptions import CommunicationError

from _config import *
from text_renderer import TextRenderer
from gcm_controller import GCMController


DISPLAY_MODES = [
    "arr_dep_eta",
    "pretalx",
    "pride"
]

TRACK_CODES = {
    "Digitalcourage": "DC",
    "Live Music": "LM",
    "Bits & Bäume": "BB",
    "DJ Set": "DJ",
    "CCC": "C",
    "Nerds der OberRheinischen Tiefebene und der xHain (N\\:O:R:T:x)": "NX",
    "Entertainment": "E",
    "Performance": "P",
    "Milliways": "MW"
}

ROOM_ABBREVIATIONS = {
    "Digitalcourage": "Dig.courage",
    "Bits & Bäume": "Bits+Bäume",
    "Hardware Hacking Village": "HW Hck Vlg",
    "Milliways Workshop Dome": "MW Dome"
}

TRACK_COLORS = {
    "DC": 0xfbc617,
    "LM": 0x9d9d9d,
    "BB": 0x81c854,
    "DJ": 0x9d9d9d,
    "C":  0xfb48c4,
    "NX": 0x003a3e,
    "E":  0x1a36cd,
    "P":  0x9d9d9d,
    "MW": 0x3cacd7
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
    mode_index = 0
    mode = DISPLAY_MODES[mode_index]
    page = 1
    secondary_page = 2
    display_width = 3 * 96
    display_height = 64
    page_interval = 20 # Page switch interval in seconds (roughly)
    
    eta_lookback = 10 # How many minutes of past train positions to consider for ETA
    eta_max_jump = 30 # Maximum ETA jump in seconds
    trackmarker_delta_arrived = 20 # "station zone" size in track units
    display_trackmarker = 34 # Physical trackmarker position of the display
    
    toc = C3TOCAPI()
    pretalx = PretalxAPI("https://pretalx.c3voc.de/camp2023/schedule/export/schedule.json")
    renderer = TextRenderer("../fonts")
    display = MIS1MatrixDisplay(CONFIG_LCD_PORT, baudrate=115200, use_rts=False, debug=False)
    gcm = GCMController(CONFIG_GCM_PORT, debug=False)
    time.sleep(3)
    gcm.set_high_current(True)
    
    tracks = toc.get_tracks()
    track_length = sorted(tracks['waypoints'].values(), key=lambda e: e['trackmarker'])[-1]['trackmarker']
    #print("Track length: {}".format(track_length))
    
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
    
    while True:
        try:
            display.delete_page(secondary_page)
            gcm.clear()
            page, secondary_page = secondary_page, page
            print("Handling mode: " + mode)
            utcnow = datetime.datetime.utcnow()
            now = datetime.datetime.now()
            
            # Handle all background calculations and data operations
            
            # c3toc API #######################################################
            # Get trains from API and calculate ETAs
            # This is run more frequently than it is displayed to keep the ETA more accurate
            train_info = toc.get_train_info(display_trackmarker, eta_lookback, eta_max_jump, trackmarker_delta_arrived, track_length)
            
            for name, info in train_info.items():
                if info['eta'] is None:
                    pass #print("No ETA available for {name}".format(name=name))
                else:
                    delta = (info['eta'] - utcnow).total_seconds()
                    #print("{name} will arrive at trackmarker {trackmarker} in {seconds} seconds, at {time} UTC".format(name=name, trackmarker=display_trackmarker, seconds=delta, time=info['eta'].strftime("%H:%M:%S")))
                #pprint(info)
            ###################################################################
            
            
            # Handle displaying the required content
            if mode == "arr_dep_eta":
                if train_info:
                    items = sorted(train_info.items(), key=lambda i: i[1]['eta'] or datetime.datetime(2070, 1, 1, 0, 0, 0))
                    for i, (name, data) in enumerate(items):
                        if data['eta'] is not None:
                            eta_str = str(round(max((data['eta'] - utcnow).total_seconds(), 0) / 60))
                        else:
                            eta_str = "???"
                        y_base = i * 16
                        line = name[:2].upper()
                        # Crudely make lines have repeatable distinct colors
                        color_index = sum(hashlib.md5(line.encode('utf8')).digest()) % len(GENERIC_PALETTE)
                        for sector in range(8):
                            gcm.set_sector(y_base // 2 + sector, GENERIC_PALETTE[color_index])
                        line_image = renderer.render_text(width=24, height=16, pad_left=0, pad_top=0, font="12_DBLCD", size=0, halign='center', valign='middle', inverted=False, spacing=1, char_width=None, text=line)
                        display.image(page, 0, y_base, line_image)
                        dest_image = renderer.render_text(width=220, height=16, pad_left=0, pad_top=0, font="12_DBLCD", size=0, halign='left', valign='middle', inverted=True, spacing=1, char_width=None, text=name)
                        display.image(page, 32, y_base, dest_image)
                        eta_image = renderer.render_text(width=28, height=16, pad_left=0, pad_top=0, font="12_DBLCD", size=0, halign='right', valign='middle', inverted=True, spacing=1, char_width=None, text=eta_str)
                        display.image(page, 260, y_base, eta_image)
                else:
                    no_dep_img = renderer.render_text(width=display_width-24, height=32, pad_left=0, pad_top=0, font="21_DBLCD", size=0, halign='center', valign='middle', inverted=True, spacing=2, char_width=None, text="No Departures")
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

                        track_code = TRACK_CODES.get(event['track'], event['track'].upper()[:2])
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
                    no_evt_img = renderer.render_text(width=display_width-24, height=32, pad_left=0, pad_top=0, font="21_DBLCD", size=0, halign='center', valign='middle', inverted=True, spacing=2, char_width=None, text="No Events")
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
                info_image = renderer.render_multiline_text(width=256, height=40, pad_left=0, pad_top=0, font="10S_DBLCD", size=0, halign='left', valign='bottom', inverted=True, h_spacing=1, v_spacing=3, char_width=None, text=info['info'], auto_wrap=True, break_words=False)
                display.image(page, 32, 24, info_image)
                    
            
            # Process any messages from the display and check for errors
            while True:
                response = display.send_tx_request()
                if response[0] == 0x15:
                    break
                display.check_error(response)
            
            display.set_page(page)
            time.sleep(0.4) # LCD update delay
            gcm.update()
            mode_index += 1
            if mode_index >= len(DISPLAY_MODES):
                mode_index = 0
            mode = DISPLAY_MODES[mode_index]
            time.sleep(page_interval)
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
