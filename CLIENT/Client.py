import socket
import threading
import time

HEADER = 64
PORT = 5050
SERVER = "192.168.2.103"
ADDRESS = (SERVER, PORT)
FORMAT = 'utf-8'
START_MESSAGE = "BUHDUY"
DISCONNECT_MESSAGE = "!DISCONNECT"
FILE_REQUESTED_DOWNLOAD_PATH = "input.txt"

client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client.connect(ADDRESS)

def send_msg(msg):
    message = msg.encode(FORMAT)
    msg_length = len(message)
    send_length = str(msg_length).encode(FORMAT)
    send_length += b' ' * (HEADER - len(send_length))
    client.send(send_length)
    client.send(message)

def receive_msg():
    msg_length = int(client.recv(HEADER).decode(FORMAT))
    print(f"Message length: {msg_length} bytes")
    msg = client.recv(1024).decode(FORMAT)
    print(f"[SERVER RESPONSE]: {msg}")
    return msg

def receive_allow_dowload_file():
    file_size = int(client.recv(HEADER).decode(FORMAT))
    print(f"File size received: {file_size} bytes")

    file_data = b""
    while len(file_data) < file_size:
        chunk = client.recv(1024)
        file_data += chunk
        if len(file_data) == file_size:
            break
    print(f"Received file content:\n{file_data.decode(FORMAT)}")

def send_files_from_input():
    with open(FILE_REQUESTED_DOWNLOAD_PATH, 'r') as file:
        lines = file.readlines()

    files = [line.strip() for line in lines if line.strip() and "done" not in line]
    return files

def mark_file_as_done_inputTxt(file_name):
    with open(FILE_REQUESTED_DOWNLOAD_PATH, 'r') as file:
        lines = file.readlines()

    with open(FILE_REQUESTED_DOWNLOAD_PATH, 'w') as file:
        for line in lines:
            if line.strip() == file_name:
                file.write(line.strip() + " done\n")
            else:
                file.write(line)

def request_files_from_inputTxt():
    while True:
        files = send_files_from_input()
        if not files:
            print("No more files to request.")
            return
        for file_name in files:
            print(f"Requesting file: {file_name}")
            send_msg(file_name)
            response = receive_msg()
            if response == file_name:
                print(f"File {file_name} has been received successfully.")
                mark_file_as_done_inputTxt(file_name)
            else:
                print(f"Failed to receive file {file_name}. Server response: {response}")
        time.sleep(5)

send_msg(START_MESSAGE)
receive_allow_dowload_file()
receive_msg()
request_files_from_inputTxt()
send_msg(DISCONNECT_MESSAGE)
