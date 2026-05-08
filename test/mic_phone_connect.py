import serial

serial = serial.Serial('/dev/ttyUSB0', 115200)

while True:
    data = serial.read(1024)
    print(data)