import os
import socket
import threading
import hashlib
import struct
import time
import sys
import signal
import re

SERVER_IP = socket.gethostbyname(socket.gethostname())
SERVER_PORT = 5050
SERVER_ADDRESS = (SERVER_IP, SERVER_PORT)

ENCODE_FORMAT = 'utf-8'
HEADER_SIZE = 64
CHECKSUM_SIZE = 16

DISCONNECT_MESSAGE = '!DISCONNECT'

BUFFER_SIZE = 1024

TIMEOUT = 5

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.bind(SERVER_ADDRESS)
server.listen(5)

def convert_size(size_in_bytes):
    if size_in_bytes <= 0:
        return "0B"
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    i = 0
    while size_in_bytes >= 1024 and i < len(units) - 1:
        size_in_bytes /= 1024.0
        i += 1
    return f"{size_in_bytes:.2f} {units[i]}"

def send_downloaded_file_list(connection):
    server_dir = os.path.dirname(os.path.abspath(__file__))
    exclude_files = ['Server.py']
    files_in_directory = os.listdir(server_dir)
    files = [file for file in files_in_directory if os.path.isfile(os.path.join(server_dir, file)) and file not in exclude_files]
    file_list_str = []
    for file in files:
        file_size = os.path.getsize(os.path.join(server_dir, file))
        file_size_str = convert_size(file_size)
        file_list_str.append(f"{file} {file_size_str}")

    message = "\n".join(file_list_str)

    send_message(connection, message)

def send_message(connection, message):
    message = message.encode(ENCODE_FORMAT)
    header = f"{len(message):<{HEADER_SIZE}}".encode(ENCODE_FORMAT)
    connection.send(header)
    connection.send(message)

def receive_message(connection):
    header = connection.recv(HEADER_SIZE).decode(ENCODE_FORMAT)
    if not header:
        return None
    message = connection.recv(int(header)).decode(ENCODE_FORMAT)
    return message

def generate_checksum(data):
    return hashlib.md5(data).hexdigest()[:16]

def send_chunk_file(connection, file_name, seq, chunk_size):
    if not os.path.exists(file_name):
        connection.send(b"SERVER RESPONSE::CHUNK FILE NOT FOUND")
        return
    with open(file_name, 'rb') as file:
        file.seek(seq * chunk_size)
        chunk_data = file.read(chunk_size)
        if chunk_data:
            checksum = generate_checksum(chunk_data)
            header = struct.pack("!I I 16s", seq, chunk_size, checksum.encode('utf-8'))
            padding = b'\x00' * (HEADER_SIZE - len(header))
            header = header + padding
            packet = header + chunk_data
            connection.send(packet)
            print(f"Sent chunk {seq} with size {chunk_size} and checksum {checksum}")
            connection.settimeout(TIMEOUT)  
            try:
                ack = connection.recv(BUFFER_SIZE)
                if ack.decode(ENCODE_FORMAT) == f"ACK {seq}":
                    print(f"Received ACK for chunk {seq}")
                else:
                    print(f"Invalid ACK for chunk {seq}")
            except socket.timeout:
                print(f"Timeout waiting for ACK for chunk {seq}. Retrying...")
                send_chunk_file(connection, file_name, seq, chunk_size)


def handle_client(connection, address):
    print(f"Client connected: {address}")
    connected = True
    while connected:
        try:
            message = receive_message(connection)
            if message == DISCONNECT_MESSAGE:
                connected = False
                connection.close()
                print(f"Client {address} disconnected.")
                break
            elif message.startswith("GET"):
                match = re.match(r"^GET (\S+) (\d+) (\d+)$", message)
                if match:
                    file_name = match.group(1)
                    seq = int(match.group(2))
                    size = int(match.group(3))
                    send_chunk_file(connection, file_name, seq, size)
            else:
                send_message(connection, "Invalid Command")
                connected = False
        except (ConnectionResetError, BrokenPipeError):
            print(f"Client {address} disconnected unexpectedly.")
            connected = False
    connection.close()

def TCP_start():
    print("Server is listening for connections...")
    while True:
        connection, address = server.accept()
        send_downloaded_file_list(connection)
        thread = threading.Thread(target=handle_client, args=(connection, address))
        thread.start()

if __name__ == "__main__":
    TCP_start()
