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
import time

from c3toc import C3TOCAPI
from pprint import pprint
#from pyfis.aegmis import MIS1MatrixDisplay

from _config import *
from text_renderer import TextRenderer
from rgb_controller import RGBController


DISPLAY_MODES = [
    "arr_dep_eta",
    "map",
    "pride"
]


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
    
    api = C3TOCAPI()
    renderer = TextRenderer("../fonts")
    #display = MIS1MatrixDisplay(CONFIG_LCD_PORT, baudrate=115200, debug=False)
    #rgb = RGBController(CONFIG_RGB_PORT)
    
    tracks = api.get_tracks()
    track_length = sorted(tracks['waypoints'].values(), key=lambda e: e['trackmarker'])[-1]['trackmarker']
    print("Track length: {}".format(track_length))
    
    #display.reset()
    #time.sleep(1)
    """display.set_config(
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
    )"""
    #display.become_master()
    
    while True:
        try:
            #display.delete_page(secondary_page)
            #rgb.clear()
            page, secondary_page = secondary_page, page
            print("Handling mode: " + mode)
            utcnow = datetime.datetime.utcnow()
            
            # Handle all background calculations and data operations
            
            # Get trains from API and calculate ETAs
            train_info = api.get_train_info(display_trackmarker, eta_lookback, eta_max_jump, trackmarker_delta_arrived, track_length)
            
            for name, info in train_info.items():
                if info['eta'] is None:
                    print("No ETA available for {name}".format(name=name))
                else:
                    delta = (info['eta'] - utcnow).total_seconds()
                    print("{name} will arrive at trackmarker {trackmarker} in {seconds} seconds, at {time} UTC".format(name=name, trackmarker=display_trackmarker, seconds=delta, time=info['eta'].strftime("%H:%M:%S")))
                pprint(info)
            
            # Handle displaying the required content
            if mode == "arr_dep_eta":
                if train_info:
                    pass
                else:
                    no_dep_img = renderer.render_text(width=display_width, height=32, pad_left=0, pad_top=0, font="21_DBLCD", size=0, halign='center', valign='middle', inverted=True, spacing=2, char_width=None, text="Kein Zugverkehr")
                    #display.image(page, 0, 16, no_dep_img)
                    
            
            # Process any messages from the display and check for errors
            """while True:
                response = display.send_tx_request()
                if response[0] == 0x15:
                    break
                display.check_error(response)"""
            
            #display.set_page(page)
            #rgb.update()
            mode_index += 1
            if mode_index >= len(DISPLAY_MODES):
                mode_index = 0
            mode = DISPLAY_MODES[mode_index]
            time.sleep(page_interval)
        except KeyboardInterrupt:
            break


if __name__ == "__main__":
    main()
