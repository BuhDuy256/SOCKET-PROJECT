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

server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
server.bind(SERVER_ADDRESS)

#------------------------------------------------------------------------------------#
def convert_size(size_in_bytes):
    """Converts a file size in bytes to a human-readable format."""
    if size_in_bytes <= 0:
        return "0B"
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    i = 0
    while size_in_bytes >= 1024 and i < len(units) - 1:
        size_in_bytes /= 1024.0
        i += 1
    return f"{size_in_bytes:.2f} {units[i]}"

def send_downloaded_file_list(client_address):
    """Sends a list of downloadable files to the client."""
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

def generate_checksum(data):
    return hashlib.md5(data).hexdigest()[:16]

def send_chunk_file(client_address, file_name, seq, chunk_size):
    try:
        with open(file_name, "rb") as file:
            file.seek(seq * chunk_size)
            chunk_data = file.read(chunk_size)
            checksum = generate_checksum(chunk_data)
            header = struct.pack("!I I 16s", seq, len(chunk_data), checksum.encode(ENCODE_FORMAT))
            header = header.ljust(HEADER_SIZE, b'\x00')  
            # print(f"Send chunk {seq} of {file_name} with size: {chunk_size}, chunksum: {checksum}")
            
            server.sendto(header, client_address)  # Gửi header cho client

            # Send data in parts (each part 4096 bytes)
            offset = 0
            while offset < len(chunk_data):
                # Slice the data part of 4096 bytes
                part_data = chunk_data[offset:offset + BUFFER_SIZE]

                # Send the data part without sending the header again
                server.sendto(part_data, client_address)

                # Update offset
                offset += BUFFER_SIZE

    except FileNotFoundError:
        print(f"File {file_name} not found.")
    except Exception as e:
        print(f"[ERROR] Error sending chunk: {e}")

#------------------------------------------------------------------------------------#
def handle_client(client_address, message):
    """Handles a single client's request."""

    # print(f"Client address: {client_address}")
    # print(f"Received message: {message}")

    if message == CONNECT_MESSAGE:
        # print(f"Client {client_address} connected.")
        send_downloaded_file_list(client_address)

    # Check for disconnection message
    elif message == DISCONNECT_MESSAGE:
        # print(f"Client {client_address} disconnected.")
        return

    # Handle "GET" requests
    elif message.startswith("GET"):
        match = re.match(r"^GET (\S+) (\d+) (\d+)$", message)
        if match:
            file_name = match.group(1)
            seq = int(match.group(2))
            size = int(match.group(3))
            
            send_chunk_file(client_address, file_name, seq, size)
        else:
            # send_message_to_client("SERVER::Invalid GET request format", client_address)
            print(f"Invalid GET request format from {client_address}: {message}")

    else:
        # send_message_to_client("SERVER::Invalid Command", client_address)
        print(f"Invalid command from {client_address}: {message}")
#------------------------------------------------------------------------------------#

def UDP_start():
    """Starts the UDP server and listens for incoming messages."""
    print("Server is running and waiting for client requests...")
    while True:
        try:
            message, client_address = receive_message_from_client() 
            
            thread = threading.Thread(target=handle_client, args=(client_address, message))
            thread.start()

        except Exception as e:
            print(f"Error handling client request: {e}")

if __name__ == "__main__":
    UDP_start()