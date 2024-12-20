import os
import re
import socket
import struct
import hashlib
import threading

SERVER_IP = socket.gethostbyname(socket.gethostname())
SERVER_PORT = 12345
SERVER_ADDRESS = (SERVER_IP, SERVER_PORT)

ENCODE_FORMAT = 'utf-8'
HEADER_SIZE = 64
CHECKSUM_SIZE = 16

DISCONNECT_MESSAGE = '!DISCONNECT'
CONNECT_MESSAGE = '!CONNECT'

BUFFER_SIZE = 4096

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
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

def send_downloaded_file_list(conn):
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
    send_message_to_client(conn, message)

def send_message_to_client(conn, message):
    """Sends a message to the client."""
    message = message.encode(ENCODE_FORMAT)
    header = f"{len(message):<{HEADER_SIZE}}".encode(ENCODE_FORMAT)
    conn.sendall(header + message)

def receive_message_from_client(conn):
    """Receives a message from a client."""
    header = conn.recv(HEADER_SIZE).decode(ENCODE_FORMAT).strip()
    if not header:
        return None

    message_length = int(header)
    message = conn.recv(message_length).decode(ENCODE_FORMAT)
    return message

#------------------------------------------------------------------------------------#

def send_chunk_file(conn, file_name, start, end):
    try:
        with open(file_name, "rb") as file:
            file.seek(start)
            while start < end:
                chunk_size = min(BUFFER_SIZE, end - start)
                chunk_data = file.read(chunk_size)

                if not chunk_data:
                    break

                checksum = generate_checksum(chunk_data)
                packet = struct.pack(f"!I {CHECKSUM_SIZE}s {len(chunk_data)}s", len(chunk_data), checksum.encode(ENCODE_FORMAT), chunk_data)
                conn.sendall(packet)
                
                start += len(chunk_data)

    except FileNotFoundError:
        print(f"File {file_name} not found.")
    except Exception as e:
        print(f"[ERROR] Error sending chunk: {e}")

def handle_client(conn, addr):
    connected = True
    while connected:
        try:
            message = receive_message_from_client(conn)
            if not message:
                break

            if message == CONNECT_MESSAGE:
                send_downloaded_file_list(conn)

            elif message == DISCONNECT_MESSAGE:
                connected = False

            elif message.startswith("GET"):
                match = re.match(r"^GET (\S+) (\d+) (\d+)$", message)
                if match:
                    file_name = match.group(1)
                    start = int(match.group(2))
                    end = int(match.group(3))

                    send_chunk_file(conn, file_name, start, end)
                else:
                    print(f"Invalid GET request format from {addr}: {message}")

            else:
                print(f"Invalid command from {addr}: {message}")

        except Exception as e:
            break

    conn.close()

def TCP_start():
    server.listen()
    print(f"Server is running on {SERVER_IP}:{SERVER_PORT}...")
    while True:
        conn, addr = server.accept()
        thread = threading.Thread(target=handle_client, args=(conn, addr))
        thread.daemon = True
        thread.start()

if __name__ == "__main__":
    TCP_start()
