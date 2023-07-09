import os
import glob
import time
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from flask import Flask, request, render_template
import threading

##### globals #####

CHECK_INTERVAL = 10
UPPER_LIMIT = 28
IDEAL = 26
ON_COMMAND = "irsend SEND_ONCE mideaAC 21_COOL_AUTO"
OFF_COMMAND = "irsend SEND_ONCE mideaAC off"
RETRY_TEMP_DIFFERENCE = 0.3
ACTIVE=True
LAST_CHANGE_TEMP = IDEAL + 0.5

##### setup #####

# kernel modules
os.system('modprobe w1-gpio')
os.system('modprobe w1-therm')

# path to device modules
base_dir = '/sys/bus/w1/devices/'
device_folder = glob.glob(base_dir + '28*')[0]
device_file = device_folder + '/w1_slave'

# influxdb
client = InfluxDBClient(url="http://localhost:8086", org="devid")
write_api = client.write_api(write_options=SYNCHRONOUS)
bucket = "ac"

# flask app
app = Flask(__name__, template_folder='.')

##### temperature update loop #####

def read_temp_raw():
    f = open(device_file, 'r')
    lines = f.readlines()
    f.close()
    return lines

def read_temp():
    lines = read_temp_raw()
    while lines[0].strip()[-3:] != 'YES':
        time.sleep(0.2)
        lines = read_temp_raw()
    equals_pos = lines[1].find('t=')
    if equals_pos != -1:
        temp_string = lines[1][equals_pos+2:]
        temp_c = float(temp_string) / 1000.0
        return temp_c

def update_temp():
    global CHECK_INTERVAL
    global UPPER_LIMIT
    global IDEAL
    global ON_COMMAND
    global OFF_COMMAND
    global RETRY_TEMP_DIFFERENCE
    global ACTIVE
    global LAST_CHANGE_TEMP
    while True:
        temp = read_temp()
        print(f"temperature: {temp}°C, last change temp: {LAST_CHANGE_TEMP}°C")

        if ACTIVE and temp >= UPPER_LIMIT and temp > LAST_CHANGE_TEMP + RETRY_TEMP_DIFFERENCE:
            os.system(ON_COMMAND)
            LAST_CHANGE_TEMP = temp
            print("turned on")
            p = Point("ac").tag("turn", "on").field("temperature", temp)
        elif ACTIVE and temp <= IDEAL and temp < LAST_CHANGE_TEMP - RETRY_TEMP_DIFFERENCE:
            os.system(OFF_COMMAND)
            LAST_CHANGE_TEMP = temp
            print("turned off")
            p = Point("ac").tag("turn", "off").field("temperature", temp)
        else:
            p = Point("ac").field("temperature", temp)

        write_api.write(bucket=bucket, record=p)

        time.sleep(CHECK_INTERVAL)

##### API #####

@app.route('/', methods=['GET', 'POST'])
def root():
    if request.method == 'POST':
        global UPPER_LIMIT
        global IDEAL
        global ACTIVE
        global LAST_CHANGE_TEMP
        UPPER_LIMIT = float(request.form["upper"])
        IDEAL = float(request.form["lower"])
        ACTIVE = request.form["active"] == "on"

        if not ACTIVE:

            global OFF_COMMAND
            os.system(OFF_COMMAND)
            LAST_CHANGE_TEMP = IDEAL + 0.5

    return render_template("index.html", upper=UPPER_LIMIT, lower=IDEAL, active=ACTIVE)

##### start threads #####

loop_thread = threading.Thread(target=update_temp)
api_thread = threading.Thread(target=app.run, kwargs={'host':'192.168.1.62', 'port':'5000'})

loop_thread.start()
api_thread.start()