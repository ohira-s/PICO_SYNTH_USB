#busio.UART(tx, rx, *, baudrate=9600, bits=8, parity=None, stop=1, timeout=1000, receiver_buffer_size=64)
from board import *
import digitalio
from busio import UART			# for UART MIDI
from time import sleep

import usb_midi					# for USB MIDI
import adafruit_midi
from adafruit_midi.control_change import ControlChange
from adafruit_midi.note_off import NoteOff
from adafruit_midi.note_on import NoteOn
from adafruit_midi.pitch_bend import PitchBend

import board
import usb_host
import usb.core
#import adafruit_usb_host_midi	# for USB MIDI HOST
from adafruit_usb_host_midi.adafruit_usb_host_midi import MIDI	# for USB MIDI HOST
import supervisor

import adafruit_ssd1306			# for SSD1306 OLED Display

from busio import I2C			# for I2C

#####################
### Unit-MIDI class
#####################
class MIDIUnit:
    # Constructor
    #   uart_unit: PICO UART unit number 0 or 1
    #   port     : A tuple of (Tx, Rx)
    #              This argument is NOT USED, to keep compatibility with M5Stack CORE2.
    def __init__(self, uart_unit=0, port=(GP0, GP1)):
        self._uart = UART(tx=port[0], rx=port[1], baudrate=31250)

        self.set_note_on(0, 48, 127)
        sleep(1.0)
        self.set_note_off(0, 48)

        # USB HOST MODE DEFINITIONS
        # USB DEVICE   : Vender ID : Product ID
        # KORG nanoKEY2: 0x944       0x115
        self.USB_DEV_nanoKEY2 = {'VenderID': 0x944, 'ProductID': 0x115}
        self.raw_midi = None
        self._usb_midi = None
        
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

    # Look for USB MIDI device
    def look_for_usb_midi_device(self):
        self.raw_midi = None
        self._usb_midi = None

##        print("Looking for midi device")
        led_flush = False
        while self.raw_midi is None:
            led_flush = not led_flush
            pico_led.value = led_flush
            
            devices_found = usb.core.find(find_all=True)
##            print('USB LIST:', devices_found)
            display.text('USB LIST: ' + str(devices_found), 0, 9, 1)
            display.show()

            for device in devices_found:
##                print('DEVICE: ', device)
                try:
##                    print("Found", hex(device.idVendor), hex(device.idProduct))
                    display.text('Found: ' + str(hex(device.idVendor)) + str(hex(device.idProduct)), 0, 18, 1)
                    display.show()

#                    self.set_note_on(0, 72, 127)
#                    sleep(1.0)
#                    self.set_note_off(0, 72)

                    self.raw_midi = MIDI(device)
##                    print("CONNECT MIDI")
                    display.text('CONNECT MIDI', 0, 45, 1)
                    display.show()

                except ValueError:
                    self.raw_midi = None
                    display.text('EXCEPTION', 0, 45, 1)
                    display.show()
                    continue

##        print('Found USB MIDI device.')
        display.show()

        if self.raw_midi is None:
            self._usb_midi = None
            pico_led.value = False
            return None
        
        self._usb_midi = adafruit_midi.MIDI(midi_in=self.raw_midi, in_channel=0)  
#        self._usb_midi = adafruit_midi.MIDI(midi_in=usb_midi.ports[0], in_channel=0, midi_out=usb_midi.ports[1], out_channel=0)
        pico_led.value = True
        return self._usb_midi

    # MIDI-IN via USB-MIDI
    def midi_in(self):
        if self._usb_midi is not None:
            midi_msg = self._usb_midi.receive()
            return midi_msg
        
        return None

    def midi_send(self, note_key, velosity):
        if self._usb_midi is not None:
            self._usb_midi.send(NoteOn(note_key, velosity))

    # MIDI-OUT to UART MIDI
    def midi_out(self, midi_msg):
        self._uart.write(midi_msg)
    
    # Receive MIDI via USB MIDI, then send it to UART MIDI
    def midi_in_out(self):
        midi_msg = self.midi_in()
        if not midi_msg is None:
            self.midi_out(midi_msg)
    
    def set_master_volume(self, vol):
        midi_msg = bytearray([0xF0, 0x7F, 0x7F, 0x04, 0x01, 0, vol & 0x7f, 0xF7])
        self.midi_out(midi_msg)

    def set_instrument(self, gmbank, channel, prog):
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


def setup():
    global pico_led, display
    
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


######### MAIN ##########
if __name__=='__main__':
    pico_led = None
    display = None
    setup()

    synth = MIDIUnit(0, (GP0, GP1))
    channel = 0
    note_key = 60
    velocity = 127

    led_flush = False
    while True:
        try:
            led_flush = not led_flush
            pico_led.value = led_flush

            if synth.look_for_usb_midi_device() is not None:
    #            rb = synth.raw_midi.read(4)
    #            print('RB=', rb)
    #            midi_msg = None
                midi_msg = synth.midi_in()

                display.fill_rect(0, 27, 128, 18, 0)
                if midi_msg is None:
                    display.text('MIDI: 000', 0, 27, 1)
                    display.text('MIDI: none', 0, 36, 1)
                
                if not midi_msg is None:
                    # Receiver USB MIDI-IN
    ##                print('MIDI IN:', midi_msg)
                    string_msg = 'Unknown Message'
                    string_val = 'None'
                    
                    #  if a NoteOn message...
                    if isinstance(midi_msg, NoteOn):
                        string_msg = 'NoteOn'
                        #  get note number
                        string_val = str(midi_msg.note)
                        synth.set_note_on(midi_msg.channel, midi_msg.note, midi_msg.velocity)
                        display.text('MIDI: NoteOn', 0, 27, 1)
                        display.text('MIDI: ' + string_val, 0, 36, 1)

                    #  if a NoteOff message...
                    if isinstance(midi_msg, NoteOff):
                        string_msg = 'NoteOff'
                        #  get note number
                        string_val = str(midi_msg.note)
                        synth.set_note_on(midi_msg.channel, midi_msg.note, 0)
                        display.text('MIDI: NoteOff', 0, 27, 1)
                        display.text('MIDI: ' + string_val, 0, 36, 1)

                    #  if a PitchBend message...
                    if isinstance(midi_msg, PitchBend):
                        string_msg = 'PitchBend'
                        #  get value of pitchbend
                        string_val = str(midi_msg.pitch_bend)
                        display.text('MIDI: PitchBend', 0, 27, 1)
                        display.text('MIDI: ' + string_val, 0, 36, 1)

                    #  if a CC message...
                    if isinstance(midi_msg, ControlChange):
                        string_msg = 'ControlChange'
                        #  get CC message number
                        string_val = str(midi_msg.control)
                        display.text('MIDI: ControlChange', 0, 27, 1)
                        display.text('MIDI: ' + string_val, 0, 36, 1)

                    #  update text area with message type and value of message as strings
    ##                print(string_msg + ':' + string_val)
                    
                display.show()

            else:
                sleep(0.2)
        
        except Exception as e:
            print('EXCEPTION: ', e)
            display.clear()
            display.show()
            display.text('EXCEPTION: MIDI-IN', 0, 0, 1)
            display.show()
            break
            
