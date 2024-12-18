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
SERVER_PORT = 12345
SERVER_ADDRESS = (SERVER_IP, SERVER_PORT)

ENCODE_FORMAT = 'utf-8'
HEADER_SIZE = 64
CHECKSUM_SIZE = 16

DISCONNECT_MESSAGE = '!DISCONNECT'
CONNECT_MESSAGE = '!CONNECT'

BUFFER_SIZE = 4096
MAX_UDP_PAYLOAD_SIZE = 65507

server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
server.bind(SERVER_ADDRESS)

#------------------------------------------------------------------------------------#

def convert_size(size_in_bytes):
    """Converts a file size in bytes to a human-readable format with integer values."""
    if size_in_bytes <= 0:
        return "0B"
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    i = 0
    while size_in_bytes >= 1024 and i < len(units) - 1:
        size_in_bytes //= 1024
        i += 1
    return f"{size_in_bytes} {units[i]}"

def generate_checksum(data):
    return hashlib.md5(data).hexdigest()[:CHECKSUM_SIZE]

def generate_file_checksum(file_name):
    md5_hash = hashlib.md5()
    try:
        with open(file_name, "rb") as f:
            for chunk in iter(lambda: f.read(BUFFER_SIZE), b""):
                md5_hash.update(chunk)
        return md5_hash.hexdigest()
    except FileNotFoundError:
        return f"Error: File '{file_name}' not found."
    except Exception as e:
        return f"Error: {e}"

def send_downloaded_file_list(client_address):
    """Sends a list of downloadable files to the client."""
    server_dir = os.path.dirname(os.path.abspath(__file__))
    exclude_files = ['Server.py']
    files_in_directory = os.listdir(server_dir)
    files = [file for file in files_in_directory if os.path.isfile(os.path.join(server_dir, file)) and file not in exclude_files]

    file_list_str = []
    for file in files:
        file_size = os.path.getsize(os.path.join(server_dir, file))
        size_str = convert_size(file_size)
        file_checksum = generate_file_checksum(file)
        file_list_str.append(f"{file} {size_str} {file_size} {file_checksum}")

    message = "\n".join(file_list_str)

    send_message_to_client(message, client_address)

def send_message_to_client(message, client_address):
    """Sends a message to the client."""
    message = message.encode(ENCODE_FORMAT)
    header = f"{len(message):<{HEADER_SIZE}}".encode(ENCODE_FORMAT)
    server.sendto(header + message, client_address)

def receive_message_from_client():
    """Receives a message from a client."""
    data, client_address = server.recvfrom(BUFFER_SIZE)
    header = data[:HEADER_SIZE].decode(ENCODE_FORMAT).strip()
    if not header:
        return None, client_address

    message = data[HEADER_SIZE:HEADER_SIZE + int(header)].decode(ENCODE_FORMAT)
    return message, client_address

#------------------------------------------------------------------------------------#

def send_chunk_file(client_address, file_name, seq, chunk_size):
    try:
        with open(file_name, "rb") as file:
            file.seek(seq * chunk_size)
            chunk_data = file.read(chunk_size)
            checksum = generate_checksum(chunk_data)
            header = struct.pack("!I I 16s", seq, len(chunk_data), checksum.encode(ENCODE_FORMAT))
            header = header.ljust(HEADER_SIZE, b'\x00')
            
            server.sendto(header, client_address)

            offset = 0
            while offset < len(chunk_data):
                part_data = chunk_data[offset:offset + min(BUFFER_SIZE, len(chunk_data) - offset)]
                server.sendto(part_data, client_address)
                offset += BUFFER_SIZE

    except FileNotFoundError:
        print(f"File {file_name} not found.")
    except Exception as e:
        print(f"[ERROR] Error sending chunk: {e}")

#------------------------------------------------------------------------------------#

def handle_client(client_address, message):
    if message == CONNECT_MESSAGE:
        send_downloaded_file_list(client_address)

    elif message == DISCONNECT_MESSAGE:
        print(f"Client {client_address} disconnected.")
        return

    elif message.startswith("GET"):
        match = re.match(r"^GET (\S+) (\d+) (\d+)$", message)
        if match:
            file_name = match.group(1)
            seq = int(match.group(2))
            size = int(match.group(3))
            
            send_chunk_file(client_address, file_name, seq, size)
        else:
            print(f"Invalid GET request format from {client_address}: {message}")

    else:
        print(f"Invalid command from {client_address}: {message}")

def UDP_start():
    print(f"Server is running on {SERVER_IP}:{SERVER_PORT}...")
    while True:
        try:
            message, client_address = receive_message_from_client() 
            thread = threading.Thread(target=handle_client, args=(client_address, message))
            thread.start()
        except Exception as e:
            print(f"Error handling client request: {e}")

if __name__ == "__main__":
    UDP_start()