from os import geteuid, remove
from os.path import isfile
import random
from subprocess import call
from sys import argv, exit
from io import StringIO
import base64
import csv
import re
import sys
import subprocess
import traceback
import asyncio, aiohttp
import logging
import socket
from urllib import request
from concurrent.futures import ThreadPoolExecutor, as_completed

class Logger:
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    handler = logging.StreamHandler()
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter("%(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    @staticmethod
    def info(message):
        Logger.logger.info("\033[94m[*]\033[96m" + message)

    @staticmethod
    def warn(message):
        Logger.logger.warning("\033[93m[!]\033[97m" + message)

    @staticmethod
    def error(message):
        Logger.logger.error("\033[91m[x]\033[31m" + message)
        
        
class VpnGateRotator:
    def __init__(self):
        if geteuid() != 0:
            Logger.error("Run as super user!")
            exit(1)
        self.HOST_NAME = "HostName"
        self.IP = "IP"
        self.SCORE = "Score"
        self.PING = "Ping"
        self.SPEED = "Speed"
        self.COUNTRY_LONG = "CountryLong"
        self.COUNTRY_SHORT = "CountryShort"
        self.NUM_VPN_SESSIONS = "NumVpnSessions"
        self.UPTIME = "Uptime"
        self.TOTAL_USERS = "TotalUsers"
        self.TOTAL_TRAFFIC = "TotalTraffic"
        self.LOG_TYPE = "LogType"
        self.OPERATOR = "Operator"
        self.MESSAGE = "Message"
        self.OPENVPN_CONFIG_DATA = "OpenVPN_ConfigData"
        self.PROTOCOL = "Protocol"
        self.CSV_HEADER = [
            self.HOST_NAME, self.IP, self.SCORE, self.PING, self.SPEED,
            self.COUNTRY_LONG, self.COUNTRY_SHORT, self.NUM_VPN_SESSIONS,
            self.UPTIME, self.TOTAL_USERS, self.TOTAL_TRAFFIC, self.LOG_TYPE, self.OPERATOR,
            self.MESSAGE, self.OPENVPN_CONFIG_DATA
        ]
        self.servers = self.get_server_list()

    def get_server_list(self) -> list:
        Logger.info("Getting server list")
        req = request.Request("http://www.vpngate.net/api/iphone/")
        with request.urlopen(req) as res:
            with StringIO(res.read().decode()) as f:
                csv_reader = csv.DictReader(f, self.CSV_HEADER)
                next(csv_reader)
                next(csv_reader)
                Logger.info("Checking servers")
                with ThreadPoolExecutor(max_workers=20) as executor:
                    futures = [executor.submit(self.check_config, row) for row in csv_reader if (row[self.HOST_NAME] != "*") and (len(row) == 15)]
                    rows = [future.result() for future in as_completed(futures) if future.result() is not None]
        return rows

    def check_config(self, row):
        try:
            config = base64.b64decode(row[self.OPENVPN_CONFIG_DATA]).decode()
            ip, port = re.findall("remote (.*) (.*)\r", config)[0]
            proto = re.findall("proto (.*)\r", config)[0]

            if proto == "tcp":
                with socket.create_connection((ip, int(port)), timeout=3):
                    pass

            row[self.OPENVPN_CONFIG_DATA] = config
            return row

        except Exception as e:
            Logger.error(f"{ip}:{port}:{e}")
            return None
            
    def select_server(self, country = "", speed = "", ping = ""):
        filtered_data = []
        random_data = None
        for data in self.servers:
            if country and data[self.COUNTRY_SHORT] != country:
                continue
            if speed and data[self.SPEED] > speed:
                continue
            if ping and data[self.PING] > ping:
                continue
            filtered_data.append(data)

        if filtered_data:
            random_data = random.choice(filtered_data)
            
        return random_data

    def connect_new(self, country = "", speed = "", ping = ""):
        selected_server = self.select_server(country, speed, ping)
        if selected_server is None:
            raise("No VPN found")
        self.disconnect()
        with(open("/tmp/openvpnconf", "w")) as f:
            f.write(selected_server[self.OPENVPN_CONFIG_DATA])
        Logger.info(f'Connecting to {selected_server[self.HOST_NAME]} {selected_server[self.IP]} {selected_server[self.COUNTRY_SHORT]} {int(selected_server[self.SPEED])/1024/1024}Mbps {selected_server[self.PING]}ms')
        process = subprocess.Popen(["openvpn", "/tmp/openvpnconf"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        while True:
            output = process.stdout.readline().decode().rstrip("\n")   #"\n".join([line.decode().rstrip("\n") for line in process.stdout.readlines()])
            if output == '' and process.poll() is not None:
                Logger.error(f'open vpn exited')
                break
            if 'Initialization Sequence Completed' in output:
                Logger.info(f'Connected')
                return 0
            if "error" in output:
                Logger.error(output)
                break
        output, error = process.communicate()
        if error:
            raise(f'Error: {error.decode()}')
    
    def disconnect(self):
        call(["killall", "-9", "openvpn"])

    @staticmethod
    def clean_up():
        if isfile("/tmp/openvpnconf"):
            remove("/tmp/openvpnconf")
            pass

if __name__ == "__main__":
    vpn = VpnGateRotator()
    try:
        vpn.connect_new()
        
    except KeyboardInterrupt:
        ans = input("try another vpn? (y/n)")
        if ans.lower() in ("y", "yes"):
            try:
                vpn.connect_new()
            except:
                vpn.disconnect()
                vpn.clean_up()
    except Exception as e:
        Logger.error(e)
        traceback.print_exc()
        vpn.clean_up()