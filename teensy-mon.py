#!/usr/bin/env python

"""Program for monitoring serial messages from the Teensy.

This program waits for the device to be connected and when the teensy is
disconnected, then it will go back to waiting for the teensy to once again
be connected.

This program also looks for lines that start with a single letter followed
by a colon, and will colorize the lines based on the letter.

"""

import select
import pyudev
import serial
import sys
import termios
import traceback
import syslog
import argparse


(LT_BLACK, LT_RED,     LT_GREEN, LT_YELLOW,
 LT_BLUE,  LT_MAGENTA, LT_CYAN,  LT_WHITE) = [
    ("\033[1;%dm" % (30 + i)) for i in range(8)]
(DK_BLACK, DK_RED,     DK_GREEN, DK_YELLOW,
 DK_BLUE,  DK_MAGENTA, DK_CYAN,  DK_WHITE) = [
    ("\033[2;%dm" % (30 + i)) for i in range(8)]
NO_COLOR = "\033[0m"

COLORS = {
    'W': LT_YELLOW,
    'I': "",
    'D': LT_BLUE,
    'C': LT_RED,
    'E': LT_RED
}


class OutputWriter(object):
    """Class for dealing with the output from the teensy."""

    def __init__(self):
        self.buffered_output = ""
        self.column = 0
        self.colored = False

    def write(self, string):
        """Writes characters to output. Lines will be delimited by
        newline characters.

        This routine breaks the output into lines and writes each line
        individually, colorizing as appropriate.

        """
        if len(self.buffered_output) > 0:
            string = self.buffered_output + string
            self.buffered_output = ""
        while True:
            nl_index = string.find('\n')
            if self.column == 0 and nl_index < 0 and len(string) < 2:
                self.buffered_output = string
                return

            if nl_index < 0:
                line_string = string
            else:
                line_string = string[0:nl_index + 1]
            prefix = ""
            suffix = ""
            if (self.column == 0 and len(string) >= 2 and
                    string[1] == ':' and string[0] in COLORS):
                prefix = COLORS[string[0]]
                self.colored = True
            if nl_index >= 0 and self.colored:
                suffix = NO_COLOR
            sys.stdout.write(prefix + line_string + suffix)
            sys.stdout.flush()
            self.column += len(line_string)
            if nl_index < 0:
                return
            string = string[nl_index + 1:]
            self.column = 0


def is_teensy(device, serial_num=None):
    """Checks device to see if its a teensy device.

    If serial is provided, then it will further check to see if the
    serial number of the teensy device also matches.
    """
    if 'ID_VENDOR' not in device:
        return False
    if not device['ID_VENDOR'].startswith('Teensy'):
        return False
    if serial_num is None:
        return True
    return device['ID_SERIAL_SHORT'] == serial_num


def teensy_mon(monitor, device):
    """Monitors the serial port from a given teensy device.

    This function open the USDB serial port associated with device, and
    will read characters from it and send to stdout. It will also read
    characters from stdin and send them to the device.

    This function returns when the teensy deivce disconnects (or is
    disconnected).

    """
    port_name = device.device_node
    serial_num = device['ID_SERIAL_SHORT']
    print 'Teensy device connected @%s (serial %s)' % (port_name, serial_num)
    epoll = select.epoll()
    epoll.register(monitor.fileno(), select.POLLIN)

    output = OutputWriter()

    try:
        serial_port = serial.Serial(port=port_name,
                                    timeout=0.001,
                                    bytesize=serial.EIGHTBITS,
                                    parity=serial.PARITY_NONE,
                                    stopbits=serial.STOPBITS_ONE,
                                    xonxoff=False,
                                    rtscts=False,
                                    dsrdtr=False)
    except serial.serialutil.SerialException:
        print "Unable to open port '%s'" % port_name
        return

    epoll.register(serial_port.fileno(), select.POLLIN)
    epoll.register(sys.stdin.fileno(), select.POLLIN)

    while True:
        events = epoll.poll()
        for fileno, _ in events:
            if fileno == monitor.fileno():
                dev = monitor.poll()
                if (dev.device_node != port_name or
                        dev.action != 'remove'):
                    continue
                print 'Teensy device @', port_name, ' disconnected.'
                serial_port.close()
                return
            if fileno == serial_port.fileno():
                try:
                    data = serial_port.read(256)
                except serial.serialutil.SerialException:
                    print 'Teensy device @', port_name, ' disconnected.'
                    serial_port.close()
                    return
                #for x in data:
                #    print "Serial.Read '%c' 0x%02x" % (x, ord(x))
                output.write(data)
            if fileno == sys.stdin.fileno():
                data = sys.stdin.read(1)
                #for x in data:
                #    print "stdin.Read '%c' 0x%02x" % (x, ord(x))
                if data[0] == '\n':
                    serial_port.write('\r')
                else:
                    serial_port.write(data)


def main():
    """The main program."""

    parser = argparse.ArgumentParser(
        prog="teensy_mon",
        usage="%(prog)s [options] [command]",
        description="Monitor serial output from teensy devices",
        epilog="Press Control-C to quit"
    )
    parser.add_argument(
        "-l", "--list",
        dest="list",
        action="store_true",
        help="List Teensy devices currently connected"
    )
    parser.add_argument(
        "-s", "--serial",
        dest="serial",
        help="Connect to Teeny device with a given serial number"
    )
    parser.add_argument(
        "-v", "--verbose",
        dest="verbose",
        action="store_true",
        help="Turn on verbose messages",
        default=False
    )
    args = parser.parse_args(sys.argv[1:])

    if args.verbose:
        print 'pyudev version =', pyudev.__version__

    context = pyudev.Context()
    context.log_priority = syslog.LOG_NOTICE

    if args.list:
        detected = False
        for device in context.list_devices(subsystem='tty'):
            if is_teensy(device):
                print 'Teensy device serial %-5s found @%s' % (
                    device['ID_SERIAL_SHORT'], device.device_node)
                detected = True
        if not detected:
            print 'No Teensy devices detected.'
        return

    stdin_fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(stdin_fd)
    try:
        # Make some changes to stdin. We want to turn off canonical
        # processing  (so that ^H gets sent to the teensy), turn off echo,
        # and make it unbuffered.
        new_settings = termios.tcgetattr(stdin_fd)
        new_settings[3] &= ~(termios.ICANON | termios.ECHO)
        new_settings[6][termios.VTIME] = 0
        new_settings[6][termios.VMIN] = 1
        termios.tcsetattr(stdin_fd, termios.TCSANOW, new_settings)

        monitor = pyudev.Monitor.from_netlink(context)
        monitor.start()
        monitor.filter_by('tty')

        # Check to see if the teensy device is already present.
        for device in context.list_devices(subsystem='tty'):
            if is_teensy(device, args.serial):
                teensy_mon(monitor, device)

        # Otherwise wait for the teensy device to connect
        while True:
            if args.serial:
                print 'Waiting for Teensy with serial %s ...' % args.serial
            else:
                print 'Waiting for Teensy...'
            for device in iter(monitor.poll, None):
                if device.action != 'add':
                    continue
                if is_teensy(device, args.serial):
                    teensy_mon(monitor, device)
    except KeyboardInterrupt:
        pass
    except Exception:
        traceback.print_exc()
    # Restore stdin back to its old settings
    termios.tcsetattr(stdin_fd, termios.TCSANOW, old_settings)

main()
