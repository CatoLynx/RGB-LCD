"""
Copyright (C) 2020-2023 Julian Metzler

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

import json
import os

from PIL import Image, ImageOps


class TextRenderer:
    CHAR_MAP = {
        
    }
    
    def __init__(self, font_dir):
        self.font_dir = font_dir
        self.img_mode = 'L'
        self.img_bg = 255
        self.img_fg = 0
    
    def get_font_dir(self, font, size):
        return os.path.join(self.font_dir, font, "size_{}".format(size))
    
    def get_char_filename(self, font, size, code):
        return os.path.join(self.get_font_dir(font, size), "{:x}.bmp".format(code))
    
    def get_char_code(self, char):
        if char in self.CHAR_MAP:
            code = self.CHAR_MAP[char]
        else:
            code = ord(char)
        return code
    
    def get_font_metadata(self, font, size):
        metadata_file = os.path.join(self.get_font_dir(font, size), "metadata.json")
        with open(metadata_file, 'r') as f:
            metadata = json.load(f)
        return metadata
    
    def get_text_size(self, font, size, text, h_spacing, v_spacing):
        metadata = self.get_font_metadata(font, size)
        char_sizes = metadata['char_sizes']
        width = 0
        height = 0
        lines = text.splitlines()
        for line_idx, line in enumerate(lines):
            max_height = 0
            for char_idx, char in enumerate(line):
                key = str(self.get_char_code(char))
                if key in char_sizes:
                    cw, ch = char_sizes[key]
                    width += cw
                    if ch > max_height:
                        max_height = ch
                if char_idx < len(line) - 1:
                    width += h_spacing
            height += max_height
            if line_idx < len(lines) - 1:
                height += v_spacing
        return width, height
    
    def wrap_text(self, font, size, width, text, h_spacing, break_words):
        line_width, line_height = self.get_text_size(font, size, text, h_spacing, 0)
        if line_width <= width:
            #print("all good!")
            return [text]
        
        # We need to drop some words from the end
        lines = []
        words_dropped = 0
        words = text.split(" ")
        #print("=" * 40)
        #print("words:", words)
        while True:
            words_dropped += 1
            partial_line = " ".join(words[:-words_dropped])
            #print("partial_line:", partial_line)
            if not partial_line:
                # We dropped all words, this means even just one word is already too wide.
                # So we need to start breaking in the middle of a word if desired
                if break_words:
                    # Yep, break in the middle of a word
                    chars_dropped = 0
                    word = words[0]
                    empty = False
                    while True:
                        chars_dropped += 1
                        partial_word = word[:-chars_dropped]
                        #print("partial_word:", partial_word)
                        if not partial_word:
                            # Even a single character is too wide. Just give up at this point.
                            #print("char break fail")
                            if not word:
                                # The "word" is just an empty string
                                empty = True
                                partial_word = ""
                                word_remainder = ""
                            else:
                                partial_word = word[0]
                                word_remainder = word[1:]
                            break
                        line_width, line_height = self.get_text_size(font, size, partial_word, h_spacing, 0)
                        if line_width <= width:
                            word_remainder = word[-chars_dropped:]
                            break
                    lines.append(partial_word)
                    if empty:
                        remainder = word_remainder + " ".join(words[1:])
                    else:
                        remainder = word_remainder + " " + " ".join(words[1:])
                    #print("recursing, remainder:", remainder)
                    lines.extend(self.wrap_text(font, size, width, remainder, h_spacing, break_words))
                    break
                else:
                    # Nope, just accept cutting off the word
                    lines.append(words[0])
                    remainder = " ".join(words[1:])
                    #print("word break fail")
                    #print("recursing, remainder:", remainder)
                    lines.extend(self.wrap_text(font, size, width, remainder, h_spacing, break_words))
                    break
            line_width, line_height = self.get_text_size(font, size, partial_line, h_spacing, 0)
            if line_width <= width:
                remainder = " ".join(words[-words_dropped:])
                #print("recursing, remainder:", remainder)
                lines.append(partial_line)
                lines.extend(self.wrap_text(font, size, width, remainder, h_spacing, break_words))
                break
        return lines
    
    def render_character(self, img, x, y, force_width, filename):
        try:
            char_img = Image.open(filename)
        except FileNotFoundError:
            return (False, x, y)
        char_width, char_height = char_img.size
        if force_width is not None:
            if force_width < char_width:
                char_img = char_img.crop((0, 0, force_width, char_height))
            img.paste(char_img, (x, y))
            return (True, x+force_width, y)
        else:
            img.paste(char_img, (x, y))
            return (True, x+char_width, y)

    def render_text(self, width, height, pad_left, pad_top, font, size, halign, valign, inverted, spacing, char_width, text):
        text_img = Image.new(self.img_mode, (width, height), color=self.img_bg)
        x = pad_left
        y = pad_top
        for char in text:
            code = self.get_char_code(char)
            success, x, y = self.render_character(text_img, x, y, char_width, self.get_char_filename(font, size, code))
            x += spacing
        if halign in ('center', 'right') or valign in ('middle', 'bottom'):
            bbox = ImageOps.invert(text_img).getbbox()
            if bbox is not None:
                cropped = text_img.crop(bbox)
                cropped_width = cropped.size[0]
                cropped_height = cropped.size[1]
                text_img = Image.new(self.img_mode, (width, height), color=self.img_bg)
                if halign == 'center':
                    x_offset = (width - cropped_width) // 2
                elif halign == 'right':
                    x_offset = width - cropped_width
                else:
                    x_offset = 0
                if valign == 'middle':
                    y_offset = (height - cropped_height) // 2
                elif valign == 'bottom':
                    y_offset = height - cropped_height
                else:
                    y_offset = 0
                text_img.paste(cropped, (x_offset, y_offset))
        if inverted:
            text_img = ImageOps.invert(text_img)
        return text_img

    def render_multiline_text(self, width, height, pad_left, pad_top, font, size, halign, valign, inverted, h_spacing, v_spacing, char_width, text, auto_wrap=False, break_words=True):
        metadata = self.get_font_metadata(font, size)
        text_img = Image.new(self.img_mode, (width, height), color=self.img_bg)
        lines = text.splitlines()
        y = pad_top
        for line in lines:
            line_width, line_height = self.get_text_size(font, size, line, h_spacing, v_spacing)
            
            if auto_wrap:
                render_lines = self.wrap_text(font, size, width, line, h_spacing, break_words)
            else:
                render_lines = [line]
            
            for render_line in render_lines:
                render_line = render_line.strip()
                if render_line == "":
                    render_line = " "
                r_line_width, r_line_height = self.get_text_size(font, size, render_line, h_spacing, v_spacing)
                line_img = Image.new(self.img_mode, (r_line_width, r_line_height), color=self.img_bg)
                x = 0
                for char in render_line:
                    code = self.get_char_code(char)
                    success, x, y_out = self.render_character(line_img, x, 0, char_width, self.get_char_filename(font, size, code))
                    x += h_spacing
                if halign == 'center':
                    x_offset = (width - r_line_width) // 2
                elif halign == 'right':
                    x_offset = width - r_line_width - 1
                else:
                    x_offset = 0
                text_img.paste(line_img, (x_offset + pad_left, y))
                y += r_line_height
                y += v_spacing
                x = pad_left
        if halign in ('center', 'right') or valign in ('middle', 'bottom'):
            bbox = ImageOps.invert(text_img).getbbox()
            if bbox is not None:
                cropped = text_img.crop(bbox)
                cropped_width = cropped.size[0]
                cropped_height = cropped.size[1]
                text_img = Image.new(self.img_mode, (width, height), color=self.img_bg)
                if halign == 'center':
                    x_offset = (width - cropped_width) // 2
                elif halign == 'right':
                    x_offset = width - cropped_width
                else:
                    x_offset = 0
                if valign == 'middle':
                    y_offset = (height - cropped_height) // 2
                elif valign == 'bottom':
                    y_offset = height - cropped_height
                else:
                    y_offset = 0
                text_img.paste(cropped, (x_offset, y_offset))
        if inverted:
            text_img = ImageOps.invert(text_img)
        return text_img
