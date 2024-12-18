"""
Copyright (C) 2024 Julian Metzler

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

from deutschebahn import DBInfoscreen
from deutschebahn.utils import timeout

from PIL import Image
from pprint import pprint
from pyfis.aegmis import MIS1MatrixDisplay
from pyfis.aegmis.exceptions import CommunicationError

from _config import *
from text_renderer import TextRenderer
from gcm_controller import GCMController


DISPLAY_MODES = [
    "db-departures",
    "images",
]

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


def main():
    try:
        mode_index = 0
        mode = DISPLAY_MODES[mode_index]
        page = 1
        secondary_page = 2
        display_width = 3 * 96
        display_height = 64
        page_interval = 10 # Page switch interval in seconds (roughly)
        
        dbi_stations = [("FECH", "Nidderau-Eichen"), ("FHWD", "Nidderau")]
        dbi_num_trains = 3
        dbi_cur_station = 0
        
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
        while True:
            utcnow = datetime.datetime.utcnow()
            now = datetime.datetime.now()
            
            if (time.time() - last_page_update) < page_interval:
                time.sleep(0.1)
                continue
            
            display.delete_page(secondary_page)
            gcm.clear()
            page, secondary_page = secondary_page, page
            print("Handling mode: " + mode)
            
            # Handle displaying the required content
            if mode == "images":
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
                        line_image = renderer.render_text(width=24, height=16, pad_left=0, pad_top=0, font="12_DBLCD", size=0, halign='center', valign='middle', inverted=False, spacing=1, char_width=None, text=line)
                        display.image(page, 0, y_base, line_image)
                        dest_image = renderer.render_text(width=170, height=16, pad_left=0, pad_top=0, font="12_DBLCD", size=0, halign='left', valign='middle', inverted=True, spacing=1, char_width=None, text=train['destination'])
                        display.image(page, 32, y_base, dest_image)
                        dep_image = renderer.render_text(width=48, height=16, pad_left=0, pad_top=0, font="12_DBLCD", size=0, halign='left', valign='middle', inverted=True, spacing=1, char_width=None, text=dep_str)
                        display.image(page, 208, y_base, dep_image)
                        delay_image = renderer.render_text(width=30, height=16, pad_left=0, pad_top=0, font="12_DBLCD", size=0, halign='left', valign='middle', inverted=True, spacing=1, char_width=None, text=delay_str)
                        display.image(page, 258, y_base, delay_image)
                else:
                    no_dep_img = renderer.render_text(width=display_width-24, height=48, pad_left=0, pad_top=0, font="12_DBLCD", size=0, halign='center', valign='middle', inverted=True, spacing=2, char_width=None, text="Keine Abfahrten")
                    display.image(page, 24, 16, no_dep_img)
                
                dbi_cur_station += 1
                dbi_cur_station %= len(dbi_stations)
            
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
