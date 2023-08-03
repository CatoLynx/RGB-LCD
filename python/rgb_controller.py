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

import serial


class RGBController:
    def __init__(self, port, num_sectors=32):
        self.num_sectors = num_sectors
        self.port = serial.Serial(port, baudrate=115200)
        self.clear()
    
    def clear(self):
        self.sector_colors = [0x000000] * num_sectors
    
    def set_sector(self, sector, color):
        self.sector_colors[sector] = color
    
    def update(self):
        data = [0xFF, self.num_sectors * 3] # Start + length (max. 85 sectors)
        for sector in self.sector_colors:
            data.append((sector >> 16) & 0xFF)
            data.append((sector >> 8) & 0xFF)
            data.append(sector & 0xFF)
        self.port.write(data)
