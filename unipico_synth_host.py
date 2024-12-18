#########################################################################
# Unit-MIDI synthesizer with Raspberry Pi PICO (USB HOST)
# FUNCTION:
#   MIDI-IN  player via USB MIDI (as a USB Host or a USB Device)
#   MIDI-OUT via UART unit1 (2nd UART port)
# HARDWARE:
#   CONTROLER  : Raspberry Pi PICO or PICO2.
#                On board USB works as USB-MIDI device.
#                GPIO USB works as USB-MIDI host via OTG cable.
#   SYNTHESIZER: Unit-SYNTH or Unit-MIDI (UART unit0)
#                Unit-MIDI for play and MIDI-OUT (UART unit1: optional)
#   KEYBOARD   : Card.KB for parameter setting.
#   OLED       : SSD1306 (128x64) as a display.
#
# PROGRAM: circuitpython (V9.2.1)
#   pico_synth_usb.py (USB device mode program)
#     1.0.0: 12/10/2024
#     1.0.1: 12/11/2024
#            Pitch bend and modulation wheel are available.
#     1.0.2: 12/12/2024
#            Select load MIDI settings file in only existings.
#   pico_synth_host.py (USB host and device modes program)
#     1.0.0: 12/16/2024
#     1.0.1: 12/17/2024
#            Parameter input by using numeric keys, [BS] and [ENTER].
#            Auto detecte USB Host mode or Device mode.
#            2nd UART is available as MIDI-OUT only.
#     1.0.2: 12/18/2024
#            MIDI-IN  selector: USB or UART1.
#            MIDI-OUT selector: UART0 or UART1 or both
#            Resend synthesizer and effector settings to the MIDI-OUT.
#########################################################################
# COMMANDS for SYNTHESIZER PARAMETER SETTING DISPLAY:
#  CH/ch: change MIDI channel to edit
#  P /p : change instrument program number
#  RP/rp: change reverb program number
#  RL/rl: change reverb level
#  RF/rf: change reverb feedback
#  CP/cp: change chorus program number
#  CL/cl: change chorus level
#  CF/cf: change chorus feedback
#  VR/vr: change vibrate rate
#  VD/vd: change vibrate depth
#  VL/vl: change vibrate delay
#  L /l : change load file number of MIDI settings
#  S /s : change save file number of MIDI settings
#  LF/lf: load MIDI settings from the file number
#  SF/Sf: save MIDI settings to the file number
# COMMANDS for CONFIGURATION DISPLAY:
#  M /m : MIDI-IN selector (USB or UART1)
#  UA/ua: UART0 MIDI-OUT selector (OUT or OFF)
#  UT/ut: UART1 MIDI-OUT selector (OUT or OFF)
# COMMANDS common
#  SPACE: Play a test melody
#  fn+SP: Resed synthesizer and effctor settings and play test
#  ESC  : switch ignore MIDI-IN mode
#  TAB  : change the display mode
#
# VALUE CONTROLES:
#     [LEFT ]: decrement value - 1
#  fn+[LEFT ]: decrement value -10
#     [RIGHT]: increment value + 1
#  fn+[RIGHT]: increment value +10
#  [0]-[9]   : enter exact numeric value
#  [BS]      : delete the latest digit from the numeric value entered.
#  [ENTER]   : confirm a numeric value
#     [ UP  ]: master volume + 1
#  fn+[ UP  ]: master volume +10
#     [DOWN ]: master volume - 1
#  fn+[DOWN ]: master volume -10
#########################################################################
from board import *
import digitalio
from busio import UART			# for UART MIDI
from busio import I2C			# for I2C
from time import sleep
import os, re
import json

import usb_midi					# for USB MIDI
import adafruit_midi
from adafruit_midi.control_change import ControlChange
from adafruit_midi.note_off import NoteOff
from adafruit_midi.note_on import NoteOn
from adafruit_midi.pitch_bend import PitchBend
from adafruit_midi.program_change import ProgramChange

import board
import usb_host					# for USB HOST
import usb.core
from adafruit_usb_host_midi.adafruit_usb_host_midi import MIDI	# for USB MIDI HOST
import supervisor

import adafruit_ssd1306			# for SSD1306 OLED Display

#####################
### Unit-MIDI class
#####################
class MIDIUnit_class:
    # Constructor
    #   uart_unit: PICO UART unit number 0 or 1
    #   port     : A tuple of (Tx, Rx)
    #              This argument is NOT USED, to keep compatibility with M5Stack CORE2.
    def __init__(self, uart_unit=0, port0=(GP0, GP1), port1=(GP4, GP5)):
        # UART MIDI (MIDI-OUT)
        self._uart0 = UART(tx=port0[0], rx=port0[1], baudrate=31250)
        self._uart1 = None
        if port1 is not None:
            self._uart1 = UART(tx=port1[0], rx=port1[1], baudrate=31250)
            
        # USB MIDI device
        print('USB MIDI:', usb_midi.ports)
#        self._usb_midi = adafruit_midi.MIDI(midi_in=usb_midi.ports[0], in_channel=0, midi_out=usb_midi.ports[1], out_channel=0)
        self._usb_midi = adafruit_midi.MIDI(midi_in=usb_midi.ports[0], midi_out=usb_midi.ports[1], out_channel=0)
#        self._usb_midi = adafruit_midi.MIDI(midi_in=usb_midi.ports[0], midi_out=usb_midi.ports[1], out_channel=0)
#        self._usb_midi = adafruit_midi.MIDI(midi_out=usb_midi.ports[1], out_channel=0)

        # USB MIDI host
        # USB DEVICE   : Vender ID : Product ID
        # KORG nanoKEY2: 0x944       0x115
        self.USB_DEV_nanoKEY2 = {'VenderID': 0x944, 'ProductID': 0x115}
        self._init = True
        self._raw_midi_host  = None
        self._usb_midi_host  = None
        self._usb_host_mode  = True
        self._midi_in_usb    = True			# True: MIDI-IN via USB, False: via UART1
        self._midi_out_uart0 = True			# MIDI-OUT to UART0 or not
        self._midi_out_uart1 = True			# MIDI-OUT to UART1 or not
        
        print('USB PORTS:', usb_midi.ports)
        display.fill(0)
        display.text('USB PORTS:' + str(usb_midi.ports), 0, 0, 1)
        display.show()
        
#        h = usb_host.Port(board.USB_HOST_DP, board.USB_HOST_DM)
        h = usb_host.Port(board.GP26, board.GP27)		# PIN:31, 32, GND:33

        if supervisor.runtime.usb_connected:
            print("USB<host>!")
        else:
            print("!USB<host>")

        # Initialize MIDI settings
        self.master_volume = 127
        self.channel_reverb = []
        for ch in list(range(16)):
            self.channel_reverb.append({'prog'})

        self.midi_in_file_number = 0
        self.midi_in_settings = []                        # MIDI IN settings for each channel, see setup()
                                                          # Each channel has following data structure
                                                          #     {'program':0, 'gmbank':0, 'reverb':[0,0,0], 'chorus':[0,0,0,0], 'vibrate':[0,0,0]}
                                                          #     {'program':PROGRAM, 'gmbank':GM BANK, 'reverb':[PROGRAM,LEVEL,FEEDBACK], 'chorus':[PROGRAM,LEVEL,FEEDBACK,DELAY], 'vibrate':[RATE,DEPTH,DELAY]}
        for ch in list(range(16)):
            self.midi_in_settings.append({'program':ch, 'gmbank':0, 'reverb':[0,0,0], 'chorus':[0,0,0,0], 'vibrate':[0,0,0]})
            self.set_pitch_bend_range(ch, 5)

        self.get_midiset_list()

    # Is host mode or not
    def as_host(self):
        return self._usb_host_mode
    
    # Set/Get MIDI-IN via USB:True or UART (unit1):False
    def midi_in_via_usb(self, usb=None):
        if usb is not None:
            self._midi_in_usb = usb
            
        return self._midi_in_usb

    # Set/Get MIDI-OUT to UARTx (unit0 or 1)
    def midi_out_to(self, uart_unit, flg=None):
        if uart_unit == 0:
            if flg is not None:
                self._midi_out_uart0 = flg
            return self._midi_out_uart0
        elif uart_unit == 1:
            if flg is not None:
                self._midi_out_uart1 = flg
            return self._midi_out_uart1
                    
        return False
    
    # Look for USB MIDI device
    def look_for_usb_midi_device(self):
        self._raw_midi_host = None
        self._usb_midi_host = None

        if self._init:
            print("Looking for midi device")

        led_flush = False
        try_count = 10
        while self._raw_midi_host is None and try_count > 0:
            try_count = try_count - 1
            led_flush = not led_flush
            pico_led.value = led_flush
            
            devices_found = usb.core.find(find_all=True)

            if self._init:
                print('USB LIST:', devices_found)
                display.text('USB LIST: ' + str(devices_found), 0, 9, 1)
                display.show()

            for device in devices_found:
                if self._init:
                    print('DEVICE: ', device)
                
                try:
                    if self._init:
                        print("Found", hex(device.idVendor), hex(device.idProduct))
                        display.text('Found: ' + str(hex(device.idVendor)) + str(hex(device.idProduct)), 0, 18, 1)
                        display.show()
#                        self.set_note_on(0, 72, 127)
#                        sleep(1.0)
#                        self.set_note_off(0, 72)

                    self._raw_midi_host = MIDI(device)
                    if self._init:
                        print("CONNECT MIDI")
                        display.text('CONNECT MIDI', 0, 45, 1)
                        display.show()

                except ValueError:
                    self._raw_midi_host = None
                    display.text('EXCEPTION', 0, 45, 1)
                    display.show()
                    continue

        if self._init:
            if self._raw_midi_host is None:
                print('NOT Found USB MIDI device.')
                display.text('NO MIDI device.', 0, 45, 1)
            else:
                print('Found USB MIDI device.')

            display.show()

        self._init = False

        if self._raw_midi_host is None:
            self._usb_midi_host = None
            self._usb_host_mode = False
            pico_led.value = False
            return None
        
        self._usb_midi_host = adafruit_midi.MIDI(midi_in=self._raw_midi_host)  
#        self._usb_midi_host = adafruit_midi.MIDI(midi_in=self._raw_midi_host, in_channel=0)  
#        self._usb_midi = adafruit_midi.MIDI(midi_in=usb_midi.ports[0], in_channel=0, midi_out=usb_midi.ports[1], out_channel=0)
        pico_led.value = True
        return self._usb_midi_host

    def usb_midi_host(self):
        return self._usb_midi_host

    # Get instrument name
    def get_instrument_name(self, program, gmbank=0):
        try:
            with open('SYNTH/MIDI_FILE/GM0.TXT', 'r') as f:
                prg = -1
                for instrument in f:
                    prg = prg + 1
                    if prg == program:
                        return instrument

        except Exception as e:
            application.show_message('GM LIST:' + e)
            for cnt in list(range(5)):
                pico_led.value = False
                sleep(0.25)
                pico_led.value = True
                sleep(0.5)

            display.clear()
            application.show_midi_channel(True, True)

        return '???'

    # Get MIDISETxxx.json files list
    def get_midiset_list(self, num=None):
        self.midiset_list = os.listdir('SYNTH/MIDI_UNIT/')
        if len(self.midiset_list):
            self.midiset_list.sort()
            do_check = True
            while do_check:
                do_check = False
                for i in list(range(len(self.midiset_list))):
                    if re.match('^MIDISET[0-9][0-9][0-9].json$', self.midiset_list[i]) is None:
                        self.midiset_list.pop(i)
                        do_check = True
                        break                        

        print('MIDI SET FILES: ', self.midiset_list)
        if len(self.midiset_list) > 0:
            if num is None:
                num = -1
                
            self.midiset_list_number = 0
            for i in list(range(len(self.midiset_list))):
                self.midiset_list[i] = int(self.midiset_list[i][7:10])
                if num == self.midiset_list[i]:
                    self.midiset_list_number = i

            print('MIDI SET FILE NUMERS: ', self.midiset_list)

        else:
            self.midiset_list_number = -1

    # Set/Get file number to load a MIDI-IN settings
    def midi_file_number_exist(self, num=None):
        if self.midiset_list_number < 0:
            return (self.midiset_list_number, self.midiset_list_number)

        if num is not None:
            self.midiset_list_number = num % len(self.midiset_list)

        self.midi_file_number(self.midiset_list[self.midiset_list_number])
        return (self.midiset_list_number, self.midiset_list[self.midiset_list_number])

    # Set/Get file number to save a MIDI-IN settings
    def midi_file_number(self, num=None):
        if num is not None:
            self.midi_in_file_number = num % 1000
        
        if self.midi_in_file_number in self.midiset_list:
            self.midiset_list_number = self.midiset_list.index(self.midi_in_file_number)
            
        return self.midi_in_file_number

    # Load MIDI settings
    def load_midi_settings(self, num=None):
        if num is None:
            num = self.midi_file_number_exist()[1]

        if num < 0:
            return
        
        print('LOAD: SYNTH/MIDI_UNIT/MIDISET{:03d}.json'.format(num))
        try:
            with open('SYNTH/MIDI_UNIT/MIDISET{:03d}.json'.format(num), 'r') as f:
                self.midi_in_settings = json.load(f)
                print(self.midi_in_settings)

        except Exception as e:
            application.show_message('ERROR:' + str(e))
            for cnt in list(range(5)):
                pico_led.value = False
                sleep(0.25)
                pico_led.value = True
                sleep(0.5)

            display.clear()
            application.show_midi_channel(True, True)

    # Save MIDI settings
    def save_midi_settings(self, num=None):
        if num is None:
            num = self.midi_file_number()

        print('SAVE: /SYNTH/MIDI_UNIT/MIDISET{:03d}.json'.format(num))
        try:
            with open('SYNTH/MIDI_UNIT/MIDISET{:03d}.json'.format(num), 'w') as f:
                print('JSON DUMP:', self.midi_in_settings)
                json.dump(self.midi_in_settings, f)
                print('SAVED.')
                self.get_midiset_list(num)
        
        except Exception as e:
            application.show_message('ERROR:' + str(e))
            for cnt in list(range(5)):
                pico_led.value = False
                sleep(0.25)
                pico_led.value = True
                sleep(0.5)

            display.clear()
            application.show_midi_channel(True, True)

    # MIDI-IN via USB-MIDI
    def midi_in(self):
        # MIDI-IN via USB
        if self._midi_in_usb:
            try:
                if self._usb_host_mode:
                    midi_msg = self._usb_midi_host.receive()
                else:
                    midi_msg = self._usb_midi.receive()

            except:
                print('CHANGE TO DEVICE MODE')
                self._usb_host_mode = False
                midi_msg = self._usb_midi.receive()
                display.clear()
                application.show_midi_channel(True, True)
                
            return midi_msg
                    
        # MIDI-IN via UART (unit1)
        elif self._uart1 is not None:
            try:
                midi_msg = self._uart1.read(1)
#                print('UART2:', midi_msg)
                return midi_msg

            except Exception as e:
                print('EXCEPTION: UART MIDI-IN:', e)
                return None
            
        return None

    def midi_send(self, midi_msg):
        self._usb_midi.send(NoteOn(note_key, velosity))

    # MIDI-OUT to UART MIDI
    def midi_out(self, midi_msg):
        if self._midi_out_uart0:
            self._uart0.write(midi_msg)

        if self._midi_out_uart1 and self._uart1 is not None:
            self._uart1.write(midi_msg)

    # Receive MIDI via USB MIDI host, then send it to UART and USB MIDI device
    def midi_in_out(self):
        midi_msg = self.midi_in()
        if not midi_msg is None:
            self.midi_out(midi_msg)
#            self.midi_send(midi_msg)
    
    def set_master_volume(self, vol=127):
        midi_msg = bytearray([0xF0, 0x7F, 0x7F, 0x04, 0x01, 0, vol & 0x7f, 0xF7])
        self.midi_out(midi_msg)

    def set_instrument(self, channel=0, prog=0, gmbank=0):
        midi_msg = bytearray([0xC0 + channel, prog])
        self.midi_out(midi_msg)

    def set_note_on(self, channel, note_key, velosity):
        midi_msg = bytearray([0x90 + channel, note_key, velosity])
        self.midi_out(midi_msg)

    def set_note_off(self, channel, note_key):
        midi_msg = bytearray([0x90 + channel, note_key, 0])
        self.midi_out(midi_msg)

    def set_all_notes_off(self, channel = None):
        midi_msg = bytearray([0xB0 + channel, 0x78, 0])
        self.midi_out(midi_msg)

    def set_reverb(self, channel, prog, level, feedback):
        status_byte = 0xB0 + channel
        midi_msg = bytearray([status_byte, 0x50, prog, status_byte, 0x5B, level])
        self.midi_out(midi_msg)
        if feedback > 0:
            midi_msg = bytearray([0xF0, 0x41, 0x00, 0x42, 0x12, 0x40, 0x01, 0x35, feedback, 0, 0xF7])
            self.midi_out(midi_msg)
            
    def set_chorus(self, channel, prog, level, feedback, delay):
        status_byte = 0xB0 + channel
        midi_msg = bytearray([status_byte, 0x51, prog, status_byte, 0x5D, level])
        self.midi_out(midi_msg)
        if feedback > 0:
            midi_msg = bytearray([0xF0, 0x41, 0x00, 0x42, 0x12, 0x40, 0x01, 0x3B, feedback, 0, 0xF7])
            self.midi_out(midi_msg)

        if delay > 0:
            midi_msg = bytearray([0xF0, 0x41, 0x00, 0x42, 0x12, 0x40, 0x01, 0x3C, delay, 0, 0xF7])
            self.midi_out(midi_msg)

    def set_vibrate(self, channel, rate, depth, delay):
        status_byte = 0xB0 + channel
        midi_msg = bytearray([status_byte, 0x63, 0x01, 0x62, 0x08, 0x06, rate, status_byte, 0x63, 0x01, 0x62, 0x09, 0x06, depth, status_byte, 0x63, 0x01, 0x62, 0x0A, 0x06, delay])
        self.midi_out(midi_msg)

    def set_pitch_bend(self, channel, value):
        status_byte = 0xE0 + channel
        lsb = value & 0x7f					# Least
        msb = (value >> 7) & 0x7f			# Most
        midi_msg = bytearray([status_byte, lsb, msb])
        self.midi_out(midi_msg)

    def set_pitch_bend_range(self, channel, value):
        status_byte = 0xB0 + channel
        midi_msg = bytearray([status_byte, 0x65, 0x00, 0x64, 0x00, 0x06, value & 0x7f])
        self.midi_out(midi_msg)

    def set_modulation_wheel(self, channel, modulation, value):
        status_byte = 0xB0 + channel
        midi_msg = bytearray([status_byte, 0x41, 0x00, 0x42, 0x12, 0x40, (0x20 | (channel & 0x0f)), modulation, value, 0x00, 0xF7])
        self.midi_out(midi_msg)

    def midi_master_volume(self, vol=None):
        if vol is not None:
            self.master_volume = vol % 128
            self.set_master_volume(self.master_volume)
        
        return self.master_volume

    def midi_instrument(self, channel=None, program=None, gmbank=0):
        if (channel is not None) and (program is not None):
            channel = channel % 16
            program = program % 128
            self.midi_in_settings[channel]['program'] = program
            self.midi_in_settings[channel]['gmbank'] = gmbank
            self.set_instrument(channel, program, gmbank)
            
        elif (channel is not None) and (program is None):
            channel = channel % 16
            self.set_instrument(channel, self.midi_in_settings[channel]['program'], self.midi_in_settings[channel]['gmbank'])
            
        elif (channel is None) and (program is None):
            for channel in list(range(16)):
                self.set_instrument(channel, self.midi_in_settings[channel]['program'], self.midi_in_settings[channel]['gmbank'])

    def midi_get_instrument(self, channel, gmbank=0):
        return self.midi_in_settings[channel % 16]['program']
    
    def midi_effectors(self):
        for channel in list(range(16)):
            self.set_reverb(channel, self.midi_in_settings[channel]['reverb'][0], self.midi_in_settings[channel]['reverb'][1], self.midi_in_settings[channel]['reverb'][2])
            self.set_chorus(channel, self.midi_in_settings[channel]['chorus'][0], self.midi_in_settings[channel]['chorus'][1], self.midi_in_settings[channel]['chorus'][2], self.midi_in_settings[channel]['chorus'][3])
            self.set_vibrate(channel, self.midi_in_settings[channel]['vibrate'][0], self.midi_in_settings[channel]['vibrate'][1], self.midi_in_settings[channel]['vibrate'][2])

    def midi_reverb(self, channel, param, value):
        channel = channel % 16
        if   param == 0:
            value = value % 8
        else:
            value = value % 128
            
        self.midi_in_settings[channel]['reverb'][param % 3] = value
        self.set_reverb(channel, self.midi_in_settings[channel]['reverb'][0], self.midi_in_settings[channel]['reverb'][1], self.midi_in_settings[channel]['reverb'][2])
    
    def midi_get_reverb(self, channel, param=None):
        channel = channel % 16
        if param is None:
            return self.midi_in_settings[channel]['reverb']
        else:
            return self.midi_in_settings[channel]['reverb'][param % 3]
    
    def midi_chorus(self, channel, param, value):
        channel = channel % 16
        if   param == 0:
            value = value % 8
        else:
            value = value % 128
            
        self.midi_in_settings[channel]['chorus'][param % 4] = value
        self.set_chorus(channel, self.midi_in_settings[channel]['chorus'][0], self.midi_in_settings[channel]['chorus'][1], self.midi_in_settings[channel]['chorus'][2], self.midi_in_settings[channel]['chorus'][3])
    
    def midi_get_chorus(self, channel, param=None):
        channel = channel % 16
        if param is None:
            return self.midi_in_settings[channel]['chorus']
        else:
            return self.midi_in_settings[channel]['chorus'][param % 4]
    
    def midi_vibrate(self, channel, param, value):
        channel = channel % 16
        value = value % 128
            
        self.midi_in_settings[channel]['vibrate'][param % 3] = value
        self.set_vibrate(channel, self.midi_in_settings[channel]['vibrate'][0], self.midi_in_settings[channel]['vibrate'][1], self.midi_in_settings[channel]['vibrate'][2])

    def midi_get_vibrate(self, channel, param=None):
        channel = channel % 16
        if param is None:
            return self.midi_in_settings[channel]['vibrate']
        else:
            return self.midi_in_settings[channel]['vibrate'][param % 3]

    def do_task(self):
        led_flush = False
        try:
            led_flush = not led_flush
            pico_led.value = led_flush

            # USB MIDI-IN (MIDI-IN mode is auto detected in host mode or device mode)
#            if synth.usb_midi_host() is not None:
            midi_msg = synth.midi_in()
            
            # MIDI-IN via USB
            if synth.midi_in_via_usb():
                if not midi_msg is None:
                    # Receiver USB MIDI-IN
    #                    print('MIDI IN:', midi_msg)
                    
                    # if a NoteOn message...
                    if isinstance(midi_msg, NoteOn):
                        string_msg = 'NoteOn'
                        #  get note number
                        string_val = str(midi_msg.note)
                        self.set_note_on(midi_msg.channel, midi_msg.note, midi_msg.velocity)

                    # if a NoteOff message...
                    elif isinstance(midi_msg, NoteOff):
                        string_msg = 'NoteOff'
                        #  get note number
                        string_val = str(midi_msg.note)
                        self.set_note_on(midi_msg.channel, midi_msg.note, 0)

                    # if a PitchBend message...
                    elif isinstance(midi_msg, PitchBend):
                        string_msg = 'PitchBend'
                        #  get value of pitchbend
                        val = midi_msg.pitch_bend - 8192
                        if val < -8192:
                            val = -8192
                        elif val > 8191:
                            val = 8191
                            
                        string_val = str(midi_msg.pitch_bend) + '/' + str(val)
                        self.set_pitch_bend(midi_msg.channel, val)
                        
                    # if a Program Change message...
                    elif isinstance(midi_msg, ProgramChange):
                        string_msg = 'ProgramChange'
                        #  get CC message number
                        string_val = str(midi_msg.patch)
                        self.midi_instrument(midi_msg.channel, midi_msg.patch)
                        
                    #  if a CC message...
                    elif isinstance(midi_msg, ControlChange):
                        string_msg = 'ControlChange'
                        #  get CC message number
                        string_val = str(midi_msg.control)
                        self.set_modulation_wheel(midi_msg.channel, midi_msg.control, midi_msg.value)

                    else:
                        string_msg = 'Unknown Message'
                        string_val = 'None'
                        
                    # update text area with message type and value of message as strings
                    #print(string_msg + ':' + string_val)

    #            else:
    #                sleep(0.2)
    #                synth.look_for_usb_midi_device()

            # MIDI-IN via UART (unit1)
            else:
                if not midi_msg is None:
                    self.midi_out(midi_msg)
                
        except Exception as e:
            print('EXCEPTION: ', e)
            display.clear()
            display.show()
            display.text('EXCEPTION: MIDI-IN', 0, 0, 1)
            display.show()

################# End of Unit-MIDI Class Definition #################


########################
### OLED SSD1306 class
########################
class OLED_SSD1306_class:
    def __init__(self, i2c, address=0x3C, width=128, height=64):
        self.available = False
        self._display = None
        self._i2c = i2c
        self.address = address
        self._width = width
        self._height = height

    def init_device(self, device):
        if device is None:
            return
        
        self._display = device
        self.available = True
        
    def is_available(self):
        return self.available

    def i2c(self):
        return self._i2c
    
    def get_display(self):
        print('DISPLAT')
        return self._display
    
    def width(self):
        return self._width
    
    def height(self):
        return self._height
    
    def fill(self, color):
        if self.is_available():
            self._display.fill(color)
    
    def fill_rect(self, x, y, w, h, color):
        if self.is_available():
            self._display.fill_rect(x, y, w, h, color)

    def text(self, s, x, y, color=1, disp_size=1):
        if self.is_available():
            self._display.text(s, x, y, color, font_name='font5x8.bin', size=disp_size)

    def show(self):
        if self.is_available():
            self._display.show()

    def clear(self, color=0, refresh=True):
        self.fill(color)
        if refresh:
            self.show()
        
################# End of OLED SSD1306 Class Definition #################


#######################
### Application class
#######################
class Application_class:
    def __init__(self, display_obj):
        self._display = display_obj
        self._channel = 0
        self._ignore_midi = False
        
        self.DISPLAY_TYPE_SYNTH  = 0
        self.DISPLAY_TYPE_CONFIG = 1
        self._display_type = self.DISPLAY_TYPE_SYNTH
        
        self.COMMAND_MODE_NONE = -999
        self.COMMAND_MODE_U = -4
        self.COMMAND_MODE_R = -3
        self.COMMAND_MODE_C = -2
        self.COMMAND_MODE_V = -1
        self.COMMAND_MODE_CHANNEL = 0
        self.COMMAND_MODE_PROGRAM = 1
        self.COMMAND_MODE_REVERB_PROGRAM = 2
        self.COMMAND_MODE_REVERB_LEVEL = 4
        self.COMMAND_MODE_REVERB_FEEDBACK = 5
        self.COMMAND_MODE_CHORUS_PROGRAM = 6
        self.COMMAND_MODE_CHORUS_LEVEL = 7
        self.COMMAND_MODE_CHORUS_FEEDBACK = 8
        self.COMMAND_MODE_CHORUS_DELAY = 9
        self.COMMAND_MODE_VIBRATE_RATE = 10
        self.COMMAND_MODE_VIBRATE_DEPTH = 11
        self.COMMAND_MODE_VIBRATE_DELAY = 12
        self.COMMAND_MODE_FILE_LOAD = 13
        self.COMMAND_MODE_FILE_SAVE = 14
        
        self.COMMAND_MODE_MIDI_IN = 15
        self.COMMAND_MODE_MIDI_OUT_UART0 = 16
        self.COMMAND_MODE_MIDI_OUT_UART1 = 17

        self._command_mode = self.COMMAND_MODE_NONE
        
        self._hilights = [
            [],
            [self.COMMAND_MODE_VIBRATE_RATE, self.COMMAND_MODE_VIBRATE_DEPTH, self.COMMAND_MODE_VIBRATE_DELAY],
            [self.COMMAND_MODE_CHANNEL, self.COMMAND_MODE_CHORUS_PROGRAM, self.COMMAND_MODE_CHORUS_LEVEL, self.COMMAND_MODE_CHORUS_FEEDBACK, self.COMMAND_MODE_CHORUS_DELAY],
            [self.COMMAND_MODE_REVERB_PROGRAM, self.COMMAND_MODE_REVERB_LEVEL, self.COMMAND_MODE_REVERB_FEEDBACK],
            [self.COMMAND_MODE_MIDI_OUT_UART0, self.COMMAND_MODE_MIDI_OUT_UART1]
        ]

    def ignore_midi(self, flg=None):
        if flg is not None:
            self._ignore_midi = flg

        return self._ignore_midi

    def show_message(self, msg, x=0, y=0, color=1):
        self._display.text(msg, x, y, color)
        self._display.show()

    def channel(self, ch=None):
        if ch is not None:
            self._channel = ch % 16
            
        return self._channel
    
    def display_type(self, disp_type=None):
        if disp_type is not None:
            self._display_type = disp_type % 2
            
        return self._display_type
            
    def command_mode(self, command=None):
        if command is not None:
            self.show_midi_channel(False)
            self._command_mode = command
            self.show_midi_channel()

        return self._command_mode
        
    def show_midi_channel(self, disp=True, disp_all=False, channel=None):
        
        def show_a_parameter_synth(command, color):
            if command == self.COMMAND_MODE_CHANNEL:
                if synth.as_host():
                    self._display.text('[CH]an:' + ' {:02d}'.format(channel + 1), 0, 0, color[self.COMMAND_MODE_CHANNEL])
                else:
                    self._display.text('<CH>an:' + ' {:02d}'.format(channel + 1), 0, 0, color[self.COMMAND_MODE_CHANNEL])

            elif command == self.COMMAND_MODE_PROGRAM:
                if channel == 9:
                    self._display.text('[P]rog:DRM', 64, 0, color[self.COMMAND_MODE_PROGRAM])
                    self._display.text('DRUM SET', 64, 9, color[self.COMMAND_MODE_PROGRAM])
                else:
                    self._display.text('[P]rog:' + '{:03d}'.format(synth.midi_get_instrument(channel)), 64, 0, color[self.COMMAND_MODE_PROGRAM])
                    self._display.text(synth.get_instrument_name(synth.midi_get_instrument(channel)), 64, 9, color[self.COMMAND_MODE_PROGRAM])
            
            elif command == self.COMMAND_MODE_REVERB_PROGRAM:
                self._display.text('[RP]rg:' + '  {:01d}'.format(synth.midi_get_reverb(channel, 0)), 0, 9, color[self.COMMAND_MODE_REVERB_PROGRAM])
            
            elif command == self.COMMAND_MODE_REVERB_LEVEL:
                self._display.text('[RL]vl:' + '{:03d}'.format(synth.midi_get_reverb(channel, 1)), 0, 18, color[self.COMMAND_MODE_REVERB_LEVEL])
            
            elif command == self.COMMAND_MODE_REVERB_FEEDBACK:
                self._display.text('[RF]bk:' + '{:03d}'.format(synth.midi_get_reverb(channel, 2)), 64, 18, color[self.COMMAND_MODE_REVERB_FEEDBACK])
            
            elif command == self.COMMAND_MODE_CHORUS_PROGRAM:
                self._display.text('[CP]rg:' + '  {:01d}'.format(synth.midi_get_chorus(channel, 0)), 0, 27, color[self.COMMAND_MODE_CHORUS_PROGRAM])
            
            elif command == self.COMMAND_MODE_CHORUS_LEVEL:
                self._display.text('[CL]vl:' + '{:03d}'.format(synth.midi_get_chorus(channel, 1)), 64, 27, color[self.COMMAND_MODE_CHORUS_LEVEL])
            
            elif command == self.COMMAND_MODE_CHORUS_FEEDBACK:
                self._display.text('[CF]bk:' + '{:03d}'.format(synth.midi_get_chorus(channel, 2)), 0, 36, color[self.COMMAND_MODE_CHORUS_FEEDBACK])
            
            elif command == self.COMMAND_MODE_CHORUS_DELAY:
                self._display.text('[CD]ly:' + '{:03d}'.format(synth.midi_get_chorus(channel, 3)), 64, 36, color[self.COMMAND_MODE_CHORUS_DELAY])
            
            elif command == self.COMMAND_MODE_VIBRATE_RATE:
                self._display.text('[VR]at:' + '{:03d}'.format(synth.midi_get_vibrate(channel, 0)), 0, 45, color[self.COMMAND_MODE_VIBRATE_RATE])
            
            elif command == self.COMMAND_MODE_VIBRATE_DEPTH:
                self._display.text('[VD]pt:' + '{:03d}'.format(synth.midi_get_vibrate(channel, 1)), 64, 45, color[self.COMMAND_MODE_VIBRATE_DEPTH])
            
            elif command == self.COMMAND_MODE_VIBRATE_DELAY:
                self._display.text('[VdL]y:' + '{:03d}'.format(synth.midi_get_vibrate(channel, 2)), 0, 54, color[self.COMMAND_MODE_VIBRATE_DELAY])

            elif command == self.COMMAND_MODE_FILE_LOAD:
                fnum = synth.midi_file_number_exist()[1]
                if self.command_mode() == self.COMMAND_MODE_FILE_LOAD:
                    if color[self.COMMAND_MODE_FILE_LOAD] == 0:
                        if fnum >= 0:
                            self._display.text('[F]lod:' + '{:03d}'.format(synth.midi_file_number_exist()[1]), 64, 54, 0)
                        else:
                            self._display.text('[F]lod:NON', 64, 54, 0)

                        return

                if fnum >= 0:
                    self._display.text('[L|S]f:' + '{:03d}'.format(synth.midi_file_number_exist()[1]), 64, 54, 1)
                else:
                    self._display.text('[L|S]f:NON', 64, 54, 1)
 
            elif command == self.COMMAND_MODE_FILE_SAVE:
                if self.command_mode() == self.COMMAND_MODE_FILE_SAVE:
                    if color[self.COMMAND_MODE_FILE_SAVE] == 0:
                        self._display.text('[F]sav:' + '{:03d}'.format(synth.midi_file_number()), 64, 54, 0)
                        return

                self._display.text('[L|S]f:' + '{:03d}'.format(synth.midi_file_number()), 64, 54, 1)        
        

        def show_a_parameter_config(command, color):
            if command == self.COMMAND_MODE_MIDI_IN:
                if synth.midi_in_via_usb():
                    self._display.text('[MdIn]:USB', 64, 0, color[self.COMMAND_MODE_MIDI_IN])
                else:
                    self._display.text('[MdIn]:UAT', 64, 0, color[self.COMMAND_MODE_MIDI_IN])

            elif command == self.COMMAND_MODE_MIDI_OUT_UART0:
                if synth.midi_out_to(0):
                    self._display.text('[UA]t0:OUT', 0, 9, color[self.COMMAND_MODE_MIDI_OUT_UART0])
                else:
                    self._display.text('[UA]t0:OFF', 0, 9, color[self.COMMAND_MODE_MIDI_OUT_UART0])


            elif command == self.COMMAND_MODE_MIDI_OUT_UART1:
                if synth.midi_out_to(1):
                    self._display.text('[UaT]1:OUT', 64, 9, color[self.COMMAND_MODE_MIDI_OUT_UART1])
                else:
                    self._display.text('[UaT]1:OFF', 64, 9, color[self.COMMAND_MODE_MIDI_OUT_UART1])

            elif command < 0:
                if synth.as_host():
                    self._display.text('USB HOST',   0, 0, 1)
                else:
                    self._display.text('USB DEVICE', 0, 0, 1)
                    
                    
        def show_a_parameter(command, color):
            if self._display_type == self.DISPLAY_TYPE_SYNTH:
                show_a_parameter_synth(command, color)

            elif self._display_type == self.DISPLAY_TYPE_CONFIG:
                show_a_parameter_config(command, color)


        #--- show_midi_channel MAIN ---#
        channel = self.channel() if channel is None else channel % 16
        
        # Hilight parameter
        color = [1] * 18
        command = self.command_mode()
        hilight = command
        print('COMMAND=', command, ' ALL=', disp_all)
            
        if disp_all:
            if disp == False:
#                print('=== CLEAR')
                self._display.clear()
                return

            # Synthesize parameter setting display
            if self._display_type == self.DISPLAY_TYPE_SYNTH:
                if command == self.COMMAND_MODE_CHANNEL:
                    self._display.fill_rect(0, 0, 63, 8, 1)
                    color[self.COMMAND_MODE_CHANNEL] = 0

#	            print('=== SHOW ALL')
                for cmd in list(range(self.COMMAND_MODE_CHANNEL, self.COMMAND_MODE_FILE_LOAD + 1)):
                    show_a_parameter(cmd, color)

                if command == self.COMMAND_MODE_FILE_LOAD or command == self.COMMAND_MODE_FILE_SAVE:
                    show_a_parameter(command, color)
                else:
                    show_a_parameter(self.COMMAND_MODE_FILE_LOAD, color)
            
            # Configuration display
            elif self._display_type == self.DISPLAY_TYPE_CONFIG:
                show_a_parameter(-1, color)
                for cmd in list(range(self.COMMAND_MODE_MIDI_IN, self.COMMAND_MODE_MIDI_OUT_UART1 + 1)):
                    show_a_parameter(cmd, color)

            # Show display
            self._display.show()
            return

        # Disp the current one command
        if hilight >= 0:
            print('=== SHOW: ', command)
            color[hilight] = 0 if disp else 1
            if hilight == self.COMMAND_MODE_FILE_SAVE:
                hilight = self.COMMAND_MODE_FILE_LOAD

            hx = 0 if hilight % 2 == 0 else 64
            if self._display_type == self.DISPLAY_TYPE_SYNTH:
                hy = int(hilight / 2) * 9
            elif self._display_type == self.DISPLAY_TYPE_CONFIG:
                hy = int((hilight - 14) / 2) * 9
                
            self._display.fill_rect(hx, hy, 63, 8, 1 if disp else 0)
            if hilight == self.COMMAND_MODE_PROGRAM:
                self._display.fill_rect(hx, hy + 9, 63, 8, 1 if disp else 0)

            show_a_parameter(command, color)

        # Some command candidates
        elif hilight != -999:
            print('=== MULT: ', self._hilights[-hilight])
            for cmd in self._hilights[-hilight]:
                hx = 0 if cmd % 2 == 0 else 64
                if self._display_type == self.DISPLAY_TYPE_SYNTH:
                    hy = int(cmd / 2) * 9
                elif self._display_type == self.DISPLAY_TYPE_CONFIG:
                    hy = int((cmd - 14) / 2) * 9
                    
                self._display.fill_rect(hx, hy, 63, 8, 1 if disp else 0)        
                color[cmd] = 0 if disp else 1
                show_a_parameter(cmd, color)

        self._display.show()
            
################# End of Application Class Definition #################
        
        
#####################
### CARD.KB class
#####################
class CARDKB_class:
    # Constructor
    #   i2c: I2C_class object
    def __init__(self, i2c, address=0x5F):
        self.available = False
        self.command = ''
        self.numeric_param = None

        self.i2c = i2c
        if self.i2c is None:
            return
        
        self.CARDKB_ADDRESS = address
        while not self.i2c.try_lock():
            pass

        for i in self.i2c.scan():
            print('addr 0x{0:x}'.format(i))
            if i == self.CARDKB_ADDRESS:
                self.available = True
                break

        print("\n")

    def is_available(self):
        return self.available

    # Read a key value
    def read_key(self):
        if self.available:
            while self.i2c.try_lock():
                pass

            kb_value = bytearray(1)
            self.i2c.writeto_then_readfrom(self.CARDKB_ADDRESS, bytes([1]), kb_value)
            if kb_value[0] != 0x00:
                return kb_value

        return None

    def change_parameter_value(self, delta, abs_value=None):
        if   application.command_mode() == application.COMMAND_MODE_CHANNEL:
            application.show_midi_channel(False, True)
            application.channel((application.channel() if abs_value is None else abs_value) + (1 if delta > 0 else -1))
        
        elif application.command_mode() == application.COMMAND_MODE_PROGRAM:
            synth.midi_instrument(application.channel(), (synth.midi_get_instrument(application.channel()) if abs_value is None else abs_value) + delta)
        
        elif application.command_mode() == application.COMMAND_MODE_REVERB_PROGRAM:
            value = (synth.midi_get_reverb(application.channel(), 0) if abs_value is None else abs_value) + (0 if delta == 0 else (1 if delta > 0 else -1))
            synth.midi_reverb(application.channel(), 0, value)
        
        elif application.command_mode() == application.COMMAND_MODE_REVERB_LEVEL:
            value = (synth.midi_get_reverb(application.channel(), 1) if abs_value is None else abs_value) + delta
            synth.midi_reverb(application.channel(), 1, value)
        
        elif application.command_mode() == application.COMMAND_MODE_REVERB_FEEDBACK:
            value = (synth.midi_get_reverb(application.channel(), 2) if abs_value is None else abs_value) + delta
            synth.midi_reverb(application.channel(), 2, value)
        
        elif application.command_mode() == application.COMMAND_MODE_CHORUS_PROGRAM:
            value = (synth.midi_get_chorus(application.channel(), 0) if abs_value is None else abs_value) + (0 if delta == 0 else (1 if delta > 0 else -1))
            synth.midi_chorus(application.channel(), 0, value)
        
        elif application.command_mode() == application.COMMAND_MODE_CHORUS_LEVEL:
            value = (synth.midi_get_chorus(application.channel(), 1) if abs_value is None else abs_value) + delta
            synth.midi_chorus(application.channel(), 1, value)
        
        elif application.command_mode() == application.COMMAND_MODE_CHORUS_FEEDBACK:
            value = (synth.midi_get_chorus(application.channel(), 2) if abs_value is None else abs_value) + delta
            synth.midi_chorus(application.channel(), 2, value)

        elif application.command_mode() == application.COMMAND_MODE_CHORUS_DELAY:
            value = (synth.midi_get_chorus(application.channel(), 3) if abs_value is None else abs_value) + delta
            synth.midi_chorus(application.channel(), 3, value)

        elif application.command_mode() == application.COMMAND_MODE_VIBRATE_RATE:
            value = (synth.midi_get_vibrate(application.channel(), 0) if abs_value is None else abs_value) + delta
            synth.midi_vibrate(application.channel(), 0, value)

        elif application.command_mode() == application.COMMAND_MODE_VIBRATE_DEPTH:
            value = (synth.midi_get_vibrate(application.channel(), 1) if abs_value is None else abs_value) + delta
            synth.midi_vibrate(application.channel(), 1, value)
        
        elif application.command_mode() == application.COMMAND_MODE_VIBRATE_DELAY:
            value = (synth.midi_get_vibrate(application.channel(), 2) if abs_value is None else abs_value) + delta
            synth.midi_vibrate(application.channel(), 2, value)
        
        elif application.command_mode() == application.COMMAND_MODE_FILE_LOAD:
            synth.midi_file_number_exist((synth.midi_file_number_exist()[0] if abs_value is None else abs_value) + delta)
        
        elif application.command_mode() == application.COMMAND_MODE_FILE_SAVE:
            synth.midi_file_number((synth.midi_file_number() if abs_value is None else abs_value) + delta)

        elif application.command_mode() == application.COMMAND_MODE_MIDI_IN:
            synth.midi_in_via_usb(not synth.midi_in_via_usb())

        elif application.command_mode() == application.COMMAND_MODE_MIDI_OUT_UART0:
            synth.midi_out_to(0, not synth.midi_out_to(0))

        elif application.command_mode() == application.COMMAND_MODE_MIDI_OUT_UART1:
            synth.midi_out_to(1, not synth.midi_out_to(1))

        # Redraw the parameter only or all (if COMMAND_MODE_CHANNEL)
        application.show_midi_channel(True, application.command_mode() == application.COMMAND_MODE_CHANNEL)

    # Do device task
    def do_task(self):
        # Get keyboard
        kbd = self.read_key()
        if kbd is not None:
            key_code = kbd[0]
            ch = chr(key_code).upper()
            print('KBD: ', hex(key_code), 'CH: ', ch)

            # Change display type
            if   key_code == 0x09:
                application.display_type(application.display_type() + 1)
                self.command = ''
                self.numeric_param = None
                display.clear()
                application.show_midi_channel(True, True)

            # Ignore MIDI or NOT
            elif key_code == 0x1b:
                application.ignore_midi(not application.ignore_midi())
            
            # Value increment
            elif key_code == 0xB7:
                self.change_parameter_value(1)
                
            # Value increment decade
            elif key_code == 0xA5:
                self.change_parameter_value(10)
            
            # Value decrement
            elif key_code == 0xB4:
                self.change_parameter_value(-1)
            
            # Value decrement decade
            elif key_code == 0x98:
                self.change_parameter_value(-10)
            
            # Volume loud
            elif key_code == 0xB5:
                synth.midi_master_volume(synth.midi_master_volume() + 1)
            
            # Volume loud decade
            elif key_code == 0x99:
                synth.midi_master_volume(synth.midi_master_volume() + 10)
                
            # Volume off
            elif key_code == 0xB6:
                synth.midi_master_volume(synth.midi_master_volume() - 1) 
                
            # Volume off devcade
            elif key_code == 0xA4:
                synth.midi_master_volume(synth.midi_master_volume() - 10) 

            # Test sound
            elif key_code == 0x20 or key_code == 0xAF:
                if key_code == 0xAF:
                    print('RESED instruments and effecrors settings.')
                    synth.midi_instrument()
                    synth.midi_effectors()

                print('PROGRAM/VOLUME: ', synth.midi_get_instrument(0), synth.midi_master_volume())
                synth.set_note_on(application.channel(), 60, 127)
                sleep(0.5)
                synth.set_note_on(application.channel(), 64, 127)
                sleep(0.5)
                synth.set_note_on(application.channel(), 67, 127)
                sleep(0.5)
                synth.set_note_off(application.channel(), 60)
                synth.set_note_off(application.channel(), 64)
                synth.set_note_off(application.channel(), 67)

            elif (('0' <= ch and ch <= '9') or key_code == 0x0d or key_code == 0x08) and application.command_mode() != application.COMMAND_MODE_NONE:
                if key_code == 0x0d:
                    self.numeric_param = None
                    
                elif key_code == 0x08:
                    if self.numeric_param is not None:
                        print('NP1=', self.numeric_param)
                        self.numeric_param = int((self.numeric_param - (self.numeric_param % 10)) / 10)
                        print('NP2=', self.numeric_param)
                        self.change_parameter_value(0, self.numeric_param)
                    
                else:
                    if self.numeric_param == None:
                        self.numeric_param = int(ch)
                    else:
                        self.numeric_param = self.numeric_param * 10 + int(ch)
                        
                    self.change_parameter_value(0, self.numeric_param)

            # Command interpriter
            else:
                # Synthesizer parameter setting display
                if application.display_type() == application.DISPLAY_TYPE_SYNTH:
                    if 'A' <= ch and ch <= 'Z':
                        self.command = self.command + ch
                        print('COMMAND S: ', self.command)
                    
                    # Change program command mode
                    if self.command == 'P':
                        application.command_mode(application.COMMAND_MODE_PROGRAM)
                        self.numeric_param = None
                        
                    elif self.command == 'R':
                        application.command_mode(application.COMMAND_MODE_R)
                        self.numeric_param = None
                    
                    elif self.command == 'C':
                        application.command_mode(application.COMMAND_MODE_C)
                        self.numeric_param = None
                    
                    elif self.command == 'V':
                        application.command_mode(application.COMMAND_MODE_V)
                        self.numeric_param = None
                        
                    elif self.command == 'L':
                        application.command_mode(application.COMMAND_MODE_FILE_LOAD)
                        self.numeric_param = None
                        
                    elif self.command == 'S':
                        application.command_mode(application.COMMAND_MODE_FILE_SAVE)
                        self.numeric_param = None
                        
                    elif self.command == 'LF':
                        application.show_midi_channel(False, True)
                        synth.load_midi_settings()
                        application.show_midi_channel(True, True)
                        application.command_mode(application.COMMAND_MODE_NONE)
                        synth.midi_instrument()
                        synth.midi_effectors()
                        self.command = ''
                        self.numeric_param = None
                        
                    elif self.command == 'SF':
                        synth.save_midi_settings()
                        application.command_mode(application.COMMAND_MODE_NONE)
                        self.command = ''
                        self.numeric_param = None
                    
                    elif self.command == 'RP':
                        application.command_mode(application.COMMAND_MODE_REVERB_PROGRAM)
                        self.numeric_param = None
                    
                    elif self.command == 'RL':
                        application.command_mode(application.COMMAND_MODE_REVERB_LEVEL)
                        self.numeric_param = None
                    
                    elif self.command == 'RF':
                        application.command_mode(application.COMMAND_MODE_REVERB_FEEDBACK)
                        self.numeric_param = None

                    elif self.command == 'CH':
                        application.command_mode(application.COMMAND_MODE_CHANNEL)
                        self.numeric_param = None
                    
                    elif self.command == 'CP':
                        application.command_mode(application.COMMAND_MODE_CHORUS_PROGRAM)
                        self.numeric_param = None
                    
                    elif self.command == 'CL':
                        application.command_mode(application.COMMAND_MODE_CHORUS_LEVEL)
                        self.numeric_param = None
                    
                    elif self.command == 'CF':
                        application.command_mode(application.COMMAND_MODE_CHORUS_FEEDBACK)
                        self.numeric_param = None
                    
                    elif self.command == 'CD':
                        application.command_mode(application.COMMAND_MODE_CHORUS_DELAY)
                        self.numeric_param = None
                    
                    elif self.command == 'VR':
                        application.command_mode(application.COMMAND_MODE_VIBRATE_RATE)
                        self.numeric_param = None
                    
                    elif self.command == 'VD':
                        application.command_mode(application.COMMAND_MODE_VIBRATE_DEPTH)
                        self.numeric_param = None
                    
                    elif self.command == 'VL':
                        application.command_mode(application.COMMAND_MODE_VIBRATE_DELAY)
                        self.numeric_param = None

                    elif ch == 'R':
                        application.command_mode(application.COMMAND_MODE_R)
                        self.command = ch
                        self.numeric_param = None

                    elif ch == 'C':
                        application.command_mode(application.COMMAND_MODE_C)
                        self.command = ch
                        self.numeric_param = None

                    elif ch == 'V':
                        application.command_mode(application.COMMAND_MODE_V)
                        self.command = ch
                        self.numeric_param = None

                    elif ch == 'P':
                        application.command_mode(application.COMMAND_MODE_PROGRAM)
                        self.command = ch
                        self.numeric_param = None
                        
                    elif ch == 'L':
                        application.command_mode(application.COMMAND_MODE_FILE_LOAD)
                        self.command = ch
                        self.numeric_param = None
                        
                    elif ch == 'S':
                        application.command_mode(application.COMMAND_MODE_FILE_SAVE)
                        self.command = ch
                        self.numeric_param = None

                    else:
                        application.command_mode(application.COMMAND_MODE_NONE)
                        self.command = ''
                        self.numeric_param = None

                # Configration setting display
                elif application.display_type() == application.DISPLAY_TYPE_CONFIG:
                    if 'A' <= ch and ch <= 'Z':
                        self.command = self.command + ch
                        print('COMMAND C: ', self.command)
                    
                    # Change MIDI-IN via
                    if self.command == 'M':
                        application.command_mode(application.COMMAND_MODE_MIDI_IN)
                        self.numeric_param = None
                        
                    elif self.command == 'UA':
                        application.command_mode(application.COMMAND_MODE_MIDI_OUT_UART0)
                        self.numeric_param = None
                        
                    elif self.command == 'UT':
                        application.command_mode(application.COMMAND_MODE_MIDI_OUT_UART1)
                        self.numeric_param = None
                        
                    elif ch == 'U':
                        application.command_mode(application.COMMAND_MODE_U)
                        self.command = ch
                        self.numeric_param = None
                    
                    else:
                        application.command_mode(application.COMMAND_MODE_NONE)
                        self.command = ''
                        self.numeric_param = None

################# End of CARD.KB Class Definition #################
    

def setup():
    global pico_led, synth, display, cardkb, view, application

    # LED on board
    pico_led = digitalio.DigitalInOut(GP25)
    pico_led.direction = digitalio.Direction.OUTPUT
    pico_led.value = True

    # OLED SSD1306
    print('setup')
    try:
        print('OLED setup')
        i2c1 = I2C(GP7, GP6)		# I2C-1 (SCL, SDA)
        display = OLED_SSD1306_class(i2c1, 0x3C, 128, 64)
        device_oled = adafruit_ssd1306.SSD1306_I2C(display.width(), display.height(), display.i2c())
        display.init_device(device_oled)
        display.fill(1)
        display.text('PICO SYNTH', 5, 15, 0, 2)
        display.text('(C) 2024 S.Ohira', 15, 35, 0)
        display.show()
        
    except:
        display = OLED_SSD1306_class(None)
        pico_led.value = False
        print('ERROR I2C1')
        for cnt in list(range(10)):
            pico_led.value = False
            sleep(0.5)
            pico_led.value = True
            sleep(1.0)

    print('Start application.')
    application = Application_class(display)
        
    # CRAD.KB
    try:
        print('CARD.KB setup')
        i2c0 = I2C(GP9, GP8)		# I2C-0 (SCL, SDA)
        cardkb = CARDKB_class(i2c0)
        if cardkb.is_available() == False:
            print('CARD.KB not availalbe.')
            application.show_midi_channel(False, True)
            application.show_message('NO KEYBOARD.')
            for cnt in list(range(10)):
                pico_led.value = True
                sleep(1.0)
                pico_led.value = False
                sleep(0.5)

        else:
            print('Keyboard ready.')
            display.text('Welcome!!', 40, 45, 0)
            display.show()
            sleep(3.0)
            display.fill(0)
            display.show()
            
    except:
        cardkb = CARDKB_class(None)
        print('ERROR I2C0')
        application.show_midi_channel(False, True)
        application.show_message('ERROR I2C0')
        for cnt in list(range(10)):
            pico_led.value = True
            sleep(1.0)
            pico_led.value = False
            sleep(0.5)

    # Unit Synthesizer
    synth = MIDIUnit_class(0, (GP0, GP1))
    synth.look_for_usb_midi_device()
    synth.midi_master_volume(127)
    synth.midi_instrument()
    synth.midi_effectors()
    sleep(1.0)
    display.clear()
    display.show()
    
    application.show_midi_channel(True, True)


######### MAIN ##########
if __name__=='__main__':
    # Setup
    pico_led = None
    synth = None
    display = None
    cardkb = None
    application = None
    setup()

    while True:
        try:
            # CARD.KB task
            cardkb.do_task()
            
            # Unit SYNTH task
            if application.ignore_midi() == False:
                synth.do_task()

        except Exception as e:
            print('CATCH EXCEPTION:', e)
            application.show_midi_channel(False, True)
            application.show_message('ERROR: ' + str(e))
            for cnt in list(range(10)):
                pico_led.value = False
                sleep(0.5)
                pico_led.value = True
                sleep(1.0)

            display.clear()
            application.show_midi_channel(True, True)


