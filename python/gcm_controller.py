"""
Copyright (C) 2021-2023 Julian Metzler

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
import time


class CommunicationError(IOError):
    pass


class GCMController:
    ACT_SET_SEC = 0xA0  # Set sector colors

    def __init__(self, port, debug=False, exclusive=True, baudrate=9600, num_sectors=32):
        self.debug = debug
        self.num_sectors = num_sectors
        self.port = serial.Serial(port, baudrate=baudrate, timeout=2.0, exclusive=exclusive)
        self.clear()
    
    def clear(self):
        self.sector_colors = [0x000000] * self.num_sectors
    
    def set_sector(self, sector, color):
        self.sector_colors[sector] = color

    def debug_message(self, message):
        """
        Turn a message into a readable form
        """
        result = ""
        for byte in message:
            if byte in range(0, 32) or byte >= 127:
                result += "<{:02X}>".format(byte)
            else:
                result += chr(byte)
            result += " "
        return result

    def read_response(self):
        """
        Read the response from the addressed station
        """
        response = self.port.read(1)
        if not response:
            raise CommunicationError("Timeout waiting for response")
        if self.debug:
            print("RX: " + self.debug_message(response))
        return response

    def send_command(self, action, payload):
        data = [0xFF, action, len(payload)] + payload
        print("TX: " + self.debug_message(data))
        self.port.write(bytearray(data))

    def send_command_with_response(self, action, payload):
        """
        Send a command and retrieve the response data
        """
        self.send_command(action, payload)
        return self.read_response()

    def update(self):
        data = []
        for sector in self.sector_colors:
            data.append(sector & 0xFF)
            data.append((sector >> 8) & 0xFF)
            data.append((sector >> 16) & 0xFF)
            data.append(0x00) # dummy byte to facilitate writing 4x uint8_t into a uint32_t on the target
        return self.send_command_with_response(self.ACT_SET_SEC, data)
