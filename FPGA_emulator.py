""" This is an FPGA target emulator for testing and debugging the NIcRIO class.
    Some comments about the NIcRIO class:
    1.  The attribute of NIcRIO and Connection class: self.port is a tuple (sendport, receiveport)
    2.  In RunCommand(): TCP REQUIRES an ACK and is responsible for most of the command sending; while UDP is only there to
        periodically check the status of the FPGA (see next)
    3.  The FPGAStatus class is designed to periodically check the status of the FPGA by polling a UDP socket. The key parts
        that ensure its survival and continuous operation are found within the run() method, which is a standard approach for
        creating a thread in Python.
    4.  For the format of the TCP ACK, it is expected by the NIcRIO to be a JSON string that contains the confirmation
        msg (or error msg from the FPGA); the received data is then parsed as JSON into a python dict through json.loads();
        then it checks if the parsed msg contains a 'status' key and reports an error if it does (I know, it is very strange).
        This means that any msg with a 'status' key is considered an error report (WTF?). If it prints "We received a TCP..."
        it indicates that the msg received is not of valid JSON.
    *4. Since the error checking in (4) does not make sense at all, I have changed the NIcRIO (See line 395, ni_cRIOFPGA.py).
"""
from cockpit.devices.ni_cRIOFPGA import NIcRIO

import json
import socket
import threading
import time

HOST = '127.0.0.1'
SEND_PORT = 7704  # TCP (cmd)
RECEIVE_PORT = 7705  # UDP (status update)
PERIODIC_UPDATE_INTERVAL = 1  # Interval in seconds for sending status updates
""" Separate threads for TCP and UDP servers should keep both servers alive
    throughout the execution the script. These threads continuously listen for
    incoming connections and data, respectively.
"""
# TCP server setup: listening
def tcp_server():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp_sock:
        tcp_sock.bind((HOST, SEND_PORT))
        tcp_sock.listen()
        print(f"EMULATOR: TCP server listening on {HOST}:{SEND_PORT}\n")
        conn, addr = tcp_sock.accept()
        with conn:
            print(f"EMULATOR: Connected by {addr}")
            while True:
                data = conn.recv(1024)
                if not data:
                    break
                print(f"EMULATOR: Received (TCP): {data.decode()}")
                # Process the data or respond back
                ack_message = json.dumps({"status": "OK"}).encode()
                conn.sendall(ack_message)

# UDP server setup: listening for any incoming messages (not necessary for status update)
# NOTE: RECEIVE_PORT+1 to avoid binding conflict with the NIcRIO UDP
def udp_server():
    udp_host = HOST
    udp_port = RECEIVE_PORT+1
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp_sock:
        udp_sock.bind((udp_host, udp_port))
        print(f"EMULATOR: UDP server listening on {udp_host}:{udp_port}\n")
        while True:
            data, addr = udp_sock.recvfrom(1024)
            print(f"EMULATOR: Received (UDP) from {addr}: {data.decode()}")

# Periodic status update function: sends status updates to NIcRIO
def send_periodic_status():
    while True:
        status_message = json.dumps({"Event": "done"}).encode()  # Example status message
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp_sock:
            udp_sock.sendto(status_message, (HOST, RECEIVE_PORT))  # Send status to the port NIcRIO listens on ONLY
            print("EMULATOR (UDP): Status update sent")
        time.sleep(PERIODIC_UPDATE_INTERVAL)
# Start TCP and UDP servers in separate threads; also start to send periodic status updates
tcp_thread = threading.Thread(target=tcp_server)
# udp_thread = threading.Thread(target=udp_server)
status_thread = threading.Thread(target=send_periodic_status)
tcp_thread.start()
# udp_thread.start()
status_thread.start()
# Now create an instance of NIcRIO
# config = {
#     'ipaddress': HOST,
#     'sendport': SEND_PORT,
#     'receiveport': RECEIVE_PORT,
# }
# nicrio_instance = NIcRIO(name="FPGA Emulator", config=config)
# nicrio_instance.initialize()