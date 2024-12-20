import os
import re
import time
import socket
import struct
import hashlib
import threading
import random

SERVER_IP = socket.gethostbyname(socket.gethostname())
SERVER_PORT = 12345
SERVER_ADDRESS = (SERVER_IP, SERVER_PORT)

ENCODE_FORMAT = 'utf-8'
HEADER_SIZE = 64
CHECKSUM_SIZE = 16

DISCONNECT_MESSAGE = '!DISCONNECT'
GET_DOWLOADED_FILES_LIST_MESSAGE = 'GET DOWLOADED FILES LIST'
CONNECT_MESSAGE = '!CONNECT'

BUFFER_SIZE = 4096
MAX_UDP_PAYLOAD_SIZE = 65507

CLIENT_ID_LENGTH = 26 # FIX
DEFAULT_CLIENT_ID = '23127006_23127179_23127189'

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

def send_downloaded_file_list(client_id, client_address):
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

    send_message_to_client(message, client_id, client_address)

def send_message_to_client(message, client_id, client_address):
    client_id_encoded = client_id.encode(ENCODE_FORMAT)
    message_encoded = message.encode(ENCODE_FORMAT)

    combined_message = client_id_encoded + b"|" + message_encoded

    header = f"{len(combined_message):<{HEADER_SIZE}}".encode(ENCODE_FORMAT)

    server.sendto(header + combined_message, client_address)

def receive_message_from_client():
    data, client_address = server.recvfrom(BUFFER_SIZE)
    
    header = data[:HEADER_SIZE].decode(ENCODE_FORMAT).strip()
    if not header:
        return None, None, client_address

    combined_message = data[HEADER_SIZE:HEADER_SIZE + int(header)]
    client_id, message = combined_message.split(b"|", 1)

    client_id = client_id.decode(ENCODE_FORMAT)
    message = message.decode(ENCODE_FORMAT)

    return message, client_id, client_address

#------------------------------------------------------------------------------------#

def introduce_bit_error(chunk_data):
    if random.random() < 0.0001: # 0.01% chance of introducing an error
        if len(chunk_data) > 0:
            error_pos = random.randint(0, len(chunk_data) - 1)
            chunk_data = bytearray(chunk_data)
            chunk_data[error_pos] = random.randint(0, 255)
            return bytes(chunk_data)
    return chunk_data

def send_chunk_file(client_address, file_name, start, end):
    try:
        with open(file_name, "rb") as file:
            file.seek(start)
            while (start < end):
                chunk_size = min(BUFFER_SIZE, end - start)
                chunk_data = file.read(chunk_size)

                if not chunk_data:
                    break
                
                checksum = generate_checksum(chunk_data)
                chunk_data_with_error = introduce_bit_error(chunk_data)
                packet = struct.pack(f"!I {CHECKSUM_SIZE}s {len(chunk_data)}s", len(chunk_data), checksum.encode(ENCODE_FORMAT), chunk_data_with_error)
                server.sendto(packet, client_address)
                start += len(chunk_data)

    except FileNotFoundError:
        print(f"File {file_name} not found.")
    except Exception as e:
        print(f"[ERROR] Error sending chunk: {e}")

def send_chunk_file_no2(client_address, file_name, start, chunk_size):
    try:
        with open(file_name, "rb") as file:
            file.seek(start)
            chunk_data = file.read(chunk_size)
            
            checksum = generate_checksum(chunk_data)
            chunk_data_with_error = introduce_bit_error(chunk_data)
            packet = struct.pack(f"!I {CHECKSUM_SIZE}s {len(chunk_data)}s", len(chunk_data), checksum.encode(ENCODE_FORMAT), chunk_data_with_error)
            server.sendto(packet, client_address)
        
    except FileNotFoundError:
        print(f"File {file_name} not found.")
    except Exception as e:
        print(f"[ERROR] Error sending chunk: {e}")

#------------------------------------------------------------------------------------#

lock = threading.Lock()
current_client_ip = None
current_client_id = DEFAULT_CLIENT_ID

def generate_client_id():
    while True:
        part1 = random.randint(10000000, 99999999)
        part2 = random.randint(10000000, 99999999)
        part3 = random.randint(10000000, 99999999)

        client_id = f"{part1}_{part2}_{part3}"

        if client_id != DEFAULT_CLIENT_ID:
            return client_id

def handle_client(client_id, client_address, message):
    global current_client_ip
    global current_client_id

    client_ip, client_port = client_address

    if message == CONNECT_MESSAGE:
        with lock:
            if current_client_ip is None and current_client_id is DEFAULT_CLIENT_ID:
                new_client_id = generate_client_id()
                send_message_to_client(new_client_id, client_id, client_address)
                current_client_ip = client_ip
                current_client_id = new_client_id
            else:
                send_message_to_client("BUSY", client_id, client_address)
                return

    elif message == GET_DOWLOADED_FILES_LIST_MESSAGE:
        send_downloaded_file_list(current_client_id, client_address)

    elif message == DISCONNECT_MESSAGE:
        print(f"Client {client_address} disconnected.")
        with lock:
            if current_client_ip == client_ip and current_client_id == client_id:
                current_client_ip = None
                current_client_id = DEFAULT_CLIENT_ID
        return

    elif message.startswith("GET_NO2"):
        match = re.match(r"^GET_NO2 (\S+) (\d+) (\d+)$", message)
        if match:
            file_name = match.group(1)
            start = int(match.group(2))
            chunk_size = int(match.group(3))
            
            send_chunk_file_no2(client_address, file_name, start, chunk_size)
        else:
            print(f"Invalid GET_NO2 request format from {client_address}: {message}")

    elif message.startswith("GET"):
        match = re.match(r"^GET (\S+) (\d+) (\d+)$", message)
        if match:
            file_name = match.group(1)
            start = int(match.group(2))
            end = int(match.group(3))
            
            send_chunk_file(client_address, file_name, start, end)
        else:
            print(f"Invalid GET request format from {client_address}: {message}")

    else:
        print(f"Invalid command from {client_address}: {message}")

def UDP_start():
    print(f"Server is running on {SERVER_IP}:{SERVER_PORT}...")
    while True:
        try:
            message, client_id, client_address = receive_message_from_client() 
            thread = threading.Thread(target=handle_client, args=(client_id, client_address, message))
            thread.start()
        except Exception as e:
            print(f"Error handling client request: {e}")

if __name__ == "__main__":
    UDP_start()