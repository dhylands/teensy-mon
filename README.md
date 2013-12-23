teensy-mon
==========

A serial monitor for the Teensy.

teensy-mon will automatically detect your connected Teensy device and
print the output from it.

This is similar in functionality to the Arduino serial monitor, except that
teensy-mon deals with the device disconnects automtically, and will wait
for the teensy device to reconnect.

teensy-mon will also recognize lines that start with a single letter
followed by a colon and colorize them.

```
Letter Level         Color
------ ------------- ---------
  I    Informational None
  D    Debug         Light Blue
  W    Warning       Light Yellow
  E    Error         Light Red
  C    Critical      Light Red
```

If you have more than one teensy device connected, you can use the -s
option to specify the serial number of the device you wish to connect to.

Use -l to list all of the connected teensy devices.

Currently, this program only works under linux.

It was tested with a pair of Teensy 3.1 boards.
