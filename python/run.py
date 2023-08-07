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
import json
import os
import random
import time

from c3toc import C3TOCAPI
from pretalx_api import PretalxAPI

from PIL import Image
from pprint import pprint
from pyfis.aegmis import MIS1MatrixDisplay
from pyfis.aegmis.exceptions import CommunicationError

from _config import *
from text_renderer import TextRenderer
from gcm_controller import GCMController


DISPLAY_MODES = [
    #"arr_dep_eta",
    #"pretalx",
    "pride"
]


# Pretalx event filters
def _max_duration(event, hours, minutes):
    _time = datetime.datetime.strptime(event['duration'], "%H:%M").time()
    duration = datetime.timedelta(hours=_time.hour, minutes=_time.minute)
    return (duration <= datetime.timedelta(hours=hours, minutes=minutes))

def _ongoing_or_future(event):
    now = datetime.datetime.now()
    _time = datetime.datetime.strptime(event['duration'], "%H:%M").time()
    duration = datetime.timedelta(hours=_time.hour, minutes=_time.minute)
    start = dateutil.parser.isoparse(event['date']).replace(tzinfo=None)
    end = start + duration
    return (now < end)

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
    page_interval = 10
    
    eta_lookback = 10 # How many minutes of past train positions to consider for ETA
    eta_max_jump = 30 # Maximum ETA jump in seconds
    trackmarker_delta_arrived = 20 # "station zone" size in track units
    display_trackmarker = 163 # Physical trackmarker position of the display
    
    toc = C3TOCAPI()
    pretalx = PretalxAPI("https://pretalx.c3voc.de/camp2023/schedule/export/schedule.json")
    renderer = TextRenderer("../fonts")
    #display = MIS1MatrixDisplay(CONFIG_LCD_PORT, baudrate=115200, use_rts=False, debug=False)
    #gcm = GCMController(CONFIG_GCM_PORT)
    
    tracks = toc.get_tracks()
    track_length = sorted(tracks['waypoints'].values(), key=lambda e: e['trackmarker'])[-1]['trackmarker']
    print("Track length: {}".format(track_length))
    
    """try:
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
    display.become_master()"""
    
    while True:
        try:
            #display.delete_page(secondary_page)
            #gcm.clear()
            page, secondary_page = secondary_page, page
            print("Handling mode: " + mode)
            utcnow = datetime.datetime.utcnow()
            
            # Handle all background calculations and data operations
            
            # c3toc API #######################################################
            # Get trains from API and calculate ETAs
            # This is run more frequently than it is displayed to keep the ETA more accurate
            """
            train_info = toc.get_train_info(display_trackmarker, eta_lookback, eta_max_jump, trackmarker_delta_arrived, track_length)
            
            for name, info in train_info.items():
                if info['eta'] is None:
                    print("No ETA available for {name}".format(name=name))
                else:
                    delta = (info['eta'] - utcnow).total_seconds()
                    print("{name} will arrive at trackmarker {trackmarker} in {seconds} seconds, at {time} UTC".format(name=name, trackmarker=display_trackmarker, seconds=delta, time=info['eta'].strftime("%H:%M:%S")))
                pprint(info)
            """
            ###################################################################
            
            
            # Handle displaying the required content
            if mode == "arr_dep_eta":
                pass
                """
                if train_info:
                    items = sorted(train_info.items(), key=lambda i: i[1]['eta'] or datetime.datetime(2070, 1, 1, 0, 0, 0))
                    for i, (name, data) in enumerate(items):
                        if data['eta'] is not None:
                            eta_str = str(round(max((data['eta'] - utcnow).total_seconds(), 0) / 60))
                        else:
                            eta_str = "???"
                        y_base = i * 16
                        for sector in range(8):
                            gcm.set_sector(y_base // 2 + sector, 0xffffff)
                        line_image = renderer.render_text(width=28, height=16, pad_left=0, pad_top=0, font="12_DBLCD", size=0, halign='center', valign='middle', inverted=False, spacing=1, char_width=None, text=name[:2].upper())
                        display.image(page, 0, y_base, line_image)
                        dest_image = renderer.render_text(width=130, height=16, pad_left=0, pad_top=0, font="12_DBLCD", size=0, halign='left', valign='middle', inverted=True, spacing=1, char_width=None, text=name)
                        display.image(page, 32, y_base, dest_image)
                        eta_image = renderer.render_text(width=28, height=16, pad_left=0, pad_top=0, font="12_DBLCD", size=0, halign='right', valign='middle', inverted=True, spacing=1, char_width=None, text=eta_str)
                        display.image(page, 260, y_base, eta_image)
                else:
                    no_dep_img = renderer.render_text(width=display_width, height=32, pad_left=0, pad_top=0, font="21_DBLCD", size=0, halign='center', valign='middle', inverted=True, spacing=2, char_width=None, text="Kein Zugverkehr")
                    display.image(page, 0, 16, no_dep_img)
                """
            elif mode == "pretalx":
                # Get schedule from pretalx
                events = pretalx.get_all_events()
                
                # Filter out all events longer then 2 hours
                events = filter(lambda event: _max_duration(event, 2, 0), events)
                
                # Filter out all events that are finished
                events = filter(lambda event: _ongoing_or_future(event), events)
                
                events = list(events)
                pprint(["{date} {duration} {title}".format(**event) for event in events[:10]])
            elif mode == "pride":
                display.fill_area(page, x=0, y=0, width=28, height=64, state=1)
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
                name_image = renderer.render_text(width=256, height=16, pad_left=0, pad_top=0, font="17_DBLCD", size=0, halign='left', valign='middle', inverted=True, spacing=2, char_width=None, text=info['name'])
                display.image(page, 32, 0, name_image)
                info_image = renderer.render_multiline_text(width=256, height=44, pad_left=0, pad_top=0, font="10S_DBLCD", size=0, halign='left', valign='bottom', inverted=True, h_spacing=1, v_spacing=3, char_width=None, text=info['info'], auto_wrap=True, break_words=False)
                display.image(page, 32, 20, info_image)
                    
            
            # Process any messages from the display and check for errors
            """
            while True:
                response = display.send_tx_request()
                if response[0] == 0x15:
                    break
                display.check_error(response)
            """
            
            #display.set_page(page)
            #gcm.update()
            mode_index += 1
            if mode_index >= len(DISPLAY_MODES):
                mode_index = 0
            mode = DISPLAY_MODES[mode_index]
            time.sleep(page_interval)
        except KeyboardInterrupt:
            break


if __name__ == "__main__":
    main()
